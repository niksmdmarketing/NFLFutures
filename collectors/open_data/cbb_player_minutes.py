# Open-data collector, run from the public repo (free Actions minutes). Writes under $DATA_ROOT/collected_data/... (the open-data branch).
"""Per player-team-season minutes from Sportsdataverse ESPN player box scores (open data). Output: collected_data/cbb/player_minutes.csv.gz
Columns: season, team_id, athlete_id, minutes, games, first_date (the player's first regular-season appearance for that team, so roster
membership can be taken as of any cutoff date without looking ahead), early (1 if he appeared in one of the team's first 5 games).
Regular season (season_type 2) only. Usage: python research/cbb_player_minutes.py [first] [last]"""
import io
import os
import sys
import urllib.request

import pandas as pd

ROOT = os.environ.get("DATA_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "collected_data", "cbb", "player_minutes.csv.gz")
URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_player_boxscores/player_box_{y}.csv"
COLS = ["game_id", "season_type", "game_date", "athlete_id", "team_id", "minutes", "did_not_play"]


def season(y):
    req = urllib.request.Request(URL.format(y=y), headers={"User-Agent": "SportsFuturesPrivate/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        b = pd.read_csv(io.BytesIO(r.read()), usecols=lambda c: c in COLS, low_memory=False)
    b = b[(b.season_type == 2) & b.athlete_id.notna() & b.team_id.notna()].copy()
    b["minutes"] = pd.to_numeric(b.minutes, errors="coerce").fillna(0)
    b = b[b.minutes > 0]
    b["game_date"] = pd.to_datetime(b.game_date, errors="coerce")
    tg = b.drop_duplicates(["team_id", "game_id"]).sort_values("game_date")
    tg["n"] = tg.groupby("team_id").cumcount()
    first5 = set(zip(tg[tg.n < 5].team_id, tg[tg.n < 5].game_id))
    b["early"] = [((t, g) in first5) for t, g in zip(b.team_id, b.game_id)]
    a = b.groupby(["team_id", "athlete_id"]).agg(minutes=("minutes", "sum"), games=("game_id", "nunique"), first_date=("game_date", "min"), early=("early", "max")).reset_index()
    a.insert(0, "season", y)
    a["team_id"], a["athlete_id"] = a.team_id.astype(int), a.athlete_id.astype(int)
    a["early"] = a.early.astype(int)
    a["first_date"] = a.first_date.dt.strftime("%Y-%m-%d")
    return a


def main(a, b):
    parts = []
    for y in range(a, b + 1):
        try:
            s = season(y)
            print(y, len(s), "player-team rows;", s.team_id.nunique(), "teams", flush=True)
            parts.append(s)
        except Exception as e:  # noqa: BLE001
            print(y, "failed", repr(e)[:120], flush=True)
    new = pd.concat(parts, ignore_index=True)
    if os.path.exists(OUT):
        old = pd.read_csv(OUT)
        new = pd.concat([old[~old.season.isin(new.season.unique())], new], ignore_index=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    new.to_csv(OUT, index=False, compression="gzip")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2005, int(sys.argv[2]) if len(sys.argv) > 2 else 2026)
