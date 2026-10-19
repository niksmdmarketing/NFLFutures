# Open-data collector, run from the public repo (free Actions minutes). Writes under $DATA_ROOT/collected_data/... (the open-data branch).
"""Possessions per game from ESPN team box scores (sportsdataverse releases). Output: collected_data/cbb/possessions.csv.gz
One row per game: game_id, season, poss (mean of the two teams' FGA - ORB + TO + 0.475 FTA), plus each team's estimate.
Usage: python research/cbb_box.py [first_year] [last_year]   (replaces only the seasons downloaded)"""
import io
import os
import sys
import urllib.request

import pandas as pd

ROOT = os.environ.get("DATA_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "collected_data", "cbb", "possessions.csv.gz")
URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_team_boxscores/team_box_{y}.csv"


def season(y):
    req = urllib.request.Request(URL.format(y=y), headers={"User-Agent": "SportsFuturesPrivate/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        b = pd.read_csv(io.BytesIO(r.read()), low_memory=False)
    to = b["total_turnovers"] if "total_turnovers" in b else b["turnovers"]
    if "total_turnovers" in b:
        to = to.fillna(b["turnovers"])
    b["p"] = b.field_goals_attempted - b.offensive_rebounds + to + 0.475 * b.free_throws_attempted
    b = b[b.team_home_away.isin(["home", "away"])]
    h = b[b.team_home_away == "home"][["game_id", "p"]].rename(columns={"p": "poss_home"})
    a = b[b.team_home_away == "away"][["game_id", "p"]].rename(columns={"p": "poss_away"})
    g = h.merge(a, on="game_id").drop_duplicates("game_id")
    g["poss"] = (g.poss_home + g.poss_away) / 2
    g.insert(1, "season", y)
    return g


def main(a, b):
    parts = []
    for y in range(a, b + 1):
        try:
            g = season(y)
            print(y, len(g), "games; mean possessions", round(g.poss.mean(), 1), flush=True)
            parts.append(g)
        except Exception as e:  # noqa: BLE001
            print(y, "failed", repr(e)[:100])
    if not parts:
        return
    new = pd.concat(parts, ignore_index=True)
    if os.path.exists(OUT):
        old = pd.read_csv(OUT)
        new = pd.concat([old[~old.season.isin(new.season.unique())], new], ignore_index=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    new.to_csv(OUT, index=False, compression="gzip")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2005, int(sys.argv[2]) if len(sys.argv) > 2 else 2026)
