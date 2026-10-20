"""NBA points dispersion test per research/NBA_POINTS_DISPERSION_RULE.md (with amendment 1).
python research/nba_points_dispersion_test.py -> research/nba_points_dispersion_results.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_minutes_tail_test as T  # noqa: E402
import nba_props_simple_test as P  # noqa: E402

K = P.SUP_FULL["pts"]
KM = np.arange(1, 54)


def nb_logpmf_r(k, mu, r):
    mu = np.maximum(mu, 0.01)
    return gammaln(k + r) - gammaln(r) - gammaln(k + 1) + r * np.log(r / (r + mu)) + k * np.log(mu / (r + mu))


def r_of(mu, a, b):
    return np.exp(a + b * np.log(np.maximum(mu, 0.01)))


def fit_ab(y, mu):
    f = lambda p: -nb_logpmf_r(y, mu, r_of(mu, p[0], p[1])).sum()
    o = minimize(f, x0=[np.log(7.5), 0.0], method="Nelder-Mead", options=dict(xatol=1e-6, fatol=1e-4, maxiter=2000))
    return [float(o.x[0]), float(o.x[1])], -float(o.fun)


def mix(rate, q, rfun):
    """P(k | appear) = sum_m q(m) NB(k; rate m, r(rate m)), k = 0..K."""
    mu = np.maximum(rate[:, None] * KM[None, :], 0.01)
    r = rfun(mu)
    k = np.arange(K + 1, dtype=float)
    lp = nb_logpmf_r(k[None, None, :], mu[:, :, None], r[:, :, None])
    Pm = np.einsum("nm,nmk->nk", q, np.exp(lp))
    Pm[:, -1] += np.clip(1 - Pm.sum(1), 0, None)
    return Pm


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D = T.features(D)
    rng = np.random.default_rng(23)
    rows, fits = [], {}
    for y in P.TEST:
        F = D[(D.season < y) & (D.season >= 2017)]
        Z = D[D.season == y].reset_index(drop=True)
        fit = T.fit_m2(F)
        q2, _ = T.m2_q(Z, fit)
        FA = F[F.app]
        grp_rate = {s: FA.groupby("grp")[s].sum() / FA.groupby("grp").minutes.sum() for s in P.STATS}
        grp_pg = {s: FA.groupby("grp")[s].mean() for s in P.STATS}
        f = R["fits"][str(y)]["pts"]
        rate_F = P.adjust(FA, "pts", P.rates(FA, "pts", f["m0"], grp_rate), b=f["b"], tag="1")
        (a, b), ll = fit_ab(FA.pts.to_numpy(), rate_F * FA.minutes.to_numpy())
        fits[int(y)] = dict(a=a, b=b, r_const=f["r_T"])
        rate = P.adjust(Z, "pts", P.rates(Z, "pts", f["m0"], grp_rate), b=f["b"], tag="1")
        b1, b2, r3 = P.base_means(Z, "pts", grp_rate, grp_pg)
        pa = np.clip(Z.pa1.to_numpy(), 1e-3, 1 - 1e-3)
        yv = Z.pts.to_numpy()
        app = Z.app.to_numpy()
        li = np.floor(np.floor(b1) + 0.5).astype(int)
        out = dict(season=np.full(len(Z), y), tip=Z.tip.to_numpy(), app=app, pts=yv, exp_min=q2 @ KM, p_short15=q2[:, :14].sum(1),
                   rate=rate, over=yv > (np.floor(b1) + 0.5))
        models = {"R": ("mix", rate, lambda mu, r_=f["r_T"]: np.full_like(mu, r_)), "D": ("mix", rate, lambda mu, a_=a, b_=b: r_of(mu, a_, b_)),
                  "B1": ("nb", b1, f["r_B1"]), "B2": ("nb", b2, f["r_B2"]), "B3": ("nb", r3 * Z.emin_app1.to_numpy(), f["r_B3"]),
                  "B3m": ("mix", r3, lambda mu, r_=f["r_B3m"]: np.full_like(mu, r_))}
        for nm, (kd, par, rr) in models.items():
            ru, rc, pt, po, p0, p01, mean, e95p, e95o, e99p, e99o = ([] for _ in range(11))
            for b0 in range(0, len(Z), 2500):
                sl = slice(b0, b0 + 2500)
                cond = mix(par[sl], q2[sl], rr) if kd == "mix" else P.nb_pmf(par[sl], rr, K)
                unc = pa[sl, None] * cond
                unc[:, 0] += 1 - pa[sl]
                yy = yv[sl]
                ru.append(P.rps_rows(unc, yy, P.SUP_CLIP["pts"]))
                rc.append(P.rps_rows(cond, yy, P.SUP_CLIP["pts"]))
                Fc = np.cumsum(cond, 1)
                yi = np.clip(yy, 0, K).astype(int)
                hi = Fc[np.arange(len(yi)), yi]
                lo = np.where(yi > 0, Fc[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
                pt.append(lo + rng.random(len(yi)) * (hi - lo))
                po.append(1 - Fc[np.arange(len(yi)), np.clip(li[sl], 0, K)])
                p0.append(cond[:, 0])
                p01.append(cond[:, :2].sum(1))
                mean.append(cond @ np.arange(K + 1))
                for lev, ep, eo in ((0.95, e95p, e95o), (0.99, e99p, e99o)):
                    qk = (Fc < lev).sum(1)
                    ep.append(1 - Fc[np.arange(len(qk)), np.minimum(qk, K)])
                    eo.append(yy > qk)
            for key, v in (("ru", ru), ("rc", rc), ("pit", pt), ("po", po), ("p0", p0), ("p01", p01), ("mean", mean),
                           ("e95p", e95p), ("e95o", e95o), ("e99p", e99p), ("e99o", e99o)):
                out[f"{nm}_{key}"] = np.concatenate(v)
        rows.append(pd.DataFrame(out))
        print("season", y, fits[int(y)], flush=True)
    X = pd.concat(rows, ignore_index=True)
    app = X.app.to_numpy()
    seasons = X.season.to_numpy()
    wk = (X.season.astype(str) + "_" + pd.to_datetime(X.tip).dt.isocalendar().week.astype(str)).to_numpy()
    keys = np.unique(wk)
    widx = {k: np.where(wk == k)[0] for k in keys}
    brng = np.random.default_rng(2026)
    draws = [np.concatenate([widx[k] for k in brng.choice(keys, len(keys))]) for _ in range(2000)]
    boot = lambda v: np.array([v[d].mean() for d in draws])
    dec = lambda v: [round(float(a), 3) for a in np.histogram(v, bins=10, range=(0, 1))[0] / len(v)]
    groups = {"all": app, "A_confident_R": app & (X.R_po.to_numpy() >= 0.8), "B_proj_min_le15": app & (X.exp_min.to_numpy() <= 15),
              "C_low_minute_risk": app & (X.p_short15.to_numpy() >= 0.2), "E_established": app & (X.exp_min.to_numpy() >= 25)}
    res = {"fits": fits, "groups": {}}
    for gname, m in groups.items():
        g = dict(n=int(m.sum()), actual=dict(p0=round(float((X.pts[m] == 0).mean()), 4), p01=round(float((X.pts[m] <= 1).mean()), 4),
                                               mean=round(float(X.pts[m].mean()), 3), over=round(float(X.over[m].mean()), 4)))
        for nm in ("R", "D"):
            g[nm] = dict(p0=round(float(X[f"{nm}_p0"][m].mean()), 4), p01=round(float(X[f"{nm}_p01"][m].mean()), 4),
                         mean=round(float(X[f"{nm}_mean"][m].mean()), 3), over=round(float(X[f"{nm}_po"][m].mean()), 4),
                         tail95=dict(pred=round(float(X[f"{nm}_e95p"][m].mean()), 4), obs=round(float(X[f"{nm}_e95o"][m].mean()), 4)),
                         tail99=dict(pred=round(float(X[f"{nm}_e99p"][m].mean()), 4), obs=round(float(X[f"{nm}_e99o"][m].mean()), 4)),
                         rps_given_appearing=round(float(X[f"{nm}_rc"][m].mean()), 6))
        res["groups"][gname] = g
    # own confident group for D
    mD = app & (X.D_po.to_numpy() >= 0.8)
    res["groups"]["D_own_confident"] = dict(n=int(mD.sum()), pred=round(float(X.D_po[mD].mean()), 4), actual=round(float(X.over[mD].mean()), 4))
    # descriptive: average points by pre-game rate and projected minutes (for a later shrinkage question)
    A = X[app].assign(rb=pd.qcut(X.rate[app], 5, duplicates="drop"), mb=pd.cut(X.exp_min[app], [0, 15, 25, 48]))
    res["mean_by_rate_and_minutes"] = {f"{r}|{m}": dict(n=int(len(g)), pred_R=round(float(g.R_mean.mean()), 3), actual=round(float(g.pts.mean()), 3))
                                       for (r, m), g in A.groupby(["rb", "mb"], observed=True)}
    # gates
    gates = {}
    for b in ("B1", "B2", "B3", "B3m"):
        gain = (X[f"{b}_ru"] - X.D_ru).to_numpy()
        bs = boot(gain)
        sb = int(sum(X.D_ru[seasons == y].mean() < X[f"{b}_ru"][seasons == y].mean() for y in P.TEST))
        cg = float((X[f"{b}_rc"][app] - X.D_rc[app]).mean())
        gates[b] = dict(gain=round(float(gain.mean()), 6), lower90=round(float(np.percentile(bs, 10)), 6), seasons_better=sb, cond_gain=round(cg, 6),
                        ok=bool(np.percentile(bs, 10) > 0 and sb >= 4 and cg > 0))
    pitD = dec(X.D_pit[app])
    g1 = all(v["ok"] for v in gates.values()) and all(0.07 <= v <= 0.13 for v in pitD)
    dr = (X.R_ru - X.D_ru).to_numpy()
    bs = boot(dr)
    mE = groups["E_established"]
    g2 = bool(X.D_ru.mean() <= X.R_ru.mean() and X.D_ru[mE].mean() <= X.R_ru[mE].mean())
    G = res["groups"]
    terr = lambda g, nm, lv: abs(G[g][nm][f"tail{lv}"]["obs"] - G[g][nm][f"tail{lv}"]["pred"])
    g3 = all(terr(g, "D", 95) <= 0.010 and terr(g, "D", 99) <= 0.005 for g in ("all", "E_established")) and \
        all(terr(g, "D", lv) <= terr(g, "R", lv) + 0.005 for g in ("B_proj_min_le15", "C_low_minute_risk") for lv in (95, 99))
    a_gap = lambda nm: abs(G["A_confident_R"][nm]["over"] - G["A_confident_R"]["actual"]["over"])
    z_close = lambda g, nm: abs(G[g][nm]["p0"] - G[g]["actual"]["p0"])
    g4 = bool(a_gap("D") < a_gap("R") and all(z_close(g, "D") < z_close(g, "R") for g in ("B_proj_min_le15", "C_low_minute_risk")))
    res["gates"] = dict(g1_original_points_gates=dict(vs=gates, pit_D=pitD, passes=bool(g1)),
                        g2_not_worse_than_R=dict(rps_R=round(float(X.R_ru.mean()), 6), rps_D=round(float(X.D_ru.mean()), 6),
                                                 rps_R_E=round(float(X.R_ru[mE].mean()), 6), rps_D_E=round(float(X.D_ru[mE].mean()), 6), passes=g2),
                        g3_tail=dict(passes=bool(g3)), g4_target=dict(gap_R=round(a_gap("R"), 4), gap_D=round(a_gap("D"), 4), passes=g4),
                        paired_D_vs_R=dict(gain=round(float(dr.mean()), 7), lower90=round(float(np.percentile(bs, 10)), 7),
                                           upper90=round(float(np.percentile(bs, 90)), 7)),
                        pit_R=dec(X.R_pit[app]))
    res["D_passes"] = bool(g1 and g2 and g3 and g4)
    with open(os.path.join(HERE, "nba_points_dispersion_results.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({k: res[k] for k in ("fits", "gates", "D_passes")}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
