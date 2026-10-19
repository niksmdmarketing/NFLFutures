"""Summarise research/nfl_futures_diagnosis.py output into the four checks. Usage: python research/nfl_futures_diagnosis_report.py"""
import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = pd.read_csv(os.path.join(ROOT, "research", "nfl_futures_diagnosis_rows.csv"))
PL = pd.read_csv(os.path.join(ROOT, "research", "nfl_futures_diagnosis_playoff_rows.csv"))
MK = ["div", "playoff", "seed1", "conf", "title"]


def ll(p, y):
    p = np.clip(p, 0.003, 0.997)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def logit_slope(p, y):
    """calibration slope: y ~ logistic(a + b * logit(p)); b > 1 = forecasts too cautious."""
    p = np.clip(p, 0.003, 0.997)
    x = np.log(p / (1 - p))

    def nll(v):
        q = 1 / (1 + np.exp(-(v[0] + v[1] * x)))
        q = np.clip(q, 1e-9, 1 - 1e-9)
        return -(y * np.log(q) + (1 - y) * np.log(1 - q)).sum()
    return round(float(minimize(nll, [0, 1], method="Nelder-Mead").x[1]), 2)


out = {}
# 1-2 win totals
wt = {}
for (m, w), d in R.groupby(["model", "week"]):
    z = (d.wins - d.exp_w) / d.sd_w.clip(lower=0.05)
    wt[f"{m} wk{w}"] = {"rmse": round(float(np.sqrt(((d.exp_w - d.wins) ** 2).mean())), 2),
                       "slope_actual_on_expected": round(float(np.polyfit(d.exp_w, d.wins, 1)[0]), 2),
                       "z_sd (1=right, >1 too little uncertainty)": round(float(z.std()), 2),
                       "cover80": round(float(((d.wins >= d.q10) & (d.wins <= d.q90)).mean()), 2),
                       "mean_80_width": round(float((d.q90 - d.q10).mean()), 2)}
out["win_totals_by_stage"] = wt
zs = {}
for (m, y), d in R[R.week == 0].groupby(["model", "season"]):
    zs.setdefault(m, {})[int(y)] = round(float(((d.wins - d.exp_w) / d.sd_w).std()), 2)
out["preseason_win_total_z_sd_by_season"] = zs
rs = {}
for (m, y), d in R[R.week == 0].groupby(["model", "season"]):
    rs.setdefault(m, {})[int(y)] = round(float(np.sqrt(((d.exp_w - d.wins) ** 2).mean())), 2)
out["preseason_win_rmse_by_season"] = rs
# 3 playoffs given the actual field
pf = {}
for m, d in PL.groupby("model"):
    base_c = np.full(len(d), 1 / 7)
    base_t = np.full(len(d), 1 / 14)
    pf[m] = {"seasons": int(d.season.nunique()), "ll_conf": round(ll(d.p_conf.values, d.y_conf.values), 4), "ll_conf_uniform": round(ll(base_c, d.y_conf.values), 4),
             "ll_title": round(ll(d.p_title.values, d.y_title.values), 4), "ll_title_uniform": round(ll(base_t, d.y_title.values), 4),
             "slope_conf": logit_slope(d.p_conf.values, d.y_conf.values), "slope_title": logit_slope(d.p_title.values, d.y_title.values),
             "sum_p_conf_of_actual_champs": round(float(d[d.y_conf == 1].p_conf.mean()), 3),
             "seed1_conf_rate_actual": round(float(d[d.seed == 1].y_conf.mean()), 3), "seed1_conf_rate_model": round(float(d[d.seed == 1].p_conf.mean()), 3),
             "by_seed_conf_actual": d.groupby("seed").y_conf.mean().round(3).to_dict(), "by_seed_conf_model": d.groupby("seed").p_conf.mean().round(3).to_dict()}
out["playoffs_given_actual_field"] = pf
# 4 futures by stage and season
fs = {}
for (m, w), d in R.groupby(["model", "week"]):
    fs[f"{m} wk{w}"] = {k: {"ll": round(ll(d["p_" + k].values, d["y_" + k].values), 4), "slope": logit_slope(d["p_" + k].values, d["y_" + k].values)} for k in MK}
out["futures_by_stage"] = fs
by = {}
for (m, y), d in R.groupby(["model", "season"]):
    by.setdefault(m, {})[int(y)] = {k: round(ll(d["p_" + k].values, d["y_" + k].values), 4) for k in MK}
out["futures_ll_by_season_all_stages"] = by
diff = {}
for y in sorted(R.season.unique()):
    a, b = by["v4wf"][int(y)], by["v5like"][int(y)]
    diff[int(y)] = {k: round(a[k] - b[k], 4) for k in MK}
out["v5like_gain_by_season (positive = better)"] = diff
json.dump(out, open(os.path.join(ROOT, "research", "nfl_futures_diagnosis.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
