#!/bin/bash
# Debug the live injury step in Actions. Writes data/research/nhl_inj_debug.txt
mkdir -p data/research
cd pipeline && python3 - > ../data/research/nhl_inj_debug.txt 2>&1 <<'PY'
import traceback, nhl, nhl_injuries as I, nhl_absence as A, nhl_model as M
try:
    h = I.fetch(0)
    print("html", None if h is None else len(h))
    d = I.current(nhl.start_year()); print("rows", None if d is None else len(d))
    teams = sorted(t for v in nhl.DIVS.values() for t in v)
    games, failed, dates = M.fetch_schedule(teams, nhl.start_year(), with_dates=True)
    print("games", len(games), failed, dates[:2])
    adj, po, C = A.adjustments(nhl.start_year(), teams, games, dates)
    print("adj", None if C is None else len(C), float(abs(adj).sum()))
    print(C.sort_values("season_goals").tail(5).to_string())
except Exception:
    traceback.print_exc()
PY
