"""Calibration slope per market and stage: fit y ~ logistic(a + b*logit(p)). b<1: probabilities too extreme (overconfident);
b>1: too timid. Also the log loss after the fitted re-calibration (in-sample, so an upper bound on any gain).
Usage: python research/replay_slope.py <sport> [out.json]"""
import json
import sys

import numpy as np
from scipy.optimize import minimize

import replay_score as S


def fit(p, y):
    p = np.clip(np.asarray(p, float), 0.002, 0.998)
    z = np.log(p / (1 - p))
    y = np.asarray(y, float)

    def nll(w):
        q = np.clip(1 / (1 + np.exp(-(w[0] + w[1] * z))), 1e-6, 1 - 1e-6)
        return -(y * np.log(q) + (1 - y) * np.log(1 - q)).mean()
    r = minimize(nll, [0.0, 1.0], method="Nelder-Mead")
    return float(r.x[0]), float(r.x[1]), float(r.fun)


if __name__ == "__main__":
    D = S.load(sys.argv[1])
    out = {}
    for lo, hi, name in S.STAGES:
        x = D[(D.frac >= lo) & (D.frac < hi)] if name != "preseason" else D[D.week == 0]
        out[name] = {}
        for m, (pc, yc) in S.MARKETS.items():
            if pc in x and yc in x and not x[yc].isna().all():
                a, b, f = fit(x[pc], x[yc])
                out[name][m] = {"intercept": round(a, 3), "slope": round(b, 3), "ll": round(S.ll(x[pc], x[yc]), 4), "ll_recal": round(f, 4), "n": int(len(x))}
                print(f"{name:15s} {m:8s} slope {b:5.2f} int {a:+.2f} ll {S.ll(x[pc], x[yc]):.4f} -> {f:.4f}")
    if len(sys.argv) > 2:
        json.dump(out, open(sys.argv[2], "w"), indent=1)
