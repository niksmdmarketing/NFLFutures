"""Re-parse the selected pre-game official NBA injury reports with the corrected parser (research only).

GPT's audit of the first handover found team/game assignment errors (pipeline/nba_official.parse lost the team
column when body text contained the word 'Team', could not read team names containing digits such as
'Philadelphia 76ers', did not split wrapped team names, and folded the 2019-20 'Category' column into player names).
The report SELECTION (latest report published 60+ minutes before tip-off) is unchanged and was verified separately
(verify_<season>.csv.gz); only the parsing is redone here.

For every game in pregame_<season>.csv.gz: download its selected PDF once, check the SHA-256 against the verification
record, keep the PDF (for a release asset keyed by SHA-256), parse it, and keep ONLY rows printed under that game's
date and matchup (the two teams). Nothing is repaired from box scores.
Outputs (research/nba_pregame/):
  pregame_v2_<season>.csv.gz   one row per listed player: game, report, printed time, Last-Modified, SHA-256,
                               matchup, team (ESPN code) + team_code (league code), player, status, previous status, reason
  coverage_v2_<season>.csv.gz  one row per game x team: listed / not_yet_submitted / no_rows (game section printed, no
                               row for that team) / game_not_in_report
  reparse_v2_<season>.json     counts, unresolved team cells, and a comparison with the first parse
Usage: python research/nba_pregame_reparse.py <season end year> <market-data dir> <pdf output dir>
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nba_official as O  # noqa: E402

ESPN = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}
TO_LEAGUE = {v: k for k, v in ESPN.items()}
y, root, pdf_dir = int(sys.argv[1]), sys.argv[2], sys.argv[3]
folder = os.path.join(root, "research", "nba_pregame")
os.makedirs(pdf_dir, exist_ok=True)
old = pd.read_csv(os.path.join(folder, f"pregame_{y}.csv.gz"))
ver = pd.read_csv(os.path.join(folder, f"verify_{y}.csv.gz")).drop_duplicates("game_id").set_index("game_id")
games = old.drop_duplicates("game_id")[["season", "game_id", "game_date", "tip_utc", "cutoff_utc", "report_url"]]

# the two teams of each game from ESPN's schedule (the first parse's team column cannot be trusted)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nba as N  # noqa: E402
S = pd.read_csv(N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 24 * 365), low_memory=False)
S = S.drop_duplicates("id").set_index(S.drop_duplicates("id").id.astype(int))

parsed, meta, sha_ok = {}, {}, {}
for name in sorted(games.report_url.dropna().unique()):
    local = os.environ.get("LOCAL_PDF_DIR")       # offline testing against already downloaded originals
    if local:
        if not os.path.exists(os.path.join(local, name)):
            continue
        body = open(os.path.join(local, name), "rb").read()
    else:
        time.sleep(0.12)
    try:
        if local:
            raise StopIteration
        with urllib.request.urlopen(urllib.request.Request(O.BASE.format(name.removeprefix("Injury-Report_").removesuffix(".pdf")),
                                                           headers=O.UA), timeout=30) as r:
            body = r.read()
    except StopIteration:
        pass
    except Exception as e:  # noqa: BLE001
        meta[name] = {"download_error": str(e)[:80]}
        continue
    sha = hashlib.sha256(body).hexdigest()
    open(os.path.join(pdf_dir, f"{sha}.pdf"), "wb").write(body)
    rows, m = O.parse(body, with_meta=True)
    parsed[name], meta[name] = rows, {"sha256": sha, "rows": len(rows), "unresolved_team_cells": m["unresolved_team_cells"]}
    expected = ver[ver.report_url == name].sha256.dropna().unique()
    sha_ok[name] = bool(len(expected)) and sha == expected[0]

out, cov = [], []
for g in games.itertuples():
    e = S.loc[int(g.game_id)] if int(g.game_id) in S.index else None
    if e is None:
        continue
    home, away = e.home_abbreviation, e.away_abbreviation
    want = {TO_LEAGUE.get(home, home), TO_LEAGUE.get(away, away)}
    rows = parsed.get(g.report_url) if isinstance(g.report_url, str) else None
    v = ver.loc[g.game_id] if g.game_id in ver.index else None
    base = dict(season=y, game_id=g.game_id, game_date=g.game_date, tip_utc=g.tip_utc, cutoff_utc=g.cutoff_utc,
                report_url=g.report_url, printed_et=None if v is None else v.printed_et,
                uploaded_utc=None if v is None else v.uploaded_utc, sha256=meta.get(g.report_url, {}).get("sha256"))
    if rows is None:
        for t in (home, away):
            cov.append(dict(base, team=t, coverage="report_unavailable"))
        continue
    mine = [r for r in rows if r["game_date"] == g.game_date and r["matchup"] and set(r["matchup"].split("@")) == want]
    for r in mine:
        if r["status"] == O.NOT_SUBMITTED or not r.get("team_code"):
            continue
        out.append(dict(base, matchup=r["matchup"], team=ESPN.get(r["team_code"], r["team_code"]), team_code=r["team_code"],
                        player=r["player"], status=r["status"], previous_status=r.get("previous_status"), reason=r["reason"]))
    for t in (home, away):
        tc = TO_LEAGUE.get(t, t)
        if any(r["status"] == O.NOT_SUBMITTED and r.get("team_code") == tc for r in mine):
            c = "not_yet_submitted"
        elif any(r.get("team_code") == tc for r in mine):
            c = "listed"
        elif mine:
            c = "no_rows"
        else:
            c = "game_not_in_report"
        cov.append(dict(base, team=t, coverage=c))

D, C = pd.DataFrame(out), pd.DataFrame(cov)
D.to_csv(os.path.join(folder, f"pregame_v3_{y}.csv.gz"), index=False)
C.to_csv(os.path.join(folder, f"coverage_v3_{y}.csv.gz"), index=False)
# comparison with the first parse: same (game, player, status)? same team?
o = old[old.player.notna()][["game_id", "team", "player", "status"]]
k = lambda df: set(zip(df.game_id, df.player, df.status))
kt = lambda df: set(zip(df.game_id, df.team, df.player, df.status))
summary = {"season": y, "games": int(len(games)), "reports": int(len(parsed)), "download_errors": sum(1 for m in meta.values() if "download_error" in m),
           "sha_matches_verification": int(sum(sha_ok.values())), "rows_v2": int(len(D)),
           "coverage": C.coverage.value_counts().to_dict() if len(C) else {},
           "unresolved_team_cells": sum(len(m.get("unresolved_team_cells", [])) for m in meta.values()),
           "status_counts_v2": D.status.value_counts().to_dict() if len(D) else {},
           "first_parse_rows": int(len(o)),
           "rows_in_both_same_team": len(kt(o) & kt(D)) if len(D) else 0,
           "rows_only_in_first_parse": len(k(o) - k(D)) if len(D) else len(k(o)),
           "rows_only_in_v2": len(k(D) - k(o)) if len(D) else 0,
           "rows_same_player_status_different_team": len({(a, p, s) for a, t, p, s in kt(o)} & {(a, p, s) for a, t, p, s in kt(D)}) - len(kt(o) & kt(D)) if len(D) else 0}
json.dump(summary, open(os.path.join(folder, f"reparse_v3_{y}.json"), "w"), indent=1)
json.dump(meta, open(os.path.join(folder, f"reparse_v3_{y}_reports.json"), "w"))
print(json.dumps(summary, indent=1))
