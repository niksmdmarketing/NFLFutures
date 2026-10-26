"""Pre-registered recalibration-layer test: research/NFL_RECALIBRATION_RULE.md. Research only; no live change.
Usage: python research/nfl_recalibration_test.py
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit, logit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import DIVS  # noqa: E402

WEEKS = (4, 8, 12)
TESTS = range(2016, 2026)
PRIOR_SD = .25
DIV_OF = {t: d for d, ts in DIVS.items() for t in ts}


def load(path, arm=None, model=None):
    r = pd.read_csv(path)
    if arm:
        r = r[r.arm == arm]
    if model:
        r = r[r.model == model]
    if "seedset" in r:
        r = r.groupby(["season", "week", "team"], as_index=False).mean(numeric_only=True)
    r = r[r.week.astype(str).isin([str(w) for w in WEEKS])].copy()
    r["week"] = r.week.astype(int)
    r["div"] = r.team.map(DIV_OF)
    r["conf"] = r["div"].str[:3]
    return r.reset_index(drop=True)


def divq(z, b):
    """q proportional to p^b within each division; decided (0/1) unchanged automatically."""
    p = z.p_div.to_numpy()
    w = np.where(p > 0, np.power(np.where(p > 0, p, 1.), b), 0.)
    s = pd.Series(w).groupby([z.season.to_numpy(), z["div"].to_numpy()]).transform("sum").to_numpy()
    return np.where(s > 0, w / s, p)


def playq(z, b, qdiv):
    """logistic(b logit p + c) per conference/snapshot, summing to the spots; floor at the division probability."""
    p = z.p_playoff.to_numpy(); out = p.copy()
    for (season, conf), idx in z.groupby(["season", "conf"]).indices.items():
        spots = 7 if season >= 2020 else 6
        pi, fl = p[idx], qdiv[idx]
        decided = (pi <= 0) | (pi >= 1)
        q = pi.copy(); free = ~decided
        x = logit(np.clip(pi, 1e-12, 1 - 1e-12))
        for _ in range(40):
            need = spots - q[~free].sum()
            lo, hi = -50., 50.
            for _ in range(200):
                c = (lo + hi) / 2
                if expit(b * x[free] + c).sum() > need: hi = c
                else: lo = c
            q[free] = expit(b * x[free] + c)
            below = free & (q < fl - 1e-12)
            if not below.any():
                break
            q[below] = fl[below]; free = free & ~below
        out[idx] = q
    return out


def nll(q, y):
    q = np.clip(q, 1e-6, 1 - 1e-6)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q)).sum()


def fit(train):
    pen = lambda b: (b - 1) ** 2 / (2 * PRIOR_SD ** 2)
    bd = minimize_scalar(lambda b: nll(divq(train, b), train.y_div.to_numpy()) + pen(b), bounds=(.05, 4), method="bounded").x
    qd = divq(train, bd)
    bp = minimize_scalar(lambda b: nll(playq(train, b, qd), train.y_playoff.to_numpy()) + pen(b), bounds=(.05, 4), method="bounded").x
    return float(bd), float(bp)


def score(p, y):
    p = np.clip(p, .001, .999)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def slope(p, y):
    p = np.clip(p, .001, .999); x = np.log(p / (1 - p))
    f = lambda t: np.sum(np.logaddexp(0, t[0] + t[1] * x) - y * (t[0] + t[1] * x))
    return minimize(f, [0, 1], method="Nelder-Mead").x


def run(r):
    preds, fits = [], {}
    for Y in TESTS:
        for w in WEEKS:
            tr = r[(r.week == w) & r.season.between(2013, Y - 1)].reset_index(drop=True)
            te = r[(r.week == w) & (r.season == Y)].reset_index(drop=True)
            bd, bp = fit(tr)
            qd = divq(te, bd); qp = playq(te, bp, qd)
            fits[f"{Y}_w{w}"] = dict(division_slope=bd, playoff_slope=bp)
            preds.append(te.assign(q_div=qd, q_playoff=qp))
    P = pd.concat(preds, ignore_index=True)
    cells = {}
    for (s, w), z in P.groupby(["season", "week"]):
        for m in ("div", "playoff"):
            cells[(s, w, m)] = float((score(z["p_" + m], z["y_" + m]) - score(z["q_" + m], z["y_" + m])).mean())
    seasons = list(TESTS)
    g = np.array([np.mean([cells[(s, w, m)] for w in WEEKS for m in ("div", "playoff")]) for s in seasons])
    rng = np.random.default_rng(20261026)
    boot = g[rng.integers(0, len(g), (10000, len(g)))].mean(1)
    mk = {m: float(np.mean([cells[(s, w, m)] for s in seasons for w in WEEKS])) for m in ("div", "playoff")}
    cell_gain = {f"{m}_w{w}": float(np.mean([cells[(s, w, m)] for s in seasons])) for m in ("div", "playoff") for w in WEEKS}
    recent = np.array(seasons) >= 2020
    rec_cp = {f"w{w}": float(np.mean([cells[(s, w, m)] for s in seasons if s >= 2020 for m in ("div", "playoff")])) for w in WEEKS}
    loso = {str(s): float(np.delete(g, i).mean()) for i, s in enumerate(seasons)}
    cal = {}
    for m in ("div", "playoff"):
        for w in WEEKS:
            z = P[P.week == w]
            a0, b0 = slope(z["p_" + m].to_numpy(), z["y_" + m].to_numpy()); a1, b1 = slope(z["q_" + m].to_numpy(), z["y_" + m].to_numpy())
            bs = []
            for _ in range(400):
                pick = rng.choice(seasons, len(seasons)); zz = pd.concat([z[z.season == s] for s in pick])
                bs.append(slope(zz["q_" + m].to_numpy(), zz["y_" + m].to_numpy())[1])
            cal[f"{m}_w{w}"] = dict(n=len(z), v4_intercept=float(a0), v4_slope=float(b0), recal_intercept=float(a1), recal_slope=float(b1),
                                    recal_slope_90=[float(v) for v in np.percentile(bs, [5, 95])])
    gates = {"1_lower90_and_7of10": bool(np.quantile(boot, .10) > 0 and (g > 0).sum() >= 7),
             "2_division_and_playoff_positive": bool(mk["div"] > 0 and mk["playoff"] > 0),
             "3_positive_2020_25": bool(g[recent].mean() > 0),
             "4_no_cell_worse_0.002": bool(all(v >= -.002 for v in cell_gain.values())),
             "5_slope_guardrail_0.80_1.25": bool(all(.80 <= c["recal_slope"] <= 1.25 for c in cal.values()))}
    return P, dict(primary_gain=float(g.mean()), lower90=float(np.quantile(boot, .10)), seasons_better=int((g > 0).sum()),
                   by_season={str(s): float(v) for s, v in zip(seasons, g)}, market_gain=mk, cell_gain=cell_gain,
                   gain_2020_25=float(g[recent].mean()), gain_2020_25_by_checkpoint=rec_cp, leave_one_season_out=loso,
                   calibration=cal, fitted_slopes=fits, gates=gates, passes=all(gates.values()))


def main():
    started = datetime.now(timezone.utc).isoformat()
    r = load(os.path.join(ROOT, "research", "nfl_tau_fade_rows.csv"), arm="v4")
    # Identity check: slope 1 reproduces v4.
    assert np.allclose(divq(r, 1.), r.p_div, atol=1e-9)
    qd = divq(r, 1.); qp = playq(r, 1., qd)
    identity_max = float(np.abs(qp - r.p_playoff).max())
    floor_violations_v4 = int((r.p_playoff < r.p_div - 1e-9).sum())
    P, res = run(r)
    P.to_csv(os.path.join(ROOT, "research", "nfl_recalibration_predictions.csv"), index=False)
    _, chk = run(load(os.path.join(ROOT, "research", "nfl_futures_diagnosis_rows_format_fix.csv"), model="v4wf"))
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    out = dict(rule="research/NFL_RECALIBRATION_RULE.md", started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
               identity_max_abs_playoff_diff=identity_max, v4_floor_violations=floor_violations_v4, verdict="pass" if res["passes"] else "fail",
               primary=res, consistency_check_3000_sims={k: chk[k] for k in ("primary_gain", "lower90", "seasons_better", "market_gain", "gain_2020_25", "gates")},
               code_sha256=sha(__file__), rule_sha256=sha(os.path.join(ROOT, "research", "NFL_RECALIBRATION_RULE.md")))
    open(os.path.join(ROOT, "research", "nfl_recalibration_results.json"), "w").write(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("verdict", "identity_max_abs_playoff_diff", "v4_floor_violations")} |
                     {"primary": {k: res[k] for k in ("primary_gain", "lower90", "seasons_better", "market_gain", "cell_gain", "gain_2020_25",
                                                      "gain_2020_25_by_checkpoint", "gates")},
                      "consistency": out["consistency_check_3000_sims"]}, indent=2))


if __name__ == "__main__":
    main()
