"""Collect a bounded, private-to-the-workflow NBA research-data cache.

This is deliberately independent of the website build: unknown schemas and raw
feeds are inventoried first and must be validated before any are displayed.
Only season-scoped CSV/Parquet assets from the most recent 12 NBA seasons are
eligible; giant play-by-play releases are not included.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "nba", "research")
MANIFEST = os.path.join(ROOT, "build", "nba_research_collection.json")
API = "https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags"
RAW = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
HEADERS = {"User-Agent": "NFLFutures-NBA-Research-Collector/1.0", "Accept": "application/vnd.github+json"}

# Prioritize compact, non-box-score or less-duplicative sources. Full PBP and
# full shot files are omitted: the existing pipeline already has box scores and
# shot-zone summaries, while these archives run to multiple gigabytes.
TAG_FILTERS = {
    "nba_stats_leaguedash": (
        "player_stats_advanced", "player_stats_defense", "player_stats_misc",
        "player_stats_scoring", "player_stats_usage", "player_tracking_",
        "team_stats_advanced", "team_stats_defense", "team_stats_fourfactors",
        "team_stats_misc", "team_stats_scoring", "team_stats_usage",
    ),
    "nba_stats_hustle": (),
    "nba_stats_matchups": (),
    "nba_stats_game_matchups": (),
    "nba_stats_synergy": (),
    "nba_stats_game_lineups": (),
    "nba_stats_lineups": (),
    "nba_stats_possessions": (),
    "nba_stats_player_game_logs": (),
    "nba_player_impact": (),
}

SEASON_RE = re.compile(r"(?<!\d)(20\d{2})(?=\D|$)")
FORMAT_ORDER = {".csv": 0, ".csv.gz": 0, ".parquet": 1}


def end_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year + 1 if today.month >= 7 else today.year


def request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def release_assets(tag: str) -> tuple[list[dict], str | None]:
    try:
        release = request_json(f"{API}/{tag}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return [], "release tag not found"
        raise
    return release.get("assets", []), release.get("published_at")


def season_from(name: str) -> int | None:
    match = SEASON_RE.search(name)
    return int(match.group(1)) if match else None


def suffix(name: str) -> str:
    lower = name.lower()
    return ".csv.gz" if lower.endswith(".csv.gz") else os.path.splitext(lower)[1]


def matches(tag: str, name: str) -> bool:
    ext = suffix(name)
    if ext not in FORMAT_ORDER:
        return False
    if tag != "nba_stats_leaguedash":
        return True
    stem = name.lower()
    return any(part in stem for part in TAG_FILTERS[tag])


def choose_assets(tag: str, assets: list[dict], min_year: int, max_year: int) -> list[dict]:
    candidates = []
    for asset in assets:
        name = asset.get("name", "")
        year = season_from(name)
        if year is None or not min_year <= year <= max_year or not matches(tag, name):
            continue
        candidates.append((year, name, asset))
    # Prefer one inspectable format per dataset-season; parquet is a fallback.
    selected: dict[tuple[int, str], tuple[int, dict]] = {}
    for year, name, asset in candidates:
        ext = suffix(name)
        stem = name[:-len(ext)] if ext else name
        key = (year, stem)
        rank = FORMAT_ORDER[ext]
        if key not in selected or rank < selected[key][0]:
            selected[key] = (rank, asset)
    return [item[1] for _, item in sorted(selected.items(), reverse=True)]


def download_asset(tag: str, asset: dict, max_file_bytes: int, max_total_bytes: int,
                   used_bytes: int) -> tuple[dict, int]:
    name = asset["name"]
    size = int(asset.get("size", 0))
    record = {"name": name, "size_bytes": size, "source_updated_utc": asset.get("updated_at"),
              "url": asset.get("browser_download_url"), "status": "pending"}
    if size > max_file_bytes:
        record.update(status="skipped_file_limit", max_file_bytes=max_file_bytes)
        return record, used_bytes
    if used_bytes + size > max_total_bytes:
        record.update(status="skipped_run_limit", remaining_bytes=max(0, max_total_bytes - used_bytes))
        return record, used_bytes

    path = os.path.join(DEST, tag, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path) and os.path.getsize(path) == size:
        record.update(status="cached", path=os.path.relpath(path, ROOT).replace("\\", "/"))
        return record, used_bytes

    tmp = path + ".part"
    try:
        request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(request, timeout=180) as response, open(tmp, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        if os.path.getsize(tmp) != size:
            raise IOError(f"download size mismatch ({os.path.getsize(tmp)} != {size})")
        os.replace(tmp, path)
        record.update(status="downloaded", path=os.path.relpath(path, ROOT).replace("\\", "/"))
        return record, used_bytes + size
    except Exception as exc:  # keep collecting other independent datasets
        try:
            os.remove(tmp)
        except OSError:
            pass
        record.update(status="download_failed", error=str(exc)[:300])
        return record, used_bytes


def collect(seasons: int = 12, max_file_mb: int = 75, max_total_mb: int = 1200) -> dict:
    current = end_year()
    first = current - seasons + 1
    max_file_bytes, max_total_bytes = max_file_mb * 1024**2, max_total_mb * 1024**2
    manifest = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "current_season_end_year": current, "season_start": first, "season_end": current,
                "max_file_mb": max_file_mb, "max_total_mb": max_total_mb,
                "displayed_on_site": False,
                "note": "Raw source cache only; fields remain hidden until schema and coverage validation.",
                "datasets": {}, "totals": {"downloaded": 0, "cached": 0, "skipped": 0,
                                             "failed": 0, "bytes_downloaded": 0}}
    used_bytes = 0
    for tag in TAG_FILTERS:
        try:
            assets, published = release_assets(tag)
        except Exception as exc:
            manifest["datasets"][tag] = {"release_status": "lookup_failed", "error": str(exc)[:300], "assets": []}
            manifest["totals"]["failed"] += 1
            continue
        selected = choose_assets(tag, assets, first, current)
        dataset = {"release_status": "found" if assets else "missing", "published_at": published,
                   "eligible_assets": len(selected), "assets": []}
        for asset in selected:
            record, used_bytes = download_asset(tag, asset, max_file_bytes, max_total_bytes, used_bytes)
            dataset["assets"].append(record)
            status = record["status"]
            if status == "downloaded":
                manifest["totals"]["downloaded"] += 1
            elif status == "cached":
                manifest["totals"]["cached"] += 1
            elif status == "download_failed":
                manifest["totals"]["failed"] += 1
            else:
                manifest["totals"]["skipped"] += 1
        manifest["datasets"][tag] = dataset
        print(f"{tag}: {len(selected)} eligible assets", flush=True)
        time.sleep(.15)  # be polite to the public GitHub API

    manifest["totals"]["bytes_downloaded"] = used_bytes
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, default=12)
    parser.add_argument("--max-file-mb", type=int, default=75)
    parser.add_argument("--max-total-mb", type=int, default=1200)
    args = parser.parse_args()
    result = collect(args.seasons, args.max_file_mb, args.max_total_mb)
    totals = result["totals"]
    print(json.dumps(totals, indent=2), flush=True)
    if not totals["downloaded"] and not totals["cached"]:
        raise SystemExit("No eligible NBA research assets were collected; inspect build/nba_research_collection.json")


if __name__ == "__main__":
    main()
