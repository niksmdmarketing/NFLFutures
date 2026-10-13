"""Future-information check for the NHL replay: scramble every game result (goals, result) from a cut date on in season y; probabilities at
checkpoints on or before the cut must be identical. Usage: python research/replay_leak_check_nhl.py <nhl/data dir> [year] [days]"""
import os, sys
import numpy as np, pandas as pd
os.environ.setdefault("BT_SIMS", "300")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
data = sys.argv[1]
sys.argv = [sys.argv[0], data] + sys.argv[2:]
import replay_nhl as R
M, nhl = R.M, R.nhl
y = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
days = int(sys.argv[3]) if len(sys.argv) > 3 else 70
cur = nhl.start_year()
TT, GG = {}, {}
for yy in range(nhl.FIRST, cur + 1):
    t = M.read_team(yy)
    if not t.empty: TT[yy] = t
    gg = M.read_games(yy)
    if not gg.empty: GG[yy] = gg
done = [z for z in TT if z < cur and z in GG and GG[z].groupby("team").size().min() >= 40]
fit_years = [z for z in done if z - 1 in TT]
a = R.run_season(TT, GG, fit_years, done, y)
g = GG[y].copy(); d = pd.to_datetime(g.date)
cutdate = d.min() + pd.Timedelta(days=days)
m = (d >= cutdate).values
rng = np.random.default_rng(0)
perm = rng.permutation(np.where(m)[0])
cols = [c for c in ("goalsFor", "goalsAgainst", "res") if c in g.columns]
G2 = g.copy()
for c in cols:
    vals = g[c].values.copy(); vals[np.where(m)[0]] = g[c].values[perm]; G2[c] = vals
GG2 = dict(GG); GG2[y] = G2
b = R.run_season(TT, GG2, fit_years, done, y)
pc = [c for c in a.columns if c.startswith("p_")]
k = (pd.to_datetime(a.date) <= cutdate).values
print(y, "checkpoints up to", cutdate.date(), "rows", int(k.sum()), "max abs diff", float(np.abs(a[k][pc].values - b[k][pc].values).max()))
print("later checkpoints differ (sanity):", float(np.abs(a[~k][pc].values - b[~k][pc].values).max()) > 0)
