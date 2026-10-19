"""Season-cluster bootstrap intervals for the calibration slopes in research/nfl_futures_diagnosis.json, plus the 2025 breakdown."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nfl_futures_diagnosis_report import logit_slope, ll, R, PL  # noqa: E402
rng = np.random.default_rng(3)
ss = sorted(R.season.unique())
out = {}
for m in ("v4wf", "v5like"):
    for w in (0, 4, 8, 12, 16):
        d = R[(R.model == m) & (R.week == w)]
        for k in ("seed1", "conf", "title", "playoff", "div"):
            bs = []
            for _ in range(300):
                pick = rng.choice(ss, len(ss))
                x = pd.concat([d[d.season == s] for s in pick])
                bs.append(logit_slope(x["p_" + k].values, x["y_" + k].values))
            out[f"{m} wk{w} {k}"] = [logit_slope(d["p_" + k].values, d["y_" + k].values), round(float(np.percentile(bs, 5)), 2), round(float(np.percentile(bs, 95)), 2)]
y25 = {}
for w in (0, 4, 8, 12, 16):
    a = R[(R.season == 2025) & (R.week == w) & (R.model == "v4wf")].set_index("team")
    b = R[(R.season == 2025) & (R.week == w) & (R.model == "v5like")].set_index("team")
    y25[f"wk{w}"] = {k: round(ll(a["p_" + k].values, a["y_" + k].values) - ll(b["p_" + k].values, b["y_" + k].values), 4) for k in ("div", "playoff", "seed1", "conf", "title")}
    y25[f"wk{w}"]["win_rmse_v4,v5"] = [round(float(np.sqrt(((a.exp_w - a.wins) ** 2).mean())), 2), round(float(np.sqrt(((b.exp_w - b.wins) ** 2).mean())), 2)]
    y25[f"wk{w}"]["mean_sd_w_v4,v5"] = [round(float(a.sd_w.mean()), 2), round(float(b.sd_w.mean()), 2)]
a = R[(R.season == 2025) & (R.week == 0) & (R.model == "v4wf")].assign(err=lambda d: d.wins - d.exp_w).sort_values("err")
y25["biggest_preseason_misses_v4"] = {r.team: [round(r.exp_w, 1), r.wins] for r in pd.concat([a.head(4), a.tail(4)]).itertuples()}
out["2025"] = y25
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nfl_futures_diagnosis_ci.json"), "w"), indent=1)
for k, v in out.items():
    print(k, v)
