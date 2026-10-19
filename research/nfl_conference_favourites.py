"""Conference market: calibration intercept and slope by stage, and predicted vs actual for favourites (GPT review, 20 Oct 2026).
Reads research/nfl_futures_diagnosis_rows.csv. Teams are ranked by p_conf within their conference at each checkpoint."""
import json, os, sys
import numpy as np, pandas as pd
from scipy.optimize import minimize
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
from common import TEAMS  # noqa: E402
import simulate  # noqa: E402

R = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nfl_futures_diagnosis_rows.csv"))
conf_of = {t: int(simulate.CONF_OF[i]) for i, t in enumerate(TEAMS)}
R["c"] = R.team.map(conf_of)


def fit(p, y):
    p = np.clip(p, 0.003, 0.997)
    x = np.log(p / (1 - p))

    def nll(v):
        q = np.clip(1 / (1 + np.exp(-(v[0] + v[1] * x))), 1e-9, 1 - 1e-9)
        return -(y * np.log(q) + (1 - y) * np.log(1 - q)).sum()
    a, b = minimize(nll, [0, 1], method="Nelder-Mead").x
    return round(float(a), 2), round(float(b), 2)


def main():
    out = {}
    for (m, w), d in R.groupby(["model", "week"]):
        d = d.copy()
        d["rank"] = d.groupby(["season", "c"]).p_conf.rank(ascending=False, method="first")
        a, b = fit(d.p_conf.values, d.y_conf.values)
        fav = {}
        for lab, mask in (("1st favourite", d["rank"] == 1), ("2nd", d["rank"] == 2), ("3rd", d["rank"] == 3), ("4th-6th", d["rank"].between(4, 6)), ("7th-16th", d["rank"] >= 7)):
            x = d[mask]
            fav[lab] = {"predicted": round(float(x.p_conf.sum()), 2), "actual": int(x.y_conf.sum()), "n": int(len(x))}
        bins = pd.cut(d.p_conf, [0, .05, .15, .30, 1.0])
        bb = {str(k): {"mean_p": round(float(v.p_conf.mean()), 3), "actual_rate": round(float(v.y_conf.mean()), 3), "n": int(len(v))} for k, v in d.groupby(bins, observed=True)}
        out[f"{m} wk{w}"] = {"intercept": a, "slope": b, "by_favourite_rank": fav, "by_probability_bin": bb}
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nfl_conference_favourites.json"), "w"), indent=1)
    for k, v in out.items():
        if "wk8" in k or "wk12" in k or "wk4" in k:
            print(k, "int", v["intercept"], "slope", v["slope"]); print("  ", v["by_favourite_rank"]); print("  ", v["by_probability_bin"])


if __name__ == "__main__":
    main()
