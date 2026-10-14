"""Collect MoneyPuck game-by-game team expected goals (research): one file per team, regular season and playoffs,
situation 'all', 2010 on. Checks robots.txt first, sequential requests, stops on 403/429. Run in GitHub Actions.
Writes data/research/mp/team_games.csv.gz. Data: MoneyPuck.com (free, attribution)."""
import io
import os
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "research", "mp", "team_games.csv.gz")
UA = "SportsFutures/1.0"
BASE = "https://moneypuck.com/moneypuck/playerData/careers/gameByGame"
TEAMS = ["ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "L.A", "MIN", "MTL", "N.J",
         "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "S.J", "SEA", "STL", "T.B", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH", "ATL", "LAK", "NJD", "SJS", "TBL"]
KEEP = ["team", "season", "gameId", "playoffGame", "opposingTeam", "home_or_away", "gameDate", "situation", "xGoalsFor",
        "xGoalsAgainst", "goalsFor", "goalsAgainst", "scoreVenueAdjustedxGoalsFor", "scoreVenueAdjustedxGoalsAgainst",
        "shotsOnGoalFor", "shotsOnGoalAgainst"]


def main():
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(urllib.request.urlopen(urllib.request.Request("https://moneypuck.com/robots.txt", headers={"User-Agent": UA}), timeout=30).read().decode().splitlines())
    except urllib.error.HTTPError as e:
        print("robots", e.code)
        if e.code in (403, 429):
            return 1
    frames = []
    for t in TEAMS:
        for kind in ("regular", "playoffs"):
            url = f"{BASE}/{kind}/teams/{t}.csv"
            if not rp.can_fetch(UA, url):
                print("disallowed", url)
                return 1
            try:
                raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
            except urllib.error.HTTPError as e:
                print(url, e.code, flush=True)
                if e.code in (403, 429):
                    return 1
                continue
            d = pd.read_csv(io.BytesIO(raw), low_memory=False)
            d = d[(d.situation == "all") & (d.season >= 2010)][[c for c in KEEP if c in d.columns]]
            frames.append(d)
            print(t, kind, len(d), flush=True)
            time.sleep(2)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pd.concat(frames, ignore_index=True).drop_duplicates(["gameId", "team"]).to_csv(OUT, index=False, compression="gzip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
