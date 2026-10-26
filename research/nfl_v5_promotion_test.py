"""v4-core vs v5-core futures replay (research/NFL_V5_PROMOTION_RULE.md). Research only; nothing deployed.
Usage: python research/nfl_v5_promotion_test.py
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
import nfl_engine as E  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, DIVS, games, load_pbp  # noqa: E402
from nfl_futures_diagnosis import WF, V4, V5, eng_weights  # noqa: E402

SEASONS = range(2013, 2026)
CHECKS = (0, 4, 9, 13, 16)
N = 5000
SEEDS = {"A": lambda y, w: 1000 * y + w, "B": lambda y, w: 7000 * y + w}
MK = ("div", "playoff", "seed1", "conf", "sb")
PRIMARY = [(m, w) for m in ("div", "playoff") for w in (4, 9, 13)]
SECONDARY = [(m, w) for m in ("div", "playoff") for w in (0, 16)] + [(m, w) for m in ("seed1", "conf", "sb") for w in CHECKS]
DIV_OF = {t: d for d, ts in DIVS.items() for t in ts}
OUT = os.path.join(ROOT, "research")


def rows_for(g):
    rows = []
    for y in SEASONS:
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        out = B.outcomes(g, y)
        ew = eng_weights(y)
        for w in CHECKS:
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > w), "result"] = np.nan
            cur = cur_all[(cur_all.week <= w) & (cur_all.season_type == "REG")] if w else cur_all.iloc[0:0]
            ratings.P["coef"] = WF[str(y)]["coef"]
            b4, _ = ratings.base_ratings(cur, pri, gg, y)
            _, XT = E.team_features(cur, pri, gg, y, w + 1, 4.0, 0, False)
            b5 = XT @ ew
            greg = gg[(gg.season == y) & (gg.game_type == "REG")]
            for arm, base, P in (("v4", b4, V4), ("v5", b5, V5)):
                R = P["scale"] * (base - base.mean())
                for sset, fn in SEEDS.items():
                    res = simulate.simulate(greg, R, N, P["tau"], P["sigma"], P["hfa"], seed=fn(y, w), hfa_post=P["hfa_post"],
                                            n_seeds=7 if y >= 2020 else 6)
                    for i, t in enumerate(TEAMS):
                        rows.append(dict(season=y, week=w, arm=arm, seedset=sset, team=t, **{"p_" + k: float(res[k][i]) for k in MK},
                                         **{"y_" + k: float(out[k][i]) for k in MK}))
            print(y, w, flush=True)
    return pd.DataFrame(rows)


def bll(p, y):
    p = np.clip(p, .001, .999)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def slope(p, y):
    p = np.clip(p, .001, .999); x = np.log(p / (1 - p))
    f = lambda t: np.sum(np.logaddexp(0, t[0] + t[1] * x) - y * (t[0] + t[1] * x))
    return minimize(f, [0, 1], method="Nelder-Mead").x


def evaluate(df):
    seasons = list(SEASONS)
    L = {}
    for (s, w, arm), z in df.groupby(["season", "week", "arm"]):
        for m in MK:
            L[(s, w, arm, m)] = float(bll(z["p_" + m].to_numpy(), z["y_" + m].to_numpy()).mean())
    gain = lambda cells, ss=seasons: np.array([np.mean([L[(s, w, "v4", m)] - L[(s, w, "v5", m)] for m, w in cells]) for s in ss])
    g = gain(PRIMARY)
    rng = np.random.default_rng(20261026)
    boot = g[rng.integers(0, len(g), (10000, len(g)))].mean(1)
    gd = gain([c for c in PRIMARY if c[0] == "div"]); gp = gain([c for c in PRIMARY if c[0] == "playoff"])
    recent = np.array(seasons) >= 2020
    sec = {f"{m}_w{w}": float(np.mean([L[(s, w, "v5", m)] - L[(s, w, "v4", m)] for s in seasons])) for m, w in SECONDARY}
    cat = {}
    for w in CHECKS:
        for arm in ("v4", "v5"):
            ll = []
            for s in seasons:
                z = df[(df.season == s) & (df.week == w) & (df.arm == arm)].assign(d=lambda x: x.team.map(DIV_OF))
                for _, G in z.groupby("d"):
                    p = np.clip(G.p_div.to_numpy(), .002, 1); p = p / p.sum()
                    if (G.y_div == 1).sum() == 1:
                        ll.append(-np.log(p[G.y_div.to_numpy() == 1][0]))
            cat[f"w{w}_{arm}"] = float(np.mean(ll))
    cal = {}
    for m, w in PRIMARY:
        for arm in ("v4", "v5"):
            z = df[(df.week == w) & (df.arm == arm)]
            a, b = slope(z["p_" + m].to_numpy(), z["y_" + m].to_numpy())
            cal[f"{m}_w{w}_{arm}"] = dict(intercept=float(a), slope=float(b))
    gates = {"1_lower90_and_8of13": bool(np.quantile(boot, .10) > 0 and (g > 0).sum() >= 8),
             "2_division_and_playoff_positive": bool(gd.mean() > 0 and gp.mean() > 0),
             "3_positive_2020_25": bool(g[recent].mean() > 0),
             "4_secondary_not_worse_0.003": bool(all(v <= .003 for v in sec.values()))}
    return dict(primary_gain=float(g.mean()), lower90=float(np.quantile(boot, .10)), seasons_better=int((g > 0).sum()),
                by_season={str(s): float(v) for s, v in zip(seasons, g)}, division_gain=float(gd.mean()), playoff_gain=float(gp.mean()),
                gain_2020_25=float(g[recent].mean()), gain_2013_19=float(g[~recent].mean()),
                leave_one_out={str(s): float(np.delete(g, i).mean()) for i, s in enumerate(seasons)},
                secondary_v5_minus_v4=sec, division_categorical=cat, calibration=cal, gates=gates)


def main():
    started = datetime.now(timezone.utc).isoformat()
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    df = rows_for(g)
    df.to_csv(os.path.join(OUT, "nfl_v5_promotion_rows.csv.gz"), index=False)
    res = {s: evaluate(df[df.seedset == s]) for s in SEEDS}
    avg = df.groupby(["season", "week", "arm", "team"], as_index=False).mean(numeric_only=True)
    res["average"] = evaluate(avg)
    agree = all(res["A"]["gates"][k] == res["B"]["gates"][k] for k in res["A"]["gates"])
    verdict = "inconclusive" if not agree else ("historical pass" if all(res["average"]["gates"].values()) else "historical fail")
    # reconciliation with the existing 3,000-simulation corrected rows (direction only)
    old = pd.read_csv(os.path.join(OUT, "nfl_futures_diagnosis_rows_format_fix.csv"))
    old["week"] = old.week.astype(str)
    rec = {}
    for w in ("4", "8", "12"):
        for m in ("div", "playoff"):
            a = old[(old.week == w) & (old.model == "v4wf")]; b = old[(old.week == w) & (old.model == "v5like")]
            rec[f"{m}_w{w}"] = float(bll(a["p_" + m].to_numpy(), a["y_" + m].to_numpy()).mean() - bll(b["p_" + m].to_numpy(), b["y_" + m].to_numpy()).mean())
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    out = dict(rule="research/NFL_V5_PROMOTION_RULE.md", started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
               sims_per_seedset=N, seed_sets_agree=agree, verdict=verdict, results=res, reconciliation_3000_sims_gain_v4_minus_v5=rec,
               code_sha256=sha(__file__), rule_sha256=sha(os.path.join(OUT, "NFL_V5_PROMOTION_RULE.md")))
    open(os.path.join(OUT, "nfl_v5_promotion_results.json"), "w").write(json.dumps(out, indent=2))
    print(json.dumps({"verdict": verdict, "agree": agree, **{s: {k: res[s][k] for k in ("primary_gain", "lower90", "seasons_better", "division_gain",
                      "playoff_gain", "gain_2020_25", "gates")} for s in res}, "reconciliation": rec}, indent=2))


if __name__ == "__main__":
    main()
