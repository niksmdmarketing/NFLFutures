"""pipeline/freshness.py — per-sport data freshness read-out.

Reads only files the build has already written under site/, writes
site/data/freshness.json, never raises. No model change.
Status precedence: unknown (unreadable input) > off-season (in_progress false)
> off-season (no remaining fixtures, or today past last_date) > behind > current.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

# name, prefix, has schedule.json, has games_<season>.json, has meta in_progress
SPORTS = [
    ("NFL", "",     True,  False, False),
    ("NBA", "nba/", True,  True,  True),
    ("NHL", "nhl/", True,  True,  False),
    ("NBL", "nbl/", True,  True,  True),
    ("AFL", "afl/", True,  True,  True),
    ("CFB", "cfb/", False, True,  True),
]

# Sports with no fixture list (CFB) are judged on the age of the last result instead: weekly competitions, so more than
# this many days without a new result while in progress reads "behind". (Supervisor addition, 15 Nov 2026.)
NO_FIXTURE_GAP_DAYS = 8


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _week_text(meta):
    tw, nw = meta.get("through_week"), meta.get("next_week")
    nwp = meta.get("next_week_played") or 0
    if tw is None:
        return None
    s = "week %s" % tw
    if nw is not None and nwp:
        s += " (+%d game%s of week %s)" % (nwp, "" if nwp == 1 else "s", nw)
    return s


def _latest_game_date(path):
    rows = (_load_json(path).get("rows") or [])
    dates = [str(r[0]) for r in rows if isinstance(r, (list, tuple)) and r]
    return max(dates) if dates else None


def _fixtures(sched):
    """Each unplayed fixture once: it is listed by both teams."""
    seen = {}
    for t in (sched.get("teams") or []):
        team = str(t.get("team") or "")
        for g in (t.get("games") or []):
            if not isinstance(g, (list, tuple)) or len(g) < 2:
                continue
            key = (str(g[0]), frozenset((team, str(g[1]))))
            seen.setdefault(key, {"date": str(g[0]), "team": team, "opp": str(g[1])})
    return list(seen.values())


def _one(site, prefix, name, has_sched, has_games, has_prog, today):
    rec = {"sport": name, "season": None, "results_through": None,
           "games_awaiting": None, "games_overdue": None, "oldest_overdue": None,
           "status": "unknown", "note": "", "model_updated_utc": None}
    notes, fatal = [], False
    base = Path(site) / prefix / "data"

    meta = {}
    try:
        meta = _load_json(base / "meta.json")
        if not isinstance(meta, dict):
            raise ValueError("not an object")
    except Exception as exc:
        fatal = True
        notes.append("meta.json unreadable (%s)" % type(exc).__name__)
        meta = {}
    rec["season"] = meta.get("season")
    rec["model_updated_utc"] = meta.get("updated_utc")

    sched = None
    if has_sched:
        try:
            sched = _load_json(base / "schedule.json")
            if not isinstance(sched, dict):
                raise ValueError("not an object")
        except Exception as exc:
            fatal = True
            notes.append("schedule.json unreadable (%s)" % type(exc).__name__)

    season = rec["season"] if rec["season"] is not None else (sched or {}).get("season")
    if has_games:
        if season is None:
            notes.append("season unknown, games file not read")
        else:
            try:
                rec["results_through"] = _latest_game_date(base / ("games_%s.json" % season))
                finals = base / ("games_%sp.json" % season)      # finals file, when the season has reached them
                if finals.exists():
                    try:
                        rec["results_through"] = max(filter(None, [rec["results_through"], _latest_game_date(finals)]), default=None)
                    except Exception:   # noqa: BLE001 - the regular-season date stands
                        pass
            except Exception as exc:
                fatal = True
                notes.append("games_%s.json unreadable (%s)" % (season, type(exc).__name__))
    else:
        rec["results_through"] = _week_text(meta)

    fixtures = _fixtures(sched) if sched is not None else None
    if fixtures is not None:
        cut = (today - timedelta(days=2)).isoformat()
        overdue = [f for f in fixtures if f["date"] <= cut]
        rec["games_awaiting"] = sum(1 for f in fixtures
                                    if f["date"] == (today - timedelta(days=1)).isoformat())
        rec["games_overdue"] = len(overdue)
        rec["oldest_overdue"] = min((f["date"] for f in overdue), default=None)

    prog = meta.get("in_progress") if has_prog else None
    last_date = (sched or {}).get("last_date")
    if fatal:
        rec["status"] = "unknown"
    elif prog is False:
        rec["status"] = "off-season"
        if rec["games_overdue"]:
            notes.append("%d fixture(s) overdue despite in_progress=false"
                         % rec["games_overdue"])
    elif fixtures is None:
        last = str(rec["results_through"] or "")[:10]
        try:
            age = (today - datetime.strptime(last, "%Y-%m-%d").date()).days
        except ValueError:
            age = None
        if age is None:
            rec["status"] = "unknown"
            notes.append("no fixture list and no dated result")
        else:
            rec["status"] = "behind" if age > NO_FIXTURE_GAP_DAYS else "current"
            notes.append("no fixture list: judged on the last result being %d day%s old" % (age, "" if age == 1 else "s"))
    elif not fixtures:
        rec["status"] = "off-season"
    elif last_date and today.isoformat() > str(last_date):
        rec["status"] = "off-season"
        notes.append("regular season complete; finals are not fixture-checked")
        if rec["games_overdue"]:
            notes.append("%d fixture(s) listed past last_date" % rec["games_overdue"])
    elif rec["games_overdue"]:
        rec["status"] = "behind"
        notes.append("%d game%s played on or before %s not in the model yet (oldest %s)"
                     % (rec["games_overdue"], "" if rec["games_overdue"] == 1 else "s",
                        (today - timedelta(days=2)).isoformat(), rec["oldest_overdue"]))
    else:
        rec["status"] = "current"
        if rec["games_awaiting"]:
            notes.append("%d game%s dated %s not in yet (normal: still being played, or waiting on the source's daily update)"
                         % (rec["games_awaiting"], "" if rec["games_awaiting"] == 1 else "s",
                            (today - timedelta(days=1)).isoformat()))

    rec["note"] = "; ".join(notes)
    return rec


def build(site=SITE, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    today = now.date()
    site = Path(site)

    out = {"checked_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "sports": []}
    for name, prefix, has_sched, has_games, has_prog in SPORTS:
        rec = _one(site, prefix, name, has_sched, has_games, has_prog, today)
        print("freshness %s: %s through=%s awaiting=%s overdue=%s %s"
              % (rec["sport"], rec["status"], rec["results_through"],
                 rec["games_awaiting"], rec["games_overdue"], rec["note"]))
        out["sports"].append(rec)

    dst = site / "data" / "freshness.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name("freshness.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, dst)
    return out


def html_block(data):
    esc = lambda v: html.escape("" if v is None else str(v))
    head = "".join("<th>%s</th>" % h for h in
                   ("Sport", "Results through", "Status", "Note"))
    body = []
    for s in (data.get("sports") or []):
        cells = (s.get("sport"), s.get("results_through"), s.get("status"), s.get("note"))
        body.append("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in cells))
    return ('<table class="freshness"><thead><tr>%s</tr></thead>'
            "<tbody>%s</tbody></table>" % (head, "".join(body)))


__all__ = ["build", "html_block", "SITE"]
