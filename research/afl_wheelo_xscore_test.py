"""AFL Wheelo xScore test per research/AFL_WHEELO_XSCORE_RULE.md (+ Amendment 1). Raw Wheelo files are read from a local directory and never committed.
Usage: python afl_wheelo_xscore_test.py <match_stats_dir> [--out results.json]"""
import glob, json, sys
import numpy as np, pandas as pd
from math import erf, sqrt

def _frame(block):
    b = block[0]
    return pd.DataFrame(b) if all(isinstance(v, list) for v in b.values()) else pd.DataFrame([b])

def load(d):
    rows = []
    for p in sorted(glob.glob(d + "/*.json")):
        x = json.load(open(p))
        if len(p.split("/")[-1]) != 11 or "TeamData" not in x or not x.get("Matches"): continue
        s = x["Summary"][0]; td = _frame(x["TeamData"]); m = _frame(x["Matches"])     # one-match files (grand finals) hold scalars, not lists
        has = "xScore" in td
        ix = td.set_index(["MatchId", "Team"])
        for r in m.itertuples():
            h, a = ix.loc[(r.MatchId, r.HomeTeam)], ix.loc[(r.MatchId, r.AwayTeam)]
            rows.append((int(s["Season"]), int(s["RoundNumber"]), r.HomeTeam, r.AwayTeam, pd.to_numeric(h.Score, errors="coerce"), pd.to_numeric(a.Score, errors="coerce"),
                         pd.to_numeric(h.xScore, errors="coerce") if has else np.nan, pd.to_numeric(a.xScore, errors="coerce") if has else np.nan))
    df = pd.DataFrame(rows, columns="season round home away sh sa xh xa".split())
    n0 = len(df); df = df[df.sh.notna() & df.sa.notna()].reset_index(drop=True)
    print("matches", n0, "dropped without score", n0 - len(df), "| 2021+ missing xScore:", int(df[df.season >= 2021].xh.isna().sum()))
    bad = df[(df.season >= 2021) & df.xh.isna()]
    print(bad[["season", "round", "home", "away"]].to_string())
    return df.drop(bad.index).reset_index(drop=True)      # games with no xScore are excluded from every model so all are scored on identical games

def fit(g, target, lam, prior):
    """ridge margin ratings on games g (home +1 / away -1 + home-advantage col), shrinking toward prior dict."""
    teams = sorted(set(g.home) | set(g.away) | set(prior))
    ix = {t: i for i, t in enumerate(teams)}
    X = np.zeros((len(g), len(teams) + 1)); X[:, -1] = 1
    for k, (h, a) in enumerate(zip(g.home, g.away)): X[k, ix[h]] = 1; X[k, ix[a]] = -1
    p = np.array([prior.get(t, 0.0) for t in teams] + [0.0])
    P = np.eye(len(teams) + 1) * lam; P[-1, -1] = 1e-6
    b = np.linalg.solve(X.T @ X + P, X.T @ target + P @ p)
    return {t: b[i] for t, i in ix.items()}, b[-1]

def run(df, col, lam, c, scale=1.0, wa=None):
    """sequentially predict every game round 2+; returns frame with pred margin. col: 'A','X','M'."""
    def tgt(g):
        a = (g.sh - g.sa).to_numpy(); x = (g.xh - g.xa).to_numpy() * scale
        return a if col == "A" else x if col == "X" else 0.5 * a + 0.5 * x
    out, prior_end = [], {}
    for yr in sorted(df.season.unique()):
        s = df[df.season == yr]
        if col != "A" and s.xh.isna().any(): prior_end = {}; continue
        prior = {t: c * v for t, v in prior_end.items()}
        for r in sorted(s["round"].unique()):
            past = s[s["round"] < r]
            if r >= 2 and len(past):
                rt, ha = fit(past, tgt(past), lam, prior)
                now = s[s["round"] == r]
                pm = [rt.get(h, c * prior_end.get(h, 0)) - rt.get(a, c * prior_end.get(a, 0)) + ha for h, a in zip(now.home, now.away)]
                out.append(pd.DataFrame({"season": yr, "round": r, "pred": pm, "act": (now.sh - now.sa).to_numpy()}))
        rt, _ = fit(s, tgt(s), lam, prior); prior_end = rt
    return pd.concat(out, ignore_index=True)

def phi(z): return 0.5 * (1 + erf(z / sqrt(2)))
def logloss(pred, act, sd):
    p = np.clip([phi(m / sd) for m in pred], 1e-4, 1 - 1e-4); y = (act > 0).astype(float); ok = act != 0
    return float(-np.mean(y[ok] * np.log(p[ok]) + (1 - y[ok]) * np.log(1 - p[ok])))

def main(d, outp):
    df = load(d); res = {}
    tune = df[(df.season >= 2013) & (df.season <= 2018)]
    grid = {}
    for lam in (2, 4, 8, 16, 32):
        for c in (0.4, 0.5, 0.6, 0.7, 0.8):
            r = run(df[(df.season >= 2012) & (df.season <= 2018)], "A", lam, c); r = r[r.season >= 2013]
            grid[(lam, c)] = float(np.mean((r.act - r.pred) ** 2))
    (lam, c) = min(grid, key=grid.get); res["lam"], res["c"], res["tune_mse_A"] = lam, c, grid[(lam, c)]
    t2 = df[(df.season >= 2021) & (df.season <= 2022)]
    xm = (t2.xh - t2.xa).to_numpy(); am = (t2.sh - t2.sa).to_numpy()
    s = float((xm @ am) / (xm @ xm)); res["scale_s"] = s
    sub = df[df.season >= 2020]                       # 2020 is only used if needed as A prior; X/M need 2021+
    models = {k: run(df[df.season >= 2019] if k == "A" else df[df.season >= 2021], k, lam, c, s) for k in "AXM"}
    # sd per model from 2021-2022 residuals (A from same games)
    sd = {k: float(np.sqrt(np.mean((m[m.season.isin([2021, 2022])].act - m[m.season.isin([2021, 2022])].pred) ** 2))) for k, m in models.items()}
    res["sd"] = sd
    T = {k: m[m.season >= 2023].reset_index(drop=True) for k, m in models.items()}
    assert all(len(T[k]) == len(T["A"]) for k in T) and (T["A"].act.values == T["M"].act.values).all()
    se = {k: (T[k].act - T[k].pred) ** 2 for k in T}
    res["n_games"] = len(T["A"]); res["mse"] = {k: float(se[k].mean()) for k in se}
    res["logloss"] = {k: logloss(T[k].pred.to_numpy(), T[k].act.to_numpy(), sd[k]) for k in T}
    diff = se["A"] - se["M"]                        # positive = M better
    rng = np.random.default_rng(7); rounds = T["A"].groupby(["season", "round"]).indices; keys = list(rounds)
    bs = []
    for _ in range(2000):
        pick = rng.integers(0, len(keys), len(keys)); idx = np.concatenate([rounds[keys[i]] for i in pick]); bs.append(diff.values[idx].mean())
    res["gain_M_vs_A"] = float(diff.mean()); res["gain_ci90"] = [float(np.percentile(bs, 5)), float(np.percentile(bs, 95))]
    res["gain_X_vs_A"] = float((se["A"] - se["X"]).mean())
    res["by_season"] = {int(y): float(diff[T["A"].season == y].mean()) for y in sorted(T["A"].season.unique())}
    early = T["A"]["round"] <= 8
    res["gain_early"], res["gain_late"] = float(diff[early].mean()), float(diff[~early].mean())
    m = T["M"]; slope = float(np.polyfit(m.pred, m.act, 1)[0]); res["calib_slope_M"] = slope
    g = {"1_mse_ci_above_0": res["gain_ci90"][0] > 0, "2_seasons_3of4": sum(v > 0 for v in res["by_season"].values()) >= 3,
         "3_early_and_late": res["gain_early"] > 0 and res["gain_late"] > 0, "4_logloss": res["logloss"]["M"] < res["logloss"]["A"],
         "5_calib_0.8_1.2": 0.8 <= slope <= 1.2}
    res["gates"] = g; res["all_pass"] = all(g.values())
    json.dump(res, open(outp, "w"), indent=1); print(json.dumps(res, indent=1))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "afl_wheelo_xscore_results.json")
