"""Timestamp-safe historical official NBA injury reports: for EVERY regular-season game, the latest official report
published before that game's forecast cutoff (tip-off minus CUTOFF_MIN minutes), not one report per day.

- Tip-off from ESPN's schedule (game_date_time, US Eastern with offset; time_valid must be true).
- Report time = the time in the PDF file name (US Eastern, 15-minute names from 2023-24 on, hourly names earlier).
  The HTTP Last-Modified header is kept as the upload time; a report uploaded after the cutoff is skipped and the
  search continues backwards.
- Only rows for the two teams in that game (by team name and game date printed in the report) are kept.
- Each output row: season, game_id, tip_utc, cutoff_utc, report_et, report_url, uploaded_utc, team, player, status, reason.
Resumable: one file per season; a season already finished is skipped. Time budget per run (CI job limit).
Usage: python research/nba_official_pregame.py <first_end_year> <last_end_year> <market-data dir>
"""
import datetime as dt
import email.utils
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import nba as N  # noqa: E402
import nba_official as O  # noqa: E402

ET = ZoneInfo("America/New_York")
CUTOFF_MIN = 60
MAX_BACK_H = 30
BUDGET_S = 38 * 60
first, last = int(sys.argv[1]), int(sys.argv[2])
out = os.path.join(sys.argv[3], "research", "nba_pregame")
os.makedirs(out, exist_ok=True)
start = time.time()
cache = {}      # url -> (uploaded_utc or None, rows) ; None entry = not found


def fetch(url):
    if url in cache:
        return cache[url]
    time.sleep(0.12)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=O.UA), timeout=20) as r:
            body = r.read()
            lm = r.headers.get("Last-Modified")
        up = email.utils.parsedate_to_datetime(lm).astimezone(dt.timezone.utc) if lm else None
        try:
            rows = O.parse(body)
        except Exception as e:  # noqa: BLE001
            rows = [{"parse_error": str(e)[:100]}]
        cache[url] = (up, rows)
    except Exception:  # noqa: BLE001
        cache[url] = None
    return cache[url]


def candidates(cutoff_et):
    """Report names at or before the cutoff, newest first: 15-minute names, plus hourly names on the hour."""
    t = cutoff_et.replace(minute=cutoff_et.minute - cutoff_et.minute % 15, second=0, microsecond=0)
    for _ in range(MAX_BACK_H * 4):
        yield t, t.strftime("%Y-%m-%d_%I_%M%p")
        if t.minute == 0:
            yield t, t.strftime("%Y-%m-%d_%I%p")
        t -= dt.timedelta(minutes=15)


log = {}
for y in range(first, last + 1):
    path = os.path.join(out, f"pregame_{y}.csv.gz")
    if os.path.exists(path):
        continue
    s = pd.read_csv(N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 24 * 365), low_memory=False)
    s = s[(pd.to_numeric(s.season_type, errors="coerce") == 2) & s.home_abbreviation.isin(N.TEAMS) & s.away_abbreviation.isin(N.TEAMS)]
    s = s[s.time_valid.astype(str).str.lower().eq("true")]
    s["tip"] = pd.to_datetime(s.game_date_time, utc=True)
    s = s.sort_values("tip", ascending=False)
    rows, stats = [], {"games": 0, "with_report": 0, "skipped_late_upload": 0, "no_report": 0}
    partial = os.path.join(out, f"pregame_{y}.partial.csv.gz")
    done_ids = set()
    if os.path.exists(partial):
        P = pd.read_csv(partial)
        rows = P.to_dict("records")
        done_ids = set(P.game_id.astype(str))
    stopped = False
    for g in s.itertuples():
        if str(g.id) in done_ids:
            continue
        if time.time() - start > BUDGET_S:
            stopped = True
            break
        stats["games"] += 1
        cutoff = g.tip.to_pydatetime() - dt.timedelta(minutes=CUTOFF_MIN)
        found = None
        for t_et, name in candidates(cutoff.astimezone(ET)):
            u = O.BASE.format(name)
            r = fetch(u)
            if not r:
                continue
            up, rep = r
            if up and up > cutoff:
                stats["skipped_late_upload"] += 1
                continue
            found = (t_et, u, up, rep)
            break
        gd = str(g.game_date)[:10]
        teams = {N.NAMES[g.home_abbreviation]: g.home_abbreviation, N.NAMES[g.away_abbreviation]: g.away_abbreviation}
        base = dict(season=y, game_id=g.id, game_date=gd, tip_utc=g.tip.isoformat(), cutoff_utc=cutoff.isoformat())
        if not found:
            stats["no_report"] += 1
            rows.append(dict(base, report_et=None))
            continue
        stats["with_report"] += 1
        t_et, u, up, rep = found
        kept = 0
        for r in rep:
            if r.get("game_date") != gd:
                continue
            ab = O.team_abbr(r.get("team"), {k: N.NAMES[k] for k in teams.values()})
            if ab not in teams.values():
                continue
            rows.append(dict(base, report_et=t_et.isoformat(), report_url=u.rsplit("/", 1)[-1],
                             uploaded_utc=up.isoformat() if up else None, team=ab, player=r["player"], status=r["status"], reason=r.get("reason", "")))
            kept += 1
        if not kept:
            rows.append(dict(base, report_et=t_et.isoformat(), report_url=u.rsplit("/", 1)[-1], uploaded_utc=up.isoformat() if up else None,
                             team=None, player=None, status="(none listed)"))
        if stats["games"] % 100 == 0:
            pd.DataFrame(rows).to_csv(partial, index=False)
            print(y, stats, round(time.time() - start), flush=True)
    D = pd.DataFrame(rows)
    if stopped:
        D.to_csv(partial, index=False)
        log[y] = {**stats, "status": "partial (time budget); rerun to continue"}
        break
    D.to_csv(path, index=False)
    if os.path.exists(partial):
        os.remove(partial)
    log[y] = {**stats, "status": "complete", "rows": len(D)}
json.dump(log, open(os.path.join(out, f"log_{first}_{last}_{int(time.time())}.json"), "w"), indent=1)
print(json.dumps(log, indent=1))
