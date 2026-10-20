"""Diagnostics after the simple prop challenger outcome (GPT review, 20 Oct 2026). Not a test; nothing is selected here.
1. Calibration of the exact frozen versions (rebounds P+O, assists P+T) and of points P+T.
2. Points: forecast minutes vs actual minutes (actual minutes is a diagnostic only, never a forecast input).
3. Confident overs and the low-minute-risk subgroup by season.
python research/nba_props_diag.py -> research/nba_props_diag.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_props_simple_test as P  # noqa: E402

FROZEN = {"pts": ("P+T", dict(b=True)), "reb": ("P+O", dict(c=True)), "ast": ("P+T", dict(b=True))}


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D["app"] = D.minutes > 0
    rng = np.random.default_rng(3)
    rows = {s: [] for s in P.STATS}
    for y in P.TEST:
        F = D[(D.season < y) & D.app]
        Z = D[(D.season == y) & D.app].reset_index(drop=True)     # given appearing
        grp_rate = {s: F.groupby("grp")[s].sum() / F.groupby("grp").minutes.sum() for s in P.STATS}
        grp_pg = {s: F.groupby("grp")[s].mean() for s in P.STATS}
        q = P.q_minutes(Z.mu1, Z.sd1)
        for s in P.STATS:
            f = R["fits"][str(y)][s]
            K = P.SUP_FULL[s]
            rate = P.rates(Z, s, f["m0"], grp_rate)
            name, kw = FROZEN[s]
            if "b" in kw:
                rate_f, r_f = P.adjust(Z, s, rate, b=f["b"], tag="1"), f["r_T"]
            else:
                rate_f, r_f = P.adjust(Z, s, rate, c=f["c"]), f["r_O"]
            b1, _, _ = P.base_means(Z, s, grp_rate, grp_pg)
            line = np.floor(b1) + 0.5
            li = np.floor(line).astype(int)
            yv = Z[s].to_numpy()
            amin = np.clip(np.round(Z.minutes.to_numpy()), 1, None)
            out = {}
            for tag, (rt, rr, mode) in {"P": (rate, f["r_P"], "fc"), name: (rate_f, r_f, "fc"),
                                        name + " with actual minutes (diagnostic)": (rate_f, r_f, "am")}.items():
                pits, pov = [], []
                for b0 in range(0, len(Z), 4000):
                    sl = slice(b0, b0 + 4000)
                    if mode == "fc":
                        cond = P.mixture_pmf(rt[sl], q[sl], rr, K)
                    else:
                        cond = P.nb_pmf(rt[sl] * amin[sl], rr, K)
                    Fc = np.cumsum(cond, 1)
                    yi = np.clip(yv[sl], 0, K).astype(int)
                    hi = Fc[np.arange(len(yi)), yi]
                    lo = np.where(yi > 0, Fc[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
                    pits.append(lo + rng.random(len(yi)) * (hi - lo))
                    pov.append(1 - Fc[np.arange(len(yi)), np.clip(li[sl], 0, K)])
                out[tag] = (np.concatenate(pits), np.concatenate(pov))
            rows[s].append(dict(season=y, out=out, over=(yv > line), low=q[:, :14].sum(1) >= 0.2))
        print("season", y, flush=True)
    res = {}
    for s in P.STATS:
        r = {}
        tags = rows[s][0]["out"].keys()
        over = np.concatenate([x["over"] for x in rows[s]])
        low = np.concatenate([x["low"] for x in rows[s]])
        seas = np.concatenate([np.full(len(x["over"]), x["season"]) for x in rows[s]])
        for tag in tags:
            pit = np.concatenate([x["out"][tag][0] for x in rows[s]])
            pov = np.concatenate([x["out"][tag][1] for x in rows[s]])
            dec = np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit)
            conf = pov >= 0.8
            r[tag] = {"pit_deciles_given_appearing": [round(float(v), 3) for v in dec],
                      "pit_within_0.07_0.13": bool(((dec >= 0.07) & (dec <= 0.13)).all()),
                      "over_all": dict(mean_p=round(float(pov.mean()), 4), freq=round(float(over.mean()), 4)),
                      "over_low_minute_risk": dict(n=int(low.sum()), mean_p=round(float(pov[low].mean()), 4), freq=round(float(over[low].mean()), 4)),
                      "over_not_low_minute_risk": dict(n=int((~low).sum()), mean_p=round(float(pov[~low].mean()), 4), freq=round(float(over[~low].mean()), 4)),
                      "confident_overs_p>=0.8": dict(n=int(conf.sum()), mean_p=round(float(pov[conf].mean()), 4) if conf.any() else None,
                                                     freq=round(float(over[conf].mean()), 4) if conf.any() else None,
                                                     by_season={int(y): dict(n=int((conf & (seas == y)).sum()),
                                                                             mean_p=round(float(pov[conf & (seas == y)].mean()), 3) if (conf & (seas == y)).any() else None,
                                                                             freq=round(float(over[conf & (seas == y)].mean()), 3) if (conf & (seas == y)).any() else None)
                                                                 for y in P.TEST}),
                      "low_minute_risk_by_season": {int(y): dict(mean_p=round(float(pov[low & (seas == y)].mean()), 3), freq=round(float(over[low & (seas == y)].mean()), 3))
                                                    for y in P.TEST}}
        res[s] = r
    with open(os.path.join(HERE, "nba_props_diag.json"), "w") as f:
        json.dump(res, f, indent=1)
    for s in P.STATS:
        for tag, v in res[s].items():
            print(s, tag, v["pit_deciles_given_appearing"], v["pit_within_0.07_0.13"], "low", v["over_low_minute_risk"], "conf", {k: v["confident_overs_p>=0.8"][k] for k in ("n", "mean_p", "freq")})


if __name__ == "__main__":
    main()
