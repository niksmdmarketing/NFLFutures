"""Replay of the AFL Coleman Medal race (most home-and-away goals) with pipeline/race_sim.py.
Per-match player goals from the fitzRoy AFL Tables archive; checkpoint after every 3rd round; prior = last season's goals
per game (8+ games), else NEW_RATE. Grid over K and talent-noise shape; score -log p(winner(s)).
Usage: python research/afl_coleman_replay.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import race_sim  # noqa: E402

NEW_RATE = 0.4


def load():
    d = pd.read_parquet(os.path.join(ROOT, "data", "afl", "afltables_player_stats.parquet"),
                        columns=["Season", "Round", "Date", "ID", "First.name", "Surname", "Playing.for", "Goals"])
    d = d[d.Round.astype(str).str.isdigit()].copy()
    d["rnd"] = d.Round.astype(int)
    d["pid"] = d.ID
    d["team"] = d["Playing.for"]
    return d


def checkpoint(d, prev, rnd, k, shape):
    done = d[d.rnd <= rnd]
    n_rounds = d.rnd.max()
    tm_played = done.groupby("team").rnd.nunique()
    tm_total = d.groupby("team").rnd.nunique()
    g = done.groupby("pid").agg(goals=("Goals", "sum"), apps=("rnd", "nunique"), team=("team", "last"))
    pr = prev.groupby("pid").agg(goals=("Goals", "sum"), apps=("rnd", "nunique"))
    prior = (pr.goals / pr.apps).where(pr.apps >= 8)
    g["prior"] = g.index.map(prior).fillna(NEW_RATE)
    g["T"] = g.team.map(tm_played).fillna(0)
    g["R"] = (g.team.map(tm_total) - g["T"]).clip(lower=0)
    g = g.sort_values("goals", ascending=False).head(60)
    p, proj = race_sim.simulate_race(g.goals, g.apps, g["T"], g["R"], g.prior, k, shape, sims=4000)
    return dict(zip(g.index, p))


def main():
    d = load()
    rows = []
    for y in range(2013, int(d.Season.max()) + 1):
        cur, prev = d[d.Season == y], d[d.Season == y - 1]
        if cur.empty or cur.rnd.max() < 20:
            continue
        fin = cur.groupby("pid").Goals.sum()
        winners = set(fin[fin == fin.max()].index)
        for rnd in range(3, int(cur.rnd.max()) - 1, 3):
            for k in (4, 8, 12):
                for shape in (3, 5, 8):
                    pm = checkpoint(cur, prev, rnd, k, shape)
                    pw = sum(pm.get(p, 0) for p in winners)
                    fav = max(pm, key=pm.get)
                    rows.append(dict(season=y, rnd=rnd, frac=rnd / cur.rnd.max(), k=k, shape=shape, p_winner=pw, fav=pm[fav],
                                     fav_won=int(fav in winners), nll=-np.log(max(pw, 0.002))))
        print(y, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    R = main()
    R.to_csv(os.path.join(ROOT, "model", "replay", "afl_coleman_replay.csv"), index=False)
    R["stage"] = pd.cut(R.frac, [0, .33, .66, 1.01], labels=["early", "mid", "late"])
    print(R.groupby(["k", "shape"]).nll.mean().round(3).unstack().to_string())
    best = R.groupby(["k", "shape"]).nll.mean().idxmin()
    x = R[(R.k == best[0]) & (R["shape"] == best[1])]
    print("best", best, x.groupby("stage", observed=True).agg(nll=("nll", "mean"), fav=("fav", "mean"), won=("fav_won", "mean")).round(3).to_string())
