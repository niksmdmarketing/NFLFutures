"""Collect NHL player birth dates (research): skater and goalie bios reports, one request per season and kind.
Writes data/research/nhl_bios.csv (player_id, name, birth_date, pos)."""
import json
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []
for y in range(2010, 2027):
    for kind, nm in (("skater", "skaterFullName"), ("goalie", "goalieFullName")):
        q = {"isAggregate": "false", "isGame": "false", "limit": "-1", "start": "0", "cayenneExp": f"seasonId={y * 10000 + y + 1} and gameTypeId=2"}
        url = f"https://api.nhle.com/stats/rest/en/{kind}/bios?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"}), timeout=120) as r:
            d = json.load(r).get("data", [])
        for x in d:
            rows.append((x.get("playerId"), x.get(nm), x.get("birthDate"), x.get("positionCode", "G")))
        print(y, kind, len(d), flush=True)
        time.sleep(1)
pd.DataFrame(rows, columns=["player_id", "name", "birth_date", "pos"]).drop_duplicates("player_id").to_csv(os.path.join(ROOT, "data", "research", "nhl_bios.csv"), index=False)
