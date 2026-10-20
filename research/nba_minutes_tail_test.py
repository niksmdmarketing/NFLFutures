"""NBA minutes short-night tail correction per research/NBA_MINUTES_TAIL_RULE.md (with amendment 1).
  python research/nba_minutes_tail_test.py -> research/nba_minutes_tail_results.json
Uses <W>/props_rows.parquet (research/nba_props_simple_test.py build) and the prop fits in research/nba_props_simple_results.json
(those fits use actual minutes, so they do not depend on the minutes model).
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
import nba_game_env_test as E  # noqa: E402

TEST = P.TEST
SHORT = 0.6
RATIO_BINS = np.linspace(0, SHORT, 61)
VERS = {"pts": ("P+T", "b"), "reb": ("P+O", "c"), "ast": ("P+T", "b")}


def features(D):
    D = D.copy()
    D["newcomer"] = (D["ewm"] <= 0).astype(float)
    D["ewm_f"] = D["ewm"].where(D["ewm"] > 0, 12.0)
    for c, v in {"season_mpg": 12.0, "mpg10": 12.0, "app10": 0.5}.items():
        D[c] = D[c].fillna(v)
    D["early"] = (D.gi < 10).astype(float)
    G = E.load_games()
    D["absm"] = D.game_id.map(dict(zip(G.gid, G.m_L.abs()))).fillna(5.0)
    # back-to-back: the team played the previous calendar day (US Eastern date)
    d = pd.concat([G[["gid", "date", "home"]].rename(columns={"home": "team"}), G[["gid", "date", "away"]].rename(columns={"away": "team"})])
    d = d.sort_values("date")
    d["prev"] = d.groupby("team").date.shift()
    d["b2b"] = ((pd.to_datetime(d.date) - pd.to_datetime(d.prev)).dt.days == 1).astype(float)
    D = D.merge(d[["gid", "team", "b2b"]].rename(columns={"gid": "game_id"}), on=["game_id", "team"], how="left")
    D["b2b"] = D.b2b.fillna(0.0)
    # short night (outcome) and the player's short-night share over his last 20 appearances (before this game), shrunk
    D["app"] = D.minutes > 0
    D["short"] = D.app & (np.round(D.minutes) < SHORT * D.mu1)
    D = D.sort_values(["aid", "tip"]).reset_index(drop=True)
    A = D[D.app]
    roll = A.groupby("aid").short.transform(lambda x: x.astype(float).shift().rolling(20, min_periods=1).sum())
    cnt = A.groupby("aid").short.transform(lambda x: x.astype(float).shift().rolling(20, min_periods=1).count())
    D.loc[A.index, "s_sum"] = roll
    D.loc[A.index, "s_cnt"] = cnt
    D[["s_sum", "s_cnt"]] = D.groupby("aid")[["s_sum", "s_cnt"]].ffill()   # carry to non-appearance rows (state before the game)
    # for non-appearance rows the carried value already includes only earlier appearances; shift-based values above exclude the game
    D[["s_sum", "s_cnt"]] = D[["s_sum", "s_cnt"]].fillna(0.0)
    for c in ("Questionable", "Probable", "Available"):
        D["st_" + c] = (D.st1 == c).astype(float)
    D["st_OD"] = D.st1.isin(["Out", "Doubtful"]).astype(float)
    return D


def x_pi(Z, league_rate):
    sh = (Z.s_sum + 10 * league_rate) / (Z.s_cnt + 10)
    return np.column_stack([Z.mu1 / 48, Z.st_Questionable + Z.st_OD, Z.st_Probable, Z.st_Available, Z.absm / 10, Z.b2b, sh, Z.early])


def x_mean(Z):
    return np.column_stack([np.ones(len(Z)), Z.ewm_f, Z.season_mpg, Z.vac_same1 * Z.ewm_f / 36, Z.vac_other1 * Z.ewm_f / 36,
                            ((Z.streak >= 2) & (Z.st1 != "Out")).astype(float), Z.start10, Z.early, Z.newcomer])


def m2_q(Z, fit):
    """minutes given appearing under M2, k = 1..53."""
    k = np.arange(1, M.MAXM + 1)
    pi = fit["lr"].predict_proba(x_pi(Z, fit["league"]))[:, 1]
    mu2 = np.clip(x_mean(Z) @ fit["bm"], 1, 48)
    sd2 = fit["sd"](mu2)
    thr = SHORT * Z.mu1.to_numpy()
    c = norm.cdf((k[None, :] + 0.5 - mu2[:, None]) / sd2[:, None]) - norm.cdf((k[None, :] - 0.5 - mu2[:, None]) / sd2[:, None])
    c = np.where(k[None, :] >= thr[:, None], np.clip(c, 1e-12, None), 0.0)
    tot = c.sum(1, keepdims=True)
    # if the whole support is excluded (tiny means), fall back to the top minute
    c = np.where(tot > 0, c / np.where(tot > 0, tot, 1), 0.0)
    c[(tot[:, 0] <= 0), -1] = 1.0
    # short component: ratio histogram x stage-one mean, restricted below the threshold
    centers = (RATIO_BINS[:-1] + RATIO_BINS[1:]) / 2
    mins = np.clip(np.round(centers[None, :] * Z.mu1.to_numpy()[:, None]), 1, M.MAXM).astype(int)
    s = np.zeros((len(Z), M.MAXM))
    for j in range(len(centers)):
        np.add.at(s, (np.arange(len(Z)), mins[:, j] - 1), fit["ratio"][j])
    s = np.where(k[None, :] < np.maximum(thr[:, None], 1.0001), s, 0.0)
    st = s.sum(1, keepdims=True)
    s = np.where(st > 0, s / np.where(st > 0, st, 1), 0.0)
    s[(st[:, 0] <= 0), 0] = 1.0
    return pi[:, None] * s + (1 - pi[:, None]) * c, pi


def fit_m2(F):
    from sklearn.linear_model import LogisticRegression
    A = F[F.app]
    league = float(A.short.mean())
    lr = LogisticRegression(C=1.0, max_iter=1000).fit(x_pi(A, league), A.short.astype(int))
    N = A[~A.short]
    bm = np.linalg.lstsq(x_mean(N), N.minutes.to_numpy(), rcond=None)[0]
    sd = M.sd_fit(np.clip(x_mean(N) @ bm, 1, 48), N.minutes.to_numpy())
    S = A[A.short]
    ratio = np.histogram((np.round(S.minutes) / S.mu1).clip(0, SHORT - 1e-9), bins=RATIO_BINS)[0].astype(float)
    ratio /= ratio.sum()
    return dict(lr=lr, bm=bm, sd=sd, ratio=ratio, league=league)


def pit_dec(pit):
    return [round(float(v), 3) for v in np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit)]


def main():
    R = json.load(open(os.path.join(HERE, "nba_props_simple_results.json")))
    D = pd.read_parquet(os.path.join(P.W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D = features(D)
    rng = np.random.default_rng(17)
    rows = []
    coefs = {}
    for y in TEST:
        F = D[(D.season < y) & (D.season >= 2017)]
        Z = D[D.season == y].reset_index(drop=True)
        fit = fit_m2(F)
        coefs[int(y)] = dict(pi_coef=[round(float(v), 4) for v in fit["lr"].coef_[0]], pi_intercept=round(float(fit["lr"].intercept_[0]), 4),
                             league_short_rate=round(fit["league"], 4), ratio_hist=[round(float(v), 4) for v in fit["ratio"]])
        q1 = M.disc_normal(Z.mu1.to_numpy(), Z.sd1.to_numpy())
        q2, pi = m2_q(Z, fit)
        pa = np.clip(Z.pa1.to_numpy(), 1e-3, 1 - 1e-3)
        ymin = Z.minutes.to_numpy()
        app = Z.app.to_numpy()
        out = dict(season=np.full(len(Z), y), tip=Z.tip.to_numpy(), app=app, pi=pi, short=Z.short.to_numpy(),
                   mrps1=M.rps(pa, q1, ymin), mrps2=M.rps(pa, q2, ymin),
                   low_fixed=q1[:, :14].sum(1) >= 0.2, low_own2=q2[:, :14].sum(1) >= 0.2)
        yk = np.clip(np.round(ymin), 1, M.MAXM).astype(int)
        for nm, q in (("1", q1), ("2", q2)):
            Fq = np.cumsum(q, 1)
            hi = Fq[np.arange(len(yk)), yk - 1]
            lo = np.where(yk > 1, Fq[np.arange(len(yk)), np.maximum(yk - 2, 0)], 0.0)
            out["mpit" + nm] = np.where(app, lo + rng.random(len(yk)) * (hi - lo), np.nan)
        # props
        F_app = F[F.app]
        grp_rate = {s: F_app.groupby("grp")[s].sum() / F_app.groupby("grp").minutes.sum() for s in P.STATS}
        grp_pg = {s: F_app.groupby("grp")[s].mean() for s in P.STATS}
        for s in P.STATS:
            f = R["fits"][str(y)][s]
            K = P.SUP_FULL[s]
            rate = P.rates(Z, s, f["m0"], grp_rate)
            ver, kind = VERS[s]
            rate_f = P.adjust(Z, s, rate, b=f["b"], tag="1") if kind == "b" else P.adjust(Z, s, rate, c=f["c"])
            r_f = f["r_T"] if kind == "b" else f["r_O"]
            b1, b2, r3 = P.base_means(Z, s, grp_rate, grp_pg)
            line = np.floor(b1) + 0.5
            li = np.floor(line).astype(int)
            yv = Z[s].to_numpy()
            models = {"V1": ("mix", rate_f, r_f, q1), "V2": ("mix", rate_f, r_f, q2),
                      "B1": ("nb", b1, f["r_B1"], None), "B2": ("nb", b2, f["r_B2"], None),
                      "B3": ("nb", r3 * Z.emin_app1.to_numpy(), f["r_B3"], None), "B3m_M2": ("mix", r3, f["r_B3m"], q2)}
            for name, (kd, par, rr, q) in models.items():
                ru, rc, pt, po = [], [], [], []
                for b0 in range(0, len(Z), 3000):
                    sl = slice(b0, b0 + 3000)
                    cond = P.mixture_pmf(par[sl], q[sl], rr, K) if kd == "mix" else P.nb_pmf(par[sl], rr, K)
                    unc = pa[sl, None] * cond
                    unc[:, 0] += 1 - pa[sl]
                    yy = yv[sl]
                    ru.append(P.rps_rows(unc, yy, P.SUP_CLIP[s]))
                    rc.append(P.rps_rows(cond, yy, P.SUP_CLIP[s]))
                    Fc = np.cumsum(cond, 1)
                    yi = np.clip(yy, 0, K).astype(int)
                    hi = Fc[np.arange(len(yi)), yi]
                    lo = np.where(yi > 0, Fc[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
                    pt.append(lo + rng.random(len(yi)) * (hi - lo))
                    po.append(1 - Fc[np.arange(len(li[sl])), np.clip(li[sl], 0, K)])
                out[f"{s}_{name}_ru"] = np.concatenate(ru)
                out[f"{s}_{name}_rc"] = np.concatenate(rc)
                out[f"{s}_{name}_pit"] = np.concatenate(pt)
                out[f"{s}_{name}_po"] = np.concatenate(po)
            out[f"{s}_over"] = yv > line
        rows.append(pd.DataFrame(out))
        print("season", y, flush=True)
    T = pd.concat(rows, ignore_index=True)
    wk = (T.season.astype(str) + "_" + pd.to_datetime(T.tip).dt.isocalendar().week.astype(str)).to_numpy()
    keys = np.unique(wk)
    widx = {k: np.where(wk == k)[0] for k in keys}
    brng = np.random.default_rng(2026)
    draws = [np.concatenate([widx[k] for k in brng.choice(keys, len(keys))]) for _ in range(2000)]
    boot = lambda v: np.array([v[d].mean() for d in draws])
    seasons = T.season.to_numpy()
    app = T.app.to_numpy()
    res = {"fits": coefs, "minutes": {}, "props": {}}
    g = (T.mrps1 - T.mrps2).to_numpy()
    bs = boot(g)
    d1, d2 = pit_dec(T.mpit1[app]), pit_dec(T.mpit2[app])
    res["minutes"] = dict(rps_stage_one=round(float(T.mrps1.mean()), 6), rps_M2=round(float(T.mrps2.mean()), 6), gain=round(float(g.mean()), 6),
                          lower90=round(float(np.percentile(bs, 10)), 6), gate1=bool(np.percentile(bs, 10) > 0),
                          pit_stage_one=d1, pit_M2=d2, gate2=all(0.08 <= v <= 0.12 for v in d2),
                          short_night_rate_actual=round(float(T.short[app].mean()), 4), mean_pi=round(float(T.pi[app].mean()), 4),
                          by_season={int(y): dict(stage_one=round(float(T.mrps1[seasons == y].mean()), 6), M2=round(float(T.mrps2[seasons == y].mean()), 6)) for y in TEST})
    res["minutes"]["M2_passes"] = res["minutes"]["gate1"] and res["minutes"]["gate2"]
    low = T.low_fixed.to_numpy()
    for s in P.STATS:
        over = T[f"{s}_over"].to_numpy()
        r = {}
        for nm in ("V1", "V2", "B1", "B2", "B3", "B3m_M2"):
            r[nm] = dict(rps_uncond=round(float(T[f"{s}_{nm}_ru"].mean()), 6), rps_given_appearing=round(float(T[f"{s}_{nm}_rc"][app].mean()), 6),
                         pit_given_appearing=pit_dec(T[f"{s}_{nm}_pit"][app]),
                         by_season={int(y): round(float(T[f"{s}_{nm}_ru"][seasons == y].mean()), 6) for y in TEST})
        conf_fixed = (T[f"{s}_V1_po"] >= 0.8).to_numpy() & app
        for nm in ("V1", "V2"):
            po = T[f"{s}_{nm}_po"].to_numpy()
            own_conf = (po >= 0.8) & app
            r[nm]["over_overall"] = dict(mean_p=round(float(po[app].mean()), 4), freq=round(float(over[app].mean()), 4))
            r[nm]["over_low_minute_risk_fixed_group"] = dict(n=int((low & app).sum()), mean_p=round(float(po[low & app].mean()), 4), freq=round(float(over[low & app].mean()), 4))
            r[nm]["confident_overs_fixed_group"] = dict(n=int(conf_fixed.sum()), mean_p=round(float(po[conf_fixed].mean()), 4), freq=round(float(over[conf_fixed].mean()), 4),
                                                        by_season={int(y): dict(mean_p=round(float(po[conf_fixed & (seasons == y)].mean()), 3), freq=round(float(over[conf_fixed & (seasons == y)].mean()), 3)) for y in TEST})
            r[nm]["confident_overs_own_group"] = dict(n=int(own_conf.sum()), mean_p=round(float(po[own_conf].mean()), 4) if own_conf.any() else None,
                                                      freq=round(float(over[own_conf].mean()), 4) if own_conf.any() else None)
        own_low = T.low_own2.to_numpy() & app
        r["V2"]["over_low_minute_risk_own_group"] = dict(n=int(own_low.sum()), mean_p=round(float(T[f"{s}_V2_po"][own_low].mean()), 4), freq=round(float(over[own_low].mean()), 4))
        if s == "pts":
            gates = {}
            for b in ("B1", "B2", "B3", "B3m_M2"):
                gain = (T[f"{s}_{b}_ru"] - T[f"{s}_V2_ru"]).to_numpy()
                bsg = boot(gain)
                sb = int(sum(T[f"{s}_V2_ru"][seasons == y].mean() < T[f"{s}_{b}_ru"][seasons == y].mean() for y in TEST))
                cg = float((T[f"{s}_{b}_rc"][app] - T[f"{s}_V2_rc"][app]).mean())
                gates[b] = dict(gain=round(float(gain.mean()), 6), lower90=round(float(np.percentile(bsg, 10)), 6), g1=bool(np.percentile(bsg, 10) > 0),
                                seasons_better=sb, g2=sb >= 4, cond_gain=round(cg, 6), g4=cg > 0)
            g3 = all(0.07 <= v <= 0.13 for v in r["V2"]["pit_given_appearing"])
            r["gates_points_V2"] = dict(vs=gates, g3_calibration=g3, passes=bool(g3 and all(x["g1"] and x["g2"] and x["g4"] for x in gates.values())))
        else:
            gain = (T[f"{s}_V1_ru"] - T[f"{s}_V2_ru"]).to_numpy()
            bsg = boot(gain)
            g3 = all(0.07 <= v <= 0.13 for v in r["V2"]["pit_given_appearing"])
            gap1 = r["V1"]["over_low_minute_risk_fixed_group"]["mean_p"] - r["V1"]["over_low_minute_risk_fixed_group"]["freq"]
            gap2 = r["V2"]["over_low_minute_risk_fixed_group"]["mean_p"] - r["V2"]["over_low_minute_risk_fixed_group"]["freq"]
            r["replacement"] = dict(gain=round(float(gain.mean()), 6), lower95=round(float(np.percentile(bsg, 5)), 6), rps_ok=bool(np.percentile(bsg, 5) > 0),
                                    calibration_ok=g3, gap_frozen=round(gap1, 4), gap_M2=round(gap2, 4), gap_ok=abs(gap2) < abs(gap1))
            r["replacement"]["replace"] = bool(r["replacement"]["rps_ok"] and g3 and r["replacement"]["gap_ok"])
        res["props"][s] = r
    with open(os.path.join(HERE, "nba_minutes_tail_results.json"), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps(res["minutes"], indent=1))
    print(json.dumps({s: {k: v for k, v in res["props"][s].items() if k in ("gates_points_V2", "replacement")} for s in P.STATS}, indent=1))


if __name__ == "__main__":
    main()
