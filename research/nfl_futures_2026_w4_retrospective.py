"""Retrospective v4 forecast at the 2026 week-4 checkpoint (research/NFL_FUTURES_PAPER_BET_RULE.md, amendment of 26 Oct 2026).
Same method as pipeline/nfl_backtest.py: ratings from 2026 play-by-play and results through week 4 only, QB/pressure layers off."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402
import simulate  # noqa: E402
from common import FIX, TEAMS, games, load_pbp  # noqa: E402

Y, W, N = 2026, 4, 4000
g = games()
for c in ("home_team", "away_team"):
    g[c] = g[c].replace(FIX)
cur_all, pri = load_pbp(Y), load_pbp(Y - 1)
gg = g.copy()
gg.loc[(gg.season == Y) & (gg.game_type == "REG") & (gg.week > W), "result"] = np.nan
cur = cur_all[cur_all.week <= W]
base, _ = ratings.base_ratings(cur, pri, gg, Y)
greg = gg[(gg.season == Y) & (gg.game_type == "REG")]
v4 = ratings.S["sim"]
R = v4.get("rating_scale", 1.0) * base
R = R - R.mean()
res = simulate.simulate(greg, R, N, v4["tau"], v4["sigma"], v4["hfa"])
rows = [dict(season=Y, week=W, model="v4 (retrospective)", team=t, **{k: float(res[k][i]) for k in ("div", "playoff", "seed1", "conf", "sb")})
        for i, t in enumerate(TEAMS)]
pd.DataFrame(rows).to_csv(os.path.join(ROOT, "research", "nfl_futures_2026_w4_retrospective.csv"), index=False)
print(pd.DataFrame(rows)[["team", "div", "playoff"]].round(3).to_string())
print("played through week", W, ":", int(greg.result.notna().sum()), "games; plays used:", len(cur))
