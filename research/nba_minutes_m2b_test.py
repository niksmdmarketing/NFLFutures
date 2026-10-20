"""NBA minutes M2b per research/NBA_MINUTES_M2B_RULE.md: M2 with the normal-night component moment-matched after truncation.
  python research/nba_minutes_m2b_test.py -> research/nba_minutes_m2b_results.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_minutes_test as M  # noqa: E402
import nba_props_simple_test as P  # noqa: E402
import nba_minutes_tail_test as T  # noqa: E402

K = np.arange(1, M.MAXM + 1)
_z = np.linspace(-8, 6, 4001)
_lam = norm.pdf(_z) / norm.sf(_z)
_v = 1 + _z * _lam - _lam ** 2
_g = (_lam - _z) / np.sqrt(_v)          # (mean - t) / sd as a function of z = (t - mu*) / sigma*; decreasing


def match(target_m, target_s, t):
    """location and scale of a normal whose truncation to [t, inf) has the target mean and sd."""
    r = np.clip((target_m - t) / target_s, _g[-1] + 1e-6, _g[0])
    z = np.interp(r, _g[::-1], _z[::-1])
    lam = norm.pdf(z) / norm.sf(z)
    sig = target_s / np.sqrt(1 + z * lam - lam ** 2)
    return t - sig * z, sig


def normal_part(Z, fit, matched):
    mu2 = np.clip(T.x_mean(Z) @ fit["bm"], 1, 48)
    sd2 = fit["sd"](mu2)
    thr = T.SHORT * Z.mu1.to_numpy()
    kmin = np.maximum(np.ceil(thr), 1)
    if matched:
        loc, sc = match(mu2, sd2, kmin - 0.5)
    else:
        loc, sc = mu2, sd2
    c = norm.cdf((K[None, :] + 0.5 - loc[:, None]) / sc[:, None]) - norm.cdf((K[None, :] - 0.5 - loc[:, None]) / sc[:, None])
    c = np.where(K[None, :] >= thr[:, None], np.clip(c, 1e-12, None), 0.0)
    tot = c.sum(1, keepdims=True)
    c = np.where(tot > 0, c / np.where(tot > 0, tot, 1), 0.0)
    c[(tot[:, 0] <= 0), -1] = 1.0
    return c, mu2, sd2


def q_m2(Z, fit, matched):
    q_old, pi = T.m2_q(Z, fit)                      # M2 (unmatched); reuse its short part and pi
    c_old, _, _ = normal_part(Z, fit, False)
    short = (q_old - (1 - pi[:, None]) * c_old) / np.maximum(pi[:, None], 1e-12)
    if not matched:
        return q_old, pi
    c_new, _, _ = normal_part(Z, fit, True)
    return pi[:, None] * short + (1 - pi[:, None]) * c_new, pi


def checks(Z, fit, low):
    N = ~Z.short.to_numpy() & Z.app.to_numpy()
    out = {}
    for nm, matched in (("M2", False), ("M2b", True)):
        c, mu2, sd2 = normal_part(Z, fit, matched)
        m = c @ K
        s = np.sqrt(c @ K ** 2 - m ** 2)
        y = Z.minutes.to_numpy()
        for g, msk in (("fringe", N & low), ("other", N & ~low)):
            out[f"{nm}_{g}"] = dict(n=int(msk.sum()), component_mean=round(float(m[msk].mean()), 3), actual_mean=round(float(y[msk].mean()), 3),
                                    component_sd=round(float(np.sqrt((s[msk] ** 2).mean())), 3),
                                    actual_sd_around_target=round(float(np.sqrt(((y[msk] - mu2[msk]) ** 2).mean())), 3))
    return out


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D = T.features(D)
    rng = np.random.default_rng(19)
    res = {"implementation_checks": {}, "minutes": {}, "props": {}}
    rows = []
    for y in P.TEST:
        F = D[(D.season < y) & (D.season >= 2017)]
        fit = T.fit_m2(F)
        # implementation check on the fitting seasons' normal nights (last fitting season for speed) and the test season
        Fl = F[F.season == y - 1].reset_index(drop=True)
        low_f = M.disc_normal(Fl.mu1.to_numpy(), Fl.sd1.to_numpy())[:, :14].sum(1) >= 0.2
        Z = D[D.season == y].reset_index(drop=True)
        q1 = M.disc_normal(Z.mu1.to_numpy(), Z.sd1.to_numpy())
        low = q1[:, :14].sum(1) >= 0.2
        res["implementation_checks"][int(y)] = {"fit_season_" + str(y - 1): checks(Fl, fit, low_f), "test_season": checks(Z, fit, low)}
        q2, _ = q_m2(Z, fit, False)
        q3, pi = q_m2(Z, fit, True)
        pa = np.clip(Z.pa1.to_numpy(), 1e-3, 1 - 1e-3)
        ym = Z.minutes.to_numpy()
        app = Z.app.to_numpy()
        out = dict(season=np.full(len(Z), y), tip=Z.tip.to_numpy(), app=app, low=low, minutes=ym)
        yk = np.clip(np.round(ym), 1, M.MAXM).astype(int)
        for nm, q in (("1", q1), ("2", q2), ("3", q3)):
            out["mrps" + nm] = M.rps(pa, q, ym)
            Fq = np.cumsum(q, 1)
            hi = Fq[np.arange(len(yk)), yk - 1]
            lo = np.where(yk > 1, Fq[np.arange(len(yk)), np.maximum(yk - 2, 0)], 0.0)
            out["mpit" + nm] = np.where(app, lo + rng.random(len(yk)) * (hi - lo), np.nan)
            out["em" + nm] = q @ K
            out["p15_" + nm] = q[:, :14].sum(1)
        F_app = F[F.app]
        grp_rate = {s: F_app.groupby("grp")[s].sum() / F_app.groupby("grp").minutes.sum() for s in P.STATS}
        grp_pg = {s: F_app.groupby("grp")[s].mean() for s in P.STATS}
        for s in P.STATS:
            f = R["fits"][str(y)][s]
            KK = P.SUP_FULL[s]
            rate = P.rates(Z, s, f["m0"], grp_rate)
            ver, kind = T.VERS[s]
            rate_f = P.adjust(Z, s, rate, b=f["b"], tag="1") if kind == "b" else P.adjust(Z, s, rate, c=f["c"])
            r_f = f["r_T"] if kind == "b" else f["r_O"]
            b1, b2, r3 = P.base_means(Z, s, grp_rate, grp_pg)
            li = np.floor(np.floor(b1) + 0.5).astype(int)
            yv = Z[s].to_numpy()
            models = {"V1": ("mix", rate_f, r_f, q1), "V2": ("mix", rate_f, r_f, q2), "V3": ("mix", rate_f, r_f, q3),
                      "B1": ("nb", b1, f["r_B1"], None), "B2": ("nb", b2, f["r_B2"], None),
                      "B3": ("nb", r3 * Z.emin_app1.to_numpy(), f["r_B3"], None), "B3m_M2b": ("mix", r3, f["r_B3m"], q3)}
            for name, (kd, par, rr, q) in models.items():
                ru, rc, pt, po = [], [], [], []
                for b0 in range(0, len(Z), 3000):
                    sl = slice(b0, b0 + 3000)
                    cond = P.mixture_pmf(par[sl], q[sl], rr, KK) if kd == "mix" else P.nb_pmf(par[sl], rr, KK)
                    unc = pa[sl, None] * cond
                    unc[:, 0] += 1 - pa[sl]
                    yy = yv[sl]
                    ru.append(P.rps_rows(unc, yy, P.SUP_CLIP[s]))
                    rc.append(P.rps_rows(cond, yy, P.SUP_CLIP[s]))
                    Fc = np.cumsum(cond, 1)
                    yi = np.clip(yy, 0, KK).astype(int)
                    hi = Fc[np.arange(len(yi)), yi]
                    lo = np.where(yi > 0, Fc[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
                    pt.append(lo + rng.random(len(yi)) * (hi - lo))
                    po.append(1 - Fc[np.arange(len(li[sl])), np.clip(li[sl], 0, KK)])
                out[f"{s}_{name}_ru"] = np.concatenate(ru)
                out[f"{s}_{name}_rc"] = np.concatenate(rc)
                out[f"{s}_{name}_pit"] = np.concatenate(pt)
                out[f"{s}_{name}_po"] = np.concatenate(po)
            out[f"{s}_over"] = yv > (np.floor(b1) + 0.5)
        rows.append(pd.DataFrame(out))
        print("season", y, flush=True)
    X = pd.concat(rows, ignore_index=True)
    # implementation gate
    ok = True
    for y, c in res["implementation_checks"].items():
        for part in c.values():
            for g in ("fringe", "other"):
                v = part[f"M2b_{g}"]
                if abs(v["component_mean"] - v["actual_mean"]) > 0.3 or abs(v["component_sd"] / v["actual_sd_around_target"] - 1) > 0.10:
                    ok = False
    res["implementation_checks_pass"] = ok
    wk = (X.season.astype(str) + "_" + pd.to_datetime(X.tip).dt.isocalendar().week.astype(str)).to_numpy()
    keys = np.unique(wk)
    widx = {k: np.where(wk == k)[0] for k in keys}
    brng = np.random.default_rng(2026)
    draws = [np.concatenate([widx[k] for k in brng.choice(keys, len(keys))]) for _ in range(2000)]
    boot = lambda v: np.array([v[d].mean() for d in draws])
    seasons = X.season.to_numpy()
    app = X.app.to_numpy()
    low = X.low.to_numpy()
    dec = lambda v: [round(float(a), 3) for a in np.histogram(v, bins=10, range=(0, 1))[0] / len(v)]
    g13 = (X.mrps1 - X.mrps3).to_numpy()
    bs = boot(g13)
    d3 = dec(X.mpit3[app])
    tab = {nm: dict(avg_min=round(float(X["em" + k][app & low].mean()), 3), p15=round(float(X["p15_" + k][app & low].mean()), 3))
           for nm, k in (("stage_one", "1"), ("M2", "2"), ("M2b", "3"))}
    tab["actual"] = dict(avg_min=round(float(X.minutes[app & low].mean()), 3), p15=round(float((X.minutes[app & low] < 15).mean()), 3))
    closer = (abs(tab["M2b"]["avg_min"] - tab["actual"]["avg_min"]) < abs(tab["M2"]["avg_min"] - tab["actual"]["avg_min"])
              and abs(tab["M2b"]["p15"] - tab["actual"]["p15"]) < abs(tab["M2"]["p15"] - tab["actual"]["p15"]))
    res["minutes"] = dict(rps=dict(stage_one=round(float(X.mrps1.mean()), 6), M2=round(float(X.mrps2.mean()), 6), M2b=round(float(X.mrps3.mean()), 6)),
                          gain_vs_stage_one=round(float(g13.mean()), 6), lower90=round(float(np.percentile(bs, 10)), 6),
                          pit_M2=dec(X.mpit2[app]), pit_M2b=d3, fixed_group_table=tab,
                          gate1=bool(np.percentile(bs, 10) > 0 and all(0.08 <= v <= 0.12 for v in d3)),
                          gate2=bool(X.mrps3.mean() <= X.mrps2.mean()), gate3=bool(closer),
                          by_season={int(y): dict(M2=round(float(X.mrps2[seasons == y].mean()), 6), M2b=round(float(X.mrps3[seasons == y].mean()), 6)) for y in P.TEST})
    res["minutes"]["M2b_replaces_M2"] = bool(ok and res["minutes"]["gate1"] and res["minutes"]["gate2"] and res["minutes"]["gate3"])
    for s in P.STATS:
        over = X[f"{s}_over"].to_numpy()
        r = {}
        for nm in ("V1", "V2", "V3", "B1", "B2", "B3", "B3m_M2b"):
            r[nm] = dict(rps_uncond=round(float(X[f"{s}_{nm}_ru"].mean()), 6), rps_given_appearing=round(float(X[f"{s}_{nm}_rc"][app].mean()), 6),
                         pit_given_appearing=dec(X[f"{s}_{nm}_pit"][app]))
        conf_fixed = (X[f"{s}_V1_po"] >= 0.8).to_numpy() & app
        for nm in ("V1", "V2", "V3"):
            po = X[f"{s}_{nm}_po"].to_numpy()
            own = (po >= 0.8) & app
            r[nm]["over_low_minute_risk_fixed"] = dict(mean_p=round(float(po[low & app].mean()), 4), freq=round(float(over[low & app].mean()), 4))
            r[nm]["confident_fixed"] = dict(n=int(conf_fixed.sum()), mean_p=round(float(po[conf_fixed].mean()), 4), freq=round(float(over[conf_fixed].mean()), 4),
                                            by_season={int(y): dict(mean_p=round(float(po[conf_fixed & (seasons == y)].mean()), 3), freq=round(float(over[conf_fixed & (seasons == y)].mean()), 3)) for y in P.TEST})
            r[nm]["confident_own"] = dict(n=int(own.sum()), mean_p=round(float(po[own].mean()), 4) if own.any() else None, freq=round(float(over[own].mean()), 4) if own.any() else None)
        if s == "pts":
            gates = {}
            for b in ("B1", "B2", "B3", "B3m_M2b"):
                gain = (X[f"{s}_{b}_ru"] - X[f"{s}_V3_ru"]).to_numpy()
                bsg = boot(gain)
                sb = int(sum(X[f"{s}_V3_ru"][seasons == y].mean() < X[f"{s}_{b}_ru"][seasons == y].mean() for y in P.TEST))
                cg = float((X[f"{s}_{b}_rc"][app] - X[f"{s}_V3_rc"][app]).mean())
                gates[b] = dict(gain=round(float(gain.mean()), 6), lower90=round(float(np.percentile(bsg, 10)), 6), seasons_better=sb, cond_gain=round(cg, 6),
                                ok=bool(np.percentile(bsg, 10) > 0 and sb >= 4 and cg > 0))
            g3 = all(0.07 <= v <= 0.13 for v in r["V3"]["pit_given_appearing"])
            r["points_V3_gates"] = dict(vs=gates, calibration=g3, passes=bool(g3 and all(v["ok"] for v in gates.values())))
        else:
            gain = (X[f"{s}_V2_ru"] - X[f"{s}_V3_ru"]).to_numpy()
            bsg = boot(gain)
            g3 = all(0.07 <= v <= 0.13 for v in r["V3"]["pit_given_appearing"])
            gap2 = r["V2"]["over_low_minute_risk_fixed"]["mean_p"] - r["V2"]["over_low_minute_risk_fixed"]["freq"]
            gap3 = r["V3"]["over_low_minute_risk_fixed"]["mean_p"] - r["V3"]["over_low_minute_risk_fixed"]["freq"]
            r["v3_replaces_v2"] = dict(gain=round(float(gain.mean()), 6), lower95=round(float(np.percentile(bsg, 5)), 6), calibration=g3,
                                       gap_v2=round(gap2, 4), gap_v3=round(gap3, 4),
                                       replace=bool(np.percentile(bsg, 5) > 0 and g3 and abs(gap3) < abs(gap2)))
        res["props"][s] = r
    with open(os.path.join(HERE, "nba_minutes_m2b_results.json"), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({"implementation_checks_pass": ok, "minutes": res["minutes"]}, indent=1))
    print(json.dumps({s: {k: v for k, v in res["props"][s].items() if k in ("points_V3_gates", "v3_replaces_v2")} for s in P.STATS}, indent=1))


if __name__ == "__main__":
    main()
