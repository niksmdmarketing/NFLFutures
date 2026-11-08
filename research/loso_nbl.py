"""LOSO refit of NBL constants (research/LOSO_REFIT_RULE.md, Amendment 1). Usage: python loso_nbl.py <nbl.xlsx>"""
import sys, itertools, numpy as np, pandas as pd
from scipy.stats import norm
sys.path.insert(0, "pipeline")
import nbl_site as S
O = pd.read_excel(sys.argv[1], header=1); O["date"] = pd.to_datetime(O.Date).dt.normalize()
O["season"] = np.where(O.date.dt.month >= 8, O.date.dt.year, O.date.dt.year - 1)
O = O[~O["Play Off Game?"].fillna("").eq("Y")].dropna(subset=["Home Score", "Away Score"]).sort_values("date")
rows = []
for se, dt_, ht, at, hs, as_ in zip(O.season, O.date, O["Home Team"], O["Away Team"], O["Home Score"], O["Away Score"]):
    rows.append(dict(season=se, date=dt_, team=ht, opp=at, ha="H", pf=hs, pa=as_)); rows.append(dict(season=se, date=dt_, team=at, opp=ht, ha="A", pf=as_, pa=hs))
G = pd.DataFrame(rows); G["margin"] = G.pf - G.pa; G["win"] = (G.margin > 0).astype(float)
ys = sorted(G.season.unique()); ys = [y for y in ys if y >= 2012]
PRI = [.2, .3, .4, .5, .6, .7, .8]; KS = [6, 10, 20, 30, 40]; HC = [2, 3, 4]; SDS = [12, 13, 14, 15, 16, 18]
def diffs(prior, k, hca, y):
    S.HCA = float(hca)
    prev = G[G.season == y - 1]; pr = {t: prior * v for t, v in S.srs(prev).items()}
    g = G[G.season == y]; out = []
    for d in sorted(g.date.unique()):
        done = g[g.date < d]
        R = S.srs(done, prior=pr, k=k) if len(done) else pr
        for r in g[(g.date == d) & (g.ha == "H")].itertuples():
            if r.margin != 0: out.append((R.get(r.team, 0.0) - R.get(r.opp, 0.0), r.win))
    return np.array(out)
def LL(d, win, hca, sd):
    p = np.clip(norm.cdf((d + hca) / sd), 1e-6, 1 - 1e-6); return -np.mean(win * np.log(p) + (1 - win) * np.log(1 - p))
cache = {(p, k, h, y): diffs(p, k, h, y) for p in PRI for k in KS for h in HC for y in ys[1:]}
print("cache built", flush=True)
tab = pd.DataFrame([{"p": p, "k": k, "h": h, "sd": sd, "y": y, "ll": LL(cache[(p, k, h, y)][:, 0], cache[(p, k, h, y)][:, 1], h, sd)}
                    for p, k, h, sd in itertools.product(PRI, KS, HC, SDS) for y in ys[1:]])
def live(y): D = cache[(0.4, 20, 3, y)]; return LL(D[:, 0], D[:, 1], 3.0, 14.0)
rows = []
for y in ys[1:]:
    tr = tab[tab.y != y].groupby(["p", "k", "h", "sd"]).ll.mean(); b = tr.idxmin()
    rows.append(dict(season=y, fit=b, held=float(tab[(tab.p == b[0]) & (tab.k == b[1]) & (tab.h == b[2]) & (tab.sd == b[3]) & (tab.y == y)].ll.iloc[0]), live=live(y)))
R = pd.DataFrame(rows); R["d"] = R.held - R.live; print(R.to_string(index=False))
f = np.array([list(x) for x in R.fit]); print("fold ranges prior", f[:, 0].min(), f[:, 0].max(), "K", f[:, 1].min(), f[:, 1].max(), "HCA", f[:, 2].min(), f[:, 2].max(), "SD", f[:, 3].min(), f[:, 3].max())
rng = np.random.default_rng(1); b = [rng.choice(R.d.values, len(R)).mean() for _ in range(4000)]
print("LOSO minus live held-out LL", round(R.d.mean(), 4), np.percentile(b, [5, 95]).round(4), "better", int((R.d < 0).sum()), "of", len(R), "detectable", round(1.645 * R.d.std(ddof=1) / np.sqrt(len(R)), 4))
a = tab.groupby(["p", "k", "h", "sd"]).ll.mean(); print("in-sample best", a.idxmin(), round(a.min(), 4), "live", round(np.mean([live(y) for y in ys[1:]]), 4))
