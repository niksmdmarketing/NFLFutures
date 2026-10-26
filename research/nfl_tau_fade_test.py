"""Pre-registered uncertainty-schedule test: research/NFL_TAU_FADE_RULE.md. Research only; no live change.
Ratings exactly as the v4wf arm of research/nfl_futures_diagnosis.py (corrected format). Usage: python research/nfl_tau_fade_test.py
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nfl_backtest as B  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, games, load_pbp  # noqa: E402
from nfl_futures_diagnosis import WF, V4  # noqa: E402

N = 5000
SEEDS = {"A": 7, "B": 20261026}
CHECK = [4, 8, 12, 16]
MARKETS = ["div", "playoff", "seed1", "conf", "title"]
PRIMARY = [(m, w) for m in ("div", "playoff") for w in (4, 8, 12)]
NONREG = [(m, w) for m in ("seed1", "conf", "title") for w in (4, 8, 12, 16)] + [("div", 16), ("playoff", 16)]
OUT = os.path.join(ROOT, "research", "nfl_tau_fade_rows.csv")


def schedule(n, tau0=5.0, sig0=11.37):
    tau = tau0 / np.sqrt(1 + n * tau0 ** 2 / sig0 ** 2)
    return float(tau), float(np.sqrt(sig0 ** 2 + 2 * (tau0 ** 2 - tau ** 2)))


def run_season(y, g):
    cur_all, pri = load_pbp(y), load_pbp(y - 1)
    out = B.outcomes(g, y)
    rows = []
    for wk in CHECK:
        gg = g.copy()
        gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > wk), "result"] = np.nan
        cur = cur_all[(cur_all.week <= wk) & (cur_all.season_type == "REG")]
        ratings.P["coef"] = WF[str(y)]["coef"]
        b4, _ = ratings.base_ratings(cur, pri, gg, y)
        greg = gg[(gg.season == y) & (gg.game_type == "REG")]
        R = V4["scale"] * (b4 - b4.mean())
        done = greg[greg.result.notna()]
        n = 2 * len(done) / 32
        tau_n, sig_n = schedule(n)
        for arm, (tau, sig) in (("v4", (V4["tau"], V4["sigma"])), ("schedule", (tau_n, sig_n))):
            for sname, seed in SEEDS.items():
                res = simulate.simulate(greg, R, N, tau, sig, V4["hfa"], seed=seed, hfa_post=V4["hfa_post"], n_seeds=7 if y >= 2020 else 6)
                for i, t in enumerate(TEAMS):
                    rows.append(dict(season=y, week=wk, arm=arm, seedset=sname, team=t, n_games=n, tau=tau, sigma=sig,
                                     **{"p_" + m: float(res["sb" if m == "title" else m][i]) for m in MARKETS},
                                     **{"y_" + m: float(out["sb" if m == "title" else m][i]) for m in MARKETS}))
        print(y, wk, round(n, 2), round(tau_n, 3), round(sig_n, 3), flush=True)
    return rows


def ll(p, y):
    p = np.clip(p, .001, .999)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def slope(p, y):
    p = np.clip(p, .001, .999); x = np.log(p / (1 - p))
    f = lambda t: np.sum(np.logaddexp(0, t[0] + t[1] * x) - y * (t[0] + t[1] * x))
    return minimize(f, [0, 1], method="Nelder-Mead").x


def evaluate(df):
    cell = {}
    for (season, week, arm), z in df.groupby(["season", "week", "arm"]):
        for m in MARKETS:
            cell[(season, week, arm, m)] = float(ll(z["p_" + m].to_numpy(), z["y_" + m].to_numpy()).mean())
    seasons = sorted(df.season.unique())
    def gains(cells):
        return np.array([np.mean([cell[(s, w, "v4", m)] - cell[(s, w, "schedule", m)] for m, w in cells]) for s in seasons])
    g = gains(PRIMARY)
    rng = np.random.default_rng(20261026)
    boot = g[rng.integers(0, len(g), (10000, len(g)))].mean(1)
    gd, gp = gains([c for c in PRIMARY if c[0] == "div"]), gains([c for c in PRIMARY if c[0] == "playoff"])
    sl = {}
    for m in MARKETS:
        for w in CHECK:
            for arm in ("v4", "schedule"):
                z = df[(df.week == w) & (df.arm == arm)]
                a, b = slope(z["p_" + m].to_numpy(), z["y_" + m].to_numpy())
                sl[f"{m}_w{w}_{arm}"] = dict(intercept=float(a), slope=float(b))
    nonreg = {f"{m}_w{w}": float(np.mean([cell[(s, w, "schedule", m)] - cell[(s, w, "v4", m)] for s in seasons])) for m, w in NONREG}
    recent = np.array(seasons) >= 2020
    gates = {
        "1_primary_lower90_and_8of13": bool(np.quantile(boot, .10) > 0 and (g > 0).sum() >= 8),
        "2_division_and_playoff_each_positive": bool(gd.mean() > 0 and gp.mean() > 0),
        "3_slopes_closer_to_1_none_below_0.85": bool(all(
            abs(sl[f"{m}_w{w}_schedule"]["slope"] - 1) < abs(sl[f"{m}_w{w}_v4"]["slope"] - 1) and sl[f"{m}_w{w}_schedule"]["slope"] >= .85
            for m in ("div", "playoff") for w in (4, 8))),
        "4_nonregression_0.002": bool(all(v <= .002 for v in nonreg.values())),
        "5_positive_2020_25": bool(g[recent].mean() > 0)}
    return dict(primary_gain=float(g.mean()), lower90=float(np.quantile(boot, .10)), seasons_better=int((g > 0).sum()),
                by_season={str(s): float(v) for s, v in zip(seasons, g)}, division_gain=float(gd.mean()), playoff_gain=float(gp.mean()),
                gain_2020_25=float(g[recent].mean()), gain_2013_19=float(g[~recent].mean()), nonregression_worse_by=nonreg,
                calibration=sl, gates=gates, passes=all(gates.values()))


def main():
    started = datetime.now(timezone.utc).isoformat()
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows = []
    for y in range(2013, 2026):
        rows += run_season(y, g)
        pd.DataFrame(rows).to_csv(OUT, index=False)
    df = pd.DataFrame(rows)
    res = {s: evaluate(df[df.seedset == s]) for s in SEEDS}
    avg = df.groupby(["season", "week", "arm", "team"], as_index=False).mean(numeric_only=True)
    res["average"] = evaluate(avg)
    agree = all(res["A"]["gates"][k] == res["B"]["gates"][k] for k in res["A"]["gates"])
    verdict = "inconclusive" if not agree else ("pass" if res["average"]["passes"] else "fail")
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    out = dict(rule="research/NFL_TAU_FADE_RULE.md", started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
               sims=N, seeds=SEEDS, seed_sets_agree=agree, verdict=verdict, results=res,
               code_sha256=sha(__file__), rule_sha256=sha(os.path.join(ROOT, "research", "NFL_TAU_FADE_RULE.md")))
    open(os.path.join(ROOT, "research", "nfl_tau_fade_results.json"), "w").write(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("verdict", "seed_sets_agree")} | {s: {k: res[s][k] for k in ("primary_gain", "lower90", "seasons_better",
          "division_gain", "playoff_gain", "gain_2020_25", "gates")} for s in res}, indent=2))


if __name__ == "__main__":
    main()
