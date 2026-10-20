"""Stage-two failure diagnostics (after the recorded fail; research/NBA_GAME_ENV_RULE.md). Not a test; nothing is selected here.
python research/nba_game_env_diag.py -> research/nba_game_env_diag.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nba_game_env_test as E  # noqa: E402


def load(m, T):
    z = [dict(np.load(f"{E.W}/sim_{m}_{s}.npz")) for s in E.TEST]
    z = {k: np.concatenate([p[k] for p in z]) for k in z[0]}
    o = pd.Series(np.arange(len(z["gid"])), index=z["gid"]).reindex(T.gid).to_numpy()
    return {k: v[o] for k, v in z.items()}


def variance_decomposition(T, z, mean_h, mean_a):
    eh, ea = T.hs.to_numpy() - mean_h, T.as_.to_numpy() - mean_a
    act = dict(var_home_err=eh.var(), var_away_err=ea.var(), cov_err=np.cov(eh, ea)[0, 1], var_margin_err=(eh - ea).var(),
               var_total_err=(eh + ea).var(), mean_margin_err=(eh - ea).mean(), mean_total_err=(eh + ea).mean())
    sim = dict(var_home=z["vh"].mean(), var_away=z["va"].mean(), cov=z["cov"].mean(), var_margin=(z["vh"] + z["va"] - 2 * z["cov"]).mean(),
               var_total=(z["vh"] + z["va"] + 2 * z["cov"]).mean())
    return {"actual_prediction_errors": {k: round(float(v), 2) for k, v in act.items()},
            "simulated_within_game_mean": {k: round(float(v), 2) for k, v in sim.items()},
            "between_games": {"var_sim_mean_margin": round(float(np.var(z["mh"] - z["ma"])), 2),
                              "var_actual_margin": round(float(np.var(T.hs - T.as_)), 2),
                              "var_sim_mean_total": round(float(np.var(z["mh"] + z["ma"])), 2),
                              "var_actual_total": round(float(np.var(T.total)), 2)}}


def pbp_possessions(y):
    """per team-game possession counts and points from play-by-play (same definition as the simulation inputs)."""
    import nba_game_env_poss as PP
    P = pd.read_parquet(os.path.join(PP.PBP, f"pbp_{y}.parquet"), columns=[
        "game_id", "season_type", "sequence_number", "period_number", "type_text", "team_id", "scoring_play", "score_value",
        "shooting_play", "start_quarter_seconds_remaining", "home_team_id"])
    P = P[(pd.to_numeric(P.season_type, errors="coerce") == 2)].copy()
    P["sequence_number"] = pd.to_numeric(P.sequence_number, errors="coerce")
    P = P.sort_values(["game_id", "period_number", "sequence_number"])
    tt = P.type_text.astype(str)
    tech = tt.str.contains("Technical")
    is_shot = P.shooting_play.astype(bool) & ~tech
    is_tov = tt.str.contains("Turnover") | tt.isin(["Traveling", "Offensive Charge", "Offensive Foul Turnover", "Kicked Ball Turnover"])
    is_reb = tt.isin(["Offensive Rebound", "Defensive Rebound"])
    P["pt"] = np.where(is_shot | is_tov | is_reb, P.team_id, np.nan)
    P["pts"] = np.where(P.scoring_play.astype(bool) & ~tech, pd.to_numeric(P.score_value, errors="coerce").fillna(0), 0)
    P["pt"] = P.groupby(["game_id", "period_number"]).pt.ffill()
    P = P.dropna(subset=["pt"])
    key = P.game_id.astype(str) + "_" + P.period_number.astype(str)
    P["run"] = ((P.pt != P.pt.shift()) | (key != key.shift())).cumsum()
    R = P.groupby("run").agg(gid=("game_id", "first"), per=("period_number", "first"), team=("pt", "first"), home=("home_team_id", "first"), pts=("pts", "sum"))
    R["is_home"] = R.team == R.home
    reg = R[R.per <= 4]
    g = reg.groupby(["gid", "is_home"]).agg(n=("pts", "size"), pts=("pts", "sum"), v=("pts", "var")).reset_index()
    w = g.pivot(index="gid", columns="is_home", values=["n", "pts"])
    return reg, g, w


def main():
    G = E.load_games()
    Lu = pd.read_csv(os.path.join(E.W, "lineup.csv.gz"), dtype={"tag": str})
    T, _ = E.test_games(G, Lu)
    out = {}
    # 1 + 3: variance decomposition, prediction errors vs within-game simulated uncertainty
    for m in ("G0", "G1"):
        z = load(m, T)
        out[m] = variance_decomposition(T, z, z["mh"], z["ma"])
    # 2: possession accounting (play-by-play, regulation, test seasons)
    acc = {}
    for y in E.TEST:
        reg, g, w = pbp_possessions(y)
        nh, na = w[("n", True)], w[("n", False)]
        ph, pa = w[("pts", True)], w[("pts", False)]
        p_mean, p_var = reg.pts.mean(), reg.pts.var()
        # dispersion: variance of a team's regulation points given its possession count, vs n x per-possession variance
        gg = g.copy()
        gg["exp"] = gg.n * p_mean
        resid = gg.pts - gg.exp
        acc[int(y)] = dict(poss_per_team_game_mean=round(float(g.n.mean()), 2), poss_per_team_game_sd=round(float(g.n.std()), 2),
                           diff_home_away_poss_sd=round(float((nh - na).std()), 2), corr_home_away_poss=round(float(np.corrcoef(nh, na)[0, 1]), 3),
                           pts_per_poss=round(float(p_mean), 4), var_per_poss=round(float(p_var), 4),
                           var_team_pts_given_n=round(float(resid.var()), 1), n_x_var_per_poss=round(float((gg.n * p_var).mean()), 1),
                           corr_home_away_regulation_pts=round(float(np.corrcoef(ph, pa)[0, 1]), 3),
                           corr_home_away_pts_resid_given_n=round(float(np.corrcoef(ph - nh * p_mean, pa - na * p_mean)[0, 1]), 3))
        print("pbp", y, flush=True)
    out["possession_accounting_actual"] = acc
    # simulated possession counts for a sample (G0 settings, 2024, 200 games) via a counting run
    out["simulated_possession_sample"] = sim_counts(G, T)
    # G1 audit (mean level)
    out["G1_audit"] = g1_audit(G, Lu, T)
    with open(os.path.join(HERE, "nba_game_env_diag.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


def sim_counts(G, T, s=2024, n_games=200, D=2000):
    rng = np.random.default_rng(5)
    dur, pmf, ys = E.poss_inputs(s)
    scales, per_team, sig = E.calibrate(dur, G, s, rng)
    Z = T[T.season == s].head(n_games)
    sc = np.interp(Z.pace.to_numpy(), per_team[::-1], scales[::-1])
    M = len(Z) * D
    gi = np.repeat(np.arange(len(Z)), D)
    scale = sc[gi]
    nh, na = np.zeros(M), np.zeros(M)
    tipw = rng.random(M) < 0.5
    for q in range(4):
        clock = np.full(M, 720.0)
        offh = tipw.copy() if q in (0, 3) else ~tipw
        act = np.arange(M)
        while len(act):
            nh[act] += offh[act]
            na[act] += ~offh[act]
            clock[act] -= dur[rng.integers(len(dur), size=len(act))] * scale[act]
            offh[act] = ~offh[act]
            act = act[clock[act] > 0]
    nH, nA = nh.reshape(len(Z), D), na.reshape(len(Z), D)
    resid = (nH + nA) / 2 - Z.pace.to_numpy()[:, None]
    return dict(season=s, games=len(Z), mean_poss_per_team=round(float(((nH + nA) / 2).mean()), 2),
                within_game_sd_poss_per_team=round(float(((nH + nA) / 2).std(1).mean()), 2),
                sd_home_minus_away_poss=round(float((nH - nA).std()), 2),
                actual_sd_poss_resid_same_games=round(float((Z.poss - Z.pace).std()), 2),
                mean_poss_resid=round(float(resid.mean()), 2), duration_mean=round(float(dur.mean()), 2), duration_sd=round(float(dur.std()), 2),
                duration_p99=round(float(np.percentile(dur, 99)), 1), share_zero_duration=round(float((dur == 0).mean()), 4),
                pace_factor_sd=sig)


def g1_audit(G, Lu, T):
    L = Lu[Lu.tag == "1"].drop_duplicates(["gid", "side"]).set_index(["gid", "side"])
    g = lambda side, c: np.array([L.loc[(x, side), c] for x in T.gid])
    dOh, dOa, dDh, dDa = g("h", "dO"), g("a", "dO"), g("h", "dD"), g("a", "dD")
    yM, yT = (T.hs - T.as_).to_numpy(), T.total.to_numpy()
    pace = T.pace.to_numpy() / 100
    res = {"lineup_delta_means": dict(dO=round(float(np.r_[dOh, dOa].mean()), 3), dD=round(float(np.r_[dDh, dDa].mean()), 3)),
           "lineup_delta_sds": dict(dO=round(float(np.r_[dOh, dOa].std()), 3), dD=round(float(np.r_[dDh, dDa].std()), 3)),
           "corr_net_lineup_delta_with_injury_term": None, "k_by_season": {}, "mean_level": {}}
    net = (dOh + dDh) - (dOa + dDa)
    res["corr_net_lineup_delta_with_injury_term"] = round(float(np.corrcoef(net, -T.d_av)[0, 1]), 3)
    variants = {}
    kk = {s: E.fit_k(G, Lu, s)[:2] for s in E.TEST}
    res["k_by_season"] = {int(s): [round(v, 3) for v in kk[s]] for s in E.TEST}
    kO = np.array([kk[s][0] for s in T.season])
    kD = np.array([kk[s][1] for s in T.season])
    base_h, base_a = T.ortg_h_exp.to_numpy(), T.ortg_a_exp.to_numpy()
    inj = (E.AV_SCALE * T.d_av / 2 / pace).to_numpy()
    for nm, oh, oa in (("L_team_plus_injury (G0 means)", base_h - inj, base_a + inj),
                       ("team_only_no_injury", base_h, base_a),
                       ("G1 offence+defence", base_h + kO * dOh - kD * dDa, base_a + kO * dOa - kD * dDh),
                       ("G1 offence only", base_h + kO * dOh, base_a + kO * dOa),
                       ("G1 defence only", base_h - kD * dDa, base_a - kD * dDh),
                       ("G1 + injury term (both)", base_h + kO * dOh - kD * dDa - inj, base_a + kO * dOa - kD * dDh + inj)):
        m, t = (oh - oa) * pace, (oh + oa) * pace
        variants[nm] = dict(margin_mse=round(float(np.mean((yM - m) ** 2)), 2), total_mse=round(float(np.mean((yT - t) ** 2)), 2),
                            total_bias=round(float(np.mean(yT - t)), 2), margin_bias=round(float(np.mean(yM - m)), 2))
    mB, tB = E.b_model(G.set_index("gid").reindex(T.gid).reset_index())
    hfa = float((G[G.season < 2022].hs - G[G.season < 2022].as_).mean())
    variants["B simple averages"] = dict(total_mse=round(float(np.nanmean((yT - tB) ** 2)), 2), total_bias=round(float(np.nanmean(yT - tB)), 2),
                                         margin_mse=round(float(np.nanmean((yM - mB - hfa) ** 2)), 2))
    # does G1's total gain survive removing level bias? (season-level bias removed using that season's own mean: diagnostic only)
    for nm in ("L_team_plus_injury (G0 means)", "G1 offence+defence"):
        pass
    res["mean_level"] = variants
    by = {}
    for s in E.TEST:
        msk = (T.season == s).to_numpy()
        by[int(s)] = {"L_total_bias": round(float(np.mean(yT[msk] - (base_h[msk] + base_a[msk]) * pace[msk])), 2),
                      "B_total_bias": round(float(np.nanmean(yT[msk] - tB[msk])), 2)}
    res["total_bias_by_season"] = by
    return res


if __name__ == "__main__":
    main()
