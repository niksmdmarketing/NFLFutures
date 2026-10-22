"""NBA props role-aware per-minute rate adjustment per research/NBA_ROLE_RATE_RULE.md (M2b minutes unchanged).
  python research/nba_props_role_rate_test.py -> research/nba_props_role_rate_results.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_minutes_test as M  # noqa: E402
import nba_props_simple_test as P  # noqa: E402
import nba_minutes_tail_test as T  # noqa: E402
import nba_minutes_m2b_test as B  # noqa: E402
import nba_points_dispersion_test as PD  # noqa: E402

PRIOR_SD, CAP = 0.05, (0.85, 1.15)
K = np.arange(1, M.MAXM + 1)


def role_x(Z):
    s10 = Z.start10.astype(float).fillna(0.5).to_numpy()
    a10 = Z.app10.astype(float).fillna(0.5).to_numpy()
    return np.column_stack([1 - s10, 1 - a10])


def mult(X, th):
    return np.clip(np.exp(X @ th), *CAP)


def stat_rate(Z, s, f, grp_rate):
    rate = P.rates(Z, s, f["m0"], grp_rate)
    _, kind = T.VERS[s]
    return P.adjust(Z, s, rate, b=f["b"], tag="1") if kind == "b" else P.adjust(Z, s, rate, c=f["c"])


def fit_theta(y, base_mu, X, rfun):
    def nll(th):
        mu = np.maximum(base_mu * mult(X, th), 0.01)
        return -PD.nb_logpmf_r(y, mu, rfun(mu)).sum() + (th ** 2).sum() / (2 * PRIOR_SD ** 2)
    o = minimize(nll, x0=np.zeros(2), method="Nelder-Mead", options=dict(xatol=1e-6, fatol=1e-3, maxiter=2000))
    return [float(v) for v in o.x]


def pmf(rate, q, s, rfun):
    if s == "pts":
        return PD.mix(rate, q, rfun)
    mu = rate[:, None] * K[None, :].astype(float)
    kk = np.arange(P.SUP_FULL[s] + 1, dtype=float)
    r = rfun(mu)
    lp = PD.nb_logpmf_r(kk[None, None, :], mu[:, :, None], r[:, :, None])
    Pm = np.einsum("nm,nmk->nk", q, np.exp(lp))
    Pm[:, -1] += np.clip(1 - Pm.sum(1), 0, None)
    return Pm


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    RD = json.load(open(os.path.join(HERE, "nba_points_dispersion_results.json")))["fits"]
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D = T.features(D)
    rng = np.random.default_rng(31)
    res = {"rule": "research/NBA_ROLE_RATE_RULE.md", "theta": {}, "stats": {}}
    rows = []
    for y in P.TEST:
        F = D[(D.season < y) & (D.season >= 2017)]
        fit = T.fit_m2(F)
        Z = D[D.season == y].reset_index(drop=True)
        q3, _ = B.q_m2(Z, fit, True)
        q1 = M.disc_normal(Z.mu1.to_numpy(), Z.sd1.to_numpy())
        pa = np.clip(Z.pa1.to_numpy(), 1e-3, 1 - 1e-3)
        app = Z.app.to_numpy()
        out = dict(season=np.full(len(Z), y), tip=Z.tip.to_numpy(), app=app,
                   bench=(Z.start10.astype(float).fillna(0).to_numpy() < 0.5), risk=q1[:, :14].sum(1) >= 0.2,
                   established=Z.emin_app1.to_numpy() >= 25, em=q3 @ K)
        F_app = F[F.app]
        grp_rate = {s: F_app.groupby("grp")[s].sum() / F_app.groupby("grp").minutes.sum() for s in P.STATS}
        Xz = role_x(Z)
        for s in P.STATS:
            f = R["fits"][str(y)][s]
            if s == "pts":
                a, b = RD[str(y)]["a"], RD[str(y)]["b"]
                rfun = lambda mu, a=a, b=b: PD.r_of(mu, a, b)
            else:
                rr = f["r_T"] if T.VERS[s][1] == "b" else f["r_O"]
                rfun = lambda mu, rr=rr: np.full_like(np.asarray(mu, float), rr)
            Fa = F_app.reset_index(drop=True)
            th = fit_theta(Fa[s].to_numpy().astype(float), stat_rate(Fa, s, f, grp_rate) * Fa.minutes.to_numpy(), role_x(Fa), rfun)
            res["theta"].setdefault(s, {})[int(y)] = [round(v, 5) for v in th]
            rate0 = stat_rate(Z, s, f, grp_rate)
            rate1 = rate0 * mult(Xz, np.array(th))
            yv = Z[s].to_numpy()
            b1, _, _ = P.base_means(Z, s, grp_rate, {s2: F_app.groupby("grp")[s2].mean() for s2 in P.STATS})
            li = np.floor(np.floor(b1) + 0.5).astype(int)
            out[f"{s}_over"] = yv > (np.floor(b1) + 0.5)
            out[f"{s}_y"] = yv
            for nm, rate in (("base", rate0), ("role", rate1)):
                ru, rc, pt, po, mn = [], [], [], [], []
                for b0 in range(0, len(Z), 2000):
                    sl = slice(b0, b0 + 2000)
                    cond = pmf(rate[sl], q3[sl], s, rfun)
                    unc = pa[sl, None] * cond
                    unc[:, 0] += 1 - pa[sl]
                    yy = yv[sl]
                    ru.append(P.rps_rows(unc, yy, P.SUP_CLIP[s]))
                    rc.append(P.rps_rows(cond, yy, P.SUP_CLIP[s]))
                    Fc = np.cumsum(cond, 1)
                    yi = np.clip(yy, 0, cond.shape[1] - 1).astype(int)
                    hi = Fc[np.arange(len(yi)), yi]
                    lo = np.where(yi > 0, Fc[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
                    pt.append(lo + rng.random(len(yi)) * (hi - lo))
                    po.append(1 - Fc[np.arange(len(yi)), np.clip(li[sl], 0, cond.shape[1] - 1)])
                    mn.append(cond @ np.arange(cond.shape[1]))
                out[f"{s}_{nm}_ru"] = np.concatenate(ru)
                out[f"{s}_{nm}_rc"] = np.concatenate(rc)
                out[f"{s}_{nm}_pit"] = np.concatenate(pt)
                out[f"{s}_{nm}_po"] = np.concatenate(po)
                out[f"{s}_{nm}_mean"] = np.concatenate(mn)
        rows.append(pd.DataFrame(out))
        print("season", y, res["theta"], flush=True)
    X = pd.concat(rows, ignore_index=True)
    wk = (X.season.astype(str) + "_" + pd.to_datetime(X.tip).dt.isocalendar().week.astype(str)).to_numpy()
    keys = np.unique(wk)
    widx = {k: np.where(wk == k)[0] for k in keys}
    brng = np.random.default_rng(2026)
    draws = [np.concatenate([widx[k] for k in brng.choice(keys, len(keys))]) for _ in range(2000)]
    seasons = X.season.to_numpy()
    app = X.app.to_numpy()
    dec = lambda v: [round(float(a), 3) for a in np.histogram(v, bins=10, range=(0, 1))[0] / len(v)]
    for s in P.STATS:
        g = (X[f"{s}_base_ru"] - X[f"{s}_role_ru"]).to_numpy()
        bs = np.array([g[d].mean() for d in draws])
        by = {int(y): round(float(g[seasons == y].mean()), 7) for y in P.TEST}
        cg = float((X[f"{s}_base_rc"][app] - X[f"{s}_role_rc"][app]).mean())
        pit = dec(X[f"{s}_role_pit"][app])
        grp = {}
        for gname in ("bench", "risk", "established"):
            m = X[gname].to_numpy() & app
            yv = X[f"{s}_y"].to_numpy()[m]
            grp[gname] = {"n": int(m.sum()), "actual_mean": round(float(yv.mean()), 4),
                          **{nm: {"mean": round(float(X[f"{s}_{nm}_mean"][m].mean()), 4),
                                  "rps_uncond": round(float(X[f"{s}_{nm}_ru"][X[gname].to_numpy()].mean()), 6),
                                  "over_gap": round(float(X[f"{s}_{nm}_po"][m].mean() - X[f"{s}_over"][m].mean()), 4)} for nm in ("base", "role")}}
        err = lambda gname, nm: abs(grp[gname][nm]["mean"] - grp[gname]["actual_mean"])
        gates = {
            "1_overall": bool(g.mean() > 0 and np.percentile(bs, 2.5) > 0 and sum(v > 0 for v in by.values()) >= 4 and cg > 0),
            "2_calibration": bool(all(0.07 <= v <= 0.13 for v in pit)),
            "3_fixed_group_bias": bool(err("bench", "role") < err("bench", "base") and err("risk", "role") < err("risk", "base")
                                       and abs(grp["risk"]["role"]["over_gap"]) < abs(grp["risk"]["base"]["over_gap"])),
            "4_established_no_harm": bool(grp["established"]["role"]["rps_uncond"] <= grp["established"]["base"]["rps_uncond"] * 1.0025
                                          and err("established", "role") <= err("established", "base") + 0.02)}
        res["stats"][s] = {"rps_uncond": {"base": round(float(X[f"{s}_base_ru"].mean()), 7), "role": round(float(X[f"{s}_role_ru"].mean()), 7)},
                           "gain": round(float(g.mean()), 8), "lower97_5": round(float(np.percentile(bs, 2.5)), 8), "by_season": by,
                           "cond_gain": round(cg, 8), "pit_role": pit, "pit_base": dec(X[f"{s}_base_pit"][app]), "groups": grp,
                           "gates": gates, "passes": bool(all(gates.values()))}
    res["label"] = "Development seasons 2022-2026: a pass makes a frozen forward challenger only (separate decision); not adoption."
    json.dump(res, open(os.path.join(HERE, "nba_props_role_rate_results.json"), "w"), indent=1)
    print(json.dumps({s: {k: v for k, v in r.items() if k in ("gain", "lower97_5", "by_season", "cond_gain", "gates", "passes")} for s, r in res["stats"].items()}, indent=1))


if __name__ == "__main__":
    main()
