"""Research: does roster continuity change how much the NHL preseason prior should be trusted? (17 Oct 2026)
continuity = share of last season's skater ice time belonging to players in the team's first five games of the season. Walk-forward test of
goal difference per game on prior and prior x continuity, using the table written by research/nhl_player_strength_test.py (PS_OUT=<csv>).
Result 2019-2025 (281 team-seasons): RMSE 0.4922 -> 0.4918 (better 2/7), interaction -1.24 (se 0.83). No effect; not adopted.
Usage: python research/nhl_continuity_test.py <ps.csv>"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L = os.path.join(ROOT, "data", "research", "nhl_lineups")
D = pd.read_csv(sys.argv[1])
rows = []
for y in sorted(D.season.unique()):
    p, c = os.path.join(L, f"skaters_{y - 1}.csv.gz"), os.path.join(L, f"skaters_{y}.csv.gz")
    if not (os.path.exists(p) and os.path.exists(c)):
        continue
    P, C = pd.read_csv(p), pd.read_csv(c)
    for t in D[D.season == y].team:
        pt, ct = P[P.team == t], C[C.team == t]
        if not len(pt) or not len(ct):
            continue
        first = sorted(ct.game_id.unique())[:5]
        on = set(ct[ct.game_id.isin(first)].player_id)
        w = pt.groupby("player_id").toi.sum()
        rows.append(dict(season=y, team=t, cont=w[w.index.isin(on)].sum() / w.sum()))
X = D.merge(pd.DataFrame(rows), on=["season", "team"])
X["cont"] -= X.groupby("season").cont.transform("mean")
X["pc"] = X.prior * X.cont
out = []
for y in sorted(X.season.unique()):
    tr, te = X[X.season < y], X[X.season == y]
    if tr.season.nunique() < 2:
        continue
    def fit(cols):
        b = np.linalg.lstsq(np.c_[np.ones(len(tr)), *[tr[c] for c in cols]], tr.gd, rcond=None)[0]
        return float(np.sqrt(np.mean((te.gd - np.c_[np.ones(len(te)), *[te[c] for c in cols]] @ b) ** 2)))
    out.append((y, fit(["prior"]), fit(["prior", "pc"])))
O = pd.DataFrame(out, columns=["season", "rmse_prior", "rmse_cont"])
print(O.round(4).to_string(index=False))
print("mean RMSE prior %.4f with continuity %.4f, better %d/%d" % (O.rmse_prior.mean(), O.rmse_cont.mean(), (O.rmse_cont < O.rmse_prior).sum(), len(O)))
