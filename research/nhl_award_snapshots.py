"""Fetch dated NHL season-to-date snapshots for the award replay (runs in GitHub Actions; the NHL API is not reachable
from every machine). For each regular season 2011-12 .. 2025-26 and a checkpoint every 21 days, three aggregated reports
filtered to games on or before the checkpoint: skater summary, goalie summary, team summary. Only the columns the award
model uses are kept. Output: model/replay/nhl_award_snapshots/<start year>.json.gz  {date: {skaters, goalies, teams}}.
Sequential and polite (0.5 s between requests); resumable (finished seasons are skipped).
Usage: python research/nhl_award_snapshots.py [first] [last]
"""
import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.nhle.com/stats/rest/en"
OUT = os.path.join(ROOT, "model", "replay", "nhl_award_snapshots")
KEEP = {"skater": ["playerId", "skaterFullName", "teamAbbrevs", "positionCode", "gamesPlayed", "points", "goals", "timeOnIcePerGame"],
        "goalie": ["playerId", "goalieFullName", "teamAbbrevs", "gamesPlayed", "saves", "shotsAgainst", "wins"],
        "team": ["teamId", "teamFullName", "gamesPlayed", "pointPct", "points"]}


def get(kind, y, day):
    sid = y * 10000 + y + 1
    q = {"isAggregate": "true" if kind != "team" else "false", "isGame": "false", "limit": "-1", "start": "0",
         "cayenneExp": f'seasonId={sid} and gameTypeId=2 and gameDate<="{day} 23:59:59"'}
    url = f"{API}/{kind}/summary?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0 (award research)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                rows = json.load(r).get("data", [])
            return [{k: x.get(k) for k in KEEP[kind]} for x in rows]
        except Exception as e:  # noqa: BLE001
            print("retry", kind, y, day, e, flush=True)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"failed {kind} {y} {day}")


def season_dates(y):
    """First and last regular-season game dates from the published games file (site/nhl/data/games_<y>.json)."""
    p = os.path.join(ROOT, "site", "nhl", "data", f"games_{y}.json")
    d = json.load(open(p))
    days = sorted({r[0] for r in d["rows"]})
    return dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])


def main(first, last):
    os.makedirs(OUT, exist_ok=True)
    for y in range(first, last + 1):
        path = os.path.join(OUT, f"{y}.json.gz")
        if os.path.exists(path):
            continue
        try:
            a, b = season_dates(y)
        except Exception as e:  # noqa: BLE001
            print("no dates", y, e)
            continue
        out = {}
        d = a + dt.timedelta(days=21)
        while d < b - dt.timedelta(days=5):
            out[str(d)] = {k: get(k, y, str(d)) for k in ("skater", "goalie", "team")}
            time.sleep(0.5)
            d += dt.timedelta(days=21)
        with gzip.open(path, "wt") as f:
            json.dump(out, f, separators=(",", ":"))
        print("season", y, "checkpoints", len(out), flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2011, int(sys.argv[2]) if len(sys.argv) > 2 else 2025)
