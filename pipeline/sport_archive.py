"""Append the NBA / NHL / AFL / NBL futures probabilities of this run to the forecast archive (append-only git branch).

    python pipeline/sport_archive.py <archive_dir> [site_dir]

Writes <archive_dir>/<sport>/<season>/<YYYYmmddTHHMMZ>.json.gz and one line to <archive_dir>/<sport>/<season>/index.csv.
A snapshot is skipped when the probabilities are identical to the previous one. These are the numbers the site actually
showed at the time; pipeline/replay_site.py turns them into the live part of each sport's History page.
Each snapshot: {generated_utc, status, gp_avg, teams:[...], p:{market:[permille per team]}} with the same market keys as the replay files.
"""
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# market key -> field in that sport's futures.json team rows (keys match replay_site.SPORTS)
FIELDS = {
    "nba": {"title": "p_title", "finals": "p_conf", "div": "p_div", "seed1": "p_seed1", "playoff": "p_playoff"},
    "nhl": {"title": "p_cup", "finals": "p_final", "div": "p_div", "playoff": "p_playoffs"},
    "nbl": {"title": "champ", "finals": "gf", "div": "p2", "seed1": "p1", "playoff": "p6"},
    "afl": {"title": "flag", "finals": "gf", "pf": "pf", "div": "p4", "seed1": "p1", "top8": "p8", "playoff": "p10"},
}


def snapshot(sport, site_dir):
    path = os.path.join(site_dir, sport, "data", "futures.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    teams = d.get("teams") or []
    if not teams:
        return None
    rows = sorted(teams, key=lambda r: r["team"])
    p = {k: [int(round(float(r.get(f) or 0.0) * 1000)) for r in rows] for k, f in FIELDS[sport].items() if f in rows[0]}
    gp = [r.get("gp") for r in rows if r.get("gp") is not None]
    return {"season": int(d["season"]), "status": d.get("status"), "gp_avg": round(sum(gp) / len(gp), 1) if gp else 0.0,
            "teams": [r["team"] for r in rows], "p": p}


def archive_one(sport, arch, site_dir, now=None):
    snap = snapshot(sport, site_dir)
    if snap is None:
        return "no data"
    body = {k: snap[k] for k in ("gp_avg", "teams", "p")}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    d = os.path.join(arch, sport, str(snap["season"]))
    os.makedirs(d, exist_ok=True)
    idx = os.path.join(d, "index.csv")
    rows = list(csv.DictReader(open(idx))) if os.path.exists(idx) else []
    if rows and rows[-1]["hash"] == digest:
        return "unchanged"
    now = now or dt.datetime.now(dt.timezone.utc)
    name = now.strftime("%Y%m%dT%H%MZ") + ".json.gz"
    with gzip.open(os.path.join(d, name), "wt") as f:
        json.dump({"generated_utc": now.isoformat(timespec="minutes"), "status": snap["status"], **body}, f, separators=(",", ":"))
    new = not rows
    with open(idx, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file", "generated_utc", "gp_avg", "hash"])
        w.writerow([name, now.isoformat(timespec="minutes"), snap["gp_avg"], digest])
    return "wrote " + name


def main(arch, site_dir=None):
    site_dir = site_dir or os.path.join(ROOT, "site")
    for sport in FIELDS:
        print("sport archive", sport, archive_one(sport, arch, site_dir))


if __name__ == "__main__":
    main(*sys.argv[1:3])
