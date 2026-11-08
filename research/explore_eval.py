"""All-sports exploratory evaluation (research/EXPLORATORY_ALLSPORTS_RULE.md). Usage: python explore_eval.py <sport> <root> <null_tag> <arm_tag> [...]
For each arm vs null, per stage x market: paired log-loss difference (arm - null, negative = arm better) with season-cluster Bayesian-bootstrap 90% interval;
no-harm (no stage/market with gain interval worse than +0.002 on the 90% upper side), pooled gain, 60/40 split, best-season-removed, decision-market slope contrast.
ALL IN-SAMPLE. clip 0.001/0.999, 2000 draws, seed 20261108."""
import glob, sys, numpy as np, pandas as pd
sys.path.insert(0, "research")
import replay_score as S
sport, root, null, arms = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
DEC = {"nba": ("preseason", "playoff"), "afl": ("third quarter", "playoff"), "nhl": ("preseason", "r3"), "nfl": ("preseason", "playoff")}[sport]
B = 2000; LAM = 1.0
def load(tag):
    D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{root}/{sport}/{tag}/{sport}_[0-9]*.csv"))], ignore_index=True)
    D["frac"] = D.groupby("season").week.transform(lambda w: w / max(w.max(), 1)); return D
def stage(D, name):
    lo, hi = [(a, b) for a, b, n in S.STAGES if n == name][0]
    return D[D.week == 0] if name == "preseason" else D[(D.frac >= lo) & (D.frac < hi)]
def ll(p, y):
    p = np.clip(p, 0.001, 0.999); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
def wfit(z, y, w):
    th = np.array([0.0, 1.0])
    for _ in range(25):
        q = 1 / (1 + np.exp(-(th[0] + th[1] * z))); g = np.array([(w * (y - q)).sum(), (w * (y - q) * z).sum()]) - LAM * (th - [0, 1])
        h = np.array([[(w * q * (1 - q)).sum(), (w * q * (1 - q) * z).sum()], [(w * q * (1 - q) * z).sum(), (w * q * (1 - q) * z * z).sum()]]) + LAM * np.eye(2)
        st = np.linalg.solve(h, g); th = th + np.clip(st, -3, 3)
        if np.abs(st).max() < 1e-8: break
    return th[1]
N = load(null); seas = sorted(N.season.unique()); rng = np.random.default_rng(20261108)
W = rng.exponential(1.0, (B, len(seas))); W /= W.mean(1, keepdims=True)
cut = seas[int(len(seas) * 0.6)]
print(f"{sport}: seasons {seas[0]}-{seas[-1]} ({len(seas)}), null {null}; IN-SAMPLE, EXPLORATORY. discovery < {cut} <= check")
for a in arms:
    A = load(a); cells = []; tot = {}
    for st in ("preseason", "first quarter", "second quarter", "third quarter", "last quarter"):
        xn, xa = stage(N, st), stage(A, st)
        for mk, (pc, yc) in S.MARKETS.items():
            if pc not in xn or yc not in xn or xn[yc].isna().all(): continue
            m = xn[[pc, yc]].notna().all(axis=1).values
            if m.sum() < 30: continue
            d = ll(xa[pc].values[m], xa[yc].values[m]) - ll(xn[pc].values[m], xn[yc].values[m])
            ss = xn.season.values[m]; sm = pd.Series(d).groupby(ss).agg(["sum", "count"]).reindex(seas).fillna(0)
            cells.append((st, mk, sm["sum"].values, sm["count"].values))
    res = []
    for st, mk, s_, c_ in cells:
        bs = (W @ s_) / np.maximum(W @ c_, 1); res.append((st, mk, s_.sum() / max(c_.sum(), 1), np.percentile(bs, 90), np.percentile(bs, 10)))
    worst = max(res, key=lambda r: r[3]); harm = [r for r in res if r[3] > 0.002]
    pooled = sum(c[2].sum() for c in cells) / sum(c[3].sum() for c in cells)
    per_season = np.array([sum(c[2][i] for c in cells) / max(sum(c[3][i] for c in cells), 1) for i in range(len(seas))])
    first = [i for i, y in enumerate(seas) if y < cut]; last = [i for i, y in enumerate(seas) if y >= cut]
    nobest = np.delete(per_season, per_season.argmin()).mean()
    sn, sm_ = DEC; xn, xa = stage(N, sn), stage(A, sm_ and sn); pc, yc = S.MARKETS[sm_]
    slope = ""
    if pc in xn:
        zn = np.log(xn[pc].clip(.001, .999) / (1 - xn[pc].clip(.001, .999))); za = np.log(xa[pc].clip(.001, .999) / (1 - xa[pc].clip(.001, .999)))
        idn = np.searchsorted(seas, xn.season.values); ida = np.searchsorted(seas, xa.season.values)
        bn, ba = wfit(zn.values, xn[yc].values.astype(float), np.ones(len(zn))), wfit(za.values, xa[yc].values.astype(float), np.ones(len(za)))
        c = np.array([wfit(za.values, xa[yc].values.astype(float), W[i][ida]) - wfit(zn.values, xn[yc].values.astype(float), W[i][idn]) for i in range(B)])
        slope = f"decision {sm_}@{sn}: slope null {bn:.2f} arm {ba:.2f} contrast {ba - bn:+.3f} [10% {np.percentile(c, 10):+.3f}, 90% {np.percentile(c, 90):+.3f}]"
    print(f"{a:14s} pooled dLL {pooled:+.4f} | disc {per_season[first].mean():+.4f} check {per_season[last].mean():+.4f} | best season removed {nobest:+.4f} | worst cell {worst[0]}/{worst[1]} {worst[2]:+.4f} (90% up {worst[3]:+.4f}) | harm cells {len(harm)}/{len(res)} | {slope}")
