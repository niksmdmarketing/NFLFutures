"""Step 1 of the NFL caution investigation: are the team-rating GAPS too small, separately from the simulation's noise?
Walk-forward game predictions (pipeline/nfl_engine.py npz caches; test season s fitted on 2010..s-1 only). For each test season the
slope of actual margin on predicted margin is computed (1 = gaps right; >1 = gaps too small, i.e. ratings compressed). Also by week
block, and the win-probability sharpness k (probit slope of wins on predicted margin / sigma) for comparison.
Usage: python research/nfl_caution_diagnosis.py [tag ...]   (default: base h4a60)"""
import json
import os
import sys

import numpy as np
import statsmodels.api as sm
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402

D = os.path.join(ROOT, "data", "research")


def wf(tag, alpha):
    d = np.load(os.path.join(D, f"nfl_eng_{tag}.npz"), allow_pickle=True)
    X, y, s, w = d["X"], d["y"], d["s"], d["w"]
    sd = X[s < 2013].std(0)
    sd[sd == 0] = 1
    Xs = X / sd
    P, Y, S, W, SIG = [], [], [], [], []
    for t in range(2013, 2026):
        tr, te = s < t, s == t
        m = Ridge(alpha=alpha).fit(Xs[tr], y[tr])
        P.append(m.predict(Xs[te]))
        SIG.append(np.full(te.sum(), (y[tr] - m.predict(Xs[tr])).std()))
        Y.append(y[te]), S.append(s[te]), W.append(w[te])
    return [np.concatenate(v) for v in (P, Y, S, W, SIG)]


def slope(p, y):
    b = np.polyfit(p, y, 1)
    r = y - np.polyval(b, p)
    se = np.sqrt(np.sum(r ** 2) / (len(y) - 2) / np.sum((p - p.mean()) ** 2))
    return round(float(b[0]), 3), round(float(se), 3)


def probit_k(p, y, sig):
    keep = y != 0
    z = (p / sig)[keep]
    m = sm.Probit((y[keep] > 0).astype(float), z[:, None]).fit(disp=0)
    return round(float(m.params[0]), 3), round(float(m.bse[0]), 3)


out = {}
for tag in (sys.argv[1:] or ["base", "h4a60"]):
    for alpha in (ratings.P["alpha"], 1e-6):
        p, y, s, w, sig = wf(tag, alpha)
        key = f"{tag}_ridge{alpha:g}"
        blocks = {"wk1-4": w <= 4, "wk5-9": (w >= 5) & (w <= 9), "wk10+": w >= 10}
        out[key] = {"margin_slope_all": slope(p, y), "win_k_all": probit_k(p, y, sig),
                    "margin_slope_by_weeks": {b: slope(p[m], y[m]) for b, m in blocks.items()},
                    "win_k_by_weeks": {b: probit_k(p[m], y[m], sig[m]) for b, m in blocks.items()},
                    "margin_slope_by_season": {int(t): slope(p[s == t], y[s == t])[0] for t in range(2013, 2026)},
                    "pred_sd": round(float(p.std()), 2), "rmse": round(float(np.sqrt(np.mean((y - p) ** 2))), 3)}
json.dump(out, open(os.path.join(ROOT, "research", "nfl_caution_diagnosis.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
