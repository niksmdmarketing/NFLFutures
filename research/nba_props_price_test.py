"""Scoring for research/NBA_PROPS_PRICE_TEST_RULE.md (NBA player props against market prices). Prices are never a model input.

Pieces (each testable on its own; `python research/nba_props_price_test.py selftest` runs them on synthetic data):
  prices_long(df)      OddsPapi reduced rows (private repo, collected_data/oddspapi_nba/props/*.csv.gz) -> one row per
                       fixture, player, stat, book, line, side with entry (60 min), 6 h and close prices
  main_lines(P)        per fixture, player and stat: the consensus main line (the line most books quote as their main line, a
                       book's main line being its half-point line with over and under closest to even), both sides at entry
  devig(L)             each book's two-way prices -> fair over probability; consensus = mean over books on that line
  p_over(pmf, line)    model probability of the over for a half-point line from a distribution given appearing
  info_test(D)         logistic regression of the over on logit(market) and logit(model), date-clustered bootstrap
  bets(D, thr)         one side per player-game-stat, edge = p_model x best entry price - 1 >= thr; closing-line value; profit
Name matching lives in research/nba_props_names.py. Forecasts: window 2 from the forward archive (forecast-archive branch,
nba/props_forward/<date>/<game>_60_*.json.gz, params_id "b"; points pts_d_v2, rebounds reb_v2, assists ast_v2); window 1 from the
frozen 2026b parameters (research/nba_props_window1.py).
"""
import re
import sys

import numpy as np
import pandas as pd

STAT_PATTERNS = [("pra", r"points.*rebounds.*assists|\bpra\b"), ("pr", r"points.*rebounds"), ("pa", r"points.*assists"),
                 ("ra", r"rebounds.*assists"), ("pts", r"points"), ("reb", r"rebounds"), ("ast", r"assists")]
EXCLUDE = re.compile(r"alternate|milestone|\d\+|first|quarter|half|1st|2nd|3rd|4th|double|triple|steals|blocks|threes|3-point|3 point|turnover",
                     re.I)
PRIMARY_STATS = ("pts", "reb", "ast")
BOOT, SEED = 10000, 1   # Amendment 14 item 3: 10,000 draws


def stat_of(market_name):
    """Stat of a full-game player over/under market from its name, whatever order the components are listed in
    (OddsPapi: 'Over Under Player Points + Assists + Rebounds (incl. overtime)'). Quarter, half, alternate and other markets: None."""
    m = str(market_name or "").lower()
    if EXCLUDE.search(m):
        return None
    has = tuple(w in m for w in ("points", "rebounds", "assists"))
    return {(1, 1, 1): "pra", (1, 1, 0): "pr", (1, 0, 1): "pa", (0, 1, 1): "ra", (1, 0, 0): "pts", (0, 1, 0): "reb",
            (0, 0, 1): "ast"}.get(tuple(map(int, has)))


def side_of(outcome_name):
    o = str(outcome_name or "").lower()
    return "over" if o.startswith("over") or o == "o" else "under" if o.startswith("under") or o == "u" else None


def line_of(row):
    """Line from the market's handicap, else from the outcome name (e.g. 'Over 24.5')."""
    h = row.get("handicap")
    try:
        if h is not None and h == h and str(h) != "":
            return float(h)
    except (TypeError, ValueError):
        pass
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(row.get("outcome_name") or ""))
    return float(m.group(1)) if m else np.nan


def prices_long(df):
    d = df.copy()
    d["stat"] = d.market_name.map(stat_of)
    d["side"] = d.outcome_name.map(side_of)
    d["line"] = [line_of(r) for r in d.to_dict("records")]
    d = d[d.stat.notna() & d.side.notna() & d.line.notna()]
    d = d[(d.line * 2) % 2 == 1]          # half-point lines only (no pushes)
    for c in ("t60_price", "t360_price", "close_price", "open_price"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


KEY = ["fixture_id", "player_name", "stat", "bookmaker", "line"]
ENTRY_MAX_AGE = pd.Timedelta(hours=24)     # Amendment 2: entry quote last changed at most 24 h before the cutoff
CLOSE_MAX_AGE = pd.Timedelta(minutes=60)   # close quote last changed at most 60 min before tip-off
MIN_BOOKS = 2                              # primary consensus needs two books on the common line


def _two_way(d, col):
    w = d.pivot_table(index=KEY, columns="side", values=col, aggfunc="last")
    return w.dropna(subset=[c for c in ("over", "under") if c in w.columns]) if {"over", "under"} <= set(w.columns) else w.iloc[0:0]


def _times(d, col):
    w = d.assign(_t=pd.to_datetime(d[col], utc=True, errors="coerce")).pivot_table(index=KEY, columns="side", values="_t", aggfunc="last")
    w = w.reindex(columns=["over", "under"])
    complete = w[["over", "under"]].notna().all(axis=1)
    return pd.DataFrame({col: pd.to_datetime(w.min(axis=1).where(complete), utc=True),
                         col + "_latest": pd.to_datetime(w.max(axis=1).where(complete), utc=True)})


def main_lines(P, col="t60_price", horizon=pd.Timedelta(minutes=60)):
    """Common main line per fixture, player and stat, and each book's two-way entry and close prices on exactly that line.
    A book's entry pair counts only if both sides were last changed at or before the cutoff and within 24 h of it; a close pair
    only if both sides were last changed within 60 min before tip-off (else the close is missing for that book)."""
    W = _two_way(P, col)
    if W.empty:
        return W.reset_index()
    tcol = col.replace("_price", "_time")
    start = P.drop_duplicates("fixture_id").set_index("fixture_id").start_time.map(lambda s: pd.Timestamp(s).tz_convert("UTC")
                                                                                    if pd.Timestamp(s).tzinfo else pd.Timestamp(s, tz="UTC"))
    W = W.join(_times(P, tcol)).reset_index()
    W["cutoff"] = W.fixture_id.map(start) - horizon
    W = W[(W[tcol + "_latest"] <= W.cutoff) & (W.cutoff - W[tcol] <= ENTRY_MAX_AGE)].copy()
    if W.empty:
        return W
    W["gap"] = (1 / W.over - 1 / W.under).abs()
    book_main = W.sort_values(["gap", "line"]).groupby(["fixture_id", "player_name", "stat", "bookmaker"]).head(1)
    def pick(g):   # the line most books treat as main; ties go to Pinnacle's main line, then the lower line
        vc = g.line.value_counts()
        tied = sorted(vc[vc == vc.max()].index)
        pin = g[g.bookmaker.str.lower().str.contains("pinnacle")].line
        return pin.iloc[0] if len(tied) > 1 and len(pin) and pin.iloc[0] in tied else tied[0]
    mode = book_main.groupby(["fixture_id", "player_name", "stat"]).apply(pick, include_groups=False).rename("main_line")
    W = W.merge(mode, on=["fixture_id", "player_name", "stat"])
    W = W[W.line == W.main_line].drop(columns=["gap", "main_line"])
    C = _two_way(P, "close_price").join(_times(P, "close_time")).reset_index()
    C["tip"] = C.fixture_id.map(start)
    C = C[(C.close_time_latest < C.tip) & (C.tip - C.close_time <= CLOSE_MAX_AGE)]
    C = C.rename(columns={"over": "close_over", "under": "close_under"})[KEY + ["close_over", "close_under"]]
    return W.merge(C, on=KEY, how="left")


def devig(W):
    """Per book: multiplicative fair over probability on the common line at entry and close. Consensus = mean over the books
    with an entry pair; the close consensus uses the same book set and is missing unless every one of them has a valid close."""
    W = W.copy()
    io, iu = 1 / W.over, 1 / W.under
    W["fair_over"] = io / (io + iu)
    co, cu = 1 / W.close_over, 1 / W.close_under
    W["close_fair_over"] = co / (co + cu)
    g = W.groupby(["fixture_id", "player_name", "stat", "line"])
    out = g.agg(market_over=("fair_over", "mean"), close_market_over=("close_fair_over", "mean"),
                close_books=("close_fair_over", "count"), best_over=("over", "max"), best_under=("under", "max"),
                books=("bookmaker", "nunique")).reset_index()
    out["close_complete"] = out.close_books == out.books
    out.loc[~out.close_complete, "close_market_over"] = np.nan
    out["primary"] = out.books >= MIN_BOOKS
    pin = W[W.bookmaker.str.lower().str.contains("pinnacle")].set_index(["fixture_id", "player_name", "stat", "line"]).fair_over
    out["pinnacle_over"] = out.set_index(["fixture_id", "player_name", "stat", "line"]).index.map(pin.to_dict()).astype(float)
    return out


def p_over(pmf, line):
    """P(stat > line | appearing) for a half-point line; pmf indexed 0, 1, 2, ..."""
    pmf = np.asarray(pmf, float)
    k = int(np.floor(line)) + 1
    tot = pmf.sum()
    return float(pmf[k:].sum() / tot) if tot > 0 else np.nan


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def logistic(X, y, iters=100):
    """Unpenalized maximum-likelihood logistic regression with an intercept on standardized predictors (Amendment 2).
    Returns (coefficients on the standardized scale, status); status is 'ok', 'rank', 'condition', 'separation' or 'noconv'."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    sd = X.std(axis=0)
    if len(np.unique(y)) < 2:
        return None, "separation"
    if (sd <= 1e-8).any():
        return None, "rank"
    Z = np.column_stack([np.ones(len(y)), (X - X.mean(axis=0)) / sd])
    if np.linalg.matrix_rank(Z) < Z.shape[1]:
        return None, "rank"
    if np.linalg.cond(Z) >= 1e8:
        return None, "condition"
    b = np.zeros(Z.shape[1])
    for _ in range(iters):
        mu = 1 / (1 + np.exp(-np.clip(Z @ b, -35, 35)))
        W = mu * (1 - mu)
        try:
            step = np.linalg.solve(Z.T @ (Z * W[:, None]), Z.T @ (y - mu))
        except np.linalg.LinAlgError:
            return None, "separation"
        b += step
        if np.abs(b).max() > 50:
            return None, "separation"
        if np.abs(step).max() < 1e-9:
            return b, "ok"
    return None, "noconv"


def _cluster_boot(D, stat_fn, key="date"):
    """Date-cluster bootstrap: whole dates resampled, the statistic recomputed in each draw. Returns values (NaN = failed draw)."""
    rng = np.random.default_rng(SEED)
    groups = {k: g.index.to_numpy() for k, g in D.groupby(key)}
    keys = np.array(list(groups))
    vals = []
    for _ in range(BOOT):
        pick = rng.choice(keys, len(keys), replace=True)
        idx = np.concatenate([groups[k] for k in pick])
        v = stat_fn(D.loc[idx])
        vals.append(np.nan if v is None else v)
    return np.array(vals, float)


def info_test(D):
    """D: one row per player, game, stat, common line (bets and non-bets) with over (0/1), market_over, model_over, date.
    Model coefficient (standardized logits) with a 90% date-bootstrap interval; insufficient if the full fit fails or over 5% of draws fail."""
    def f(x):
        b, st = logistic(np.column_stack([_logit(x.market_over), _logit(x.model_over)]), x.over.to_numpy(float))
        return None if b is None else float(b[2])
    b, status = logistic(np.column_stack([_logit(D.market_over), _logit(D.model_over)]), D.over.to_numpy(float))
    ll = lambda p: float(-np.mean(D.over * np.log(np.clip(p, 1e-6, 1)) + (1 - D.over) * np.log(np.clip(1 - p, 1e-6, 1))))
    out = {"n": int(len(D)), "dates": int(D.date.nunique()), "fit_status": status,
           "logloss_market": ll(D.market_over), "logloss_model": ll(D.model_over)}
    if b is None:
        return out | {"model_coef": None, "lb90": None, "ub90": None, "failed_draws": None, "assessable": False}
    bs = _cluster_boot(D.reset_index(drop=True), f)
    fail = float(np.isnan(bs).mean())
    ok = bs[~np.isnan(bs)]
    return out | {"model_coef": float(b[2]), "lb90": float(np.percentile(ok, 5)) if len(ok) else None,
                  "ub90": float(np.percentile(ok, 95)) if len(ok) else None, "failed_draws": fail, "assessable": fail <= 0.05,
                  "anti_predictive": bool(len(ok) and np.percentile(ok, 95) < 0)}


def bets(D, thr=0.05):
    """At most one bet per player, game and stat (D holds one common line each): the side with the higher edge at the best
    entry price across books (ties: over), kept if edge >= thr. CLV uses the same-line close consensus of the entry book set."""
    eo = D.model_over * D.best_over - 1
    eu = (1 - D.model_over) * D.best_under - 1
    side_over = eo >= eu
    B = D.assign(side=np.where(side_over, "over", "under"), edge=np.where(side_over, eo, eu),
                 price=np.where(side_over, D.best_over, D.best_under),
                 close_fair=np.where(side_over, D.close_market_over, 1 - D.close_market_over),
                 won=np.where(side_over, D.over, 1 - D.over))
    B = B[B.edge >= thr].copy()
    B["clv"] = B.close_fair * B.price - 1
    B["profit"] = np.where(B.won == 1, B.price - 1, -1.0)
    return B


def trigger_counts(D, thr=0.05):
    """Amendment 15 item 2: bets with a complete same-line close, and distinct dates. Prices and forecasts only; no outcome, no CLV."""
    m, bo, bu, cl = (D[c].to_numpy(float) for c in ("model_over", "best_over", "best_under", "close_market_over"))
    eo, eu = m * bo - 1, (1 - m) * bu - 1
    keep = (np.maximum(eo, eu) >= thr) & np.isfinite(cl)
    return {"bets": int(keep.sum()), "dates": int(D.date.to_numpy()[keep].astype(str).size and len(set(D.date.to_numpy()[keep].astype(str))))}


ALPHA_CONTROL = 0.05 / 3   # Amendment 16: Bonferroni across the three stats (Holm needs all three looks at once)


def _row_clv(model, bo, bu, cl):
    eo, eu = model * bo - 1, (1 - model) * bu - 1
    over = eo >= eu
    return np.maximum(eo, eu), np.where(over, cl * bo, (1 - cl) * bu) - 1


def placebo_arms(D, thr=0.05, n_perm=1000, seed=20261107):
    """Amendments 15-16. Same rows, dates and prices as the confirmatory bets; information removed, not the side.
    residual-permutation null: r = model - market is permuted within date x market-price bucket, placebo = market + r_perm, and the
    same NUMBER of bets per date as the real run is taken (top edge); random side: the selected rows with a coin for the side;
    shopping: every priced row, both sides at the best price, no selection."""
    rng = np.random.default_rng(seed)
    m, mk, bo, bu, cl = (D[c].to_numpy(float) for c in ("model_over", "market_over", "best_over", "best_under", "close_market_over"))
    ok = np.isfinite(cl)
    edge, clv_row = _row_clv(m, bo, bu, cl)
    sel = ok & (edge >= thr)
    obs = float(np.mean(clv_row[sel])) if sel.any() else float("nan")
    dates = D.date.to_numpy().astype(str)
    bucket = np.digitize(mk, [.2, .3, .4, .5, .6, .7, .8])
    cells = {}
    for i, key in enumerate(zip(dates, bucket)):
        cells.setdefault(key, []).append(i)
    cells = [np.array(v) for v in cells.values()]
    by_date = {}
    for i in np.flatnonzero(ok):
        by_date.setdefault(dates[i], []).append(i)
    k = {d: int(sel[np.array(ix)].sum()) for d, ix in by_date.items()}
    by_date = {d: np.array(ix) for d, ix in by_date.items() if k[d] > 0}
    resid = m - mk
    nulls = []
    for _ in range(n_perm):
        rp = resid.copy()
        for ix in cells:
            if len(ix) > 1:
                rp[ix] = rng.permutation(resid[ix])
        pm = np.clip(mk + rp, 0.001, 0.999)
        e_p, c_p = _row_clv(pm, bo, bu, cl)
        take = np.concatenate([ix[np.argsort(-e_p[ix])[:k[d]]] for d, ix in by_date.items()]) if by_date else np.array([], int)
        if len(take):
            nulls.append(float(np.mean(c_p[take])))
    nulls = np.array(nulls)
    coin = []
    for _ in range(min(n_perm, 1000)):
        o = rng.random(sel.sum()) < 0.5
        if sel.any():
            coin.append(np.mean(np.where(o, cl[sel] * bo[sel], (1 - cl[sel]) * bu[sel]) - 1))
    shop = float(np.mean(np.r_[cl[ok] * bo[ok] - 1, (1 - cl[ok]) * bu[ok] - 1])) if ok.any() else None
    q = float(np.quantile(nulls, 1 - ALPHA_CONTROL)) if len(nulls) else None
    perm_p = float((1 + (nulls >= obs).sum()) / (1 + len(nulls))) if len(nulls) and np.isfinite(obs) else None
    bind = max([0.0] + [v for v in (q, shop) if v is not None])
    return {"observed_clv": obs, "n_bets": int(sel.sum()), "perm_null_mean": float(nulls.mean()) if len(nulls) else None,
            "perm_null_p95": float(np.percentile(nulls, 95)) if len(nulls) else None, "perm_null_bonferroni_q": q, "perm_p": perm_p,
            "perm_draws": int(len(nulls)), "random_side_mean": float(np.mean(coin)) if coin else None, "shopping_all_rows_mean": shop,
            "binding_floor": bind,
            "floor_bound_by": "zero (null inert)" if bind == 0.0 else ("null quantile" if q is not None and bind == q else "shopping arm"), "exceeds_binding": bool(np.isfinite(obs) and obs > bind),
            "exceeds_null_p95": bool(len(nulls) and np.isfinite(obs) and obs > np.percentile(nulls, 95)),
            "breakeven_book_premium_r": obs}   # EV at a book with price disadvantage r is about (1+obs)/(1+r)-1


def clv_summary(B):
    """CLV over bets with a complete same-line close; bets missing one are counted and excluded from CLV only (never from profit)."""
    if len(B) == 0:
        return {"n": 0, "dates": 0}
    C = B.dropna(subset=["clv"]).reset_index(drop=True)
    out = {"n": int(len(C)), "n_all": int(len(B)), "missing_close": int(len(B) - len(C)), "dates": int(C.date.nunique()) if len(C) else 0,
           "roi_all": float(B.profit.mean()), "hit_rate_all": float(B.won.mean()), "mean_edge": float(B.edge.mean())}
    if len(C) == 0:
        return out
    bs = _cluster_boot(C, lambda x: x.clv.mean())
    # Amendment 14 items 1, 2, 4: placebo floor, close coverage (G2 insufficient above 30% missing), cluster diagnostics
    miss = B[B.clv.isna()]
    g = C.groupby("date").clv
    k, n = g.ngroups, len(C)
    msw, msb = (g.apply(lambda v: ((v - v.mean()) ** 2).sum()).sum() / max(n - k, 1)), (g.apply(lambda v: len(v) * (v.mean() - C.clv.mean()) ** 2).sum() / max(k - 1, 1))
    n0 = (n - (g.size() ** 2).sum() / n) / max(k - 1, 1)
    icc = float((msb - msw) / (msb + (n0 - 1) * msw)) if k > 1 and n0 > 0 and (msb + (n0 - 1) * msw) > 0 else None
    return out | {"clv_mean": float(C.clv.mean()), "clv_lb90": float(np.percentile(bs, 5)),
                  "clv_pessimistic_mean": float(np.r_[C.clv.to_numpy(), np.full(len(miss), np.percentile(C.clv, 10))].mean()), "missing_close_share": float(len(miss) / len(B)),
                  "roi_with_close": float(C.profit.mean()), "roi_missing_close": float(miss.profit.mean()) if len(miss) else None,
                  "close_coverage_ok": bool(len(miss) / len(B) <= 0.30), "bets_per_date": float(n / k), "date_icc": icc,
                  "fewer_than_40_dates": bool(k < 40)}


def selftest():
    """Synthetic check: the model holds information the market lacks; bets should show positive CLV and coefficient."""
    rng = np.random.default_rng(7)
    n = 6000
    true = 1 / (1 + np.exp(-rng.normal(0, 0.6, n)))
    mkt = 1 / (1 + np.exp(-(_logit(true) + rng.normal(0, 0.35, n))))
    mdl = 1 / (1 + np.exp(-(_logit(true) + rng.normal(0, 0.35, n))))
    close = 1 / (1 + np.exp(-(0.5 * _logit(mkt) + 0.5 * _logit(true))))
    over = (rng.random(n) < true).astype(int)
    vig = 1.045
    D = pd.DataFrame(dict(over=over, market_over=mkt, model_over=mdl, close_market_over=close, best_over=1 / (mkt * vig),
                          best_under=1 / ((1 - mkt) * vig), date=rng.integers(0, 120, n)))
    it = info_test(D)
    B = bets(D, 0.05)
    cs = clv_summary(B)
    assert it["model_coef"] > 0.15 and it["lb90"] > 0, it
    assert cs["n"] > 200 and cs["clv_mean"] > 0, cs
    # no information: coefficient near zero, CLV not positive
    D2 = D.assign(model_over=1 / (1 + np.exp(-(_logit(mkt) + rng.normal(0, 0.35, n)))))
    it2 = info_test(D2)
    cs2 = clv_summary(bets(D2, 0.05))
    assert abs(it2["model_coef"]) < 0.1 and cs2["clv_mean"] < 0.01, (it2, cs2)
    # an exact copy of the market must never pass G1: the design is rank-deficient, so the test is insufficient
    it3 = info_test(D.assign(model_over=D.market_over))
    assert it3["model_coef"] is None and not it3["assessable"] and it3["fit_status"] in ("rank", "condition"), it3
    # pieces on toy price rows (tip 2026-01-10 00:00 UTC; cutoff 23:00 the day before)
    def row(b, h, s, p, t60="2026-01-09T20:00:00Z", close="2026-01-09T23:50:00Z", fx="f"):
        return dict(fixture_id=fx, start_time="2026-01-10T00:00:00Z", player_name="A B", bookmaker=b, market_name="Player Points",
                    handicap=h, outcome_name=s, t60_price=p, t60_time=t60, t360_price=p, close_price=p, close_time=close, open_price=p)
    toy = pd.DataFrame([row(b, h, s, p) for b in ("draftkings", "fanduel")
                        for h, s, p in ((24.5, "Over", 1.91), (24.5, "Under", 1.91), (22.5, "Over", 1.6), (22.5, "Under", 2.3))])
    L = devig(main_lines(prices_long(toy)))
    assert len(L) == 1 and L.line.iloc[0] == 24.5 and abs(L.market_over.iloc[0] - 0.5) < 1e-9 and L.close_complete.iloc[0], L
    # entry quote older than 24 h at the cutoff is dropped; a stale close (over 60 min before tip) leaves the close missing
    toy2 = pd.DataFrame([row("draftkings", 24.5, s, 1.91, t60="2026-01-08T20:00:00Z") for s in ("Over", "Under")] +
                        [row("fanduel", 24.5, s, 1.91, close="2026-01-09T22:00:00Z") for s in ("Over", "Under")] +
                        [row("pinnacle", 24.5, s, 1.91) for s in ("Over", "Under")])
    L2 = devig(main_lines(prices_long(toy2)))
    assert L2.books.iloc[0] == 2 and not L2.close_complete.iloc[0] and np.isnan(L2.close_market_over.iloc[0]), L2
    # a quote changed after the cutoff is not an entry quote
    toy3 = pd.DataFrame([row("draftkings", 24.5, s, 1.91, t60="2026-01-09T23:30:00Z") for s in ("Over", "Under")])
    assert len(main_lines(prices_long(toy3))) == 0
    # one side changed after the cutoff (over 20:00, under 23:30) is not a valid entry pair (GPT review finding 1)
    toy4 = pd.DataFrame([row("draftkings", 24.5, "Over", 1.91), row("draftkings", 24.5, "Under", 1.91, t60="2026-01-09T23:30:00Z")])
    assert len(main_lines(prices_long(toy4))) == 0
    # one closing side stamped after tip-off leaves the close missing
    toy5 = pd.DataFrame([row("draftkings", 24.5, "Over", 1.91), row("draftkings", 24.5, "Under", 1.91, close="2026-01-10T00:05:00Z")])
    assert main_lines(prices_long(toy5)).close_over.isna().all()
    assert abs(p_over([0.1] * 10, 4.5) - 0.5) < 1e-9
    assert stat_of("Over Under Player Points + Assists + Rebounds (incl. overtime)") == "pra"
    assert stat_of("Over Under Player Assists + Rebounds (incl. overtime)") == "ra" and stat_of("Over Under Player Points First Quarter") is None
    assert stat_of("Over Under Player Rebounds (incl. overtime)") == "reb" and stat_of("Over Under Player Steals (incl. overtime)") is None
    assert stat_of("Player Points") == "pts" and stat_of("Player Points + Rebounds + Assists") == "pra" and stat_of("Player Points Alternate") is None
    print("selftest passed:", {k: round(v, 4) if isinstance(v, float) else v for k, v in it.items()}, {k: round(v, 4) if isinstance(v, float) else v for k, v in cs.items()})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
