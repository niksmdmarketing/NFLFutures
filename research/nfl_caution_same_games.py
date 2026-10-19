"""Step 2 of the NFL caution investigation: the walk-forward engine and the live v4 rating path on IDENTICAL games.
Both use the same point-in-time feature differences (data/research/nfl_eng_base.npz = v4 components, no recency):
  engine : ridge on the features, refitted walk-forward (test season s uses 2010..s-1)
  v4     : the frozen v4 coefficients (ratings.P, fitted offline on 2010-2021) with its 0.25 multiplier on the efficiency terms;
           reported raw (dR) and as used by the simulation (rating_scale 0.89 x dR, home edge 1.8, S = sqrt(sigma^2 + 2 tau^2) = 13.39)
Quantities, all on the same games (regular season 2013-2025):
  margin slope  : actual margin on predicted margin (1 = gaps right, >1 = too small)
  probit k      : P(home win) = Phi(k * x + h * home) with x = predicted rating gap / S and a free home term (as research/nfl_playoff_calibration.py)
The QB layer is not in either (the earlier k 1.2 check also used base ratings only).
Usage: python research/nfl_caution_same_games.py"""
import json
import os
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402

P, SIM = ratings.P, ratings.S["sim"]
S_TOT = float(np.sqrt(SIM["sigma"] ** 2 + 2 * SIM["tau"] ** 2))
d = np.load(os.path.join(ROOT, "data", "research", "nfl_eng_base.npz"), allow_pickle=True)
X, y, s, w, cols = d["X"], d["y"], d["s"], d["w"], list(d["cols"])

# v4 frozen rating difference
coef = np.array([P["coef"][c] / P["sd"][c] * (1.0 if c.endswith("srs") else P["r"]) for c in cols])
dR = X @ coef

# engine walk-forward margin prediction and its rating gap (prediction minus intercept)
sd = X[s < 2013].std(0)
sd[sd == 0] = 1
eng_pred, eng_gap = np.full(len(y), np.nan), np.full(len(y), np.nan)
for t in range(2013, 2026):
    tr, te = s < t, s == t
    m = Ridge(alpha=P["alpha"]).fit(X[tr] / sd, y[tr])
    eng_pred[te] = m.predict(X[te] / sd)
    eng_gap[te] = eng_pred[te] - m.intercept_

T = s >= 2013


def slope(p, yy):
    b = np.polyfit(p, yy, 1)
    r = yy - np.polyval(b, p)
    se = np.sqrt(np.sum(r ** 2) / (len(yy) - 2) / np.sum((p - p.mean()) ** 2))
    return [round(float(b[0]), 3), round(float(se), 3)]


def probit(x, yy):
    keep = yy != 0
    x, win = x[keep], (yy[keep] > 0).astype(float)

    def nll(v):
        p = np.clip(norm.cdf(v[0] * x + v[1]), 1e-6, 1 - 1e-6)
        return -(win * np.log(p) + (1 - win) * np.log(1 - p)).sum()
    v = minimize(nll, [1.0, 0.1], method="Nelder-Mead").x
    return round(float(v[0]), 3)


rows = {}
blocks = {"all weeks": T, "weeks 1-4": T & (w <= 4), "weeks 5-9": T & (w >= 5) & (w <= 9), "weeks 10+": T & (w >= 10),
          "2013-21 (v4 in-sample)": T & (s <= 2021), "2022-25 (v4 out-of-sample)": T & (s >= 2022), "2025": s == 2025}
for name, m in blocks.items():
    rows[name] = {
        "games": int(m.sum()),
        "engine_margin_slope": slope(eng_pred[m], y[m]),
        "v4_raw_margin_slope (dR + 1.8)": slope(dR[m] + SIM["hfa"], y[m]),
        "v4_scaled_margin_slope (0.89 dR + 1.8)": slope(SIM["rating_scale"] * dR[m] + SIM["hfa"], y[m]),
        "engine_probit_k (gap / 13.39)": probit(eng_gap[m] / S_TOT, y[m]),
        "v4_probit_k (0.89 dR / 13.39)": probit(SIM["rating_scale"] * dR[m] / S_TOT, y[m]),
        "sd_engine_gap": round(float(eng_gap[m].std()), 2), "sd_v4_scaled_gap": round(float((SIM["rating_scale"] * dR[m]).std()), 2),
        "corr_engine_v4": round(float(np.corrcoef(eng_gap[m], dR[m])[0, 1]), 3),
        "residual_sd_engine": round(float((y[m] - eng_pred[m]).std()), 2), "residual_sd_v4": round(float((y[m] - SIM["rating_scale"] * dR[m] - SIM["hfa"]).std()), 2)}
out = {"S_total": round(S_TOT, 2), "v4_r_multiplier": P["r"], "rating_scale": SIM["rating_scale"], "rows": rows}
json.dump(out, open(os.path.join(ROOT, "research", "nfl_caution_same_games.json"), "w"), indent=1)
for k, v in rows.items():
    print(k, v)
