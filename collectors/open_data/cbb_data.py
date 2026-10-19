# Open-data collector, run from the public repo (free Actions minutes). Writes under $DATA_ROOT/collected_data/... (the open-data branch).
"""Download men's college basketball results (ESPN via sportsdataverse releases) and keep one trimmed row per game.

Output: collected_data/cbb/games.csv.gz  (season, date, game_id, season_type, home_id, away_id, home_name, away_name, hs, as, neutral, conf_game?)
Sources: team box scores (scores, home/away) and schedules (neutral-site flag). Usage: python research/cbb_data.py [first_year] [last_year]
"""
import gzip
import io
import os
import sys
import urllib.request

import pandas as pd

ROOT = os.environ.get("DATA_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "collected_data", "cbb")
REL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
BOX = REL + "espn_mens_college_basketball_team_boxscores/team_box_{y}.csv"
SCH = REL + "espn_mens_college_basketball_schedules/mbb_schedule_{y}.csv"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SportsFuturesPrivate/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return pd.read_csv(io.BytesIO(r.read()), low_memory=False)


def season(y):
    box = get(BOX.format(y=y))
    box = box[box.team_home_away.isin(["home", "away"])]
    h = box[box.team_home_away == "home"][["game_id", "game_date", "season_type", "team_id", "team_display_name", "team_score"]]
    a = box[box.team_home_away == "away"][["game_id", "team_id", "team_display_name", "team_score"]]
    g = h.merge(a, on="game_id", suffixes=("_h", "_a"))
    g.columns = ["game_id", "date", "season_type", "home_id", "home_name", "hs", "away_id", "away_name", "as"]
    g["neutral"] = float("nan")
    try:
        s = get(SCH.format(y=y))
        col = next((c for c in ("neutral_site", "game_neutral_site") if c in s.columns), None)
        if col:
            n = s[["game_id", col]].drop_duplicates("game_id").set_index("game_id")[col]
            g["neutral"] = g.game_id.map(n).astype(float)
    except Exception as e:  # noqa: BLE001
        print(y, "schedule unavailable", repr(e)[:80])
    g.insert(0, "season", y)
    return g


def main(a, b):
    os.makedirs(OUT, exist_ok=True)
    parts = []
    for y in range(a, b + 1):
        try:
            g = season(y)
        except Exception as e:  # noqa: BLE001
            print(y, "failed", repr(e)[:100])
            continue
        print(y, len(g), "games, neutral known", int(g.neutral.notna().sum()))
        parts.append(g)
    if not parts:
        print("nothing downloaded; games.csv.gz unchanged")
        return
    path = os.path.join(OUT, "games.csv.gz")
    new = pd.concat(parts)
    if os.path.exists(path):      # replace only the seasons just downloaded
        old = pd.read_csv(path, compression="gzip", low_memory=False)
        new = pd.concat([old[~old.season.isin(new.season.unique())], new])
    new.sort_values(["season", "date"]).to_csv(path, index=False, compression="gzip")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2003, int(sys.argv[2]) if len(sys.argv) > 2 else 2026)
