"""NBA bench/fringe diagnostic (22 Oct 2026; agreed with GPT): where does the remaining bench over-forecast come from?
Diagnostic only on development seasons 2022-2026 (walk-forward fits as in research/nba_minutes_m2b_test.py). No model change follows
automatically. Reading rule, written before running:
  Minutes (given appearing), per fixed group and season, M2 and M2b:
    - share of actual minutes at or below the forecast's own 10/25/50/75/90% quantiles (randomised PIT; ideal = the level);
    - predicted vs actual P(minutes >= 20, 25, 30).
    'Shift' if, in at least 4 of 5 seasons, the share below the median exceeds 0.52 and the share below q75 and q90 also exceed their levels.
    'Spread' if the share below the median is within 0.48-0.52 in at least 4 of 5 seasons while the share below q90 exceeds 0.92.
    Otherwise 'no consistent pattern' (a wrong mix of rotation roles is not distinguishable from spread here).
  Stats (reb, ast, pts; given appearing), per group and season: mean forecast with forecast minutes (rate x E[min | appear]), mean
    with actual minutes (rate x actual minutes; hindsight, affected by fouls, blowouts, performance) and actual mean.
    The error splits into a minutes part (rate x (E[min] - actual)) and a per-minute part (rate x actual - actual stat). A per-minute
    problem is flagged only if its share is the same sign in at least 4 of 5 seasons and above 1% of the actual mean.
Fixed groups, from pre-game information only: bench = start10 < 0.5; risk = stage-one P(minutes < 15 | appear) >= 0.2;
established = stage-one expected minutes given appearing >= 25.
  python research/nba_bench_diag.py  -> research/nba_bench_diag.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_minutes_test as M  # noqa: E402
import nba_props_simple_test as P  # noqa: E402
import nba_minutes_tail_test as T  # noqa: E402
import nba_minutes_m2b_test as B  # noqa: E402

K = np.arange(1, M.MAXM + 1)
LEVELS = [0.10, 0.25, 0.50, 0.75, 0.90]


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D = T.features(D)
    rng = np.random.default_rng(23)
    out = {"minutes": {}, "stats": {}}
    for y in P.TEST:
        F = D[(D.season < y) & (D.season >= 2017)]
        fit = T.fit_m2(F)
        Z = D[D.season == y].reset_index(drop=True)
        q1 = M.disc_normal(Z.mu1.to_numpy(), Z.sd1.to_numpy())
        groups = {"bench": (Z.start10.fillna(0).to_numpy() < 0.5), "risk": q1[:, :14].sum(1) >= 0.2,
                  "established": Z.emin_app1.to_numpy() >= 25}
        app = Z.app.to_numpy()
        ym = Z.minutes.to_numpy()
        yk = np.clip(np.round(ym), 1, M.MAXM).astype(int)
        F_app = F[F.app]
        grp_rate = {s: F_app.groupby("grp")[s].sum() / F_app.groupby("grp").minutes.sum() for s in P.STATS}
        for ver, matched in (("M2", False), ("M2b", True)):
            q, _ = B.q_m2(Z, fit, matched)
            Fq = np.cumsum(q, 1)
            hi = Fq[np.arange(len(yk)), yk - 1]
            lo = np.where(yk > 1, Fq[np.arange(len(yk)), np.maximum(yk - 2, 0)], 0.0)
            pit = lo + rng.random(len(yk)) * (hi - lo)
            em = q @ K
            for g, msk in groups.items():
                m = msk & app
                rec = {"n": int(m.sum()), "pred_mean": round(float(em[m].mean()), 3), "actual_mean": round(float(ym[m].mean()), 3),
                       "share_below": {str(l): round(float((pit[m] <= l).mean()), 4) for l in LEVELS},
                       "p_ge": {str(t): {"pred": round(float(q[m][:, t - 1:].sum(1).mean()), 4), "actual": round(float((ym[m] >= t).mean()), 4)}
                                for t in (20, 25, 30)}}
                out["minutes"].setdefault(ver, {}).setdefault(g, {})[int(y)] = rec
            for s in P.STATS:
                f = R["fits"][str(y)][s]
                rate = P.rates(Z, s, f["m0"], grp_rate)
                _, kind = T.VERS[s]
                rate_f = P.adjust(Z, s, rate, b=f["b"], tag="1") if kind == "b" else P.adjust(Z, s, rate, c=f["c"])
                ys = Z[s].to_numpy()
                for g, msk in groups.items():
                    m = msk & app
                    with_pred = rate_f[m] * em[m]
                    with_act = rate_f[m] * ym[m]
                    out["stats"].setdefault(ver, {}).setdefault(s, {}).setdefault(g, {})[int(y)] = {
                        "n": int(m.sum()), "forecast_minutes": round(float(with_pred.mean()), 4), "actual_minutes": round(float(with_act.mean()), 4),
                        "actual": round(float(ys[m].mean()), 4), "minutes_part": round(float((with_pred - with_act).mean()), 4),
                        "per_minute_part": round(float((with_act - ys[m]).mean()), 4)}
        print("season", y, flush=True)
    # reading rule
    verdict = {}
    for ver, gs in out["minutes"].items():
        for g, ss in gs.items():
            sh = [r["share_below"] for r in ss.values()]
            shift = sum(x["0.5"] > 0.52 and x["0.75"] > 0.75 and x["0.9"] > 0.90 for x in sh) >= 4
            spread = sum(0.48 <= x["0.5"] <= 0.52 and x["0.9"] > 0.92 for x in sh) >= 4
            verdict[f"minutes:{ver}:{g}"] = "shift" if shift else "spread" if spread else "no consistent pattern"
    for ver, st in out["stats"].items():
        for s, gs in st.items():
            for g, ss in gs.items():
                rel = [r["per_minute_part"] / r["actual"] for r in ss.values() if r["actual"] > 0]
                flag = (sum(v > 0.01 for v in rel) >= 4) or (sum(v < -0.01 for v in rel) >= 4)
                verdict[f"per_minute:{ver}:{s}:{g}"] = ("over" if np.mean(rel) > 0 else "under") + " per minute (consistent)" if flag else "no consistent per-minute bias"
    out["verdict"] = verdict
    out["label"] = "Diagnostic on development seasons; narrows possibilities, does not prove a cause; no model change follows automatically."
    json.dump(out, open(os.path.join(HERE, "nba_bench_diag.json"), "w"), indent=1)
    print(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    main()
