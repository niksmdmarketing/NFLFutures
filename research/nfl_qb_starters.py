"""Starting-QB labels for the QB oracle replay (research/NFL_QB_ORACLE_RULE.md, amendment of 27 Oct 2026).
For every 2013-2025 regular-season game and team, three independent labels (gsis ids):
  snap1  - the QB (players.csv position QB) on the field for the team's first offensive scrimmage play (pbp participation; 2016 on). This is the
           gamebook definition of a starter (the first-play lineup).
  drop1  - the QB who took the team's first dropback (pbp), the label used before the amendment.
  gcsv   - games.csv home/away_qb_id (nflverse; known to contain errors).
  snaps  - the QB with most offensive snaps in the game (PFR snap counts via nflverse), mapped to gsis via players.csv.
Choice (fixed before any gains): snap1 when available; otherwise (2013-2015, or no QB found) the majority of
drop1 / gcsv / snaps, with drop1 breaking a three-way split. Writes research/nfl_qb_starter_labels.csv.
"""
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
from common import DATA, FIX, games, load_pbp, scrimmage  # noqa: E402
from nfl_qb_backtest import starters  # noqa: E402

SEASONS = range(2013, 2026)
SNAPS = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{}.csv"


def snap_counts(y):
    p = os.path.join(DATA, f"snap_counts_{y}.csv")
    if not os.path.exists(p):
        urllib.request.urlretrieve(SNAPS.format(y), p)
    return pd.read_csv(p)


def first_snap(y, pbp, qbset, d1):
    p = os.path.join(DATA, f"pbp_participation_{y}.csv")
    if not os.path.exists(p):
        return {}
    part = pd.read_csv(p, usecols=["nflverse_game_id", "play_id", "possession_team", "offense_players"])
    s = scrimmage(pbp)[["game_id", "play_id", "posteam"]]
    m = s.merge(part, left_on=["game_id", "play_id"], right_on=["nflverse_game_id", "play_id"]).sort_values(["game_id", "play_id"])
    out = {}
    for r in m.itertuples():
        k = (r.game_id, r.posteam)
        if k in out or not isinstance(r.offense_players, str):
            continue
        q = [i for i in r.offense_players.split(";") if i in qbset]
        if len(q) > 1 and d1.get(k) in q:  # two listed QBs on the first play (e.g. a QB used as a gadget player)
            q = [d1[k]]
        if len(q) == 1:
            out[k] = q[0]
    return out


def main():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    pl = pd.read_csv(os.path.join(DATA, "players.csv"), usecols=["gsis_id", "pfr_id", "display_name", "position"], low_memory=False)
    qbset = set(pl[pl.position == "QB"].gsis_id.dropna())
    pfr2gsis = pl.dropna(subset=["pfr_id", "gsis_id"]).set_index("pfr_id").gsis_id.to_dict()
    name = pl.dropna(subset=["gsis_id"]).set_index("gsis_id").display_name.to_dict()
    rows = []
    for y in SEASONS:
        pbp = load_pbp(y)
        pbp = pbp[pbp.season_type == "REG"]
        d1 = starters(pbp)
        s1 = first_snap(y, pbp, qbset, d1)
        sc = snap_counts(y)
        sc = sc[(sc.game_type == "REG") & (sc.position == "QB")].copy()
        sc["team"] = sc.team.replace(FIX)
        lead = sc.sort_values("offense_snaps", ascending=False).drop_duplicates(["game_id", "team"])
        lead = {(r.game_id, r.team): pfr2gsis.get(r.pfr_player_id) for r in lead.itertuples()}
        reg = g[(g.season == y) & (g.game_type == "REG") & g.result.notna()]
        for r in reg.itertuples():
            for t, gc in ((r.home_team, r.home_qb_id), (r.away_team, r.away_qb_id)):
                k = (r.game_id, t)
                lab = dict(snap1=s1.get(k), drop1=d1.get(k), gcsv=gc if isinstance(gc, str) else None, snaps=lead.get(k))
                if lab["snap1"]:
                    chosen, src = lab["snap1"], "snap1"
                else:
                    v = [lab[x] for x in ("drop1", "gcsv", "snaps") if lab[x]]
                    cnt = pd.Series(v).value_counts() if v else pd.Series(dtype=int)
                    if len(cnt) and cnt.iloc[0] >= 2:
                        chosen, src = cnt.index[0], "majority"
                    else:
                        chosen, src = lab["drop1"], "drop1_fallback"
                agree = len({x for x in lab.values() if x}) == 1
                rows.append(dict(season=y, week=r.week, game_id=r.game_id, team=t, **lab, chosen=chosen, source=src,
                                 all_agree=agree, chosen_name=name.get(chosen), drop1_name=name.get(lab["drop1"]),
                                 gcsv_name=name.get(lab["gcsv"])))
        print(y, flush=True)
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(ROOT, "research", "nfl_qb_starter_labels.csv"), index=False)
    print(D.groupby("source").size())
    print("chosen != drop1:", int((D.chosen != D.drop1).sum()), " chosen != gcsv:", int((D.chosen != D.gcsv).sum()),
          " missing chosen:", int(D.chosen.isna().sum()), " rows:", len(D))


if __name__ == "__main__":
    main()
