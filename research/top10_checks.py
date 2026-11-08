"""Pre-registered checks (TOP10_NHL_CBB_PREREG.md + GPT, 8 Nov 2026): placebo for D, power vs multiplicative de-vig, tail paired loss.
Usage: python top10_checks.py <sport> <edges dir>"""
import sys, os, numpy as np, pandas as pd
from scipy.optimize import brentq
sport, ed = sys.argv[1:3]
J = pd.read_csv(os.path.join(ed, f"{sport}_proxy_edges.csv"))
LL = lambda p, y: -(y * np.log(np.clip(p, 1e-4, 1 - 1e-4)) + (1 - y) * np.log(1 - np.clip(p, 1e-4, 1 - 1e-4)))
def raw(m): m = pd.to_numeric(m, errors="coerce"); return np.where(m < 0, -m / (-m + 100), 100 / (m + 100))
rh, ra = raw(J.mlh), raw(J.mla)
def power(a, b):
    try:
        k = brentq(lambda k: a ** k + b ** k - 1, 0.5, 50) if a + b > 1 else 1.0
        return a ** k
    except Exception:
        return a / (a + b)
J["p_power"] = [power(a, b) for a, b in zip(rh, ra)]
rng = np.random.default_rng(0)
def Dval(X, pm, pk):
    gap = pm - pk; k = int(round(len(X) * .05)); o = np.argsort(-gap.values)
    up, dn = o[:k], o[::-1][:k]
    d = LL(pm.values, X.y.values) - LL(pk.values, X.y.values)
    return d[up].mean() - d[dn].mean(), d[up].mean(), (X.y.values[up] - pm.values[up]).mean(), (X.y.values[up] - pk.values[up]).mean()
for name, X in (("eval 2020+", J[J.season >= 2020]), ("all", J)):
    X = X.reset_index(drop=True)
    for lab, col in (("multiplicative", "p_market"), ("power", "p_power")):
        pk = X[col]; D, up, om, ok = Dval(X, X.p_model, pk)
        band = pd.qcut(pk, 10, labels=False, duplicates="drop"); gap = (X.p_model - pk).values; null = []
        for _ in range(400):
            g2 = gap.copy()
            for bnd in np.unique(band):
                ix = np.where(band == bnd)[0]; g2[ix] = rng.permutation(g2[ix])
            null.append(Dval(X, pd.Series(np.clip(pk.values + g2, 1e-3, 1 - 1e-3)), pk)[0])
        print(f"{sport} {name} {lab}: D {D:.4f} | placebo mean {np.mean(null):.4f} 95th {np.percentile(null,95):.4f} p={np.mean(np.array(null)>=D):.3f} | upward-tail paired LL(model-market) {up:.4f}; mean(y-p_model) {om:.3f}; mean(y-p_market) {ok:.3f}")
