"""Points calibration diagnostic (descriptive; GPT handoff item 4). On the fixed confident-over group (current points version P+T with
M2 minutes, p(over) >= 0.8 at the formula line) and the low-minute-risk group, where do the over-probability errors concentrate:
by forecast minutes range, by forecast scoring rate, by line, and how much remains when actual minutes replace the forecast minutes.
python research/nba_points_diag.py -> research/nba_points_diag.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_minutes_tail_test as T  # noqa: E402
import nba_props_simple_test as P  # noqa: E402


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D = T.features(D)
    out = []
    for y in P.TEST:
        F = D[(D.season < y) & (D.season >= 2017)]
        Z = D[(D.season == y) & D.app].reset_index(drop=True)
        fit = T.fit_m2(F)
        q2, _ = T.m2_q(Z, fit)
        FA = F[F.app]
        grp_rate = {s: FA.groupby("grp")[s].sum() / FA.groupby("grp").minutes.sum() for s in P.STATS}
        grp_pg = {s: FA.groupby("grp")[s].mean() for s in P.STATS}
        f = R["fits"][str(y)]["pts"]
        rate = P.adjust(Z, "pts", P.rates(Z, "pts", f["m0"], grp_rate), b=f["b"], tag="1")
        b1, _, _ = P.base_means(Z, "pts", grp_rate, grp_pg)
        line = np.floor(b1) + 0.5
        li = np.floor(line).astype(int)
        K = P.SUP_FULL["pts"]
        amin = np.clip(np.round(Z.minutes.to_numpy()), 1, None)
        po, pa_ = [], []
        for b0 in range(0, len(Z), 4000):
            sl = slice(b0, b0 + 4000)
            c = P.mixture_pmf(rate[sl], q2[sl], f["r_T"], K)
            po.append(1 - np.cumsum(c, 1)[np.arange(len(c)), np.clip(li[sl], 0, K)])
            ca = P.nb_pmf(rate[sl] * amin[sl], f["r_T"], K)
            pa_.append(1 - np.cumsum(ca, 1)[np.arange(len(ca)), np.clip(li[sl], 0, K)])
        km = np.arange(1, 54)
        out.append(pd.DataFrame(dict(season=y, p_over=np.concatenate(po), p_over_actual_min=np.concatenate(pa_), over=(Z.pts.to_numpy() > line),
                                     line=line, rate=rate, exp_min=q2 @ km, p_short15=q2[:, :14].sum(1), minutes=Z.minutes.to_numpy(),
                                     pts=Z.pts.to_numpy(), mean_pred=rate * (q2 @ km))))
        print("season", y, flush=True)
    X = pd.concat(out, ignore_index=True)
    conf = X[X.p_over >= 0.8]
    low = X[X.p_short15 >= 0.2]

    def tab(G, by, bins):
        g = G.assign(b=pd.cut(G[by], bins))
        t = g.groupby("b", observed=True).agg(n=("over", "size"), pred=("p_over", "mean"), actual=("over", "mean"),
                                              pred_actual_minutes=("p_over_actual_min", "mean"), exp_min=("exp_min", "mean"),
                                              actual_min=("minutes", "mean"), mean_pred_pts=("mean_pred", "mean"), actual_pts=("pts", "mean"))
        return {str(k): {c: (round(float(v), 4) if c != "n" else int(v)) for c, v in r.items()} for k, r in t.iterrows()}
    res = dict(
        confident_group=dict(n=len(conf), pred=round(float(conf.p_over.mean()), 4), actual=round(float(conf.over.mean()), 4),
                             pred_with_actual_minutes=round(float(conf.p_over_actual_min.mean()), 4),
                             exp_min=round(float(conf.exp_min.mean()), 2), actual_min=round(float(conf.minutes.mean()), 2),
                             line_mean=round(float(conf.line.mean()), 2),
                             by_exp_minutes=tab(conf, "exp_min", [0, 10, 15, 20, 25, 30, 48]),
                             by_rate=tab(conf, "rate", [0, 0.2, 0.3, 0.4, 0.5, 0.7, 2]),
                             by_line=tab(conf, "line", [0, 2, 5, 10, 15, 20, 60])),
        low_minute_risk=dict(n=len(low), pred=round(float(low.p_over.mean()), 4), actual=round(float(low.over.mean()), 4),
                             pred_with_actual_minutes=round(float(low.p_over_actual_min.mean()), 4),
                             by_exp_minutes=tab(low, "exp_min", [0, 10, 15, 20, 25, 48])),
        all=dict(n=len(X), pred=round(float(X.p_over.mean()), 4), actual=round(float(X.over.mean()), 4),
                 by_line=tab(X, "line", [0, 2, 5, 10, 15, 20, 60])))
    with open(os.path.join(HERE, "nba_points_diag.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps({k: {a: b for a, b in v.items() if not isinstance(b, dict)} for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
