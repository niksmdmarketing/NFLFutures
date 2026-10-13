"""Weekly point-in-time replay of the frozen NFL v4 futures model (read-only: no model code or setting is changed).

Seasons 2022-2025 only: the rating weights were trained on 2010-2021, so earlier seasons are not out-of-sample. The tau/sigma spread was
tuned on the 2022-25 final win totals, so even these four are not fully unseen (the same caveat as pipeline/nfl_backtest.py).
At each checkpoint (before the season, then after every regular-season week through week 17) ratings are rebuilt from play-by-play up to that
week only, the real remaining schedule is simulated by simulate.simulate. Quarterback/injury layers are off (no weekly history).
Outputs model/replay/nfl_<season>.csv: season, week, date, gp_avg, team, p_div, p_playoff, p_seed1, p_conf (conference champion = Super Bowl
team), p_title, and 0/1 outcomes y_*. 'p_conf' is scored against y_finals.
Usage: python research/replay_nfl.py [first] [last]    (env BT_SIMS default 4000, BT_OUTDIR)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nfl_backtest as B  # noqa: E402
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, games, load_pbp  # noqa: E402

SIMS = int(os.environ.get("BT_SIMS", "4000"))
# Research-only overrides of the simulation layer (the frozen model files are not changed):
# BT_SCALE (rating_scale), BT_TAU, BT_SIGMA, BT_TAUFADE (share of tau removed by the end of the regular season).
OVR = {k: float(os.environ[e]) for k, e in (("rating_scale", "BT_SCALE"), ("tau", "BT_TAU"), ("sigma", "BT_SIGMA")) if os.environ.get(e)}
TAUFADE = float(os.environ.get("BT_TAUFADE", "0"))
HFA_POST = float(os.environ["BT_HFA_POST"]) if os.environ.get("BT_HFA_POST") else None
# BT_COEF=wf: rating weights re-trained walk-forward (research/nfl_walkforward_weights.py), so each season is out of sample.
WF = None
if os.environ.get("BT_COEF") == "wf":
    import json
    WF = json.load(open(os.path.join(ROOT, "model", "replay", "nfl_wf_coef.json")))["seasons"]
OUT = os.environ.get("BT_OUTDIR") or os.path.join(ROOT, "model", "replay")


def run_season(g, y):
    if WF is not None:
        ratings.P["coef"] = WF[str(y)]["coef"]
    cur_all, pri = load_pbp(y), load_pbp(y - 1)
    out = B.outcomes(g, y)
    P = {**ratings.S["sim"], **OVR}
    rows = []
    reg_all = g[(g.season == y) & (g.game_type == "REG")]
    last_week = int(reg_all.week.max())
    for w in range(0, min(last_week - 1, 18)):
        gg = g.copy()
        m = (gg.season == y) & (gg.game_type == "REG") & (gg.week > w)
        gg.loc[m, "result"] = np.nan
        cur = cur_all[cur_all.week <= w] if w else cur_all.iloc[0:0]
        base, _ = ratings.base_ratings(cur, pri, gg, y)
        greg = gg[(gg.season == y) & (gg.game_type == "REG")]
        played = greg[greg.result.notna()]
        gp = np.array([((played.home_team == t) | (played.away_team == t)).sum() for t in TEAMS], float)
        R = P.get("rating_scale", 1.0) * base
        R = R - R.mean()
        res = simulate.simulate(greg, R, SIMS, P["tau"] * (1 - TAUFADE * min(gp.mean() / 17.0, 1.0)), P["sigma"], P["hfa"], hfa_post=HFA_POST)
        date = str(pd.to_datetime(played.gameday).max().date()) if len(played) else str(pd.to_datetime(reg_all.gameday).min().date())
        for i, t in enumerate(TEAMS):
            rows.append(dict(season=y, week=w, date=date, gp_avg=round(float(gp.mean()), 1), team=t, p_div=float(res["div"][i]), p_playoff=float(res["playoff"][i]),
                             p_seed1=float(res["seed1"][i]), p_conf=float(res["conf"][i]), p_title=float(res["sb"][i]),
                             y_div=float(out["div"][i]), y_playoff=float(out["playoff"][i]), y_seed1=float(out["seed1"][i]),
                             y_finals=float(out["conf"][i]), y_title=float(out["sb"][i])))
        print(y, w, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    first = int(sys.argv[1]) if len(sys.argv) > 1 else B.SEASONS[0]
    last = int(sys.argv[2]) if len(sys.argv) > 2 else B.SEASONS[-1]
    os.makedirs(OUT, exist_ok=True)
    for y in range(first, last + 1):
        D = run_season(g, y)
        D.to_csv(os.path.join(OUT, f"nfl_{y}.csv"), index=False)
