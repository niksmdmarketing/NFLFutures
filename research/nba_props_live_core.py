"""Frozen fit / predict functions for the NBA props forward test (research/NBA_MINUTES_M2B_RULE.md, forward-test protocol).
The fitting reproduces the research code exactly (stage one: research/nba_game_env_test.minutes; M2: research/nba_minutes_tail_test;
M2b: research/nba_minutes_m2b_test; props: research/nba_props_simple_test), but writes every fitted number to a JSON file so the
live forecaster only evaluates frozen formulas.
  python research/nba_props_live_core.py freeze <season>   -> model/nba_props_live_params_<season>.json
  python research/nba_props_live_core.py verify <season>   -> checks frozen predictions against the research functions on season rows
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import nba_minutes_test as M  # noqa: E402

PM = ["Out", "Doubtful", "Questionable", "Probable", "Available"]
FILL = {"app10": 0.5, "mpg10": 12.0, "ewm": 12.0, "season_mpg": 12.0, "season_app": 0.5}
STATS = ["pts", "reb", "ast"]
K = np.arange(1, M.MAXM + 1)


# ---------------------------------------------------------------- stage one
def prep(D):
    D = D.copy()
    for c in ("st1", "st6"):
        D[c] = D[c].fillna("")
    D["newcomer"] = D["ewm"].isna()
    for c, v in FILL.items():
        D[c] = D[c].fillna(v)
    D["early"] = (D.gi < 10).astype(float)
    return D


def Xf(Z, tag):
    return np.column_stack([Z.app10, Z.mpg10 / 48, Z.start10, np.log1p(Z.streak), Z["vac_same" + tag] / 48, Z["vac_other" + tag] / 48,
                            Z.early, Z["ewm"] / 48, Z.newcomer.astype(float)])


def Xm(Z, tag):
    return np.column_stack([np.ones(len(Z)), Z["ewm"], Z.season_mpg, Z["vac_same" + tag] * Z["ewm"] / 36, Z["vac_other" + tag] * Z["ewm"] / 36,
                            ((Z.streak >= 2) & (Z["st" + tag] != "Out")).astype(float), Z.start10, Z.early, Z.newcomer.astype(float)])


def sd_coef(mu, y):
    X = np.column_stack([np.ones(len(mu)), mu])
    return [float(v) for v in np.linalg.lstsq(X, np.abs(y - mu) * np.sqrt(np.pi / 2), rcond=None)[0]]


def sd_eval(c, m):
    return np.clip(c[0] + c[1] * m, 2.0, 15.0)


def fit_stage1(D, s, tag, lo):
    from sklearn.linear_model import LogisticRegression
    T = D[(D.season < s) & (D.season >= lo)]
    pmiss = {k: float(1 - T[T["st" + tag] == k].y_app.mean()) for k in PM if (T["st" + tag] == k).sum() > 50}
    ok = ~T["st" + tag].isin(["Out", "Doubtful", "Questionable"])
    lr = LogisticRegression(C=1.0, max_iter=500).fit(Xf(T[ok], tag), T[ok].y_app)
    P = T[T.minutes > 0]
    bm = np.linalg.lstsq(Xm(P, tag), P.minutes.to_numpy(), rcond=None)[0]
    muP = np.clip(Xm(P, tag) @ bm, 1, 48)
    return dict(pmiss=pmiss, lr_coef=[float(v) for v in lr.coef_[0]], lr_intercept=float(lr.intercept_[0]), bm=[float(v) for v in bm],
                sd=sd_coef(muP, P.minutes.to_numpy()))


def predict_stage1(Z, p, tag):
    pm = Z["st" + tag].map(p["pmiss"]).fillna(0.0).to_numpy()
    z = Xf(Z, tag) @ np.array(p["lr_coef"]) + p["lr_intercept"]
    pa = (1 - pm) / (1 + np.exp(-z))
    mu = np.clip(Xm(Z, tag) @ np.array(p["bm"]), 1, 48)
    return pa, mu, sd_eval(p["sd"], mu)


# ---------------------------------------------------------------- M2 / M2b
SHORT = 0.6
RATIO_BINS = np.linspace(0, SHORT, 61)


def m2_inputs(Z):
    """M2 pi inputs; Z needs columns of research/nba_minutes_tail_test.features (mu1, st1, absm, b2b, s_sum, s_cnt, early)."""
    return Z


def x_pi(Z, league):
    sh = (Z.s_sum + 10 * league) / (Z.s_cnt + 10)
    stq = (Z.st1 == "Questionable").astype(float) + Z.st1.isin(["Out", "Doubtful"]).astype(float)
    return np.column_stack([Z.mu1 / 48, stq, (Z.st1 == "Probable").astype(float), (Z.st1 == "Available").astype(float), Z.absm / 10, Z.b2b, sh,
                            Z.early])


def x_mean2(Z):
    ewm_f = Z["ewm"].where(Z["ewm"] > 0, 12.0)
    newc = (Z["ewm"] <= 0).astype(float)
    return np.column_stack([np.ones(len(Z)), ewm_f, Z.season_mpg.fillna(12.0), Z.vac_same1 * ewm_f / 36, Z.vac_other1 * ewm_f / 36,
                            ((Z.streak >= 2) & (Z.st1 != "Out")).astype(float), Z.start10, Z.early, newc])


def fit_m2(F):
    """F: rows (research tail-test features) of the fitting seasons. Mirrors nba_minutes_tail_test.fit_m2."""
    import nba_minutes_tail_test as T
    f = T.fit_m2(F)
    A = F[F.app]
    N = A[~A.short]
    muN = np.clip(T.x_mean(N) @ f["bm"], 1, 48)
    return dict(pi_coef=[float(v) for v in f["lr"].coef_[0]], pi_intercept=float(f["lr"].intercept_[0]), league=float(f["league"]),
                bm=[float(v) for v in f["bm"]], sd=sd_coef(muN, N.minutes.to_numpy()), ratio=[float(v) for v in f["ratio"]])


_z = np.linspace(-8, 6, 4001)
_lam = norm.pdf(_z) / norm.sf(_z)
_g = (_lam - _z) / np.sqrt(1 + _z * _lam - _lam ** 2)


def _match(tm, ts, t):
    r = np.clip((tm - t) / ts, _g[-1] + 1e-6, _g[0])
    z = np.interp(r, _g[::-1], _z[::-1])
    lam = norm.pdf(z) / norm.sf(z)
    sig = ts / np.sqrt(1 + z * lam - lam ** 2)
    return t - sig * z, sig


def q_m2(Z, p, matched):
    """minutes given appearing, k = 1..53, under M2 (matched=False) or M2b (matched=True); returns (q, pi)."""
    zlin = x_pi(Z, p["league"]) @ np.array(p["pi_coef"]) + p["pi_intercept"]
    pi = 1 / (1 + np.exp(-zlin))
    mu2 = np.clip(x_mean2(Z) @ np.array(p["bm"]), 1, 48)
    sd2 = sd_eval(p["sd"], mu2)
    thr = SHORT * Z.mu1.to_numpy()
    if matched:
        loc, sc = _match(mu2, sd2, np.maximum(np.ceil(thr), 1) - 0.5)
    else:
        loc, sc = mu2, sd2
    c = norm.cdf((K[None, :] + 0.5 - loc[:, None]) / sc[:, None]) - norm.cdf((K[None, :] - 0.5 - loc[:, None]) / sc[:, None])
    c = np.where(K[None, :] >= thr[:, None], np.clip(c, 1e-12, None), 0.0)
    tot = c.sum(1, keepdims=True)
    c = np.where(tot > 0, c / np.where(tot > 0, tot, 1), 0.0)
    c[(tot[:, 0] <= 0), -1] = 1.0
    centers = (RATIO_BINS[:-1] + RATIO_BINS[1:]) / 2
    mins = np.clip(np.round(centers[None, :] * Z.mu1.to_numpy()[:, None]), 1, M.MAXM).astype(int)
    s = np.zeros((len(Z), M.MAXM))
    ratio = np.array(p["ratio"])
    for j in range(len(centers)):
        np.add.at(s, (np.arange(len(Z)), mins[:, j] - 1), ratio[j])
    s = np.where(K[None, :] < np.maximum(thr[:, None], 1.0001), s, 0.0)
    st = s.sum(1, keepdims=True)
    s = np.where(st > 0, s / np.where(st > 0, st, 1), 0.0)
    s[(st[:, 0] <= 0), 0] = 1.0
    return pi[:, None] * s + (1 - pi[:, None]) * c, pi


# ---------------------------------------------------------------- props
def fit_props(F):
    """F: prop rows (research/nba_props_simple_test build) of the fitting seasons, appearances only. Mirrors the research score() fits."""
    import nba_props_simple_test as P
    grp_rate = {s: (F.groupby("grp")[s].sum() / F.groupby("grp").minutes.sum()).to_dict() for s in STATS}
    out = {"grp_rate": grp_rate}
    for s in STATS:
        y = F[s].to_numpy()
        mins = F.minutes.to_numpy()
        gr = {s: pd.Series(grp_rate[s])}
        best = None
        for m0 in P.M0_GRID:
            r_, ll = P.fit_r(y, P.rates(F, s, m0, gr) * mins)
            if best is None or ll > best[2]:
                best = (m0, r_, ll)
        m0, rP, _ = best
        rate = P.rates(F, s, m0, gr)
        bb = max(np.arange(0, 1.0001, 0.05), key=lambda b: P.nb_logpmf(y, P.adjust(F, s, rate, b=b) * mins, rP).sum())
        rT, _ = P.fit_r(y, P.adjust(F, s, rate, b=bb) * mins)
        cc = max(np.arange(0, 1.0001, 0.05), key=lambda c: P.nb_logpmf(y, P.adjust(F, s, rate, c=c) * mins, rP).sum())
        rO, _ = P.fit_r(y, P.adjust(F, s, rate, c=cc) * mins)
        out[s] = dict(m0=m0, r_P=rP, b=float(bb), r_T=rT, c=float(cc), r_O=rO)
    return out


VERSION_OF = {"pts": "P+T", "reb": "P+O", "ast": "P+T"}


def prop_rate(Z, s, pp):
    import nba_props_simple_test as P
    gr = {s: pd.Series(pp["grp_rate"][s])}
    f = pp[s]
    rate = P.rates(Z, s, f["m0"], gr)
    if VERSION_OF[s] == "P+T":
        return P.adjust(Z, s, rate, b=f["b"], tag="1"), f["r_T"]
    return P.adjust(Z, s, rate, c=f["c"]), f["r_O"]


# ---------------------------------------------------------------- freeze
def freeze(season):
    import nba_minutes_tail_test as T
    import nba_props_simple_test as P
    D = prep(pd.read_csv(M.ROWS, low_memory=False))
    D["fallback"] = D.fallback.fillna(0)
    D = D[(D.fallback == 0) & (D.aid != -1)].copy()
    D["y_app"] = (D.minutes > 0).astype(float)
    stage1 = {tag: fit_stage1(D, season, tag, lo=2020) for tag in ("1", "6")}
    R = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    R = R[R.fallback == 0].reset_index(drop=True)
    R = T.features(R)
    F = R[(R.season < season) & (R.season >= 2017)]
    m2 = fit_m2(F)
    props = fit_props(F[F.app])
    out = dict(season=season, stage1=stage1, m2=m2, props=props,
               provenance=dict(stage1="research/NBA_MINUTES_RULE.md (fit 2020..s-1)", m2="research/NBA_MINUTES_TAIL_RULE.md (fit 2017..s-1)",
                               m2b="research/NBA_MINUTES_M2B_RULE.md (same parameters as M2; normal-night part moment-matched)",
                               props="research/NBA_PROPS_SIMPLE_RULE.md (fit 2017..s-1); versions pts P+T, reb P+O, ast P+T"))
    path = os.path.join(ROOT, "model", f"nba_props_live_params_{season}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    print(path, hashlib.sha256(open(path, "rb").read()).hexdigest())


def verify(season):
    """frozen-parameter predictions must equal the research functions' predictions for that season's rows."""
    import nba_minutes_tail_test as T
    import nba_minutes_m2b_test as B
    p = json.load(open(os.path.join(ROOT, "model", f"nba_props_live_params_{season}.json")))
    # stage one vs research proj_minutes
    D = prep(pd.read_csv(M.ROWS, low_memory=False))
    D["fallback"] = D.fallback.fillna(0)
    D = D[(D.fallback == 0) & (D.aid != -1) & (D.season == season)].copy()
    PJ = pd.read_csv(os.path.join(T.P.W, "proj_minutes.csv.gz"), dtype={"tag": str})
    out = {}
    for tag in ("1", "6"):
        pa, mu, sd = predict_stage1(D, p["stage1"][tag], tag)
        Q = PJ[(PJ.tag == tag) & (PJ.season == season)].drop_duplicates(["game_id", "team", "aid"]).set_index(["game_id", "team", "aid"])
        J = Q.reindex(pd.MultiIndex.from_arrays([D.game_id, D.team, D.aid.astype(int)]))
        out["stage1_" + tag] = dict(max_abs_pa=float(np.nanmax(np.abs(J.pa.to_numpy() - pa))), max_abs_mu=float(np.nanmax(np.abs(J.mu.to_numpy() - mu))),
                                    max_abs_sd=float(np.nanmax(np.abs(J.sd.to_numpy() - sd))))
    R = pd.read_parquet(os.path.join(T.P.W, "props_rows.parquet"))
    R = R[R.fallback == 0].reset_index(drop=True)
    R = T.features(R)
    F = R[(R.season < season) & (R.season >= 2017)]
    Z = R[R.season == season].reset_index(drop=True).head(3000)
    f = T.fit_m2(F)
    q2r, _ = T.m2_q(Z, f)
    q3r, _ = B.q_m2(Z, f, True)
    q2, _ = q_m2(Z, p["m2"], False)
    q3, _ = q_m2(Z, p["m2"], True)
    out["M2_max_abs"] = float(np.abs(q2 - q2r).max())
    out["M2b_max_abs"] = float(np.abs(q3 - q3r).max())
    res = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))["fits"].get(str(season))
    if res:
        out["props_fit_match"] = {s: {k: (round(p["props"][s][k], 6), round(res[s][k], 6)) for k in ("m0", "r_P", "b", "r_T", "c", "r_O")} for s in STATS}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"freeze": lambda: freeze(int(sys.argv[2])), "verify": lambda: verify(int(sys.argv[2]))}[sys.argv[1]]()
