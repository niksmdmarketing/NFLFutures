"""Are playoff games more predictable than the v4 simulation assumes? (research only; v4 unchanged)

For each season, ratings are rebuilt point-in-time exactly as in the futures replay: before each late regular-season week
(weeks 10+) from play-by-play up to the previous week, and after the regular season for the playoffs. The simulation's
single-game probability is Phi((scale*dR + hfa) / S) with S = sqrt(sigma^2 + 2 tau^2) (the sim draws team strength with tau).
We fit p = Phi(k * (scale*dR)/S + h * home) separately for late regular-season and playoff games, with season-cluster
bootstrap intervals. k > 1 means favourites win more often than the simulation assumes.
Usage: python research/nfl_playoff_calibration.py [first] [last]
"""
import os
import sys
import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402
from common import FIX, TEAMS, TIX, games, load_pbp  # noqa: E402

P = ratings.S["sim"]
SC, TAU, SIG, HFA = P.get("rating_scale", 1.0), P["tau"], P["sigma"], P["hfa"]
S_TOT = float(np.sqrt(SIG ** 2 + 2 * TAU ** 2))


def rate(cur, pri, gg, y):
    base, _ = ratings.base_ratings(cur, pri, gg, y)
    R = SC * base
    return R - R.mean()


def season_rows(g, y, first_week=10):
    cur_all, pri = load_pbp(y), load_pbp(y - 1)
    reg = g[(g.season == y) & (g.game_type == "REG")]
    last = int(reg.week.max())
    rows = []
    for w in range(first_week, last + 1):
        gg = g.copy()
        m = (gg.season == y) & (gg.game_type == "REG") & (gg.week >= w)
        gg.loc[m, "result"] = np.nan
        R = rate(cur_all[cur_all.week < w], pri, gg, y)
        for r in reg[reg.week == w].itertuples():
            if pd.isna(r.result) or r.result == 0:
                continue
            rows.append(dict(season=y, kind="reg", x=(R[TIX[r.home_team]] - R[TIX[r.away_team]]) / S_TOT, home=1.0, y=float(r.result > 0)))
    gg = g.copy()
    R = rate(cur_all[cur_all.week <= last], pri, gg[~((gg.season == y) & (gg.game_type != "REG"))], y)
    for r in g[(g.season == y) & (g.game_type != "REG")].itertuples():
        if pd.isna(r.result) or r.result == 0:
            continue
        neutral = r.game_type == "SB" or str(getattr(r, "location", "")) == "Neutral"
        rows.append(dict(season=y, kind="post", x=(R[TIX[r.home_team]] - R[TIX[r.away_team]]) / S_TOT, home=0.0 if neutral else 1.0, y=float(r.result > 0)))
    return rows


def fit(D):
    x, h, yy = D.x.values, D.home.values, D.y.values

    def nll(w):
        p = np.clip(norm.cdf(w[0] * x + w[1] * h), 1e-6, 1 - 1e-6)
        return -(yy * np.log(p) + (1 - yy) * np.log(1 - p)).sum()
    return minimize(nll, [1.0, HFA / S_TOT], method="Nelder-Mead").x


def boot(D, B=1000, seed=1):
    rng = np.random.default_rng(seed)
    ss = D.season.unique()
    ks = []
    for _ in range(B):
        pick = rng.choice(ss, len(ss))
        ks.append(fit(pd.concat([D[D.season == s] for s in pick]))[0])
    return np.percentile(ks, [5, 95])


if __name__ == "__main__":
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2011
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    rows = []
    for y in range(first, last + 1):
        rows += season_rows(g, y)
        print(y, flush=True)
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(ROOT, "model", "replay", "nfl_game_calibration_rows.csv"), index=False)
    out = {"seasons": f"{first}-{last}", "S_total": round(S_TOT, 2), "assumed_home_term": round(HFA / S_TOT, 3)}
    for kind in ("reg", "post"):
        for lab, sub in (("all", D), ("2011-21", D[D.season <= 2021]), ("2022-25", D[D.season >= 2022])):
            X = sub[sub.kind == kind]
            if X.empty:
                continue
            k, h = fit(X)
            lo, hi = boot(X, 400)
            out[f"{kind}_{lab}"] = {"games": int(len(X)), "k": round(float(k), 3), "k_90": [round(float(lo), 3), round(float(hi), 3)], "home_term": round(float(h), 3)}
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(ROOT, "model", "replay", "nfl_game_calibration.json"), "w"), indent=1)
