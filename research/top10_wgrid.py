"""V2 diagnostic (Amendment 9): p = p_market + w (p_model - p_market), w fitted on seasons <=2018, scored 2020+, by season window.
Usage: python top10_wgrid.py <sport> <edges dir>"""
import sys, os, numpy as np, pandas as pd
sport, ed = sys.argv[1:3]
J = pd.read_csv(os.path.join(ed, f"{sport}_proxy_edges.csv"))
LL = lambda p, y: -(y * np.log(np.clip(p, 1e-4, 1 - 1e-4)) + (1 - y) * np.log(1 - np.clip(p, 1e-4, 1 - 1e-4)))
grid = np.round(np.arange(-0.5, 1.51, 0.1), 2)
win = lambda X: {"first20": X[X.frac < .2], "middle": X[(X.frac >= .2) & (X.frac < .8)], "last20": X[X.frac >= .8]}
D, E = J[J.season <= 2018], J[J.season >= 2020]
for w_name in ("first20", "middle", "last20"):
    d, e = win(D)[w_name], win(E)[w_name]
    sc = [LL(d.p_market + w * (d.p_model - d.p_market), d.y).mean() for w in grid]; wb = grid[int(np.argmin(sc))]
    f = lambda X, w: LL(X.p_market + w * (X.p_model - X.p_market), X.y).mean()
    print(f"{sport} {w_name}: n disc {len(d)} eval {len(e)} | fitted w {wb:+.1f} | eval LL market-only {f(e,0):.4f} blend {f(e,wb):.4f} model-only {f(e,1):.4f} | blend-market {f(e,wb)-f(e,0):+.4f}")
