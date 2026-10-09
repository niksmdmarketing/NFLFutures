"""Sport-agnostic winner-trend engine.

Input: regular-season game rows G, playoff game rows P and a team-season frame M (season, team, name, conf, div).
Output: one row per team-season with outcomes (playoffs, champion, finalist, division winner, top seed) and a set of
yes/no features, then each feature is tested against each outcome.

Noise filter (chosen with TypeSafe):
  1. Fisher's exact test of winners vs the rest of the pool, Benjamini-Hochberg false-discovery control at 10%
     within each market.
  2. The effect must point the same way in the earlier and the later half of the seasons.
  3. A conditional-logit test of whether the feature still matters once the team's record is known (record is the
     first thing every market prices). Signals that pass are "adds to the record"; the rest are "already in the record".
"""
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.stats import chi2, fisher_exact

FDR = 0.10
MIN_POOL_WITH = 5      # a trend needs at least this many pool teams with the feature to be judged
RECENT = 10


# ------------------------------------------------------------------ team-season table

def _rank(df, by, key, ascending=False):
    """Rank within groups (1 = best); NaN keys stay NaN."""
    return df.groupby(by)[key].rank(ascending=ascending, method="min")


def _pyth(pf, pa, e):
    """Expected win share from scoring (Pythagorean), computed as a ratio so large totals cannot overflow."""
    pf, pa = float(pf), float(pa)
    if pf <= 0 and pa <= 0:
        return np.nan
    if pf <= 0:
        return 0.0
    return 1.0 / (1.0 + (pa / pf) ** e)


def team_table(G, M, cfg):
    """Per team-season stats from regular-season games. cfg: close, pyth, top (dict of k values)."""
    G = G.sort_values(["season", "team", "date"])
    L = G.groupby(["season", "team"]).size().groupby("season").median()
    e = cfg["pyth"]
    out = []
    for (s, t), g in G.groupby(["season", "team"], sort=False):
        n = len(g)
        pts, mx = g.pts.sum(), g.maxpts.sum()
        pf, pa = g.pf.sum(), g.pa.sum()
        wp = pts / mx
        r = dict(season=s, team=t, gp=n, wp=wp, pd=(pf - pa) / n, pf_pg=pf / n, pa_pg=pa / n)
        r["pyth"] = _pyth(pf, pa, e)
        r["luck"] = wp - r["pyth"]
        c = g[(g.pf - g.pa).abs() <= cfg["close"]]
        r["close_n"], r["close_wp"] = len(c), (c.pts.sum() / c.maxpts.sum() if len(c) else np.nan)
        k = max(1, round(n / 4))
        lq = g.iloc[-k:]
        r["last_wp"] = lq.pts.sum() / lq.maxpts.sum()
        h = g[g.home]
        a = g[~g.home]
        r["home_wp"] = h.pts.sum() / h.maxpts.sum() if len(h) else np.nan
        r["road_wp"] = a.pts.sum() / a.maxpts.sum() if len(a) else np.nan
        for tag, f in (("q", .25), ("h", .5)):
            m = int(round(L[s] * f))
            sub = g.iloc[:m]
            if len(sub) < m or m == 0:
                r[f"wp_{tag}"] = r[f"pd_{tag}"] = r[f"luck_{tag}"] = np.nan
                continue
            spf, spa = sub.pf.sum(), sub.pa.sum()
            r[f"wp_{tag}"] = sub.pts.sum() / sub.maxpts.sum()
            r[f"pd_{tag}"] = (spf - spa) / m
            r[f"luck_{tag}"] = r[f"wp_{tag}"] - _pyth(spf, spa, e)
        out.append(r)
    T = pd.DataFrame(out).merge(M, on=["season", "team"], how="left")
    T["nteams"] = T.groupby("season").team.transform("size")
    # standings keys: record first, point differential as the tie-break proxy (official tie-breaks are used
    # where the source gives final ranks: NFL seeds/division ranks, NBL ladder positions)
    T["key"] = T.wp + T.pd * 1e-4
    for tag in ("q", "h"):
        T[f"key_{tag}"] = T[f"wp_{tag}"] + T[f"pd_{tag}"] * 1e-4
    T["lg_rank"] = _rank(T, "season", "key")
    T["cf_rank"] = _rank(T, ["season", "conf"], "key")
    T["dv_rank"] = _rank(T, ["season", "div"], "key")
    for c, asc in (("pd", False), ("pf_pg", False), ("pa_pg", True), ("last_wp", False), ("home_wp", False),
                   ("road_wp", False), ("luck", False)):
        T[f"{c}_lg"] = _rank(T, "season", c, asc)
    T["pd_cf"] = _rank(T, ["season", "conf"], "pd")
    T["pd_dv"] = _rank(T, ["season", "div"], "pd")
    for tag in ("q", "h"):
        T[f"lg_rank_{tag}"] = _rank(T, "season", f"key_{tag}")
        T[f"cf_rank_{tag}"] = _rank(T, ["season", "conf"], f"key_{tag}")
        T[f"dv_rank_{tag}"] = _rank(T, ["season", "div"], f"key_{tag}")
        T[f"pd_cf_{tag}"] = _rank(T, ["season", "conf"], f"pd_{tag}")
        T[f"pd_dv_{tag}"] = _rank(T, ["season", "div"], f"pd_{tag}")
        T[f"luck_{tag}_lg"] = _rank(T, "season", f"luck_{tag}")
    for c in ("final_lg_rank", "final_cf_rank", "final_dv_rank"):
        if c in T:
            T[c[6:]] = T[c].fillna(T[c[6:]])
    return T


def series(P, min_games=1, after=None):
    """Playoff series from game rows (one row per team per game): list of dicts per season."""
    after = after or {}
    P = P.sort_values("date")
    rows = []
    for s, g in P.groupby("season"):
        if s in after:
            g = g[g.date >= after[s]]
        g = g.assign(pair=[tuple(sorted((a, b))) for a, b in zip(g.team, g.opp)])
        for pair, x in g.groupby("pair"):
            games = x.groupby("gid").size().size if "gid" in x else len(x) // 2
            if games < min_games:
                continue
            w = x[x.win].groupby("team").size()
            if w.empty:
                continue
            win = w.idxmax()
            if len(w) > 1 and w.iloc[0] == w.iloc[1]:
                continue                               # unfinished
            rows.append(dict(season=s, a=pair[0], b=pair[1], winner=win, loser=pair[1] if win == pair[0] else pair[0],
                             start=x.date.min(), end=x.date.max(), games=games))
    return pd.DataFrame(rows)


def outcomes(T, S, cfg):
    """Adds playoffs, rounds_won, finalist, champ, div_win, top_seed to T from the series frame S."""
    T = T.copy()
    for c in ("playoffs", "rounds_won", "finalist", "champ"):
        T[c] = np.nan
    done = set()
    if len(S):
        for s, x in S.groupby("season"):
            fin = x.sort_values("end").iloc[-1]
            teams = set(x.a) | set(x.b)
            m = T.season == s
            T.loc[m, "playoffs"] = T.loc[m, "team"].isin(teams).astype(float)
            T.loc[m, "rounds_won"] = T.loc[m, "team"].map(x.winner.value_counts()).fillna(0)
            if s in cfg.get("unfinished", set()):
                continue
            T.loc[m, "finalist"] = T.loc[m, "team"].isin([fin.a, fin.b]).astype(float)
            T.loc[m, "champ"] = (T.loc[m, "team"] == fin.winner).astype(float)
            done.add(s)
    for s, (champ, runner) in cfg.get("known", {}).items():
        # verified results override gaps in the feed (e.g. a final game with no score)
        m = T.season == s
        if not m.any():
            continue
        T.loc[m, "finalist"] = T.loc[m, "team"].isin([champ, runner]).astype(float)
        T.loc[m, "champ"] = (T.loc[m, "team"] == champ).astype(float)
        T.loc[m & T.team.isin([champ, runner]), "playoffs"] = 1.0
        T.loc[m & (T.team == runner), "rounds_won"] = T.loc[m & (T.team == runner), "rounds_won"].clip(lower=1)
        T.loc[m & (T.team == champ), "rounds_won"] = T.loc[m & (T.team == champ), "rounds_won"].clip(lower=2)
        done.add(s)
    if "final_playoffs" in T:
        T["playoffs"] = T.final_playoffs.where(T.final_playoffs.notna(), T.playoffs)
    T["complete"] = T.season.isin(done)
    T["div_win"] = np.where(T["div"].notna() & T.complete, (T.dv_rank == 1).astype(float), np.nan)
    T["top_seed"] = np.where(T["conf"].notna() & T.complete, (T.cf_rank == 1).astype(float), np.nan)
    return T


def add_prior(T, keys):
    prev = T[["season", "team"] + keys].copy()
    prev["season"] += 1
    return T.merge(prev.rename(columns={k: f"{k}_prev" for k in keys}), on=["season", "team"], how="left")


# ------------------------------------------------------------------ features

def topk(T, n):
    """'Top-5 in a 30-team league' scaled to this league's size."""
    return np.maximum(1, np.round(T.nteams * n / 30))


def features(T, cfg):
    """List of (key, label, timing, sections, values, baseline). values: float 1/0/NaN per T row."""
    F = []
    k5, k10 = topk(T, 5), topk(T, 10)
    quarter = (T.luck_lg <= T.nteams / 4)
    bottomq = (T.luck_lg > T.nteams * 3 / 4)
    has_conf = T.conf.nunique() > 1 or cfg.get("conf_is_league")
    K5 = int(round(np.nanmedian(k5)))
    K10 = int(round(np.nanmedian(k10)))
    conf_word = cfg.get("conf_word", "conference")
    END, PRI, Q, H, PRE = "end", "prior", "q", "h", "pre"
    title_secs = ["champ", "finalist"]
    pre_secs = ["top_seed", "div_win", "playoffs"]

    def add(key, label, timing, secs, cond, base, need=None, market=False):
        v = cond.astype(float)
        if need is not None:
            v = v.where(need)
        F.append(dict(key=key, label=label, timing=timing, sections=secs, v=v, base=base, market=market))

    # end of regular season
    add("best_record", "Best regular-season record in the league", END, title_secs, T.lg_rank == 1, "wp")
    if cfg.get("conf"):
        add("conf_top", f"No. 1 seed in its {conf_word}", END, title_secs, T.cf_rank == 1, "wp")
        add("conf_top2", f"Top-two record in its {conf_word}", END, title_secs, T.cf_rank <= 2, "wp")
    else:
        add("lg_top2", "Top-two finish on the ladder", END, title_secs, T.lg_rank <= 2, "wp")
    add("pd_best", f"Best {cfg['pd_word']} in the league", END, title_secs, T.pd_lg == 1, "wp")
    add("pd_top3", f"Top-three {cfg['pd_word']} in the league", END, title_secs, T.pd_lg <= 3, "wp")
    add("off_top", f"Top-{K5} attack ({cfg['pf_word']} scored per game)", END, title_secs, T.pf_pg_lg <= k5, "wp")
    add("def_top", f"Top-{K5} defence ({cfg['pf_word']} allowed per game)", END, title_secs, T.pa_pg_lg <= k5, "wp")
    add("balanced", f"Top-{K10} in both attack and defence", END, title_secs, (T.pf_pg_lg <= k10) & (T.pa_pg_lg <= k10), "wp")
    add("def_over_off", "Defence ranked higher than attack", END, title_secs, T.pa_pg_lg < T.pf_pg_lg, "wp")
    add("pd_beats_record", f"{cfg['pd_word'].capitalize()} rank 3+ places better than record rank (underrated)", END,
        title_secs, T.pd_lg + 3 <= T.lg_rank, "wp")
    add("record_beats_pd", f"Record rank 3+ places better than {cfg['pd_word']} rank (flattered)", END, title_secs,
        T.lg_rank + 3 <= T.pd_lg, "wp")
    add("lucky", f"Won more than its {cfg['pf_word']} suggest (top quarter for luck)", END, title_secs, quarter, "wp")
    add("unlucky", f"Won fewer than its {cfg['pf_word']} suggest (bottom quarter for luck)", END, title_secs, bottomq, "wp")
    add("close_good", f"Won 60%+ of close games (decided by {cfg['close_word']})", END, title_secs,
        T.close_wp >= .6, "wp", need=T.close_n >= 4)
    add("strong_finish", f"Top-{K5} record over the last quarter of the season", END, title_secs, T.last_wp_lg <= k5, "wp")
    add("weak_finish", "Losing record over the last quarter of the season", END, title_secs, T.last_wp < .5, "wp")
    add("home_top", f"Top-{K5} home record", END, title_secs, T.home_wp_lg <= k5, "wp")
    add("road_top", f"Top-{K5} road record", END, title_secs, T.road_wp_lg <= k5, "wp")
    for key, label, cond, need in cfg.get("extra_end", []):
        add(key, label, END, title_secs, cond(T), "wp", need=need(T) if need else None)

    # prior season
    prev_ok = T.wp_prev.notna()
    allp = title_secs + pre_secs
    add("champ_prev", "Defending champion", PRI, allp, T.champ_prev == 1, "wp_prev", need=prev_ok)
    add("finalist_prev", "Played in the final last season", PRI, allp, T.finalist_prev == 1, "wp_prev", need=prev_ok)
    add("lost_final_prev", "Lost the final last season", PRI, allp, (T.finalist_prev == 1) & (T.champ_prev == 0),
        "wp_prev", need=prev_ok)
    add("deep_prev", f"Won {cfg['deep_rounds']}+ playoff rounds last season", PRI, allp,
        T.rounds_won_prev >= cfg["deep_rounds"], "wp_prev", need=prev_ok)
    add("playoffs_prev", "Made the playoffs last season", PRI, allp, T.playoffs_prev == 1, "wp_prev", need=prev_ok)
    add("pd_top_prev", f"Top-{K5} {cfg['pd_word']} last season", PRI, allp, T.pd_lg_prev <= k5, "wp_prev", need=prev_ok)
    add("lucky_prev", "Lucky last season (won more than its scoring suggested, top quarter)", PRI, allp,
        T.luck_lg_prev <= T.nteams / 4, "wp_prev", need=prev_ok)
    add("unlucky_prev", "Unlucky last season (won fewer than its scoring suggested, bottom quarter)", PRI, allp,
        T.luck_lg_prev > T.nteams * 3 / 4, "wp_prev", need=prev_ok)
    add("underrated_prev", f"Last season's {cfg['pd_word']} rank 3+ places better than its record rank", PRI, allp,
        T.pd_lg_prev + 3 <= T.lg_rank_prev, "wp_prev", need=prev_ok)
    add("strong_finish_prev", f"Top-{K5} record over the last quarter of last season", PRI, allp,
        T.last_wp_lg_prev <= k5, "wp_prev", need=prev_ok)
    if cfg.get("div"):
        add("div_win_prev", "Won the division last season", PRI, ["div_win"], T.div_win_prev == 1, "wp_prev",
            need=prev_ok & T["div"].notna())
        add("div_pd_prev", f"Best {cfg['pd_word']} in its division last season", PRI, ["div_win"], T.pd_dv_prev == 1,
            "wp_prev", need=prev_ok & T["div"].notna())
    if cfg.get("conf"):
        add("top_seed_prev", f"No. 1 seed in its {conf_word} last season", PRI, ["top_seed", "champ", "finalist"],
            T.top_seed_prev == 1, "wp_prev", need=prev_ok)

    # in-season checkpoints
    for tag, word in (("q", "a quarter of the way through"), ("h", "at the halfway mark")):
        tm = Q if tag == "q" else H
        b = f"wp_{tag}"
        ok = T[b].notna()
        spots = T.spots
        add(f"spot_{tag}", f"In a playoff place {word}", tm, ["playoffs"],
            T[f"cf_rank_{tag}"] <= spots, b, need=ok & spots.notna())
        add(f"out_spot_good_pd_{tag}", f"Outside the playoff places {word} but inside them on {cfg['pd_word']}", tm,
            ["playoffs"], (T[f"cf_rank_{tag}"] > spots) & (T[f"pd_cf_{tag}"] <= spots), b, need=ok & spots.notna())
        add(f"lucky_{tag}", f"Lucky {word} (record ahead of scoring, top quarter)", tm, ["playoffs", "top_seed", "div_win"],
            T[f"luck_{tag}_lg"] <= T.nteams / 4, b, need=ok)
        if cfg.get("conf"):
            add(f"conf_lead_{tag}", f"Leading its {conf_word} {word}", tm, ["top_seed", "finalist", "champ"],
                T[f"cf_rank_{tag}"] == 1, b, need=ok)
            add(f"conf_pd_lead_{tag}", f"Best {cfg['pd_word']} in its {conf_word} {word}", tm, ["top_seed"],
                T[f"pd_cf_{tag}"] == 1, b, need=ok)
        else:
            add(f"lg_lead_{tag}", f"Top of the ladder {word}", tm, ["top_seed", "finalist", "champ"],
                T[f"lg_rank_{tag}"] == 1, b, need=ok)
        if cfg.get("div"):
            dok = ok & T["div"].notna()
            add(f"div_lead_{tag}", f"Leading its division {word}", tm, ["div_win"], T[f"dv_rank_{tag}"] == 1, b, need=dok)
            add(f"div_pd_not_lead_{tag}", f"Best {cfg['pd_word']} in its division {word} but not leading it", tm,
                ["div_win"], (T[f"pd_dv_{tag}"] == 1) & (T[f"dv_rank_{tag}"] > 1), b, need=dok)
    for key, label, secs, cond, need in cfg.get("extra_pre", []):
        add(key, label, PRE, secs, cond(T), "wp_prev", need=need(T) if need else None, market=True)
    return F


# ------------------------------------------------------------------ statistics

def bh(p):
    p = np.asarray(p, float)
    n = len(p)
    if n == 0:
        return p
    o = np.argsort(p)
    q = p[o] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[o] = np.minimum(q, 1)
    return out


FEAT_RIDGE = 0.25      # weak prior on the feature's effect (sd ~1.4 on the log-odds scale): stops a handful of
                       # 0-for-N cases producing huge, fragile effects


def _pen(beta, nfix):
    return 1e-3 * (beta[:nfix] ** 2).sum() + FEAT_RIDGE * (beta[nfix:] ** 2).sum()


def _clogit_nll(beta, X, y, gidx, ngroups, nfix=1):
    eta = X @ beta
    # sum over winners minus log-sum-exp per group (one winner per group)
    lse = np.full(ngroups, -np.inf)
    np.logaddexp.at(lse, gidx, eta)
    return -(eta[y == 1].sum() - lse.sum()) + _pen(beta, nfix)


def _logit_nll(beta, X, y, nfix=2):
    eta = X @ beta
    return -(y * eta - np.logaddexp(0, eta)).sum() + _pen(beta[1:], nfix - 1)


def beyond_test(D, base, feat, group_cols, want_exp=False):
    """LR test for the feature once the baseline is in the model. Returns (p, coef[, expected successes among
    teams with the feature under the baseline-only model])."""
    D = D[[base, feat, "y"] + group_cols].dropna()
    if D[feat].nunique() < 2 or len(D) < 10:
        return (np.nan, np.nan, np.nan) if want_exp else (np.nan, np.nan)
    b = (D[base] - D[base].mean()) / (D[base].std() or 1)
    gkey = D[group_cols].astype(str).agg("|".join, axis=1)
    wins = D.y.groupby(gkey).transform("sum")
    single = (D.y.groupby(gkey).sum() == 1).all()
    if single:
        keep = wins == 1
        D, b, gkey = D[keep], b[keep], gkey[keep]
        gidx = pd.factorize(gkey)[0]
        ng = gidx.max() + 1
        y = D.y.values
        X0 = b.values[:, None]
        X1 = np.column_stack([b.values, D[feat].values])
        f0 = minimize(_clogit_nll, np.zeros(1), args=(X0, y, gidx, ng), method="BFGS")
        f1 = minimize(_clogit_nll, np.zeros(2), args=(X1, y, gidx, ng), method="BFGS")
        eta = X0 @ f0.x
        lse = np.full(ng, -np.inf)
        np.logaddexp.at(lse, gidx, eta)
        prob = np.exp(eta - lse[gidx])
    else:
        y = D.y.values
        X0 = np.column_stack([np.ones(len(D)), b.values])
        X1 = np.column_stack([np.ones(len(D)), b.values, D[feat].values])
        f0 = minimize(_logit_nll, np.zeros(2), args=(X0, y), method="BFGS")
        f1 = minimize(_logit_nll, np.zeros(3), args=(X1, y), method="BFGS")
        prob = 1 / (1 + np.exp(-(X0 @ f0.x)))
    lr = max(0.0, 2 * (f0.fun - f1.fun))
    if want_exp:
        return float(chi2.sf(lr, 1)), float(f1.x[-1]), float(prob[D[feat].values == 1].sum())
    return float(chi2.sf(lr, 1)), float(f1.x[-1])


def evaluate(T, F, section, label_fn, cur_season, cur_ok):
    """Test every feature for one market. Returns (trends list, winners list)."""
    out_col, pool_mask, groups = section["outcome"], section["pool"], section["groups"]
    C = T[T.complete & pool_mask(T) & T[out_col].notna()].copy()
    if C.empty:
        return [], []
    seasons = sorted(C.season.unique())
    half = seasons[len(seasons) // 2]
    recent = set(seasons[-RECENT:])
    rows = []
    for f in F:
        if section["key"] not in f["sections"]:
            continue
        v = f["v"].loc[C.index]
        D = C.assign(x=v, y=C[out_col]).dropna(subset=["x"])
        if D.empty:
            continue
        W = D[D.y == 1]
        a, nw = int(W.x.sum()), len(W)
        m, n = int(D.x.sum()), len(D)
        r = dict(key=f["key"], label=f["label"], timing=f["timing"], winners_with=a, winners=nw, pool_with=m, pool=n,
                 seasons=int(D.season.nunique()))
        r["rate_with"] = a / m if m else None
        r["rate_without"] = (nw - a) / (n - m) if n - m else None
        r["lift"] = (r["rate_with"] / r["rate_without"]) if m and r["rate_without"] else None
        if m and n - m:
            r["p"] = float(fisher_exact([[a, m - a], [nw - a, (n - m) - (nw - a)]])[1])
        else:
            r["p"] = 1.0
        halves = []
        for part in (D[D.season < half], D[D.season >= half]):
            pm, pw = part.x.sum(), part.y.sum()
            pa = part[(part.x == 1)].y.sum()
            rw = pa / pm if pm else np.nan
            rwo = (pw - pa) / (len(part) - pm) if len(part) - pm else np.nan
            halves.append(None if (np.isnan(rw) or np.isnan(rwo)) else round(float(rw - rwo), 4))
        r["halves"] = halves
        direction = 0 if r["rate_with"] is None or r["rate_without"] is None else np.sign(r["rate_with"] - r["rate_without"])
        r["direction"] = int(direction)
        r["stable"] = bool(direction != 0 and all(h is not None and np.sign(h) == direction for h in halves))
        rec = D[D.season.isin(recent) & (D.y == 1)]
        r["recent_with"], r["recent"] = int(rec.x.sum()), len(rec)
        r["recent_seasons"] = len(set(D.season) & recent)
        r["winner_list"] = [[int(s), label_fn(s), t] for s, t in zip(W[W.x == 1].season, W[W.x == 1].team)]
        r["_D"] = D
        r["_base"] = f["base"]
        r["market"] = f.get("market", False)
        # who fits it now
        if cur_season is not None and cur_ok(f["timing"]):
            cv = f["v"][(T.season == cur_season)]
            r["now"] = sorted(T.loc[cv[cv == 1].index, "team"].tolist())
        else:
            r["now"] = None
        rows.append(r)
    if not rows:
        return [], []
    qs = bh([r["p"] for r in rows])
    for r, q in zip(rows, qs):
        r["q"] = float(q)
    # the second question: at the same record (or, for prior-season items, the same record last season),
    # do teams with this feature still do better or worse? Tested for every feature that is common enough,
    # with its own false-discovery control, and it must hold in both halves of the seasons.
    bp, tested = [], []
    for r in rows:
        r["beyond_p"] = r["beyond_coef"] = None
        r["beyond_stable"] = False
        if r["pool_with"] < MIN_POOL_WITH or r["pool"] - r["pool_with"] < MIN_POOL_WITH:
            continue
        D = r["_D"].rename(columns={"x": "feat"})
        p, coef, ex = beyond_test(D, r["_base"], "feat", groups, want_exp=True)
        r["expected_with"] = ex
        if p != p:
            continue
        signs = []
        for part in (D[D.season < half], D[D.season >= half]):
            _, c = beyond_test(part, r["_base"], "feat", groups)
            signs.append(np.sign(c) if c == c else 0)
        r["beyond_p"], r["beyond_coef"] = p, coef
        r["beyond_stable"] = bool(all(x == np.sign(coef) and x != 0 for x in signs))
        bp.append(p)
        tested.append(r)
    for r, q in zip(tested, bh(bp)):
        r["beyond_q"] = float(q)
    for r in rows:
        r.pop("_D")
        r.pop("_base")
        r["verdict"], r["why"] = verdict(r)
    W = C[C[out_col] == 1].sort_values("season", ascending=False)
    winners = [[int(s), label_fn(s), t] for s, t in zip(W.season, W.team)]
    return rows, winners


BASE_WORDS = {"end": "record", "prior": "record last season", "pre": "record last season",
              "q": "record at that point", "h": "record at that point"}


def verdict(r):
    """edge = better than the record says; fade = worse than the record says; priced = real but explained by the
    record; weak = consistent but unproven; noise = everything else."""
    rare = r["pool_with"] < MIN_POOL_WITH or (r["pool"] - r["pool_with"]) < MIN_POOL_WITH
    if rare:
        return "noise", "Too rare (or too common) to judge"
    same = BASE_WORDS[r["timing"]]
    bq = r.get("beyond_q")
    if bq is not None and bq <= FDR and r["beyond_stable"]:
        if r.get("market"):
            return "priced", ("The betting market's own early-season rating. It predicts better than " + same +
                              ", but it is the price, so it cannot be an edge against the price")
        if r["beyond_coef"] > 0:
            return "edge", f"Teams with this do better than their {same} suggests, in both halves of the history"
        return "fade", f"Teams with this do worse than their {same} suggests, in both halves of the history"
    if r["q"] <= FDR and r["stable"]:
        return "priced", f"Real, but explained by the {same}, which markets already price"
    if r["p"] < 0.05 and r["stable"]:
        return "weak", "Holds in both halves of the history but not yet strong enough to rule out chance"
    if r["p"] < 0.05:
        return "noise", "Came from one era only and vanished or reversed in the other"
    if r["stable"]:
        return "noise", "Points the same way in both eras, but the gap is within what chance produces"
    return "noise", "No reliable difference between teams with and without it"


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (o != o or o in (math.inf, -math.inf)) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o
