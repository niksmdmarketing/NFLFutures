"""Playoffs with the actual field and seeds, 2013-2025 (6-seed format to 2019, 7-seed from 2020). Diagnostic only."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nfl_conference_favourites import fit  # noqa: E402
H = os.path.dirname(os.path.abspath(__file__))
P = pd.concat([pd.read_csv(os.path.join(H, "nfl_futures_diagnosis_playoff_rows_2013_19.csv")), pd.read_csv(os.path.join(H, "nfl_futures_diagnosis_playoff_rows.csv"))])
P["fmt"] = np.where(P.season <= 2019, "6-seed", "7-seed")


def ll(p, y):
    p = np.clip(p, 0.003, 0.997)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


out = {}
for m, d in P.groupby("model"):
    d = d.copy()
    d["n_field"] = d.groupby(["season"]).team.transform("size") / 2
    o = {"seasons": int(d.season.nunique()), "conference_champions": int(d.y_conf.sum()),
         "ll_conf": round(ll(d.p_conf.values, d.y_conf.values), 4), "ll_conf_uniform": round(ll(1 / d.n_field.values, d.y_conf.values), 4),
         "intercept_slope_conf": fit(d.p_conf.values, d.y_conf.values),
         "by_seed": {int(s): {"predicted": round(float(x.p_conf.sum()), 2), "actual": int(x.y_conf.sum()), "n": int(len(x))} for s, x in d.groupby("seed")},
         "by_format": {f: {"intercept_slope": fit(x.p_conf.values, x.y_conf.values), "ll": round(ll(x.p_conf.values, x.y_conf.values), 4),
                           "ll_uniform": round(ll(1 / x.n_field.values, x.y_conf.values), 4)} for f, x in d.groupby("fmt")}}
    o["title_ll"] = round(ll(d.p_title.values, d.y_title.values), 4)
    o["title_ll_uniform"] = round(ll(1 / (2 * d.n_field.values), d.y_title.values), 4)
    out[m] = o
json.dump(out, open(os.path.join(H, "nfl_playoff_field_2013_2025.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
