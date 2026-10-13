"""Point-in-time replay of the AFL Brownlow Medal chances (live method: conditional logit on per-game numbers to date).

Footywire per-match stats (SuperCoach, disposals, contested possessions, clearances, goals) to each checkpoint round,
team win rate to date from the published games files, pool = 50%+ of team games and top 30 by SuperCoach, weights fitted
leave-one-season-out on final season pools (as the live page does on all seasons). Logit temperatures are scored too.
Winner = most votes in the AFL Tables archive (ties: all co-winners). Score -log p(winner(s)).
Usage: python research/afl_brownlow_replay.py <dir with published afl games_<y>.json>
"""
import json
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import award_model as AM  # noqa: E402

CODES = {"Adelaide": "ADE", "Brisbane": "BRI", "Carlton": "CAR", "Collingwood": "COL", "Essendon": "ESS", "Fremantle": "FRE",
         "GWS": "GWS", "Geelong": "GEE", "Gold Coast": "GCS", "Hawthorn": "HAW", "Melbourne": "MEL", "North Melbourne": "NTH",
         "Port Adelaide": "PTA", "Richmond": "RIC", "St Kilda": "STK", "Sydney": "SYD", "West Coast": "WCE", "Western Bulldogs": "WBD"}
FEATS = ["sc", "disposals_pg", "contested_possessions_pg", "clearances_pg", "goals_pg", "wp", "gshare"]
TEMPS = [0.7, 1.0, 1.4, 2.0]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def team_wins(games_dir, y):
    d = json.load(open(os.path.join(games_dir, f"games_{y}.json")))
    rows = []
    for r in d["rows"]:
        if str(r[1]).isdigit():
            rows.append((int(r[1]), r[2], 1.0 if r[5] == "W" else (0.5 if r[5] == "D" else 0.0)))
    return pd.DataFrame(rows, columns=["rnd", "team", "win"])


def season_pool(fw, tw, upto):
    x = fw[fw.rnd <= upto]
    t = tw[tw.rnd <= upto].groupby("team").agg(tg=("rnd", "nunique"), w=("win", "sum"))
    a = x.groupby("key").agg(name=("Player", "last"), team=("code", "last"), games=("rnd", "nunique"), sc=("SC", "mean"),
                              disposals_pg=("D", "mean"), contested_possessions_pg=("CP", "mean"), clearances_pg=("CL", "mean"),
                              goals_pg=("G", "mean"))
    a["wp"] = a.team.map(t.w / t.tg).fillna(0.5)
    a["gshare"] = a.games / a.team.map(t.tg).clip(lower=1)
    P = a[a.gshare >= .5].sort_values("sc", ascending=False).head(30).copy()
    P[FEATS] = P[FEATS].fillna(P[FEATS].median())
    return P


def main(games_dir):
    fw = pd.read_parquet(os.path.join(ROOT, "data", "afl", "footywire_player_stats.parquet"),
                         columns=["Season", "Round", "Player", "Team", "SC", "D", "CP", "CL", "G"])
    fw = fw[fw.Round.astype(str).str.match(r"^Round \d+$")].copy()
    fw["rnd"] = fw.Round.str.extract(r"(\d+)").astype(int)
    fw["code"] = fw.Team.map(CODES)
    fw["key"] = fw.Player.map(norm)
    at = pd.read_parquet(os.path.join(ROOT, "data", "afl", "afltables_player_stats.parquet"),
                         columns=["Season", "Round", "ID", "First.name", "Surname", "Brownlow.Votes"])
    at = at[at.Round.astype(str).str.isdigit()]
    votes = at.groupby(["Season", "ID"]).agg(v=("Brownlow.Votes", "sum"), first=("First.name", "last"), sur=("Surname", "last"))
    fw_names = fw.groupby(["Season", "key"]).Player.last()
    winners = {}
    for y, v in votes.groupby(level=0):
        v = v.droplevel(0)
        if v.v.max() <= 0:
            continue
        keys = set()
        for _, r in v[v.v == v.v.max()].iterrows():
            k = norm(f"{r['first']} {r['sur']}")
            have = set(fw_names.loc[y].index) if y in fw_names.index.get_level_values(0) else set()
            if k not in have:           # nickname / full-name differences (Nat/Nathan, Ollie/Oliver): unique surname + initial
                cand = [h for h in have if h.endswith(norm(r["sur"])) and h[:1] == k[:1]]
                k = cand[0] if len(cand) == 1 else k
            keys.add(k)
        winners[int(y)] = keys
    years = [y for y in range(2012, int(fw.Season.max()) + 1) if y in winners and os.path.exists(os.path.join(games_dir, f"games_{y}.json"))]
    final = {}
    tws = {}
    for y in years:
        tws[y] = team_wins(games_dir, y)
        f = fw[fw.Season == y]
        P = season_pool(f, tws[y], 99)
        P["win"] = P.index.isin(winners[y]).astype(float)
        P["season"] = y
        final[y] = P
    rows = []
    for y in years:
        if y < 2013:
            continue
        train = pd.concat([final[z] for z in years if z != y], ignore_index=True)
        train = train[train.groupby("season").win.transform("sum") == 1]
        beta = AM.fit(train, FEATS)
        f = fw[fw.Season == y]
        last = int(f.rnd.max())
        for r in range(3, last - 1, 3):
            P = season_pool(f, tws[y], r)
            P["season"] = y
            eta = AM._z(P, FEATS) @ beta
            for T in TEMPS:
                e = np.exp(eta / T - (eta / T).max())
                p = e / e.sum()
                pm = dict(zip(P.index, p))
                pw = sum(pm.get(k, 0) for k in winners[y])
                fav = max(pm, key=pm.get)
                rows.append(dict(season=y, rnd=r, frac=r / last, T=T, p_winner=pw, fav=pm[fav], fav_won=int(fav in winners[y]),
                                 nll=-np.log(max(pw, 0.002))))
        print(y, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    R = main(sys.argv[1])
    R.to_csv(os.path.join(ROOT, "model", "replay", "afl_brownlow_replay.csv"), index=False)
    R["stage"] = pd.cut(R.frac, [0, .33, .66, 1.01], labels=["early", "mid", "late"])
    print(R.pivot_table(index="stage", columns="T", values="nll", observed=True).round(3).to_string())
    print(R[R["T"] == 1.0].groupby("stage", observed=True).agg(fav=("fav", "mean"), won=("fav_won", "mean"), inpool=("p_winner", lambda s: (s > 0).mean())).round(2).to_string())
