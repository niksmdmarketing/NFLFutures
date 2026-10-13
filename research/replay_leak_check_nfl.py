"""Future-results check for the NFL replay: in season y scramble, for every week after C, the play-by-play numbers and the game scores/results;
probabilities at checkpoints <= C must be identical. Usage: python research/replay_leak_check_nfl.py [year] [C]"""
import os, sys
import numpy as np, pandas as pd
os.environ.setdefault("BT_SIMS", "500")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_nfl as R
from common import FIX
y = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
C = int(sys.argv[2]) if len(sys.argv) > 2 else 8
g = R.games()
for c in ("home_team", "away_team"):
    g[c] = g[c].replace(FIX)
a = R.run_season(g, y)
rng = np.random.default_rng(0)
# games: scramble results and scores for weeks after C (regular season and playoffs) in season y
g2 = g.copy()
late = ((g2.season == y) & ((g2.week > C) | (g2.game_type != "REG"))).values
idx = np.where(late)[0]
for c in [c for c in g2.columns if c in ("result", "home_score", "away_score", "total", "overtime") or "score" in c]:
    v = g2[c].values.copy(); v[idx] = v[rng.permutation(idx)]; g2[c] = v
orig = R.load_pbp
def patched(season):
    d = orig(season).copy()
    if season == y:
        late_p = (d.week > C).values
        ii = np.where(late_p)[0]
        for c in d.columns:
            if pd.api.types.is_numeric_dtype(d[c]) and c not in ("week", "season"):
                v = d[c].values.copy(); v[ii] = v[rng.permutation(ii)]; d[c] = v
    return d
R.load_pbp = patched
b = R.run_season(g2, y)
pc = [c for c in a.columns if c.startswith("p_")]
k = (a.week <= C).values
print(y, "checkpoints <=", C, "rows", int(k.sum()), "max abs diff", float(np.abs(a[k][pc].values - b[k][pc].values).max()))
print("later checkpoints differ (sanity):", float(np.abs(a[~k][pc].values - b[~k][pc].values).max()) > 0)
