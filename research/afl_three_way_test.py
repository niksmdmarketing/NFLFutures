"""AFL three-way test per research/AFL_THREE_WAY_RULE.md. Reads the clean Wheelo tables (never committed).
Usage: python afl_three_way_test.py <clean_dir> [--out afl_three_way_results.json]"""
import json
import sys
from math import erf, sqrt

import numpy as np
import pandas as pd

HGA, K_PRIOR, PRIOR_REG, GAME_SD = 7.0, 12.0, 0.65, 32.0          # live model constants (pipeline/afl_site.py, 19 Oct 2026)
STATS = ["ShotsAtGoal", "Inside50s", "TotalClearances", "CentreClearances", "ContestedPossessions", "GroundBallGets", "MetresGained",
         "Marks", "InterceptMarks", "Intercepts", "Tackles", "DisposalEfficiency"]
TUNE, TEST = list(range(2013, 2019)), list(range(2019, 2027))


def srs(h, a, y, prior=None, k=8.0, free_home=False):
    """live srs: least squares of y - HGA on +1 home / -1 away, shrunk to prior with weight k games, centred. free_home: estimate home term instead."""
    teams = sorted(set(h) | set(a) | set(prior or {}))
    ix = {t: i for i, t in enumerate(teams)}
    n, m = len(teams), len(h)
    A = np.zeros((m + n, n + int(free_home)))
    b = np.zeros(m + n)
    for r, (t, o, v) in enumerate(zip(h, a, y)):
        A[r, ix[t]], A[r, ix[o]] = 1, -1
        if free_home:
            A[r, n] = 1
        b[r] = v if free_home else v - HGA
    lam = np.sqrt(k / 2)
    for t, i in ix.items():
        A[m + i, i] = lam
        b[m + i] = lam * (prior or {}).get(t, 0.0)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    r = sol[:n] - sol[:n].mean()
    return dict(zip(teams, r)), (sol[n] if free_home else HGA)


def season_ratings(M, y_col_fn, free_home):
    """point-in-time rating differences (home - away, plus home term) for every match, per the A machinery. Returns array aligned with M."""
    out = np.full(len(M), np.nan)
    hom = np.full(len(M), np.nan)
    end = {}
    for yr in sorted(M.season.unique()):
        s = M[M.season == yr]
        prior = {t: PRIOR_REG * v for t, v in end.items()}
        for r in sorted(s["round"].unique()):
            past, now = s[s["round"] < r], s[s["round"] == r]
            if len(past):
                rt, ha = srs(past.home, past.away, y_col_fn(past), prior, K_PRIOR, free_home)
            else:
                rt, ha = prior, (HGA if not free_home else last_ha.get("v", 0.0))
            out[now.index] = [rt.get(h, 0.0) - rt.get(a, 0.0) for h, a in zip(now.home, now.away)]
            hom[now.index] = ha
        end, last_ha_v = srs(s.home, s.away, y_col_fn(s), None, 8.0, free_home)
        last_ha["v"] = last_ha_v
    return out, hom


last_ha = {}


def player_model(M, P, H, n0, lineup):
    """team strength difference (home - away) for every match; lineup 'prev' (previous-match players) or 'actual'."""
    P = P.copy()
    P["v"] = P.RatingPoints * np.where(P.season == 2020, 1.25, 1.0)
    order = M[["season", "round"]].drop_duplicates().sort_values(["season", "round"]).reset_index(drop=True)
    order["k"] = range(len(order))
    P = P.merge(order, on=["season", "round"])
    first = P.groupby("WebsiteId").k.min()
    fs = P.merge(first.rename("k0"), on="WebsiteId")
    fs = fs[fs.season.isin(TUNE) & fs.WebsiteId.isin(first.index[P.groupby("WebsiteId").season.min().reindex(first.index) >= 2013])]
    fs = fs.sort_values(["WebsiteId", "k"]).groupby("WebsiteId").head(5)
    R = float(fs.v.mean())
    d = 0.5 ** (1.0 / H)
    S, W = {}, {}
    rating = lambda pid: (S.get(pid, 0.0) + n0 * R) / (W.get(pid, 0.0) + n0)
    by_round = {k: g for k, g in P.groupby("k")}
    last_lineup = {}
    Mk = M.merge(order, on=["season", "round"], how="left")
    diff = np.full(len(M), np.nan)
    for k in range(len(order)):
        g = by_round.get(k)
        rows = Mk.index[Mk.k == k]
        for i in rows:
            h, a, mid = M.home[i], M.away[i], M.match_id[i]
            if lineup == "actual":
                lh = g[(g.MatchId == mid) & (g.Team == h)].WebsiteId.tolist()
                la = g[(g.MatchId == mid) & (g.Team == a)].WebsiteId.tolist()
            else:
                lh, la = last_lineup.get(h, []), last_lineup.get(a, [])
            diff[i] = sum(rating(p) for p in lh) - sum(rating(p) for p in la) if (lh and la) else 0.0
        if g is not None:                       # after the round: update player ratings and last lineups
            for pid, v in zip(g.WebsiteId, g.v):
                S[pid] = S.get(pid, 0.0) * d + v
                W[pid] = W.get(pid, 0.0) * d + 1.0
            for (mid, team), gg in g.groupby(["MatchId", "Team"]):
                last_lineup[team] = gg.WebsiteId.tolist()
    return diff, R


def phi(z):
    return 0.5 * (1 + erf(z / sqrt(2)))


def logloss(pred, act, sd):
    p = np.clip(np.array([phi(m / sd) for m in pred]), 1e-4, 1 - 1e-4)
    y = np.where(act > 0, 1.0, np.where(act == 0, 0.5, 0.0))
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ols(X, y, lam=0.0):
    X1 = np.column_stack([np.ones(len(X)), X])
    P = np.eye(X1.shape[1]) * lam
    P[0, 0] = 0
    return np.linalg.solve(X1.T @ X1 + P, X1.T @ y)


def predictions(clean):
    """point-in-time predictions of A, B, C, D (and actual-lineup variants) for every match; returns (M, res, extras)."""
    M = pd.read_csv(f"{clean}/afl_matches.csv").sort_values(["season", "round", "match_id"]).reset_index(drop=True)
    T = pd.read_csv(f"{clean}/afl_team_stats.csv")
    P = pd.read_csv(f"{clean}/afl_player_stats.csv.gz" if __import__("os").path.exists(f"{clean}/afl_player_stats.csv.gz") else f"{clean}/afl_player_stats.csv",
                    usecols=["season", "round", "MatchId", "Team", "WebsiteId", "RatingPoints"])
    M["act"] = (M.home_score - M.away_score).astype(float)
    res = {"n_matches": len(M)}

    # A
    a_diff, a_ha = season_ratings(M, lambda g: (g.home_score - g.away_score).to_numpy(float), free_home=False)
    M["A"] = a_diff + a_ha
    # B
    ht = T[T.is_home == 1].set_index("MatchId")
    at = T[T.is_home == 0].set_index("MatchId")
    feats = []
    for st in STATS:
        dmap = (ht[st] - at[st]).to_dict()
        rd, rh = season_ratings(M, lambda g, dm=dmap: g.match_id.map(dm).fillna(0).to_numpy(float), free_home=True)
        M["b_" + st] = rd
        feats.append("b_" + st)
    tu = M.season.isin(TUNE)
    mu, sdv = M.loc[tu, feats].mean(), M.loc[tu, feats].std()
    Z = (M[feats] - mu) / sdv
    cv = {}
    for lam in (1, 10, 100, 1000):
        se = []
        for yo in TUNE:
            tr, te = tu & (M.season != yo), M.season == yo
            b = ols(Z[tr].to_numpy(), M.act[tr].to_numpy(), lam)
            se.append(((M.act[te] - (b[0] + Z[te].to_numpy() @ b[1:])) ** 2).to_numpy())
        cv[lam] = float(np.mean(np.concatenate(se)))
    lamB = min(cv, key=cv.get)
    bB = ols(Z[tu].to_numpy(), M.act[tu].to_numpy(), lamB)
    M["B"] = bB[0] + Z.to_numpy() @ bB[1:]
    res["B"] = {"lambda": lamB, "cv": cv, "intercept": float(bB[0]), "weights_per_sd": dict(zip(STATS, map(float, bB[1:])))}
    # C
    grid = {}
    cache = {}
    for H in (5, 10, 20, 40):
        for n0 in (2, 5, 10):
            dprev, R = player_model(M, P, H, n0, "prev")
            cache[(H, n0)] = dprev
            x = dprev[tu]
            b = ols(x[:, None], M.act[tu].to_numpy())
            grid[(H, n0)] = float(np.mean((M.act[tu] - (b[0] + b[1] * x)) ** 2))
    H, n0 = min(grid, key=grid.get)
    dprev = cache[(H, n0)]
    dact, R = player_model(M, P, H, n0, "actual")
    bC = ols(dprev[tu][:, None], M.act[tu].to_numpy())
    M["C"] = bC[0] + bC[1] * dprev
    bCa = ols(dact[tu][:, None], M.act[tu].to_numpy())
    M["C_actual"] = bCa[0] + bCa[1] * dact
    res["C"] = {"H": H, "n0": n0, "R": R, "grid": {f"{k[0]}_{k[1]}": v for k, v in grid.items()}, "h": float(bC[0]), "beta": float(bC[1]),
                "actual_lineup_h_beta": [float(bCa[0]), float(bCa[1])]}
    # D
    def comb(ccol, bcpar):
        X = np.column_stack([M.A - a_ha, M.B - bB[0], M[ccol] - bcpar[0]])
        w = ols(X[tu], M.act[tu].to_numpy())
        return w[0] + X @ w[1:], w
    M["D"], wD = comb("C", bC)
    M["D_actual"], wDa = comb("C_actual", bCa)
    res["D"] = {"h": float(wD[0]), "wA": float(wD[1]), "wB": float(wD[2]), "wC": float(wD[3]), "actual_lineup_weights": list(map(float, wDa))}

    return M, res, {"a_ha": a_ha, "bB": bB, "bC": bC, "tu": tu}


def main(clean, outp):
    M, res, ex = predictions(clean)
    tu = ex["tu"]
    sd = {k: float(np.sqrt(np.mean((M.act[tu] - M[k][tu]) ** 2))) for k in ["B", "C", "D", "C_actual", "D_actual"]}
    sd["A"] = GAME_SD
    res["sd"] = sd
    res["tune_mse"] = {k: float(np.mean((M.act[tu] - M[k][tu]) ** 2)) for k in ["A", "B", "C", "D", "C_actual", "D_actual"]}

    if "--mechanics" in sys.argv:          # plumbing check on tuning seasons only; test seasons untouched
        print(json.dumps({k: res[k] for k in ["B", "C", "D", "sd", "tune_mse"]}, indent=1, default=float))
        print("NaN preds:", {k: int(M[k].isna().sum()) for k in ["A", "B", "C", "D"]})
        return
    X = M[M.season.isin(TEST)].reset_index(drop=True)
    res["n_test"] = len(X)
    se = {k: (X.act - X[k]) ** 2 for k in ["A", "B", "C", "D", "C_actual", "D_actual"]}
    res["mse"] = {k: float(v.mean()) for k, v in se.items()}
    res["logloss"] = {k: logloss(X[k].to_numpy(), X.act.to_numpy(), sd[k]) for k in se}
    rng = np.random.default_rng(11)
    seasons = np.array(TEST)
    idx = {y: np.where(X.season == y)[0] for y in TEST}
    draws = [np.concatenate([idx[y] for y in rng.choice(seasons, len(seasons))]) for _ in range(2000)]
    early = X["round"] <= 8
    gates, detail = {}, {}
    for k in ["B", "C", "D", "C_actual", "D_actual"]:
        d = (se["A"] - se[k]).to_numpy()
        bs = np.array([d[i].mean() for i in draws])
        bys = {int(y): float(d[idx[y]].mean()) for y in TEST}
        slope = float(np.polyfit(X[k], X.act, 1)[0])
        g = {"1_mse_lower_98.33_above_0": float(np.percentile(bs, 100 / 60)) > 0, "2_six_of_eight": sum(v > 0 for v in bys.values()) >= 6,
             "3_early_and_late": d[early].mean() > 0 and d[~early].mean() > 0, "4_logloss": res["logloss"][k] < res["logloss"]["A"],
             "5_calib": 0.8 <= slope <= 1.2, "6_without_2020": d[X.season != 2020].mean() > 0}
        detail[k] = {"gain": float(d.mean()), "gain_pct": float(d.mean() / se["A"].mean() * 100), "lower_98.33": float(np.percentile(bs, 100 / 60)),
                     "by_season": bys, "early": float(d[early].mean()), "late": float(d[~early].mean()), "finals": float(d[X.phase == "finals"].mean()),
                     "slope": slope, "without_2020": float(d[X.season != 2020].mean()), "gates": g, "all_pass": all(g.values()) if k in "BCD" else None}
    res["vs_A"] = detail
    blocks = pd.cut(X["round"], [-1, 1, 5, 10, 15, 20, 40], labels=["0-1", "2-5", "6-10", "11-15", "16-20", "21+"])
    res["mse_by_round_block"] = {k: {str(b): float(se[k][blocks == b].mean()) for b in blocks.cat.categories} for k in se}
    json.dump(res, open(outp, "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ["n_test", "mse", "logloss"]}, indent=1))
    for k, v in detail.items():
        print(k, {x: (round(y, 3) if isinstance(y, float) else y) for x, y in v.items() if x != "by_season"}, {a: round(b, 1) for a, b in v["by_season"].items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "afl_three_way_results.json")
