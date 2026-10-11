"""Inspect the NBA Stats research cache (data/nba/research) and write a compact coverage report.

nba_research_collect.py downloads season files for hustle, matchups, synergy, lineups, possessions, player game logs and
player impact, but nothing validates them. This reads what is actually on disk and records, per release tag: seasons
present, seasons missing inside the requested window, rows per file, columns, grain (game / player-season / other),
null shares on a sample, and one example row. Research only; it changes no projection and writes no site data.

Usage: python pipeline/nba_research_inspect.py [output.json]
"""
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "nba", "research")
MANIFEST = os.path.join(ROOT, "build", "nba_research_collection.json")
SAMPLE_ROWS = 20000
SEASON_RE = re.compile(r"(?<!\d)(20\d{2})(?=\D|$)")


def _rows_and_sample(path):
    low = path.lower()
    if low.endswith(".parquet"):
        import pyarrow.parquet as pq
        f = pq.ParquetFile(path)
        rows = f.metadata.num_rows
        sample = next(f.iter_batches(batch_size=SAMPLE_ROWS)).to_pandas() if rows else pd.DataFrame()
        return rows, sample
    comp = "gzip" if low.endswith(".gz") else None
    sample = pd.read_csv(path, nrows=SAMPLE_ROWS, low_memory=False, compression=comp)
    rows = 0
    for chunk in pd.read_csv(path, usecols=[0], chunksize=200000, compression=comp, low_memory=False):
        rows += len(chunk)
    return rows, sample


def _grain(cols):
    c = {x.lower() for x in cols}
    if "game_id" in c and ({"player_id", "person_id", "athlete_id"} & c):
        return "player-game"
    if "game_id" in c and ({"team_id", "team_abbreviation"} & c):
        return "team-game"
    if "game_id" in c:
        return "game"
    if {"player_id", "person_id"} & c:
        return "player-season"
    if {"team_id", "team_abbreviation"} & c:
        return "team-season"
    return "other"


def inspect_file(path):
    rows, sample = _rows_and_sample(path)
    nulls = {k: round(float(v), 3) for k, v in sample.isna().mean().items() if v > 0.05}
    first = {}
    if len(sample):
        for k, v in sample.iloc[0].items():
            first[str(k)] = v.item() if hasattr(v, "item") else (None if pd.isna(v) else str(v)[:60])
    return {"rows": int(rows), "columns": [str(c) for c in sample.columns], "grain": _grain(sample.columns),
            "null_share_over_5pct": nulls, "first_row": first}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "nba_research_inventory.json")
    manifest = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
    first, last = manifest.get("season_start"), manifest.get("season_end")
    report = {"generated_utc": manifest.get("generated_utc"), "season_window": [first, last], "tags": {}}
    if not os.path.isdir(SRC):
        raise SystemExit("no research cache at " + SRC)
    for tag in sorted(os.listdir(SRC)):
        folder = os.path.join(SRC, tag)
        if not os.path.isdir(folder):
            continue
        files, seasons, errors = [], set(), []
        total_bytes = 0
        for name in sorted(os.listdir(folder)):
            if name.endswith(".part"):
                continue
            path = os.path.join(folder, name)
            total_bytes += os.path.getsize(path)
            m = SEASON_RE.search(name)
            season = int(m.group(1)) if m else None
            try:
                info = inspect_file(path)
            except Exception as exc:  # noqa: BLE001
                errors.append({"file": name, "error": str(exc)[:160]})
                continue
            info.update(file=name, season=season, size_mb=round(os.path.getsize(path) / 1048576, 1))
            files.append(info)
            if season:
                seasons.add(season)
        families = {}
        for f in files:   # one entry per file family (name without season), with its season range
            fam = SEASON_RE.sub("YYYY", f["file"])
            e = families.setdefault(fam, {"grain": f["grain"], "seasons": [], "rows": 0, "columns": f["columns"],
                                          "first_row": f["first_row"], "null_share_over_5pct": f["null_share_over_5pct"]})
            e["seasons"].append(f["season"])
            e["rows"] += f["rows"]
            e["column_set_varies"] = e.get("column_set_varies", False) or f["columns"] != e["columns"]
        for e in families.values():
            e["seasons"] = sorted(s for s in e["seasons"] if s)
            if first and last:
                e["missing_seasons_in_window"] = [y for y in range(first, last + 1) if y not in e["seasons"]]
        report["tags"][tag] = {"files": len(files), "size_mb": round(total_bytes / 1048576, 1),
                               "seasons": sorted(seasons), "families": families, "errors": errors}
        print(tag, len(files), "files", round(total_bytes / 1048576), "MB", len(families), "families", len(errors), "errors")
    missing = [t for t in (manifest.get("datasets") or {}) if t not in report["tags"]]
    report["tags_requested_but_not_on_disk"] = missing
    report["release_status"] = {t: d.get("release_status") for t, d in (manifest.get("datasets") or {}).items()}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(report, open(out, "w"), indent=1, default=str)
    print("wrote", out)


if __name__ == "__main__":
    main()
