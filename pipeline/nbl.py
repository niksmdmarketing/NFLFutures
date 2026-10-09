"""NBL public statistics feeds and static-site output.

The NBL stats pages are backed by the league's public Rosetta JSON feed. Older
seasons are cached for longer; the active season is refreshed with every site
build. A failed request keeps the last successful cached response.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from common import DATA, OUT, ROOT, log, write_json

NBL_DATA = os.path.join(DATA, "nbl")
NBL_SRC = os.path.join(ROOT, "site_src", "nbl")
NBL_SITE = os.path.join(ROOT, "site", "nbl")
API = "https://prod.rosetta.nbl.com.au/get/"
HISTORY_SEASONS = 15


def _get(route: str, cache_name: str, max_age_h: float) -> tuple[dict, str, str | None]:
    os.makedirs(NBL_DATA, exist_ok=True)
    path = os.path.join(NBL_DATA, cache_name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        return saved.get("payload", {}), saved.get("updated_utc", ""), None

    url = API + route.lstrip("/")
    req = urllib.request.Request(url, headers={
        "Origin": "https://nbl.com.au", "Referer": "https://nbl.com.au/",
        "User-Agent": "SportsFutures/1.0 (+https://nbl.com.au/)",
        "Accept": "application/json", "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty",
    })
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict) or "data" not in payload:
                raise ValueError("Unexpected NBL response shape")
            saved = {"payload": payload, "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(saved, f, separators=(",", ":"), ensure_ascii=False)
            os.replace(tmp, path)
            return payload, saved["updated_utc"], None
        except Exception as exc:  # keep the existing site build alive on feed outages
            error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        return saved.get("payload", {}), saved.get("updated_utc", ""), error
    return {}, "", error


def _data(payload: dict) -> list:
    value = payload.get("data", []) if isinstance(payload, dict) else []
    return value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])


def _without_odds(value):
    """Keep the NBL view stats-only even when the source mixes odds metadata in."""
    if isinstance(value, dict):
        return {k: _without_odds(v) for k, v in value.items() if "odds" not in str(k).lower()}
    if isinstance(value, list):
        return [_without_odds(v) for v in value]
    return value


def _rows(route: str, cache_name: str, ttl: float, failures: list[str]) -> tuple[list, str]:
    payload, updated, error = _get(route, cache_name, ttl)
    if error:
        failures.append(f"{cache_name}: {error}")
    return _data(payload), updated


def build_data() -> None:
    failures: list[str] = []
    seasons, seasons_updated = _rows("nbl/seasons", "seasons.json", 24, failures)
    season_rows = []
    for row in seasons:
        if not isinstance(row, dict):
            continue
        try:
            year = int(row.get("year"))
        except (TypeError, ValueError):
            continue
        season_rows.append({**row, "_year": year})
    if season_rows:
        latest_year = max(r["_year"] for r in season_rows)
    else:
        latest_year = dt.date.today().year if dt.date.today().month >= 7 else dt.date.today().year - 1
    floor_year = latest_year - HISTORY_SEASONS + 1
    season_rows = [r for r in season_rows if floor_year <= r["_year"] <= latest_year]
    season_rows.sort(key=lambda r: (r["_year"], str(r.get("season_type", ""))))
    regular = [r for r in season_rows if str(r.get("season_type", "")).lower() == "regular"]
    # If the feed's season-type labels change, retain the latest available season rows.
    if not regular:
        regular = [r for r in season_rows if r["_year"] == latest_year]

    datasets = {}
    all_updated = [seasons_updated] if seasons_updated else []
    for season in regular:
        year = season["_year"]
        season_id = season.get("id")
        active = year == latest_year
        ttl = 3 if active else 24 * 14
        year_data = {}
        routes = {
            "standings": f"nbl/standings/{year}/regular",
            "games": f"nbl/matches/in/season/{year}/regular?limit=500&offset=0",
            "teams": f"nbl/team/stats/for/season/{year}/regular",
            "players": f"nbl/players/in/season/{year}",
        }
        for kind, route in routes.items():
            rows, updated = _rows(route, f"{year}_{kind}.json", ttl, failures)
            year_data[kind] = _without_odds(rows)
            if updated:
                all_updated.append(updated)
        leaders = []
        if season_id:
            route = "nbl/stats/leaders/for/season/id/" + urllib.parse.quote(str(season_id)) + "?limit=500&sort=-points_average"
            leaders, updated = _rows(route, f"{year}_leaders.json", ttl, failures)
            if updated:
                all_updated.append(updated)
        year_data["leaders"] = _without_odds(leaders)
        datasets[str(year)] = {"season": _without_odds({k: v for k, v in season.items() if k != "_year"}), **year_data}

    updated = max(all_updated) if all_updated else ""
    meta = {"league": "NBL", "updated_utc": updated, "seasons": sorted([int(y) for y in datasets], reverse=True),
            "source": "NBL public stats feed (Rosetta/Genius Sports)", "errors": failures[:10]}
    write_json("nbl_stats_index.json", {"meta": meta, "seasons": datasets})
    log("NBL data", len(datasets), "seasons", "feed warnings", len(failures))


def build_site() -> None:
    os.makedirs(os.path.join(NBL_SITE, "data"), exist_ok=True)
    os.makedirs(NBL_SITE, exist_ok=True)
    shutil.copy(os.path.join(NBL_SRC, "index.html"), NBL_SITE)
    shutil.copy(os.path.join(NBL_SRC, "stats.js"), os.path.join(NBL_SITE, "stats.js"))
    shutil.copy(os.path.join(OUT, "nbl_stats_index.json"), os.path.join(NBL_SITE, "data", "stats_index.json"))
