"""NBA availability layer for the live model: player values in points and who is out.

Tested on 2011-2026 (research/nba_availability.py, model/availability_nba.json): adjusting each game for missing rotation
players improved our match forecasts in 16 of 16 seasons and closed about a quarter of the gap to closing odds.

Player value (points of margin per game) = BETA x (shrunk game score per 36 - replacement level) x usual minutes / 48,
from this season's games plus 60% of last season's, shrunk toward replacement for small samples.
Live availability comes from ESPN's public NBA injuries feed (status Out / Day-To-Day and an estimated return date).
The return date is ESPN's estimate, not an official timeline, so it is used as a best guess and shown as such.
"""
import datetime as dt
import json
import os
import re
import urllib.request

import numpy as np
import pandas as pd

BETA = 0.5            # points per unit, fitted chronologically (latest season)
SHRINK_MIN = 400.0
LAST_SEASON_WEIGHT = 0.6
ROTATION_MIN = 12.0
DTD_WEIGHT = 0.5      # Day-To-Day players count half, and only for the next 3 days
DTD_DAYS = 3
NO_DATE_DAYS = 14     # Out with no estimated return: assume two weeks
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"


def _gmsc(d):
    return (d.points + .4 * d.field_goals_made - .7 * d.field_goals_attempted - .4 * (d.free_throws_attempted - d.free_throws_made)
            + .7 * d.offensive_rebounds + .3 * d.defensive_rebounds + d.steals + .7 * d.assists + .7 * d.blocks - .4 * d.fouls - d.turnovers)


def player_values(players, end_year, teams):
    """athlete_id -> dict(name, team, mpg, value_points) from regular-season box scores up to now."""
    d = players[pd.to_numeric(players.season_type, errors="coerce") == 2].copy()
    cols = ["minutes", "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
            "defensive_rebounds", "assists", "steals", "blocks", "turnovers", "fouls", "points"]
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["season"] = pd.to_numeric(d.season, errors="coerce")
    d = d[(d.minutes > 0) & d.season.isin([end_year - 1, end_year])]
    if d.empty:
        return {}, None
    d["gmsc"] = _gmsc(d)
    d["athlete_id"] = d.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    ref = d[d.season == d.season.max()]
    rep = float(np.nanpercentile((ref.gmsc / ref.minutes * 36)[ref.minutes >= 10], 30))
    w = np.where(d.season == end_year, 1.0, LAST_SEASON_WEIGHT)
    agg = d.assign(g=d.gmsc * w, m=d.minutes * w).groupby("athlete_id").agg(g=("g", "sum"), m=("m", "sum"),
                                                                          name=("athlete_display_name", "last"))
    d = d.sort_values("game_date")
    recent = d.groupby("athlete_id").tail(15).groupby("athlete_id").agg(mpg=("minutes", "mean"), team=("team_abbreviation", "last"))
    agg = agg.join(recent)
    agg["v36"] = (agg.g + rep / 36 * SHRINK_MIN) / (agg.m + SHRINK_MIN) * 36
    agg["value"] = (BETA * (agg.v36 - rep) * agg.mpg / 48).clip(lower=0)
    agg.loc[agg.mpg < ROTATION_MIN, "value"] = agg.loc[agg.mpg < ROTATION_MIN, "value"] * (agg.mpg / ROTATION_MIN)
    return {i: dict(name=r["name"], team=r.team, mpg=round(float(r.mpg), 1), value=round(float(r.value), 2)) for i, r in agg.iterrows()}, rep


def fetch_injuries(cache_dir):
    path = os.path.join(cache_dir, "nba_injuries_latest.json")
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "SportsFutures/1.0"}), timeout=30) as r:
            j = json.load(r)
        json.dump(j, open(path, "w"))
    except Exception as e:  # noqa: BLE001
        print("[nba avail] injuries feed unavailable:", e, flush=True)
        import time
        if not os.path.exists(path) or time.time() - os.path.getmtime(path) > 24 * 3600:
            return None, None   # never apply a stale report
        j = json.load(open(path))
    rows = []
    for t in j.get("injuries") or []:
        for i in t.get("injuries") or []:
            a = i.get("athlete") or {}
            href = " ".join(l.get("href", "") for l in a.get("links") or [])
            m = re.search(r"/id/(\d+)/", href)
            det = i.get("details") or {}
            rows.append(dict(athlete_id=m.group(1) if m else None, name=a.get("displayName"), team_name=t.get("displayName"),
                             status=i.get("status"), return_date=det.get("returnDate"), injury=" ".join(x for x in (det.get("side"), det.get("type"), det.get("detail")) if x),
                             updated=i.get("date")))
    return rows, j.get("timestamp")


def game_adjustments(schedule, injuries, values, names, today=None):
    """(game_date, home, away) -> points to subtract from the home margin (home missing value - away missing value)."""
    today = today or dt.date.today()
    full = {v: k for k, v in names.items()}
    full["Los Angeles Clippers"] = "LAC"
    out_by_team = {}
    listed = []
    for r in injuries or []:
        v = values.get(r["athlete_id"])
        team = full.get(r["team_name"]) or (v or {}).get("team")
        if not v or team not in names or v["value"] <= 0:
            continue
        if r["status"] == "Out":
            try:
                until = dt.date.fromisoformat(str(r["return_date"])[:10]) if r["return_date"] else today + dt.timedelta(days=NO_DATE_DAYS)
            except ValueError:
                until = today + dt.timedelta(days=NO_DATE_DAYS)
            weight = 1.0
        elif r["status"] == "Day-To-Day":
            until, weight = today + dt.timedelta(days=DTD_DAYS), DTD_WEIGHT
        else:
            continue
        out_by_team.setdefault(team, []).append((until, weight * v["value"]))
        listed.append(dict(team=team, until=until, player=v["name"], status=r["status"], est_return=str(r["return_date"] or "")[:10] or None,
                           injury=r["injury"], points=round(weight * v["value"], 1), mpg=v["mpg"]))
    adj = {}
    for g in schedule.itertuples():
        if g.completed:
            continue
        gd = dt.date.fromisoformat(str(g.game_date)[:10])
        cost = lambda t: sum(p for until, p in out_by_team.get(t, []) if gd < until)
        a = cost(g.home_abbreviation) - cost(g.away_abbreviation)
        if a:
            adj[(str(g.game_date)[:10], g.home_abbreviation, g.away_abbreviation)] = a
    left = schedule[~schedule.completed.astype(bool)]
    for r in listed:
        mine = left[(left.home_abbreviation == r["team"]) | (left.away_abbreviation == r["team"])]
        r["games"] = int((pd.to_datetime(mine.game_date).dt.date < r.pop("until")).sum())
    listed.sort(key=lambda r: (-(r["games"] > 0), -r["points"]))
    return adj, listed


def archive(store, injuries, stamp):
    """Append the feed snapshot to a history folder (the injury-monitor branch in CI) when anything changed."""
    d = os.path.join(store, "nba")
    os.makedirs(d, exist_ok=True)
    latest = os.path.join(d, "latest.json")
    rows = sorted(injuries, key=lambda r: (r["team_name"] or "", r["name"] or ""))
    key = [{k: r[k] for k in ("athlete_id", "status", "return_date", "injury")} for r in rows]
    if os.path.exists(latest) and json.load(open(latest)).get("key") == key:
        return False
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    snap = {"collected_utc": now, "feed_timestamp": stamp, "source": URL, "key": key, "rows": rows}
    json.dump(snap, open(latest, "w"), indent=0)
    with open(os.path.join(d, "history.jsonl"), "a") as f:
        f.write(json.dumps({"collected_utc": now, "feed_timestamp": stamp, "rows": rows}) + "\n")
    return True
