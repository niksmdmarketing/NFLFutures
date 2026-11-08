"""LOSO refit of AFL constants (research/LOSO_REFIT_RULE.md). Usage: python loso_afl.py <afltables.parquet>"""
import sys, itertools, numpy as np, pandas as pd
from scipy.stats import norm
sys.path.insert(0, "pipeline")
import afl, afl_site as A
base = afl._load_frame(sys.argv[1], list(dict.fromkeys(afl.BASE_MATCH_COLS + afl.BASE_PLAYER_COLS))); base = base[base.Season.ge(2012)].copy()
_, tg = afl._matches_and_team_games(base)
hist = {}
for y in sorted({r["season"] for r in tg}):
    g = A.team_games({"team_games": [r for r in tg if r["season"] == y]}, y)
    if g is None or g.empty: continue
    x = g[g.season_type == "REG"]
    if len(x): hist[y] = x.copy()
ys = sorted(hist); PRI = [.3, .4, .5, .6, .7, .8, .9, 1.0]; HG = [4, 5, 6, 7, 8, 9]; SDS = [28, 30, 32, 34, 36]
def diffs(prior, hga, y):
    """per-game (diff, win) for home sides of season y with weekly refit; uses module HGA for srs and prediction."""
    A.HGA = float(hga)
    prev = hist[y - 1]; pr = {t: prior * v for t, v in A.srs(prev).items()}
    g = hist[y]; out = []
    g = g.assign(date=pd.to_datetime(g.date), rd=g["round"].astype(str))
    for w in sorted(g.rd.unique(), key=lambda r: g[g.rd == r].date.min()):
        done = g[g.date < g[g.rd == w].date.min()]
        R = A.srs(done, prior=pr) if len(done) else pr
        for r in g[(g.rd == w) & (g.ha == "H")].itertuples():
            out.append((R.get(r.team, 0.0) - R.get(r.opp, 0.0), float(r.win)))
    return np.array(out)
LL = lambda d, win, hga, sd: -np.mean(np.where(win == 1, np.log(np.clip(1 - norm.cdf(-(d + hga) / sd), 1e-6, 1)), np.log(np.clip(norm.cdf(-(d + hga) / sd), 1e-6, 1))))
cache = {(p, h, y): diffs(p, h, y) for p in PRI for h in HG for y in ys[1:]}
def ll(p, h, sd, y): D = cache[(p, h, y)]; return LL(D[:, 0], D[:, 1], h, sd)
grid = list(itertools.product(PRI, HG, SDS))
tab = pd.DataFrame([{"p": p, "h": h, "sd": sd, "y": y, "ll": ll(p, h, sd, y)} for p, h, sd in grid for y in ys[1:]])
live_p, live_h, live_sd = 0.65, 7.0, 32.0
A.HGA = 7.0
def live(y):
    D = diffs(live_p, live_h, y); return LL(D[:, 0], D[:, 1], live_h, live_sd)
rows = []
for y in ys[1:]:
    tr = tab[tab.y != y].groupby(["p", "h", "sd"]).ll.mean(); best = tr.idxmin()
    rows.append(dict(season=y, fit=best, held=float(tab[(tab.p == best[0]) & (tab.h == best[1]) & (tab.sd == best[2]) & (tab.y == y)].ll.iloc[0]), live=live(y)))
R = pd.DataFrame(rows); R["d"] = R.held - R.live
rng = np.random.default_rng(1); b = [rng.choice(R.d.values, len(R)).mean() for _ in range(4000)]
print(R.to_string(index=False))
f = np.array([list(x) for x in R.fit]); print("fold fits range prior", f[:, 0].min(), f[:, 0].max(), "hga", f[:, 1].min(), f[:, 1].max(), "sd", f[:, 2].min(), f[:, 2].max())
print("LOSO minus live held-out LL", round(R.d.mean(), 4), np.percentile(b, [5, 95]).round(4), "seasons better", int((R.d < 0).sum()), "of", len(R))
allm = tab.groupby(["p", "h", "sd"]).ll.mean(); print("in-sample best", allm.idxmin(), round(allm.min(), 4), "live-like", round(np.mean([live(y) for y in ys[1:]]), 4))
