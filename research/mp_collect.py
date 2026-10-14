"""Collect MoneyPuck season summaries (skaters, goalies; regular season; situation 'all' and '5on5') 2010-2025 into
data/research/mp/<kind>_<year>.csv.gz with the columns the NHL player research needs. Checks robots.txt first and stops
on 403/429. Run in GitHub Actions (the research workspace cannot reach MoneyPuck). Data: MoneyPuck.com (free, attribution)."""
import io
import os
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "research", "mp")
UA = "SportsFutures/1.0"
KEEP = {
    "skaters": ["playerId", "season", "name", "team", "position", "situation", "games_played", "icetime", "I_F_points", "I_F_goals",
                "I_F_xGoals", "onIce_xGoalsPercentage", "OnIce_F_xGoals", "OnIce_A_xGoals", "OnIce_F_goals", "OnIce_A_goals",
                "offIce_xGoalsPercentage", "OffIce_F_xGoals", "OffIce_A_xGoals", "gameScore", "shifts"],
    "goalies": ["playerId", "season", "name", "team", "position", "situation", "games_played", "icetime", "xGoals", "goals",
                "unblocked_shot_attempts", "ongoal"],
}


def main(first, last):
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request("https://moneypuck.com/robots.txt", headers={"User-Agent": UA})
        rp.parse(urllib.request.urlopen(req, timeout=30).read().decode().splitlines())
    except urllib.error.HTTPError as e:
        print("robots", e.code)
        if e.code in (403, 429):
            return 1
    os.makedirs(OUT, exist_ok=True)
    for y in range(first, last + 1):
        for kind in ("skaters", "goalies"):
            url = f"https://moneypuck.com/moneypuck/playerData/seasonSummary/{y}/regular/{kind}.csv"
            if not rp.can_fetch(UA, url):
                print("disallowed", url)
                return 1
            path = os.path.join(OUT, f"{kind}_{y}.csv.gz")
            if os.path.exists(path):
                continue
            try:
                raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
            except urllib.error.HTTPError as e:
                print(url, e.code)
                if e.code in (403, 429):
                    return 1
                continue
            d = pd.read_csv(io.BytesIO(raw), low_memory=False)
            d = d[d.situation.isin(["all", "5on5"])][[c for c in KEEP[kind] if c in d.columns]]
            d.to_csv(path, index=False, compression="gzip")
            print(y, kind, len(d), flush=True)
            time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2010, int(sys.argv[2]) if len(sys.argv) > 2 else 2025))
