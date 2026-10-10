"""Collect historical official NBA injury reports (one pre-game report per game day, ~5:30 PM ET) and parse them.
Usage: python research/nba_official_history.py [first_end_year last_end_year | sample] <market-data dir>
Writes research/nba_official_reports.csv.gz (parsed rows only) and a log."""
import datetime as dt
import json
import os
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import nba as N  # noqa: E402
import nba_official as O  # noqa: E402

args, out = sys.argv[1:-1], os.path.join(sys.argv[-1], "research")
os.makedirs(out, exist_ok=True)
TIMES = ("05_30PM", "05_00PM", "05_15PM", "05_45PM", "04_30PM", "06_00PM", "01_30PM", "12_30PM",
         "05PM", "04PM", "06PM", "01PM", "12PM")   # earlier seasons were published on the hour (HHPM)
sample = args[:1] == ["sample"]
first, last = (2026, 2026) if sample else (int(args[0]), int(args[1])) if len(args) == 2 else (2020, 2026)
start = time.time()
rows, log = [], {"days": 0, "found": 0, "missing": []}
for y in range(first, last + 1):
    s = pd.read_csv(N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 24 * 365), low_memory=False)
    s = s[pd.to_numeric(s.season_type, errors="coerce") == 2]
    days = sorted(pd.to_datetime(s.game_date).dt.date.unique())
    if sample:
        days = [d for d in days if str(d) in ("2026-02-26", "2026-04-10", "2025-12-25")]
    days = sorted(days, reverse=True)   # newest first
    for d in days:
        if time.time() - start > 38 * 60:
            log["stopped_early"] = str(d)
            break
        log["days"] += 1
        for t in TIMES:
            u = O.BASE.format(f"{d.isoformat()}_{t}")
            try:
                with O.urllib.request.urlopen(O.urllib.request.Request(u, headers=O.UA), timeout=20) as resp:
                    b = resp.read()
            except Exception as e:  # noqa: BLE001
                b = None
                if len(log.setdefault("errors", [])) < 15:
                    log["errors"].append(f"{u.rsplit('/', 1)[-1]} {str(e)[:80]}")
            time.sleep(0.15)
            if b:
                try:
                    for r in O.parse(b):
                        r.update(report=f"{d} {t}", season=y)
                        rows.append(r)
                    log["found"] += 1
                except Exception as e:  # noqa: BLE001
                    log.setdefault("parse_errors", []).append(f"{u} {e}")
                break
        else:
            log["missing"].append(str(d))
R = pd.DataFrame(rows)
name = "nba_official_sample.csv" if sample else f"nba_official_reports_{first}_{last}.csv.gz"
R.to_csv(os.path.join(out, name), index=False)
log["rows"] = len(R)
log["status_counts"] = R.status.value_counts().to_dict() if len(R) else {}
log["missing_n"] = len(log["missing"])
log["missing"] = log["missing"][:50]
json.dump(log, open(os.path.join(out, name.split(".")[0] + "_log.json"), "w"), indent=1)
print(json.dumps(log, indent=1)[:3000])
