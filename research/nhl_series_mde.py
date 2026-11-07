"""Minimum detectable movement for research/NHL_SERIES_CALIBRATION_RULE.md. PREDICTIONS ONLY: this script never reads the
outcome column (home_won is dropped on load). Usage: python research/nhl_series_mde.py <dir with <season>/series_<season>.csv>"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

RHO = (0.05, 0.10, 0.20, 0.40)
T90_8DF = 1.860     # 9 season clusters: t quantile instead of 1.645 for a planning half-width


def load(root):
    fs = sorted(glob.glob(os.path.join(root, "*", "series_*.csv")))
    D = pd.concat([pd.read_csv(f, usecols=lambda c: c != "home_won") for f in fs], ignore_index=True)
    assert "home_won" not in D.columns
    return D


def slope_se(q):
    """Standard error of the calibration slope of y on logit(q) if the forecast is calibrated: 1 / sqrt(sum w (x - xbar_w)^2), w = q(1-q)."""
    q = np.clip(np.asarray(q, float), 0.002, 0.998)
    x, w = np.log(q / (1 - q)), q * (1 - q)
    xbar = (w * x).sum() / w.sum()
    return 1.0 / np.sqrt((w * (x - xbar) ** 2).sum())


def mde(D, label):
    d = D[D.label == label]
    n_seasons = d.season.nunique()
    m = len(d) / max(n_seasons, 1)
    se = slope_se(d.q)
    out = {"label": label, "series": int(len(d)), "seasons": int(n_seasons), "series_per_season": float(m),
           "sd_logit_q": float(np.std(np.log(d.q / (1 - d.q)), ddof=1)), "mean_q": float(d.q.mean()), "se_independent": float(se)}
    for r in RHO:
        deff = 1 + (m - 1) * r
        out[f"rho_{r}"] = {"design_effect": float(deff), "n_eff": float(len(d) / deff), "half_width_90": float(T90_8DF * se * np.sqrt(deff))}
    return out


if __name__ == "__main__":
    D = load(sys.argv[1])
    D["checkpoint_first_quarter"] = False
    res = {}
    for lab in ("pre", "end"):
        res[lab] = mde(D, lab)
    # first quarter: the checkpoint(s) whose games-played average is at least 0.1 x 82 and below 0.25 x 82, one per season, the earliest
    fq = D[(D.label == "wk") & (D.gp_avg >= 0.001 * 82) & (D.gp_avg < 0.25 * 82)]
    first = fq.sort_values(["season", "checkpoint"]).groupby("season").checkpoint.min()
    fq = fq.merge(first.rename("c0"), left_on="season", right_index=True)
    fq = fq[fq.checkpoint == fq.c0].assign(label="fq")
    res["fq"] = mde(pd.concat([fq]), "fq")
    print(json.dumps(res, indent=1))
