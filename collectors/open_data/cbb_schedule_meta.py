# Open-data collector, run from the public repo (free Actions minutes). Writes under $DATA_ROOT/collected_data/... (the open-data branch).
"""Game metadata for the college basketball simulator (ESPN via sportsdataverse schedules): which games are conference games, conference tournaments,
the NCAA tournament (tournament_id 22) or other events, plus each team's ESPN conference id. Output: collected_data/cbb/schedule_meta.csv.gz
Usage: python research/cbb_schedule_meta.py [first_year] [last_year]"""
import io
import os
import sys
import urllib.request

import pandas as pd

ROOT = os.environ.get("DATA_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "collected_data", "cbb", "schedule_meta.csv.gz")
URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_schedules/mbb_schedule_{y}.csv"
KEEP = ["game_id", "season", "season_type", "date", "neutral_site", "conference_competition", "type_abbreviation", "tournament_id", "notes_headline", "groups_id",
        "home_id", "away_id", "home_display_name", "away_display_name", "home_conference_id", "away_conference_id", "home_score", "away_score", "status_type_completed"]


def get(y):
    req = urllib.request.Request(URL.format(y=y), headers={"User-Agent": "SportsFuturesPrivate/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        s = pd.read_csv(io.BytesIO(r.read()), low_memory=False)
    for c in KEEP:
        if c not in s.columns:
            s[c] = pd.NA
    return s[KEEP]


def main(a, b):
    parts = []
    for y in range(a, b + 1):
        try:
            s = get(y)
        except Exception as e:  # noqa: BLE001
            print(y, "failed", repr(e)[:100])
            continue
        print(y, len(s), "games;", int((s.tournament_id == 22).sum()), "NCAA;", int(((s.type_abbreviation == "TRNMNT") & (s.conference_competition == True)).sum()), "conf-tournament")  # noqa: E712
        parts.append(s)
    new = pd.concat(parts, ignore_index=True)
    if os.path.exists(OUT):      # replace only the seasons just downloaded
        old = pd.read_csv(OUT, low_memory=False)
        new = pd.concat([old[~old.season.isin(new.season.unique())], new], ignore_index=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    new.to_csv(OUT, index=False, compression="gzip")


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 2008
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 2027
    main(a, b)
