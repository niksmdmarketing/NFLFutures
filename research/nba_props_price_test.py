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
EXCLUDE = re.compile(r"alternate|milestone|\d\+|first|quarter|half|1st|2nd|3rd|4th|double|triple|steals|blocks|threes|3-point|turnover",
                     re.I)
PRIMARY_STATS = ("pts", "reb", "ast")
BOOT, SEED = 2000, 1


def stat_of(market_name):
    m = str(market_name or "").lower()
    if EXCLUDE.search(m):
        return None
    for s, pat in STAT_PATTERNS:
        if re.search(pat, m):
            return s
    return None


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


def _two_way(d, col):
    w = d.pivot_table(index=["fixture_id", "player_name", "stat", "bookmaker", "line"], columns="side", values=col, aggfunc="last")
    return w.dropna(subset=[c for c in ("over", "under") if c in w.columns]) if {"over", "under"} <= set(w.columns) else w.iloc[0:0]


def main_lines(P, col="t60_price"):
    """Consensus main line per fixture, player and stat, with each book's two-way prices on that line at entry and close."""
    W = _two_way(P, col).reset_index()
    if W.empty:
        return W
    W["gap"] = (1 / W.over - 1 / W.under).abs()
    book_main = W.sort_values("gap").groupby(["fixture_id", "player_name", "stat", "bookmaker"]).head(1)
    def pick(g):   # the line most books treat as main; ties go to Pinnacle's main line, then the lower line
        vc = g.line.value_counts()
        tied = sorted(vc[vc == vc.max()].index)
        pin = g[g.bookmaker.str.lower().str.contains("pinnacle")].line
        return pin.iloc[0] if len(tied) > 1 and len(pin) and pin.iloc[0] in tied else tied[0]
    mode = book_main.groupby(["fixture_id", "player_name", "stat"]).apply(pick, include_groups=False).rename("main_line")
    W = W.merge(mode, on=["fixture_id", "player_name", "stat"])
    W = W[W.line == W.main_line].drop(columns=["gap", "main_line"])
    C = _two_way(P, "close_price").reset_index().rename(columns={"over": "close_over", "under": "close_under"})
    return W.merge(C, on=["fixture_id", "player_name", "stat", "bookmaker", "line"], how="left")


def devig(W):
    """Fair over probability per book (multiplicative) at entry and close; consensus over books on the same line."""
    W = W.copy()
    io, iu = 1 / W.over, 1 / W.under
    W["fair_over"] = io / (io + iu)
    co, cu = 1 / W.close_over, 1 / W.close_under
    W["close_fair_over"] = co / (co + cu)
    g = W.groupby(["fixture_id", "player_name", "stat", "line"])
    out = g.agg(market_over=("fair_over", "mean"), close_market_over=("close_fair_over", "mean"), best_over=("over", "max"),
                best_under=("under", "max"), books=("bookmaker", "nunique")).reset_index()
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


def logistic(X, y, iters=50):
    X = np.column_stack([np.ones(len(y)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu) + 1e-9
        step = np.linalg.solve(X.T @ (X * W[:, None]) + 1e-8 * np.eye(X.shape[1]), X.T @ (y - mu))
        b += step
        if np.abs(step).max() < 1e-9:
            break
    return b


def _cluster_boot(D, stat_fn, key="date"):
    rng = np.random.default_rng(SEED)
    groups = {k: g.index.to_numpy() for k, g in D.groupby(key)}
    keys = np.array(list(groups))
    vals = []
    for _ in range(BOOT):
        pick = rng.choice(keys, len(keys), replace=True)
        idx = np.concatenate([groups[k] for k in pick])
        vals.append(stat_fn(D.loc[idx]))
    return np.array(vals)


def info_test(D):
    """D: rows with over (0/1), market_over, model_over, date. Returns the model coefficient with a 90% date-bootstrap interval and log losses."""
    f = lambda x: logistic(np.column_stack([_logit(x.market_over), _logit(x.model_over)]), x.over.to_numpy(float))[2]
    b = f(D)
    bs = _cluster_boot(D.reset_index(drop=True), f)
    ll = lambda p: float(-np.mean(D.over * np.log(np.clip(p, 1e-6, 1)) + (1 - D.over) * np.log(np.clip(1 - p, 1e-6, 1))))
    return {"n": int(len(D)), "model_coef": float(b), "lb90": float(np.percentile(bs, 5)), "ub90": float(np.percentile(bs, 95)),
            "logloss_market": ll(D.market_over), "logloss_model": ll(D.model_over)}


def bets(D, thr=0.05):
    """One side per row (player-game-stat): the side with the higher edge, kept if edge >= thr."""
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


def clv_summary(B):
    if len(B) == 0:
        return {"n": 0}
    bs = _cluster_boot(B.reset_index(drop=True), lambda x: x.clv.mean())
    return {"n": int(len(B)), "clv_mean": float(B.clv.mean()), "clv_lb90": float(np.percentile(bs, 5)),
            "roi": float(B.profit.mean()), "hit_rate": float(B.won.mean()), "mean_edge": float(B.edge.mean())}


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
    assert it["model_coef"] > 0.3 and it["lb90"] > 0, it
    assert cs["n"] > 200 and cs["clv_mean"] > 0, cs
    # no information: coefficient near zero, CLV not positive
    D2 = D.assign(model_over=1 / (1 + np.exp(-(_logit(mkt) + rng.normal(0, 0.35, n)))))
    it2 = info_test(D2)
    cs2 = clv_summary(bets(D2, 0.05))
    assert abs(it2["model_coef"]) < 0.15 and cs2["clv_mean"] < 0.01, (it2, cs2)
    # pieces on toy price rows
    toy = pd.DataFrame([dict(fixture_id="f", player_name="A B", bookmaker=b, market_name="Player Points", handicap=h, outcome_name=s,
                             t60_price=p, t360_price=p, close_price=p, open_price=p)
                        for b in ("draftkings", "fanduel") for h, s, p in ((24.5, "Over", 1.91), (24.5, "Under", 1.91), (22.5, "Over", 1.6), (22.5, "Under", 2.3))])
    L = devig(main_lines(prices_long(toy)))
    assert len(L) == 1 and L.line.iloc[0] == 24.5 and abs(L.market_over.iloc[0] - 0.5) < 1e-9, L
    assert abs(p_over([0.1] * 10, 4.5) - 0.5) < 1e-9
    assert stat_of("Player Points") == "pts" and stat_of("Player Points + Rebounds + Assists") == "pra" and stat_of("Player Points Alternate") is None
    print("selftest passed:", {k: round(v, 4) if isinstance(v, float) else v for k, v in it.items()}, {k: round(v, 4) if isinstance(v, float) else v for k, v in cs.items()})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
