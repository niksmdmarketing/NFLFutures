"""NFL state-space ratings shadow test (research/NFL_STATE_SPACE_RULE.md).

Step "fit":   fit the five filter parameters on 2010-2021 only (2005-2009 burn-in), write model/replay/nfl_ss_params.json.
Step "games": Stage 1, game-level check on 2022-2025 weeks 2-18 (needs the params file; writes stage1 into the results json).
Step "futures": Stage 2, replay SS and SS-tau arms on 2022-2025 (4,000 sims, BT_REST=1 settings), writes model/replay/nfl_ss_<season>.csv.
Usage: python research/nfl_state_space_test.py fit|games|futures
"""
import itertools
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import FIX, NT, TEAMS, TIX, games  # noqa: E402

PARAMS = os.path.join(ROOT, "model", "replay", "nfl_ss_params.json")
RES = os.path.join(ROOT, "research", "nfl_state_space_results.json")
BURN0, FIT0, FIT1 = 2005, 2010, 2021
P_INIT = 36.0          # variance of every team's rating before the 2005 burn-in season (sd 6 points)


def load_games():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    g = g[(g.game_type == "REG") & (g.season >= BURN0)].copy()
    g["hi"] = g.home_team.map(TIX)
    g["ai"] = g.away_team.map(TIX)
    g["neutral"] = g.location.astype(str).str.lower().eq("neutral")
    return g


def season_frames(g, y):
    s = g[g.season == y]
    return {int(w): x for w, x in s.groupby("week")}


def run(g, p, seasons, record=False):
    """Filter through `seasons` (consecutive). Returns (loglik over scored games, n, snapshots, game rows).
    snapshots[(y, w)] = (mean, var diag) after week w (w=0 = preseason). game rows = per-game pre-week prediction."""
    rho, q_off, q_wk, s_g, hfa = p["rho"], p["q_off"], p["q_wk"], p["s_g"], p["hfa"]
    m = np.zeros(NT)
    P = np.eye(NT) * P_INIT
    ll, n = 0.0, 0
    snaps, rows = {}, []
    for k, y in enumerate(seasons):
        if k:
            m = rho * m
            m = m - m.mean()
            P = rho ** 2 * P + q_off * np.eye(NT)
        if record:
            snaps[(y, 0)] = (m.copy(), np.diag(P).copy())
        for w, x in sorted(season_frames(g, y).items()):
            x = x[x.result.notna()]
            if not len(x):
                continue
            ms, Ps = m.copy(), P.copy()           # pre-week snapshot: every game in the week is predicted from it
            for r in x.itertuples():
                h, a = r.hi, r.ai
                pred = ms[h] - ms[a] + (0.0 if r.neutral else hfa)
                S = Ps[h, h] + Ps[a, a] - 2 * Ps[h, a] + s_g ** 2
                e = r.result - pred
                if FIT0 <= y <= FIT1 or record:
                    ll += -0.5 * (np.log(2 * np.pi * S) + e * e / S)
                    n += 1
                if record:
                    rows.append(dict(season=y, week=int(w), game_id=r.game_id, result=float(r.result), pred=float(pred),
                                     spread=float(r.spread_line) if pd.notna(r.spread_line) else np.nan, var=float(S)))
                # sequential Kalman update with the running (not snapshot) state
                ph = P[h] - P[a]
                S2 = ph[h] - ph[a] + s_g ** 2
                K = ph / S2
                e2 = r.result - (m[h] - m[a] + (0.0 if r.neutral else hfa))
                m = m + K * e2
                P = P - np.outer(K, ph)
            P = P + q_wk * np.eye(NT)
            if record:
                snaps[(y, int(w))] = (m - m.mean(), np.diag(P).copy())
    return ll, n, snaps, rows


def fit_one(args):
    p, = args
    g = _G
    ll, n, _, _ = run(g, p, list(range(BURN0, FIT1 + 1)))
    return p, ll / n


_G = None


def fit():
    global _G
    _G = load_games()
    g1 = dict(rho=[0.5, 0.65, 0.8, 0.9], q_off=[0.0, 4.0, 8.0, 16.0, 24.0], q_wk=[0.0, 0.15, 0.3, 0.6], s_g=[12.5, 13.0, 13.5],
              hfa=[1.5, 2.25])
    def grid(d):
        keys = list(d)
        return [dict(zip(keys, v)) for v in itertools.product(*[d[k] for k in keys])]
    with Pool(os.cpu_count()) as pool:
        res = pool.map(fit_one, [(p,) for p in grid(g1)])
        best, ll1 = max(res, key=lambda t: t[1])
        print("coarse best", best, ll1, flush=True)
        steps = dict(rho=0.075, q_off=2.0, q_wk=0.075, s_g=0.25, hfa=0.375)
        g2 = {k: [max(best[k] - steps[k], 0.0), best[k], best[k] + steps[k]] for k in best}
        res2 = pool.map(fit_one, [(p,) for p in grid(g2)])
    best2, ll2 = max(res2 + [(best, ll1)], key=lambda t: t[1])
    print("refined best", best2, ll2, flush=True)
    json.dump({"params": best2, "mean_loglik_2010_2021": ll2, "coarse_best": best, "coarse_loglik": ll1, "burn_in": f"{BURN0}-2009",
               "fit": f"{FIT0}-{FIT1}", "rule": "research/NFL_STATE_SPACE_RULE.md"}, open(PARAMS, "w"), indent=1)


def stage1():
    g = load_games()
    p = json.load(open(PARAMS))["params"]
    ll, n, snaps, rows = run(g, p, list(range(BURN0, 2026)), record=True)
    D = pd.DataFrame(rows)
    T = D[(D.season >= 2022) & (D.season <= 2025) & (D.week >= 2)]
    from scipy.stats import norm
    from sklearn.linear_model import LinearRegression
    out = {"test_games": int(len(T)), "params": p}
    out["rmse"] = float(np.sqrt(np.mean((T.result - T.pred) ** 2)))
    out["rmse_by_season"] = {int(k): float(np.sqrt(np.mean((x.result - x.pred) ** 2))) for k, x in T.groupby("season")}
    win = (T.result > 0).astype(float)
    keep = T.result != 0
    pw = norm.cdf(T.pred / 13.4).clip(1e-6, 1 - 1e-6)
    out["win_logloss"] = float(-np.mean((win * np.log(pw) + (1 - win) * np.log(1 - pw))[keep]))
    ok = T[T.spread.notna()]
    b = LinearRegression().fit(np.column_stack([ok.pred, ok.spread]), ok.result)
    out["blend_with_close"] = {"model": float(b.coef_[0]), "spread": float(b.coef_[1])}
    out["close_rmse"] = float(np.sqrt(np.mean((ok.result - ok.spread) ** 2)))
    out["v4_rmse_recorded"] = 12.863302158096706
    out["stage1_gate_SS"] = out["rmse"] <= out["v4_rmse_recorded"]
    res = json.load(open(RES)) if os.path.exists(RES) else {}
    res["stage1"] = out
    json.dump(res, open(RES, "w"), indent=1)
    print(json.dumps(out, indent=1))


def stage2():
    """All three arms at every checkpoint: v4 (fresh), SS, SS-tau. Usage: ... futures [first] [last]"""
    import ratings
    import simulate
    from common import load_pbp
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 2022
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
    sims = int(os.environ.get("BT_SIMS", "4000"))
    g = load_games()
    p = json.load(open(PARAMS))["params"]
    _, _, snaps, _ = run(g, p, list(range(BURN0, 2026)), record=True)
    gall = games()
    for c in ("home_team", "away_team"):
        gall[c] = gall[c].replace(FIX)
    sim = ratings.S["sim"]
    rest = 17.891
    for y in range(first, last + 1):
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        reg_all = gall[(gall.season == y) & (gall.game_type == "REG")]
        last_week = int(reg_all.week.max())
        rows = []
        for w in range(0, min(last_week - 1, 18)):
            gg = gall.copy()
            msk = (gg.season == y) & (gg.game_type == "REG") & (gg.week > w)
            gg.loc[msk, "result"] = np.nan
            greg = gg[(gg.season == y) & (gg.game_type == "REG")]
            cur = cur_all[cur_all.week <= w] if w else cur_all.iloc[0:0]
            base, _ = ratings.base_ratings(cur, pri, gg, y)
            R4 = sim["rating_scale"] * base
            R4 = R4 - R4.mean()
            m, v = snaps[(y, w)]
            tau = np.sqrt(v)
            arms = {
                "v4": simulate.simulate(greg, R4, sims, sim["tau"], sim["sigma"], sim["hfa"], rest_pen=rest),
                "SS": simulate.simulate(greg, m - m.mean(), sims, tau, p["s_g"], p["hfa"], rest_pen=rest),
                "SS-tau": simulate.simulate(greg, R4, sims, tau, sim["sigma"], sim["hfa"], rest_pen=rest),
            }
            for arm, res in arms.items():
                for i, t in enumerate(TEAMS):
                    rows.append(dict(arm=arm, season=y, week=w, team=t, p_div=float(res["div"][i]), p_playoff=float(res["playoff"][i]),
                                     p_seed1=float(res["seed1"][i]), p_conf=float(res["conf"][i]), p_title=float(res["sb"][i])))
            print(y, w, flush=True)
        pd.DataFrame(rows).to_csv(os.path.join(ROOT, "model", "replay", f"nfl_ss_{y}.csv"), index=False)


def matched():
    """Amendment 1 (5 Nov 2026): recompute v4 pre-game margins point-in-time for the same 1,023 game IDs and compare with SS on identical rows.
    v4 harness form: r_home - r_away + intercept (as research/nfl_efficiency_weight_test.py); sim form: rating_scale x diff + hfa (neutral = 0)."""
    import ratings
    from common import load_pbp
    g = load_games()
    p = json.load(open(PARAMS))["params"]
    _, _, _, rows = run(g, p, list(range(BURN0, 2026)), record=True)
    SSd = pd.DataFrame(rows)
    SSd = SSd[(SSd.season >= 2022) & (SSd.season <= 2025) & (SSd.week >= 2)]
    gall = games()
    for c in ("home_team", "away_team"):
        gall[c] = gall[c].replace(FIX)
    sim = ratings.S["sim"]
    icpt = float(ratings.P["intercept"])
    out = []
    for y in range(2022, 2026):
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        reg = gall[(gall.season == y) & (gall.game_type == "REG")]
        for w in range(1, int(reg.week.max())):          # checkpoint w (results through week w) predicts week w+1
            gg = gall.copy()
            gg.loc[(gg.season == y) & (gg.game_type == "REG") & (gg.week > w), "result"] = np.nan
            base, _ = ratings.base_ratings(cur_all[cur_all.week <= w], pri, gg, y)
            for r in reg[(reg.week == w + 1) & reg.result.notna()].itertuples():
                d = base[TIX[r.home_team]] - base[TIX[r.away_team]]
                neutral = str(r.location).lower() == "neutral"
                out.append(dict(game_id=r.game_id, v4_harness=d + icpt,
                                v4_sim=sim["rating_scale"] * d + (0.0 if neutral else sim["hfa"])))
        print(y, flush=True)
    V = pd.DataFrame(out)
    M = SSd.merge(V, on="game_id", how="inner")
    def rm(c):
        return float(np.sqrt(np.mean((M.result - M[c]) ** 2)))
    res = {"games_ss": int(len(SSd)), "games_v4": int(len(V)), "games_matched": int(len(M)),
           "rmse_ss": rm("pred"), "rmse_v4_harness_form": rm("v4_harness"), "rmse_v4_sim_form": rm("v4_sim"),
           "rmse_close": float(np.sqrt(np.mean((M.dropna(subset=["spread"]).result - M.dropna(subset=["spread"]).spread) ** 2))),
           "by_season": {int(k): {"ss": float(np.sqrt(np.mean((x.result - x.pred) ** 2))),
                                  "v4_harness": float(np.sqrt(np.mean((x.result - x.v4_harness) ** 2))),
                                  "v4_sim": float(np.sqrt(np.mean((x.result - x.v4_sim) ** 2)))} for k, x in M.groupby("season")},
           "ss_minus_v4_harness": rm("pred") - rm("v4_harness"), "ss_minus_v4_sim": rm("pred") - rm("v4_sim")}
    # paired difference in squared error with a season-cluster bootstrap, SS vs v4 harness form
    dse = ((M.result - M.pred) ** 2 - (M.result - M.v4_harness) ** 2)
    rng = np.random.default_rng(1)
    seas = {k: x.index.values for k, x in M.groupby("season")}
    bs = []
    for _ in range(4000):
        pick = rng.integers(0, 4, 4)
        idx = np.concatenate([seas[list(seas)[i]] for i in pick])
        bs.append(dse.loc[idx].mean())
    res["paired_mse_diff_ss_minus_v4"] = {"mean": float(dse.mean()), "ci90": [float(np.percentile(bs, 5)), float(np.percentile(bs, 95))]}
    r0 = json.load(open(RES))
    r0["stage1_matched_amendment1"] = res
    json.dump(r0, open(RES, "w"), indent=1)
    print(json.dumps(res, indent=1))


MARKETS = {"division": ("p_div", "y_div"), "playoff": ("p_playoff", "y_playoff"), "No. 1 seed": ("p_seed1", "y_seed1"),
           "conference": ("p_conf", "y_finals"), "Super Bowl": ("p_title", "y_title")}


def score():
    """Stage 2 scoring against the pre-registered pass rule. Outcomes come from model/replay/nfl_<season>.csv (y_ columns)."""
    parts = []
    for y in range(2022, 2026):
        o = pd.read_csv(os.path.join(ROOT, "model", "replay", f"nfl_{y}.csv"))
        o = o[o.week == 0][["team"] + [c for c in o.columns if c.startswith("y_")]]
        a = pd.read_csv(os.path.join(ROOT, "model", "replay", f"nfl_ss_{y}.csv"))
        parts.append(a.merge(o, on="team"))
    D = pd.concat(parts, ignore_index=True)
    def ll(pc, yc, x):
        q = x[pc].clip(0.002, 0.998)
        return -(x[yc] * np.log(q) + (1 - x[yc]) * np.log(1 - q))
    # per season, per market mean log loss per arm
    L = {}
    for arm, x in D.groupby("arm"):
        L[arm] = {m: x.assign(l=ll(pc, yc, x)).groupby("season").l.mean() for m, (pc, yc) in MARKETS.items()}
    out = {"log_loss": {arm: {m: float(v.mean()) for m, v in d.items()} for arm, d in L.items()}, "arms": {}}
    rng = np.random.default_rng(1)
    for arm in ("SS", "SS-tau"):
        gain = {m: (L["v4"][m] - L[arm][m]) for m in MARKETS}
        comb = sum(gain.values()) / len(MARKETS)               # per season, mean over the five markets
        mean_gain = float(comb.mean())
        boots = np.array([comb.values[rng.integers(0, 4, 4)].mean() for _ in range(4000)])
        lo, hi = np.percentile(boots, [5, 95])
        r = {"combined_mean_gain": mean_gain, "ci90": [float(lo), float(hi)],
             "seasons_better": int((comb > 0).sum()), "gain_by_season": {int(k): float(v) for k, v in comb.items()},
             "gain_by_market": {m: float(g.mean()) for m, g in gain.items()},
             "worst_market_gain": float(min(g.mean() for g in gain.values()))}
        r["pass_stage2"] = bool(mean_gain > 0 and lo > 0 and r["seasons_better"] >= 3 and r["worst_market_gain"] >= -0.0005)
        out["arms"][arm] = r
    # fresh v4 vs the checked-in replay csv (baseline check from the rule)
    chk = {}
    for y in range(2022, 2026):
        old = pd.read_csv(os.path.join(ROOT, "model", "replay", f"nfl_{y}.csv"))
        new = D[(D.arm == "v4") & (D.season == y)]
        mm = old.merge(new, on=["week", "team"], suffixes=("_old", "_new"))
        chk[int(y)] = {"mean_abs_diff_p_title": float((mm.p_title_old - mm.p_title_new).abs().mean()),
                       "mean_abs_diff_p_playoff": float((mm.p_playoff_old - mm.p_playoff_new).abs().mean())}
    out["fresh_v4_vs_checked_in_replay"] = chk
    res = json.load(open(RES)) if os.path.exists(RES) else {}
    res["stage2"] = out
    stage1 = res.get("stage1", {})
    out["arms"]["SS"]["stage1_gate"] = bool(stage1.get("stage1_gate_SS", False))
    out["arms"]["SS"]["pass_overall"] = bool(out["arms"]["SS"]["pass_stage2"] and stage1.get("stage1_gate_SS", False))
    json.dump(res, open(RES, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"fit": fit, "games": stage1, "futures": stage2, "score": score, "matched": matched}[sys.argv[1]]()
