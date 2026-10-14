"""Collect per-game NHL lineups (research): every skater and goalie appearance with ice time, from the NHL stats API
(isGame=true summary reports, one request per season and kind, sequential). Writes data/research/nhl_lineups/
{skaters,goalies}_<y>.csv.gz with game_id, date, team, opp, home, player_id, name, pos, toi (seconds), started (goalies).
Usage: python research/nhl_lineups_collect.py [first] [last]"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "research", "nhl_lineups")
API = "https://api.nhle.com/stats/rest/en"


def sid(y):
    return y * 10000 + y + 1


def get(kind, y):
    rows, start, page = [], 0, 10000
    while True:
        q = {"isAggregate": "false", "isGame": "true", "limit": str(page), "start": str(start),
             "sort": "gameId", "cayenneExp": f"seasonId={sid(y)} and gameTypeId=2"}
        url = f"{API}/{kind}/summary?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0 (private research; low volume)"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    raise SystemExit(f"stopped: HTTP {e.code}")
                time.sleep(5 * (attempt + 1))
            except Exception:  # noqa: BLE001
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"failed {kind} {y} at {start}")
        part = d.get("data", [])
        rows += part
        total = d.get("total", len(rows))
        start += len(part)
        print(kind, y, start, "/", total, flush=True)
        if not part or start >= total:
            return rows
        time.sleep(1)


def main(first, last):
    os.makedirs(OUT, exist_ok=True)
    for y in range(first, last + 1):
        for kind in ("skater", "goalie"):
            path = os.path.join(OUT, f"{kind}s_{y}.csv.gz")
            if os.path.exists(path) and y < last:
                continue
            R = pd.DataFrame(get(kind, y))
            if R.empty:
                continue
            name = "skaterFullName" if kind == "skater" else "goalieFullName"
            out = pd.DataFrame({"game_id": R.gameId, "date": R.gameDate, "team": R.teamAbbrev, "opp": R.opponentTeamAbbrev,
                                "home": (R.homeRoad == "H").astype(int), "player_id": R.playerId, "name": R[name],
                                "pos": R.positionCode if "positionCode" in R else "G"})
            if kind == "skater":
                out["toi"] = R.timeOnIcePerGame.round().astype("Int64")
            else:
                out["toi"] = R.timeOnIce.round().astype("Int64")
                out["started"] = R.gamesStarted.fillna(0).astype(int)
                out["sa"] = R.shotsAgainst
                out["ga"] = R.goalsAgainst
            out.to_csv(path, index=False)
            time.sleep(2)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 2014, int(a[1]) if len(a) > 1 else 2026)
