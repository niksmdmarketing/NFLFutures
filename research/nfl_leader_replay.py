"""Replay of NFL season stat-leader races (most passing yards, passing TDs, rushing yards, receiving yards, receptions,
sacks) with pipeline/race_sim.py. Weekly player stats (nflverse) to each checkpoint (weeks 3, 5, ..., 15), rate per game
shrunk toward last season's (K games), availability, team games left. Winner(s) = season leaders (regular season).
Grid over K and talent noise; score -log p(winner(s)).
Usage: python research/nfl_leader_replay.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import race_sim  # noqa: E402
from nfl_awards_replay import weekly  # noqa: E402
from common import FIX, TEAMS, games  # noqa: E402

STATS = {"passing_yards": "yards", "passing_tds": "count", "rushing_yards": "yards", "receiving_yards": "yards",
         "receptions": "count", "def_sacks": "count"}
NEW = {"passing_yards": 150.0, "passing_tds": 1.0, "rushing_yards": 30.0, "receiving_yards": 30.0, "receptions": 2.5, "def_sacks": 0.3}


def race(d, prev, stat, wk, team_games, k, shape):
    cur = d[d.week <= wk]
    a = cur.groupby("player_id").agg(v=(stat, "sum"), g=("week", "nunique"), team=("team", "last"))
    a = a[a.v > 0]
    pv = prev.groupby("player_id").agg(v=(stat, "sum"), g=("week", "nunique"))
    prior = (pv.v / pv.g).where(pv.g >= 6)
    played = {t: n for t, n in team_games.items()}
    T = a.team.map(lambda t: played[t][0] if t in played else wk).astype(float)
    R = a.team.map(lambda t: played[t][1] if t in played else 17 - wk).astype(float)
    pr = a.index.map(prior).to_series(index=a.index).fillna(NEW[stat])
    rate = (a.v + k * pr) / (a.g + k)
    a = a.assign(T=T, R=R, pr=pr, score=a.v + rate * R).sort_values("score", ascending=False).head(50)
    f = race_sim.simulate_race_yards if STATS[stat] == "yards" else race_sim.simulate_race
    p, proj = f(a.v, a.g, a["T"], a["R"], a.pr, k, shape, sims=3000)
    return dict(zip(a.index, p))


def main():
    G = games()
    for c in ("home_team", "away_team"):
        G[c] = G[c].replace(FIX)
    W = {y: weekly(y) for y in range(2011, 2026)}
    rows = []
    for y in range(2012, 2026):
        d, prev = W[y], W[y - 1]
        g = G[(G.season == y) & (G.game_type == "REG")]
        total = {t: int(((g.home_team == t) | (g.away_team == t)).sum()) for t in TEAMS}
        for stat in STATS:
            fin = d.groupby("player_id")[stat].sum()
            winners = set(fin[fin == fin.max()].index)
            for wk in range(3, 16, 2):
                gg = g[g.week <= wk]
                tg = {t: (int(((gg.home_team == t) | (gg.away_team == t)).sum()), total[t] - int(((gg.home_team == t) | (gg.away_team == t)).sum())) for t in TEAMS}
                for k in (2, 4, 8):
                    for shape in (8, 20, 50):
                        pm = race(d, prev, stat, wk, tg, k, shape)
                        pw = sum(pm.get(p, 0) for p in winners)
                        fav = max(pm, key=pm.get)
                        rows.append(dict(season=y, stat=stat, week=wk, k=k, shape=shape, p_winner=pw, fav=pm[fav], fav_won=int(fav in winners),
                                         nll=-np.log(max(pw, 0.002))))
        print(y, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    R = main()
    R.to_csv(os.path.join(ROOT, "model", "replay", "nfl_leader_replay.csv"), index=False)
    print(R.groupby(["stat", "k", "shape"]).nll.mean().unstack().round(3).to_string())
