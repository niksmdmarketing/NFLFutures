"""Walk-forward re-training of the NFL rating weights (research only; the frozen v4 settings are not changed).

The v3/v4 weights were learned on 2010-2021 offline (the training script is not in the repo). This reconstructs that fit:
for every regular-season game, the opponent-adjusted components are built point-in-time from play-by-play before that
game's week (exactly as ratings.base_ratings does), standardised and scaled as in settings.json, and the home-minus-away
feature difference is regressed on the final margin (ridge, alpha from settings, intercept = home edge).
Step 1 (check): fit on 2010-2021 and compare with the frozen weights.
Step 2 (walk-forward): for each test season s, fit on every season before s only, and write model/replay/nfl_wf_coef.json
so research/replay_nfl.py (BT_COEF=wf) can replay each season with weights that never saw it.
Hyper-parameters (pseudo-counts k, r, alpha) are kept from settings.json; they were chosen on 2010-2021 too (noted).
Usage: python research/nfl_walkforward_weights.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ratings  # noqa: E402
from common import FIX, NT, TEAMS, TIX, games, load_pbp, scrimmage, special  # noqa: E402

P = ratings.P
COLS = P["cols"]
CACHE = os.path.join(ROOT, "data", "research", "nfl_wf_features.npz")
OUT = os.path.join(ROOT, "model", "replay", "nfl_wf_coef.json")


def features(cur_pbp, pri_pbp, g, season):
    """Team x column matrix of the scaled inputs that base_ratings multiplies by the weights."""
    cs, cst = scrimmage(cur_pbp), special(cur_pbp)
    ps, pst = scrimmage(pri_pbp), special(pri_pbp)
    F = {}
    F.update(ratings.block(ps, pst, "pri"))
    F.update(ratings.block(cs, cst, "cur"))
    F["pri_srs"] = ratings.srs(g[(g.season == season - 1) & (g.game_type == "REG")])
    F["cur_srs"] = ratings.srs(g[(g.season == season) & (g.game_type == "REG")])
    F.update(ratings.counts(cs, cst, g[(g.season == season) & (g.game_type == "REG")]))
    k = P["k"]
    feats = {}
    for grp, comps in P["groups"].items():
        n_off, n_def = P["count_cols"][grp]
        for side, ncol in (("off", n_off), ("def", n_def)):
            n = F[ncol]
            wc, wp = n / (n + k[grp]), k[grp] / (n + k[grp])
            for c in comps:
                feats[f"c_{c}_{side}"] = wc * F[f"cur_{c}_{side}"]
                feats[f"p_{c}_{side}"] = wp * F[f"pri_{c}_{side}"]
    n = F["n_games"]
    feats["c_srs"] = n / (n + k["srs"]) * F["cur_srs"]
    feats["p_srs"] = k["srs"] / (n + k["srs"]) * F["pri_srs"]
    X = np.zeros((NT, len(COLS)))
    for j, c in enumerate(COLS):
        x = feats[c] / P["sd"][c]
        X[:, j] = x if c.endswith("srs") else x * P["r"]
    return X


def build(first=2010, last=2025):
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    rows_X, rows_y, rows_s, rows_w = [], [], [], []
    for y in range(first, last + 1):
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        reg = g[(g.season == y) & (g.game_type == "REG")]
        for w in sorted(reg.week.unique()):
            gg = g.copy()
            m = (gg.season == y) & (gg.game_type == "REG") & (gg.week >= w)
            gg.loc[m, "result"] = np.nan
            X = features(cur_all[cur_all.week < w], pri, gg, y)
            for r in reg[reg.week == w].itertuples():
                if pd.isna(r.result):
                    continue
                rows_X.append(X[TIX[r.home_team]] - X[TIX[r.away_team]])
                rows_y.append(float(r.result))
                rows_s.append(y)
                rows_w.append(int(w))
        print(y, len(rows_y), flush=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    np.savez_compressed(CACHE, X=np.array(rows_X), y=np.array(rows_y), s=np.array(rows_s), w=np.array(rows_w))


def fit(X, y):
    m = Ridge(alpha=P["alpha"], fit_intercept=True).fit(X, y)
    return dict(zip(COLS, m.coef_.tolist())), float(m.intercept_)


if __name__ == "__main__":
    if not os.path.exists(CACHE) or "--rebuild" in sys.argv:
        build()
    d = np.load(CACHE)
    X, y, s = d["X"], d["y"], d["s"]
    tr = (s >= 2010) & (s <= 2021)
    coef, icpt = fit(X[tr], y[tr])
    frozen = np.array([P["coef"][c] for c in COLS])
    rec = np.array([coef[c] for c in COLS])
    print("reconstruction vs frozen: corr %.3f, intercept %.2f vs %.2f" % (np.corrcoef(frozen, rec)[0, 1], icpt, P["intercept"]))
    print(pd.DataFrame({"frozen": frozen, "refit": rec}, index=COLS).round(3).to_string())
    pred_f, pred_r = X @ frozen + P["intercept"], X @ rec + icpt
    for lab, mask in (("2010-21", tr), ("2022-25", s >= 2022)):
        print(lab, "game margin RMSE frozen %.3f refit %.3f" % (np.sqrt(np.mean((y[mask] - pred_f[mask]) ** 2)), np.sqrt(np.mean((y[mask] - pred_r[mask]) ** 2))))
    out = {"note": "walk-forward weights: season s uses only seasons 2010..s-1; hyper-parameters from settings.json",
           "reconstruction_corr_2010_2021": float(np.corrcoef(frozen, rec)[0, 1]), "seasons": {}}
    for test in range(2013, 2027):
        m = (s >= 2010) & (s < test)
        c, i = fit(X[m], y[m])
        out["seasons"][str(test)] = {"coef": c, "intercept": i, "train": f"2010-{test - 1}", "games": int(m.sum())}
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)
