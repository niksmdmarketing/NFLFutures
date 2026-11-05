"""NFL efficiency-weight test (research/NFL_EFFICIENCY_WEIGHT_RULE.md): fit E50 and E0 on 2010-2021, Stage 1 game check on 2022-2025.

Uses the point-in-time game features of research/nfl_walkforward_weights.py (data/research/nfl_wf_features.npz).
Writes model/replay/nfl_eff_coef_E50.json, nfl_eff_coef_E0.json and research/nfl_efficiency_weight_results.json (stage1).
Usage: python research/nfl_efficiency_weight_test.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LinearRegression, Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402
from common import FIX, games  # noqa: E402

P = ratings.P
COLS = P["cols"]
SRS = [j for j, c in enumerate(COLS) if c.endswith("srs")]
EFF = [j for j, c in enumerate(COLS) if not c.endswith("srs")]
CACHE = os.path.join(ROOT, "data", "research", "nfl_wf_features.npz")
RES = os.path.join(ROOT, "research", "nfl_efficiency_weight_results.json")


def fit_variant(X, y, srs_mult):
    frozen = np.array([P["coef"][c] for c in COLS])
    off = X[:, SRS] @ (srs_mult * frozen[SRS])
    m = Ridge(alpha=P["alpha"], fit_intercept=True).fit(X[:, EFF], y - off)
    coef = np.zeros(len(COLS))
    coef[SRS] = srs_mult * frozen[SRS]
    coef[EFF] = m.coef_
    return coef, float(m.intercept_)


def game_meta(first=2010, last=2025):
    """spread_line per cached row, in the order nfl_walkforward_weights.build appended them."""
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows = []
    for y in range(first, last + 1):
        reg = g[(g.season == y) & (g.game_type == "REG")]
        for w in sorted(reg.week.unique()):
            for r in reg[reg.week == w].itertuples():
                if pd.isna(r.result):
                    continue
                rows.append((y, int(w), float(r.result), float(r.spread_line) if pd.notna(r.spread_line) else np.nan))
    return pd.DataFrame(rows, columns=["season", "week", "result", "spread"])


if __name__ == "__main__":
    d = np.load(CACHE)
    X, y, s, w = d["X"], d["y"], d["s"], d["w"]
    meta = game_meta()
    assert len(meta) == len(y) and np.allclose(meta.result.values, y), "row order mismatch"
    tr = (s >= 2010) & (s <= 2021)
    frozen = np.array([P["coef"][c] for c in COLS])
    models = {"v4": (frozen, float(P["intercept"]))}
    for name, mult in (("E50", 0.5), ("E0", 0.0)):
        c, i = fit_variant(X[tr], y[tr], mult)
        models[name] = (c, i)
        json.dump({"coef": dict(zip(COLS, c.tolist())), "intercept": i, "rule": "research/NFL_EFFICIENCY_WEIGHT_RULE.md",
                   "srs_mult": mult, "train": "2010-2021"}, open(os.path.join(ROOT, "model", "replay", f"nfl_eff_coef_{name}.json"), "w"), indent=1)
    te = (s >= 2022) & (s <= 2025) & (w >= 2)
    out = {"test_games": int(te.sum()), "models": {}}
    sp = meta.spread.values
    for name, (c, i) in models.items():
        pred = X @ c + i
        sim = ratings.S["sim"]["rating_scale"] * (X @ c) + ratings.S["sim"]["hfa"]   # the form the simulator uses (neutral sites ignored)
        res = {}
        res["rmse"] = float(np.sqrt(np.mean((y[te] - pred[te]) ** 2)))
        res["rmse_sim_form"] = float(np.sqrt(np.mean((y[te] - sim[te]) ** 2)))
        res["rmse_by_season"] = {int(k): float(np.sqrt(np.mean((y[te & (s == k)] - pred[te & (s == k)]) ** 2))) for k in range(2022, 2026)}
        win = (y[te] > 0).astype(float)
        keep = y[te] != 0
        p = norm.cdf(pred[te] / 13.4).clip(1e-6, 1 - 1e-6)
        res["win_logloss"] = float(-np.mean((win * np.log(p) + (1 - win) * np.log(1 - p))[keep]))
        ok = te & np.isfinite(sp)
        b = LinearRegression().fit(np.column_stack([pred[ok], sp[ok]]), y[ok])
        res["blend_with_close"] = {"model": float(b.coef_[0]), "spread": float(b.coef_[1])}
        res["corr_with_close"] = float(np.corrcoef(pred[ok], sp[ok])[0, 1])
        res["train_rmse_2010_2021"] = float(np.sqrt(np.mean((y[tr] - pred[tr]) ** 2)))
        # share of rating spread from SRS vs efficiency on test games (home-minus-away differences)
        part_srs, part_eff = X[te][:, SRS] @ c[SRS], X[te][:, EFF] @ c[EFF]
        tot = part_srs + part_eff
        res["share_srs"] = float(np.cov(part_srs, tot)[0, 1] / tot.var())
        res["sd_pred"] = float((X[te] @ c).std())
        out["models"][name] = res
    ok = te & np.isfinite(sp)
    out["close_rmse"] = float(np.sqrt(np.mean((y[ok] - sp[ok]) ** 2)))
    out["stage1_gate_E50"] = out["models"]["E50"]["rmse"] <= out["models"]["v4"]["rmse"]
    json.dump({"stage1": out}, open(RES, "w"), indent=1)
    print(json.dumps(out, indent=1))
