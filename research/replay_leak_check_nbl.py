"""Future-information check for the NBL replay: scramble every score on or after a cut date (and the finals) in season y; probabilities at
checkpoints on or before the cut date must be identical. Usage: python research/replay_leak_check_nbl.py [year] [days_after_start]"""
import json, os, sys
import numpy as np, pandas as pd
os.environ.setdefault("BT_SIMS", "300")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_nbl as R
N = R.N
y = int(sys.argv[1]) if len(sys.argv) > 1 else 2022
days = int(sys.argv[2]) if len(sys.argv) > 2 else 70
S = json.load(open(N.SRC))["seasons"]
ys = sorted(int(k) for k in S)
prev = None
for z in ys:
    if z == y - 1:
        x0, _, _ = N.season_games(S[str(z)]); prev = N.team_rows(x0[~x0.fin])
a, _ = R.run_season(S, y, prev)
orig = N.season_games
cutdate = pd.Timestamp(orig(S[str(y)])[0][lambda d: ~d.fin].date.min()) + pd.Timedelta(days=days)
def patched(season):
    x, a_, b_ = orig(season)
    x = x.copy()
    m = x.fin | (pd.to_datetime(x.date) >= cutdate)
    rng = np.random.default_rng(0)
    for c in ("hs", "as"):
        v = x.loc[m, c].values.copy(); rng.shuffle(v); x.loc[m, c] = v
    return x, a_, b_
N.season_games = patched
b, _ = R.run_season(S, y, prev)
pc = [c for c in a.columns if c.startswith("p_")]
k = pd.to_datetime(a.date) <= cutdate
print(y, "checkpoints up to", cutdate.date(), "rows", int(k.sum()), "max abs diff", float(np.abs(a[k][pc].values - b[k][pc].values).max()))
print("later checkpoints differ (sanity):", float(np.abs(a[~k][pc].values - b[~k][pc].values).max()) > 0)
