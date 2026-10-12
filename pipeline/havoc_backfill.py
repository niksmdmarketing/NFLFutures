"""Add havoc rate to the stored completed-season tables in history/ without rebuilding anything else.

    python pipeline/havoc_backfill.py            # 2018 to last season
Havoc rate = share of run and pass plays that end in a sack, tackle for loss, pass breakup, interception or lost fumble
(common.scrimmage), split into sack / tackle for loss / pass breakup / turnover parts. offense.havoc is havoc allowed; defense.havoc is havoc created.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, TEAMS, current_season, games, load_pbp, log, scrimmage  # noqa: E402
from history import FIRST  # noqa: E402

if __name__ == "__main__":
    g = games()
    for y in [int(a) for a in sys.argv[1:]] or range(FIRST, current_season(g)):
        path = os.path.join(ROOT, "history", f"{y}.json")
        if not os.path.exists(path):
            continue
        s = scrimmage(load_pbp(y, max_age_h=24 * 365))
        d = json.load(open(path))
        for page, by in (("offense", "posteam"), ("defense", "defteam")):
            for c in ("havoc", "havoc_sack", "havoc_tfl", "havoc_pbu", "havoc_to"):
                r = s.groupby(by)[c].mean()
                for t in TEAMS:
                    if t in d["values"][page]:
                        d["values"][page][t][c] = round(float(r[t]), 4) if t in r.index else None
        with open(path, "w") as f:
            json.dump(d, f, separators=(",", ":"))
        log("havoc", y, round(float(s.havoc.mean()), 4))
