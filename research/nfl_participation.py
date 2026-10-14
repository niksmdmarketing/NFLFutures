"""Play-level dataset for NFL player ratings: scrimmage plays (as ratings.scrimmage) with EPA and the 11 offensive and
11 defensive players on the field (nflverse pbp_participation, 2016-2025). Writes <out>/plays_<season>.parquet with
game_id, season, week, posteam, defteam, epa, off (11 ids ';'-joined), def (11 ids).
Usage: python research/nfl_participation.py <out dir> [first] [last]"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import DATA, load_pbp, scrimmage  # noqa: E402


def season(y, out):
    s = scrimmage(load_pbp(y))[["game_id", "play_id", "week", "posteam", "defteam", "epa", "db", "season"]]
    p = pd.read_csv(os.path.join(DATA, f"pbp_participation_{y}.csv"), low_memory=False,
                    usecols=["nflverse_game_id", "play_id", "offense_players", "defense_players"])
    p = p.rename(columns={"nflverse_game_id": "game_id"})
    d = s.merge(p, on=["game_id", "play_id"], how="inner").dropna(subset=["offense_players", "defense_players"])
    d = d[(d.offense_players.str.count(";") == 10) & (d.defense_players.str.count(";") == 10)]
    d = d.rename(columns={"offense_players": "off", "defense_players": "def"})
    d.to_parquet(os.path.join(out, f"plays_{y}.parquet"), index=False)
    print(y, "scrimmage", len(s), "with 11+11 players", len(d), flush=True)


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    a = int(sys.argv[2]) if len(sys.argv) > 2 else 2016
    b = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
    for y in range(a, b + 1):
        season(y, out)
