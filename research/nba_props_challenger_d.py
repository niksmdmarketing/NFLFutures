"""Challenger "d" for research/NBA_PROPS_PRICE_TEST_RULE.md (Amendment 9): position-specific teammate absence in the per-minute rates
(and a team-level absence term for rebounds). Minutes, appearance, opponent and every other part are the frozen model (params "b").

  python research/nba_props_challenger_d.py check <dev_rows.parquet>     fit < 15 Dec 2025, holdout 15 Dec .. 11 Jan (log score)
  python research/nba_props_challenger_d.py freeze <dev_rows.parquet>    refit kept stats on all dev rows -> model/nba_props_challenger_d.json
  python research/nba_props_challenger_d.py selftest

rate_d(Z, s, pp, coef) is used by the replay driver (research/nba_props_d_replay.py) to forecast priced games.
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nba_props_live_core as C          # noqa: E402
import nba_props_simple_test as PS       # noqa: E402

DEV_END = pd.Timestamp("2026-01-12T00:00:00Z")
HOLD_START = pd.Timestamp("2025-12-15T00:00:00Z")
E_GRID = np.round(np.arange(0, 1.5001, 0.05), 2)
B_GRID = np.round(np.arange(0, 1.0001, 0.05), 2)
SUP = {"pts": 100, "reb": 45, "ast": 35}
OUT = os.path.join(ROOT, "model", "nba_props_challenger_d.json")


def params_b(season=2026):
    return json.load(open(os.path.join(ROOT, "model", f"nba_props_live_params_{season}b.json")))


def v_same(Z, s, tag="1"):
    """Expected missing share of the team's s from teammates in the player's own position group (own absence excluded)."""
    tot = Z.groupby(["game_id", "team"])[f"share_{s}"].transform("sum").replace(0, np.nan)
    miss = Z[f"share_{s}"] * (1 - Z[f"pa{tag}"])
    grp = miss.groupby([Z.game_id, Z.team, Z.grp]).transform("sum")
    return ((grp - miss) / tot).fillna(0.0).to_numpy()


def x_term(Z, s, w):
    return v_same(Z, s) - w * Z[f"V_now1_{s}"].to_numpy()


def rate_d(Z, s, pp, coef):
    """Frozen rate times the d absence factors; coef = {"e": .., "w": .., "b_team": .. (rebounds only)} or None (frozen)."""
    rate, _ = C.prop_rate(Z, s, pp)
    if not coef:
        return rate
    out = rate * np.clip(1 + coef["e"] * x_term(Z, s, coef["w"]), 0.2, 3.0)
    if coef.get("b_team"):
        V = Z[f"V_now1_{s}"].to_numpy() - Z[f"V_ref_{s}"].to_numpy()
        out = out * np.clip(1 + coef["b_team"] * V, 0.2, 3.0)
    return out


def weight(Z, s):
    V = Z[f"V_now1_{s}"].to_numpy()
    vs = v_same(Z, s)
    m = V > 1e-6
    return float(np.mean(vs[m] / V[m])) if m.any() else 0.0


def fit_stat(A, s, pp):
    """Grid search of e (and the rebounds team term) by negative-binomial likelihood given actual minutes; dispersion refitted."""
    y, mins = A[s].to_numpy(), A.minutes.to_numpy()
    w = weight(A, s)
    _, r0 = C.prop_rate(A, s, pp)
    best = None
    for e in E_GRID:
        for bt in (B_GRID if s == "reb" else [0.0]):
            coef = {"e": float(e), "w": w, "b_team": float(bt)}
            ll = PS.nb_logpmf(y, rate_d(A, s, pp, coef) * mins, r0).sum()
            if best is None or ll > best[1]:
                best = (coef, ll)
    coef = best[0]
    coef["r"], _ = PS.fit_r(y, rate_d(A, s, pp, coef) * mins)
    return coef


def dists(Z, s, pp, coef, m2, ptsD):
    """Appearing-conditional pmfs: frozen M2 minutes mixed with the (d or frozen) rate, as the live forecaster does."""
    q, _ = C.q_m2(Z, m2, False)
    rate = rate_d(Z, s, pp, coef)
    if s == "pts":
        import nba_points_dispersion_test as DT
        return DT.mix(rate, q, lambda mu: DT.r_of(mu, ptsD["a"], ptsD["b"]))
    r = coef["r"] if coef else C.prop_rate(Z, s, pp)[1]
    return PS.mixture_pmf(rate, q, r, SUP[s])


def logscore(P, y):
    y = np.minimum(np.asarray(y, int), P.shape[1] - 1)
    return float(np.mean(np.log(np.maximum(P[np.arange(len(y)), y], 1e-9))))


def _load(path):
    F = pd.read_parquet(path)
    F["tip"] = pd.to_datetime(F.tip, utc=True)
    F = F[(F.tip < DEV_END) & F.app & (F.minutes > 0)].reset_index(drop=True)
    return F


def check(path):
    F = _load(path)
    pb = params_b()
    ptsD = json.load(open(os.path.join(ROOT, "model", "nba_points_d_params_2026.json")))
    A = F[F.tip < HOLD_START].reset_index(drop=True)
    H = F[(F.tip >= HOLD_START) & (F.season == 2026)].reset_index(drop=True)
    res = {"n_fit": len(A), "n_holdout": len(H), "stats": {}}
    for s in C.STATS:
        coef = fit_stat(A, s, pb["props"])
        lb = logscore(dists(H, s, pb["props"], None, pb["m2"], ptsD), H[s])
        ld = logscore(dists(H, s, pb["props"], coef, pb["m2"], ptsD), H[s])
        res["stats"][s] = dict(coef=coef, holdout_logscore_b=lb, holdout_logscore_d=ld, keep=bool(ld > lb))
    json.dump(res, open(os.path.join(HERE, "nba_props_challenger_d_check.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


def freeze(path):
    chk = json.load(open(os.path.join(HERE, "nba_props_challenger_d_check.json")))
    F = _load(path)
    pb = params_b()
    coefs = {s: (fit_stat(F, s, pb["props"]) if chk["stats"][s]["keep"] else None) for s in C.STATS}
    out = dict(version="d", rule="research/NBA_PROPS_PRICE_TEST_RULE.md Amendment 9", dev_end=str(DEV_END), n_dev=len(F), coef=coefs,
               note="points keep the frozen points-D dispersion function; rebounds and assists use the refitted dispersion r")
    json.dump(out, open(OUT, "w"), indent=1)
    print(OUT, hashlib.sha256(open(OUT, "rb").read()).hexdigest(), {s: bool(c) for s, c in coefs.items()})


def selftest():
    Z = pd.DataFrame(dict(game_id=1, team=["A"] * 4 + ["B"] * 2, grp=["G", "G", "B", "B", "G", "B"], share_pts=[10, 10, 5, 5, 8, 8],
                          pa1=[1.0, 0.0, 1.0, 1.0, 1.0, 1.0]))
    vs = v_same(Z, "pts")
    # player 0 (guard, team A): the other guard (share 10 of 30) is out -> 1/3; bigs on team A see no same-position absence
    assert abs(vs[0] - 1 / 3) < 1e-9 and vs[1] == 0 and vs[2] == 0 and vs[4] == 0, vs
    print("selftest passed")


if __name__ == "__main__":
    {"check": lambda: check(sys.argv[2]), "freeze": lambda: freeze(sys.argv[2]), "selftest": selftest}[sys.argv[1]]()
