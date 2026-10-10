"""Point-in-time test of the NFL futures model, scored market by market (run offline: python pipeline/nfl_backtest.py).

Seasons 2022-2025 (after the rating weights' 2010-2021 training window). At week 0, 4, 9 and 13 the ratings are rebuilt from
play-by-play and results up to that week only, the rest of the season is simulated, and each futures market is scored
against what happened: division winner, playoffs, No. 1 seed, conference champion, Super Bowl, and final wins.
Both the live model (v4) and the challenger (v3) are tested. The quarterback and pressure layers are switched off because
historical depth charts / injury reports as they stood each week are not available, so this tests the core engine.
Caveat: the simulation spread (tau/sigma) was tuned on 2022-2025 final win totals, so these seasons are not fully unseen.
Writes model/futures_backtest.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ratings
import simulate
import simulate_v3
from common import FIX, MODEL, TEAMS, TIX, games, load_pbp

SEASONS = (2022, 2023, 2024, 2025)
WEEKS = (0, 4, 9, 13)
MARKETS = [("div", "Division winner", 8), ("playoff", "Make the playoffs", 14), ("seed1", "No. 1 seed", 2),
           ("conf", "Conference champion", 2), ("sb", "Super Bowl", 1)]
N_SIMS = int(os.environ.get("BT_SIMS", "4000"))
TEAM_ROWS = []          # per-team probabilities and outcomes (for calibration checks)


def outcomes(g, y):
    st = pd.read_csv(os.path.join(os.path.dirname(MODEL), "data", "nfl_standings.csv"))
    st["team"] = st.team.replace(FIX)
    s = st[st.season == y].set_index("team").reindex(TEAMS)
    post = g[(g.season == y) & (g.game_type != "REG") & g.result.notna()]
    sb = post[post.game_type == "SB"].iloc[-1]
    champ = sb.home_team if sb.result > 0 else sb.away_team
    reg = g[(g.season == y) & (g.game_type == "REG")]
    wins = {t: float(((reg.home_team == t) & (reg.result > 0)).sum() + ((reg.away_team == t) & (reg.result < 0)).sum()
                     + 0.5 * (((reg.home_team == t) | (reg.away_team == t)) & (reg.result == 0)).sum()) for t in TEAMS}
    return {"div": (s.div_rank == 1).astype(float).values, "playoff": s.seed.notna().astype(float).values,
            "seed1": (s.seed == 1).astype(float).values, "conf": np.array([float(t in (sb.home_team, sb.away_team)) for t in TEAMS]),
            "sb": np.array([float(t == champ) for t in TEAMS]), "wins": np.array([wins[t] for t in TEAMS])}


def ll(p, y):
    p = np.clip(p, 0.003, 0.997)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def run():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    S = ratings.S
    v4, v3 = S["sim"], S["challenger"]
    rows = []
    for y in SEASONS:
        cur_all, pri = load_pbp(y), load_pbp(y - 1)
        out = outcomes(g, y)
        prev = outcomes(g, y - 1)["wins"] if y - 1 >= 2003 else np.full(32, 8.5)
        for w in WEEKS:
            gg = g.copy()
            m = (gg.season == y) & (gg.game_type == "REG") & (gg.week > w)
            gg.loc[m, "result"] = np.nan
            cur = cur_all[cur_all.week <= w] if w else cur_all.iloc[0:0]
            base, _ = ratings.base_ratings(cur, pri, gg, y)
            greg = gg[(gg.season == y) & (gg.game_type == "REG")]
            n_games = greg.groupby("home_team").size().add(greg.groupby("away_team").size(), fill_value=0).reindex(TEAMS).values
            played = greg[greg.result.notna()]
            wins_now = np.array([((played.home_team == t) & (played.result > 0)).sum() + ((played.away_team == t) & (played.result < 0)).sum()
                                 for t in TEAMS], float)
            gp_now = np.array([((played.home_team == t) | (played.away_team == t)).sum() for t in TEAMS], float)
            for name, P, fn, R in (("v4 (live)", v4, simulate.simulate, v4.get("rating_scale", 1.0) * base),
                                   ("v3 (challenger)", v3, simulate_v3.simulate, base)):
                R = R - R.mean()
                res = fn(greg, R, N_SIMS, P["tau"], P["sigma"], P["hfa"])
                r = dict(season=y, week=w, model=name, wins_mae=float(np.abs(res["wins"].mean(0) - out["wins"]).mean()))
                for i, t in enumerate(TEAMS):
                    TEAM_ROWS.append(dict(season=y, week=w, model=name, team=t, **{k: float(res[k][i]) for k, _, _ in MARKETS},
                                          **{"y_" + k: float(out[k][i]) for k, _, _ in MARKETS}))
                for k, _, _ in MARKETS:
                    r[k] = ll(res[k], out[k])
                    r[k + "_winner_p"] = float(res[k][out[k] == 1].mean())
                rows.append(r)
            # baselines: base rates for the markets, last season's wins (pulled halfway to 8.5) for the win totals
            r = dict(season=y, week=w, model="base rate")
            for k, _, n in MARKETS:
                r[k] = ll(np.full(32, n / 32), out[k])
                r[k + "_winner_p"] = n / 32
            rem = n_games - gp_now
            r["wins_mae"] = float(np.abs(wins_now + rem * (0.5 * (0.5 * prev / 17 + 0.25) + 0.5 * np.where(gp_now > 0, wins_now / np.maximum(gp_now, 1), 0.5))
                                         - out["wins"]).mean()) if w else float(np.abs(0.5 * prev + 0.5 * 8.5 - out["wins"]).mean())
            rows.append(r)
            print(y, w, flush=True)
    return pd.DataFrame(rows)


def summarise(D):
    res = {"seasons": f"{SEASONS[0]}-{SEASONS[-1]}", "weeks": list(WEEKS), "sims": N_SIMS, "markets": [], "wins": {}}
    for k, label, n in MARKETS:
        m = {"key": k, "label": label, "by_model": {}}
        for model, x in D.groupby("model"):
            byw = x.groupby("week")[k].mean()
            base = D[D.model == "base rate"].groupby("week")[k].mean()
            m["by_model"][model] = {"logloss": [round(float(byw[w]), 4) for w in WEEKS],
                                    "skill": [round(float(1 - byw[w] / base[w]), 3) for w in WEEKS],
                                    "winner_p": [round(float(x[x.week == w][k + "_winner_p"].mean()), 3) for w in WEEKS]}
        res["markets"].append(m)
    for model, x in D.groupby("model"):
        res["wins"][model] = [round(float(x[x.week == w].wins_mae.mean()), 2) for w in WEEKS]
    return res


if __name__ == "__main__":
    D = run()
    pd.DataFrame(TEAM_ROWS).to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), "nfl_bt_teams.csv"), index=False)
    S = summarise(D)
    json.dump(S, open(os.path.join(MODEL, "futures_backtest.json"), "w"), indent=1)
    print(json.dumps(S, indent=1))
