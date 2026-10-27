"""Retrospective v5-core at the 2026 week-4 checkpoint (research/NFL_FUTURES_PAPER_BET_RULE.md, amendment of 27 Oct 2026).
Built as the v5 arm of research/nfl_v5_promotion_test.py: engine ratings with walk-forward weights, 10,000 simulations."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nfl_engine as E  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, games, load_pbp  # noqa: E402
from nfl_futures_diagnosis import V5, eng_weights  # noqa: E402

Y, W = 2026, 4
g = games()
for c in ("home_team", "away_team"):
    g[c] = g[c].replace(FIX)
cur_all, pri = load_pbp(Y), load_pbp(Y - 1)
gg = g.copy()
gg.loc[(gg.season == Y) & (gg.game_type == "REG") & (gg.week > W), "result"] = np.nan
cur = cur_all[(cur_all.week <= W) & (cur_all.season_type == "REG")]
_, XT = E.team_features(cur, pri, gg, Y, W + 1, 4.0, 0, False)
b5 = XT @ eng_weights(Y)
R = V5["scale"] * (b5 - b5.mean())
greg = gg[(gg.season == Y) & (gg.game_type == "REG")]
res = [simulate.simulate(greg, R, 5000, V5["tau"], V5["sigma"], V5["hfa"], seed=s, hfa_post=V5["hfa_post"]) for s in (1000 * Y + W, 7000 * Y + W)]
rows = [dict(season=Y, week=W, model="v5-core (retrospective)", team=t, **{k: float(np.mean([r[k][i] for r in res])) for k in ("div", "playoff", "seed1", "conf", "sb")})
        for i, t in enumerate(TEAMS)]
pd.DataFrame(rows).to_csv(os.path.join(ROOT, "research", "nfl_futures_2026_w4_retrospective_v5.csv"), index=False)
print(pd.DataFrame(rows)[["team", "div", "playoff"]].round(3).to_string())
