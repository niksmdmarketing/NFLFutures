"""Verify the pre-game report selection (research/nba_official_pregame.py) without storing PDFs.

For every distinct report selected in research/nba_pregame/pregame_<season>.csv.gz: re-download it once and record
HTTP status, Last-Modified (again), size, SHA-256 and the time PRINTED inside the PDF ("Injury Report: MM/DD/YY HH:MM PM",
US Eastern). Then, per game, flag whether the printed time and the Last-Modified time are both at or before that game's
cutoff (tip-off minus 60 minutes). Hourly file names (seasons before 2023-24) can hold half-hour reports, so the printed
time is the check that matters there. Output: research/nba_pregame/verify_<season>.csv(.gz) + verify_<season>_summary.json.
Usage: python research/nba_pregame_verify.py <season end year> <market-data dir>
"""
import datetime as dt
import email.utils
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
BASE = "https://ak-static.cms.nba.com/referee/injury/"
UA = {"User-Agent": "Mozilla/5.0 (SportsFutures research; low volume)"}
y, root = int(sys.argv[1]), sys.argv[2]
folder = os.path.join(root, "research", "nba_pregame")
G = pd.read_csv(os.path.join(folder, f"pregame_{y}.csv.gz"))
games = G.drop_duplicates("game_id")[["season", "game_id", "game_date", "tip_utc", "cutoff_utc", "report_et", "report_url", "uploaded_utc"]]
rep = {}
for name in sorted(games.report_url.dropna().unique()):
    time.sleep(0.15)
    e = {"report_url": name}
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=30) as r:
            body = r.read()
            e["http_status"] = r.status
            lm = r.headers.get("Last-Modified")
        e["last_modified_now_utc"] = email.utils.parsedate_to_datetime(lm).astimezone(dt.timezone.utc).isoformat() if lm else None
        e["bytes"], e["sha256"] = len(body), hashlib.sha256(body).hexdigest()
        import pdfplumber
        with pdfplumber.open(io.BytesIO(body)) as P:
            txt = (P.pages[0].extract_text() or "")[:600]
        m = re.search(r"Injury Report:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}:\d{2}\s*[AP]M)", txt)
        if m:
            fmt = "%m/%d/%y %I:%M %p" if len(m.group(1).split("/")[2]) == 2 else "%m/%d/%Y %I:%M %p"
            e["printed_et"] = dt.datetime.strptime(f"{m.group(1)} {m.group(2).replace(' ', '')[:-2]} {m.group(2)[-2:]}", fmt).replace(tzinfo=ET).isoformat()
        else:
            e["printed_et"] = None
    except Exception as ex:  # noqa: BLE001
        e["http_status"] = getattr(ex, "code", None) or type(ex).__name__
    rep[name] = e
R = pd.DataFrame(rep.values())
V = games.merge(R, on="report_url", how="left")
cut = pd.to_datetime(V.cutoff_utc, utc=True)
V["printed_before_cutoff"] = pd.to_datetime(V.printed_et, utc=True) <= cut
V["last_modified_before_cutoff"] = pd.to_datetime(V.uploaded_utc, utc=True) <= cut
V["last_modified_changed"] = V.last_modified_now_utc.notna() & (pd.to_datetime(V.last_modified_now_utc, utc=True) != pd.to_datetime(V.uploaded_utc, utc=True))
V.to_csv(os.path.join(folder, f"verify_{y}.csv.gz"), index=False)
summary = {"season": y, "games": int(len(V)), "distinct_reports": int(len(R)),
           "downloaded_ok": int((R.get("http_status") == 200).sum()) if "http_status" in R else 0,
           "printed_time_found": int(R.printed_et.notna().sum()) if "printed_et" in R else 0,
           "games_printed_after_cutoff": int((V.printed_et.notna() & ~V.printed_before_cutoff).sum()),
           "games_last_modified_after_cutoff": int((~V.last_modified_before_cutoff).sum()),
           "games_last_modified_changed_since_collection": int(V.last_modified_changed.sum())}
json.dump(summary, open(os.path.join(folder, f"verify_{y}_summary.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
