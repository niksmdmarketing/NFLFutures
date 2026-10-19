"""Gates for research/NFL_EXTRA_STATS_RULE.md: B (data/research/nfl_eng_x2h4a60.npz) vs A (nfl_eng_h4a60.npz).
Usage: python research/nfl_extra_stats_test.py"""
import json
import os
import sys

import numpy as np
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nfl_engine as E  # noqa: E402

D = os.path.join(ROOT, "data", "research")
A = E.score(os.path.join(D, "nfl_eng_h4a60.npz"))
B = E.score(os.path.join(D, "nfl_eng_x2h4a60.npz"))
g = (A.ll - B.ll).to_numpy()                    # positive = B better
rng = np.random.default_rng(5)
bs = np.array([g[rng.integers(0, len(g), len(g))].mean() for _ in range(2000)])
res = {"seasons": A.season.tolist(), "ll_A": float(A.ll.mean()), "ll_B": float(B.ll.mean()), "gain_ll": float(g.mean()),
       "gain_ll_ci90": [float(np.percentile(bs, 5)), float(np.percentile(bs, 95))], "seasons_better": int((g > 0).sum()),
       "rmse_A": float(A.rmse.mean()), "rmse_B": float(B.rmse.mean()), "rmse_late_A": float(A.rmse_late.mean()), "rmse_late_B": float(B.rmse_late.mean()),
       "by_season_gain_ll": dict(zip(map(int, A.season), map(float, g)))}
res["gates"] = {"1_ll_ci_above_0": res["gain_ll_ci90"][0] > 0, "2_9_of_13": res["seasons_better"] >= 9,
                "3_rmse": res["rmse_B"] < res["rmse_A"], "4_late_not_worse": res["rmse_late_B"] <= res["rmse_late_A"]}
res["all_pass"] = all(res["gates"].values())
d = np.load(os.path.join(D, "nfl_eng_x2h4a60.npz"), allow_pickle=True)
X, y, s, cols = d["X"], d["y"], d["s"], list(d["cols"])
sd = X[s < 2013].std(0)
sd[sd == 0] = 1
m = Ridge(alpha=E.P["alpha"]).fit(X[s <= 2025] / sd, y[s <= 2025])
new = [c for c in cols if any(k in c for k in ("to_rate", "expl", "havoc", "conv34", "rz_td", "qb_hit"))]
res["new_weights_per_sd_2010_2025"] = {c: round(float(m.coef_[cols.index(c)]), 3) for c in new}
json.dump(res, open(os.path.join(ROOT, "research", "nfl_extra_stats_results.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
