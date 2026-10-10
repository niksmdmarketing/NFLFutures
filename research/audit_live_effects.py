"""GPT audit (research only): size of the confirmed live-model issues, with paired simulations on today's published
inputs. Live code is imported unchanged; variants are research copies made by source substitution in memory.

NFL  A venue: no home edge for remaining games flagged Neutral vs live (home edge everywhere).
     B QB duration: a starter listed Out costs his team only the next 1 / 3 games vs the whole season (live).
     C unequal schedules: seasons 2002-2025 in which team game counts differed (when win-equivalents != win %).
NHL  D tiebreaks: add total wins and the deciding OT/SO goal to goal difference vs live comparison key.
     E points histogram cap at 160: probability mass beyond 160 in the live simulation.
NBA  F displayed game probability (game noise only) vs uncertainty-integrated probability: log loss on 2008-2026 games.
     G tiebreak exposure: how often a seeding line (1, 6, 10) or a division title is decided between teams level on wins.
Usage: python research/audit_live_effects.py <published nhl/data dir> <out.json>
"""
import inspect
import json
import math
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
SEEDS = (11, 22, 33)
res = {}


def pub(path):
    return json.loads(subprocess.check_output(["git", "-C", ROOT, "show", f"origin/published:{path}"]))


# ------------------------------------------------------------------ NFL
def nfl():
    import simulate as SIM
    from common import TEAMS, games
    S = json.load(open(os.path.join(ROOT, "model", "settings.json")))["sim"]
    src = inspect.getsource(SIM.simulate)
    needle = "+ hfa + rng.normal(0, sigma, (N, nG))"
    assert needle in src
    exec(src.replace("def simulate(", "def simulate_v(").replace(needle, "+ HV[None, :] + rng.normal(0, sigma, (N, nG))"), SIM.__dict__)
    F = pub("data/futures.json")
    wk = F["through_week"]
    R = np.array([F["teams"][t]["rating"] for t in TEAMS])
    g = games()
    g = g[(g.season == F["season"]) & (g.game_type == "REG")].copy()
    g.loc[g.week > wk, ["result", "home_score", "away_score"]] = np.nan
    g = g.sort_values(["week", "gameday", "game_id"]).reset_index(drop=True)
    keys = ("div", "playoff", "seed1", "conf", "sb")

    def run(Rv, hv, n=20000):
        outs = []
        for s in SEEDS:
            SIM.HV = hv
            p = SIM.simulate_v(g, Rv, n, S["tau"], S["sigma"], S["hfa"], seed=s)
            outs.append({k: np.asarray(p[k]) for k in keys})
        return {k: np.mean([o[k] for o in outs], 0) for k in keys}, outs

    base, bs = run(R, np.full(len(g), S["hfa"]))
    noise = {k: round(float(max(np.max(np.abs(a[k] - b[k])) for a in bs for b in bs)), 4) for k in keys}
    neutral = (g.location == "Neutral").values & g.result.isna().values
    A, _ = run(R, np.where(neutral, 0.0, S["hfa"]))
    out = {"through_week": wk, "sims": f"{len(SEEDS)} seeds x 20000", "seed_noise_max_abs": noise,
           "A_venue": {"neutral_games_remaining": int(neutral.sum()),
                       "games": [f"{a}@{h} wk{w}" for a, h, w in zip(g.away_team[neutral], g.home_team[neutral], g.week[neutral])],
                       "max_abs_change": {k: round(float(np.max(np.abs(A[k] - base[k]))), 4) for k in keys},
                       "largest": {k: sorted(((TEAMS[i], round(float(A[k][i] - base[k][i]), 4)) for i in range(32)), key=lambda x: -abs(x[1]))[:3] for k in ("playoff", "div")}}}
    # B: QB duration (only teams whose expected starter differs from the season's main QB)
    scale = json.load(open(os.path.join(ROOT, "model", "settings.json")))["sim"].get("rating_scale", 1.0)
    affected = {t: v for t, v in F["teams"].items() if v.get("qb_adj")}
    out["B_qb"] = {"teams": {t: {"qb_adj_points": v["qb_adj"], "note": v.get("qb_note")} for t, v in affected.items()}}
    if affected:
        R_no = R.copy()
        for t, v in affected.items():
            R_no[TEAMS.index(t)] -= scale * v["qb_adj"]
        R_no -= R_no.mean() - R.mean()
        for n_games in (1, 3):
            hv = np.full(len(g), S["hfa"])
            # remove the QB effect for games after the team's next n games, by shifting the home edge per game
            shift = np.zeros(len(g))
            for t, v in affected.items():
                ti = TEAMS.index(t)
                rem = g.index[g.result.isna() & ((g.home_team == t) | (g.away_team == t))]
                for j in rem[n_games:]:
                    sgn = 1 if g.home_team[j] == t else -1
                    shift[j] -= sgn * scale * v["qb_adj"]      # undo the penalty (qb_adj is negative when weaker)
            P, _ = run(R, hv + shift)
            out["B_qb"][f"out_next_{n_games}_games"] = {t: {k: [round(float(base[k][TEAMS.index(t)]), 3), round(float(P[k][TEAMS.index(t)]), 3)]
                                                           for k in ("playoff", "div", "sb")} for t in affected}
    # C: unequal schedules in history
    h = games()
    h = h[(h.game_type == "REG") & h.result.notna() & (h.season >= 2002) & (h.season < F["season"])]
    cnt = pd.concat([h[["season", "home_team"]].rename(columns={"home_team": "t"}), h[["season", "away_team"]].rename(columns={"away_team": "t"})]).groupby(["season", "t"]).size()
    uneq = cnt.groupby("season").agg(lambda x: int(x.max() - x.min()))
    out["C_unequal_schedules"] = {"seasons_with_unequal_game_counts": {int(s): int(v) for s, v in uneq.items() if v > 0},
                                  "note": "Only then can win-equivalents and win % rank teams differently."}
    res["nfl"] = out


# ------------------------------------------------------------------ NHL
def nhl_live(data_dir):
    import nhl
    import nhl_model as M
    nhl.NHL_OUT = data_dir
    F = json.load(open(os.path.join(data_dir, "futures.json")))
    sched = json.load(open(os.path.join(data_dir, "schedule.json")))
    teams = sorted(t["team"] for t in F["teams"])
    rating = {t["team"]: t["rating"] for t in F["teams"]}
    T = M.read_team(F["season"])
    state = pd.DataFrame({"points": M.numcol(T, "points"), "rw": M.numcol(T, "winsInRegulation"), "row": M.numcol(T, "regulationAndOtWins"),
                          "gd": M.numcol(T, "goalDiff"), "wins": M.numcol(T, "wins")}, index=T.index).reindex(teams).fillna(0)
    games, failed = M.fetch_schedule(teams, F["season"])      # full remaining schedule from the NHL API (as live)
    res.setdefault("nhl", {})["schedule_fetch_failed_teams"] = failed
    p = F["params"]
    per_team = pd.Series(0, index=teams)
    for a, b in games:
        per_team[a] += 1
        per_team[b] += 1
    gp = M.numcol(T, "gamesPlayed").reindex(teams).fillna(0)
    src = inspect.getsource(M.simulate)
    a1 = "gdh = (gh - ga).astype(np.float32)"
    a2 = "comp = pts * 1e8 + rw * 1e6 + rowc * 1e4 + gd * 10 + rng.random((S, T))"
    a3 = 'base = {k: state[k].reindex(teams).to_numpy(float) for k in ("points", "rw", "row", "gd")}'
    assert a1 in src and a2 in src and a3 in src
    v = (src.replace("def simulate(", "def simulate_tb(")
         .replace(a3, 'base = {k: state[k].reindex(teams).to_numpy(float) for k in ("points", "rw", "row", "gd", "wins")}')
         .replace(a1, "gdh = (gh - ga + np.where(tie, np.where(home_win, 1, -1), 0)).astype(np.float32)\n        wn = base['wins'][None, :] + home_win.astype(np.float32) @ Hm + (~home_win).astype(np.float32) @ Am")
         .replace(a2, "comp = pts * 1e10 + rw * 1e8 + rowc * 1e6 + wn * 1e4 + gd * 10 + rng.random((S, T))"))
    exec(v, M.__dict__)
    keys = ("playoffs", "div", "pres", "cup")
    runs = {"live": [], "tiebreak": []}
    for s in SEEDS:
        runs["live"].append(M.simulate(teams, state, games, rating, p["tau_now"], p["total_goals"], p["hfa"], 20000, seed=s))
        runs["tiebreak"].append(M.simulate_tb(teams, state, games, rating, p["tau_now"], p["total_goals"], p["hfa"], 20000, seed=s))
    avg = {k: {x: np.mean([r[x] for r in v_], 0) for x in keys} for k, v_ in runs.items()}
    noise = {x: round(float(max(np.max(np.abs(a[x] - b[x])) for a in runs["live"] for b in runs["live"])), 4) for x in keys}
    hist = np.mean([r["pts_hist"] for r in runs["live"]], 0)
    res["nhl"] = {**res.get("nhl", {}), "games_remaining": len(games), "per_team_played_plus_remaining": sorted(set((gp + per_team).astype(int).tolist())),
                  "seed_noise_max_abs": noise,
                  "D_tiebreak_wins_and_ot_goal": {x: round(float(np.max(np.abs(avg["tiebreak"][x] - avg["live"][x]))), 4) for x in keys},
                  "E_hist_mass_in_top_bin_160": float(hist[:, -1].max()), "E_max_mean_points": round(float(np.mean([r["pts_mean"] for r in runs["live"]], 0).max()), 1)}


# ------------------------------------------------------------------ NBA
def nba(ratings_csv):
    import nba as N
    from scipy.stats import norm
    out = {}
    if ratings_csv and os.path.exists(ratings_csv):
        R = pd.read_csv(ratings_csv).dropna(subset=["p_model", "y"])
        s_eff = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
        m = norm.ppf(R.p_model.clip(1e-4, 1 - 1e-4)) * s_eff          # research file stores the integrated probability
        y = R.y.values
        for name, s in (("game_noise_only (displayed)", N.GAME_SIGMA), ("integrated (futures)", s_eff)):
            p = np.clip(norm.cdf(m / s), 1e-4, 1 - 1e-4)
            out[name] = round(float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), 5)
        out["games"] = int(len(R))
        out["sigma_game"], out["sigma_integrated"] = N.GAME_SIGMA, round(s_eff, 2)
    res["nba_F_game_probability"] = out
    # G: exposure of seeding lines to ties in the futures simulation (wins only)
    F = pub("nba/data/futures.json")
    res["nba_G_note"] = "measured from the published win distributions: chance two teams finish level on wins at a seeding line"
    teams = F["teams"]
    lines = {}
    for conf in ("East", "West"):
        T = [t for t in teams if t.get("conf", t.get("group", "")).startswith(conf[0]) or conf in str(t.get("group", ""))]
    # approximate: independent win distributions -> P(tie at the 6/7 line) via simulation from marginals
    rng = np.random.default_rng(5)
    import nba as N2
    dist = {t["team"]: np.asarray(t.get("over") or []) for t in teams}
    sims = 20000
    ties = {"seed6_line": 0, "seed10_line": 0, "seed1": 0}
    W = {}
    for t in teams:
        o = np.asarray(t["over"])
        pmf = np.clip(o - np.append(o[1:], 0), 0, None)
        pmf = pmf / pmf.sum()
        W[t["team"]] = rng.choice(len(pmf), sims, p=pmf)
    for conf in (N2.EAST, N2.WEST):
        M_ = np.stack([W[t] for t in conf], 1)
        S_ = -np.sort(-M_, 1)
        ties["seed1"] += float((S_[:, 0] == S_[:, 1]).mean()) / 2
        ties["seed6_line"] += float((S_[:, 5] == S_[:, 6]).mean()) / 2
        ties["seed10_line"] += float((S_[:, 9] == S_[:, 10]).mean()) / 2
    res["nba_G_tie_exposure"] = {k: round(v, 3) for k, v in ties.items()}
    res["nba_G_caveat"] = "marginal win distributions treated as independent (a rough upper-level estimate of how often tiebreak rules matter)"


if __name__ == "__main__":
    data_dir, out = sys.argv[1], sys.argv[2]
    if data_dir == "fetch":      # CI: extract the published NHL data
        data_dir = os.path.join(os.path.dirname(out), "nhlpub")
        os.makedirs(data_dir, exist_ok=True)
        subprocess.run(f"git -C {ROOT} fetch -q origin published && git -C {ROOT} archive origin/published nhl/data | tar -x -C {data_dir}", shell=True, check=True)
        data_dir = os.path.join(data_dir, "nhl", "data")
    only = os.environ.get("AUDIT_ONLY")
    ratings_csv = sys.argv[3] if len(sys.argv) > 3 else None
    for f, a in ((nfl, ()), (nhl_live, (data_dir,)), (nba, (ratings_csv,))):
        if only and f.__name__ != only:
            continue
        try:
            f(*a)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            res[f.__name__ + "_error"] = str(e)
        print(f.__name__, "done", flush=True)
    json.dump(res, open(out, "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str)[:6000])
