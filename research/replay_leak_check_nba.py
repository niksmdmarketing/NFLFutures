"""Future-results check for the NBA replay: scramble scores, ratings inputs (ortg, poss) of every box-score row in season y on or after a cut date;
probabilities at checkpoints on or before the cut date must be identical. Usage: python research/replay_leak_check_nba.py [year] [days]"""
import os, sys
import numpy as np, pandas as pd
os.environ.setdefault("BT_SIMS", "200")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_nba as R
y = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
days = int(sys.argv[2]) if len(sys.argv) > 2 else 70
boxes = R.B.load_boxes(y)
a = R.run_season(boxes, y)
b0 = boxes.copy()
d = pd.to_datetime(b0.game_date)
inseason = pd.to_numeric(b0.season, errors="coerce") == y
reg = inseason & (pd.to_numeric(b0.season_type, errors="coerce") == 2)
cutdate = d[reg].min() + pd.Timedelta(days=days)
m = (inseason & (d >= cutdate)).values
rng = np.random.default_rng(0)
idx = np.where(m)[0]
for c in ("team_score", "opponent_team_score", "ortg", "poss", "drtg", "pace"):
    if c in b0.columns:
        v = pd.to_numeric(b0[c], errors="coerce").values.copy()
        v[idx] = v[rng.permutation(idx)]
        b0[c] = v
b = R.run_season(b0, y)
pc = [c for c in a.columns if c.startswith("p_") or c == "mean_wins"]
cuts = pd.to_datetime(a.date)
k = (cuts <= cutdate).values
print(y, "checkpoints up to", cutdate.date(), "rows", int(k.sum()), "max abs diff", float(np.abs(a[k][pc].values - b[k][pc].values).max()))
print("later checkpoints differ (sanity):", float(np.abs(a[~k][pc].values - b[~k][pc].values).max()) > 0)
