"""Future-information check for the ladder-sport replays: shuffle every result (margin, win, points) after round C and in the finals,
re-run the replay, and require the probabilities at checkpoints <= C to be identical. Usage: python research/replay_leak_check.py afl [year] [C]"""
import os, sys
import numpy as np, pandas as pd
os.environ.setdefault("BT_SIMS", "300")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_afl as R
y = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
C = int(sys.argv[3]) if len(sys.argv) > 3 else 10
G = R.season_frames()
a = R.run_season(G, y)
g = G[y].copy()
rnd = pd.to_numeric(g.rnd, errors="coerce")
m = (g.season_type == "FIN") | (rnd > C)
rng = np.random.default_rng(0)
for c in ("margin", "win", "points_for", "points_against"):
    v = g.loc[m, c].values.copy(); rng.shuffle(v); g.loc[m, c] = v
G2 = dict(G); G2[y] = g
b = R.run_season(G2, y)
pc = [c for c in a.columns if c.startswith("p_")]
x, z = a[a.week <= C], b[b.week <= C]
print(y, "checkpoints <=", C, "rows", len(x), "max abs diff", float(np.abs(x[pc].values - z[pc].values).max()))
print("later checkpoints differ (sanity):", float(np.abs(a[a.week > C][pc].values - b[b.week > C][pc].values).max()) > 0)
