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
    "nba": {"title": "p_title", "finals": "p_conf", "div": "p_div", "seed1": "p_seed1", "playoff": "p_playoff",
            "n_title": "n_p_title", "n_finals": "n_p_conf", "n_playoff": "n_p_playoff",   # n_: without the owner's overrides
            "pt_title": "pt_p_title", "pt_finals": "pt_p_conf", "pt_div": "pt_p_div", "pt_seed1": "pt_p_seed1", "pt_playoff": "pt_p_playoff"},   # pt_: player-term shadow (in season)
    "nhl": {"title": "p_cup", "finals": "p_final", "div": "p_div", "playoff": "p_playoffs", "c_title": "c_cup", "c_finals": "c_final", "s_title": "s_cup", "s_finals": "s_final"},
    "nbl": {"title": "champ", "finals": "gf", "div": "p2", "seed1": "p1", "playoff": "p6"},
    "nfl": {"title": "p_sb", "finals": "p_conf", "div": "p_div", "seed1": "p_seed1", "playoff": "p_playoff"},
    "afl": {"title": "flag", "finals": "gf", "pf": "pf", "div": "p4", "seed1": "p1", "top8": "p8", "playoff": "p10"},
}


def upcoming_games(site_dir, sport, days=8):
    """Pre-game win chances the Outlook page shows (pipeline/sos.py, schedule.json): games in the next `days` days, one row
    per game from the listed home side: [date, home, away, p_home x1000]. Scored later by pipeline/live_check.py."""
    path = os.path.join(site_dir, "data" if sport == "nfl" else os.path.join(sport, "data"), "schedule.json")
    if not os.path.exists(path):
        return None
    try:
        d = json.load(open(path))
        if d.get("recap"):
            return None
        today = dt.datetime.now(dt.timezone.utc).date()
        out = {}
        for t in d.get("teams", []):
            for g in t.get("games") or []:
                day, opp, home, p = g[0], g[1], g[2], g[5]
                if (dt.date.fromisoformat(day) - today).days > days:
                    continue
                key = (day, t["team"], opp) if home else (day, opp, t["team"])
                if home or key not in out:
                    out[key] = int(round((p if home else 1 - p) * 1000))
        return [[k[0], k[1], k[2], v] for k, v in sorted(out.items())]
    except Exception:  # noqa: BLE001 - archiving the futures must not depend on this
        return None


def award_chances(site_dir, sport):
    """Published award chances (name, team, per-mille) per award, for scoring at season end (pipeline/live_check.py)."""
    path = os.path.join(site_dir, "data" if sport == "nfl" else os.path.join(sport, "data"), "awards.json")
    if not os.path.exists(path):
        return None
    try:
        d = json.load(open(path))
        aw = d.get("awards", d)
        out = {}
        for k, a in aw.items():
            rows = a.get("current") or a.get("candidates") or []
            if rows and isinstance(rows, list) and isinstance(rows[0], dict) and "prob" in rows[0]:
                out[k] = [[r.get("name"), r.get("team"), int(round(float(r["prob"]) * 1000))] for r in rows[:15]]
        return out or None
    except Exception:  # noqa: BLE001
        return None


def snapshot(sport, site_dir):
    path = os.path.join(site_dir, "data" if sport == "nfl" else os.path.join(sport, "data"), "futures.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    teams = d.get("teams") or []
    if isinstance(teams, dict):       # NFL: {abbreviation: {...}}; games played = weeks completed
        teams = [dict(v, team=k, gp=d.get("through_week")) for k, v in teams.items()]
    if not teams:
        return None
    rows = sorted(teams, key=lambda r: r["team"])
    p = {k: [int(round(float(r.get(f) or 0.0) * 1000)) for r in rows] for k, f in FIELDS[sport].items() if f in rows[0]}
    gp = [r.get("gp") for r in rows if r.get("gp") is not None]
    if all(isinstance(r.get("rating"), (int, float)) for r in rows):
        p["rating_x100"] = [int(round(float(r["rating"]) * 100)) for r in rows]   # for later game-level live checks
    if sport == "nhl" and rows and "p_top3" in rows[0]:      # diagnostics (route split, rating sensitivity), never scored
        p["top3"] = [int(round(float(r.get("p_top3") or 0.0) * 1000)) for r in rows]
        for key in ("sens_po", "sens_cup"):
            if all(isinstance(r.get(key), list) and len(r[key]) == 3 for r in rows):
                for j, lab in enumerate(("lo", "0", "hi")):
                    p[f"{key}_{lab}"] = [int(round(float(r[key][j]) * 10000)) for r in rows]
    games = upcoming_games(site_dir, sport)
    awards = award_chances(site_dir, sport)
    return {"season": int(d["season"]), "status": d.get("status"), "games": games, "awards": awards, "gp_avg": round(sum(gp) / len(gp), 1) if gp else 0.0,
            "teams": [r["team"] for r in rows], "p": p}


def archive_one(sport, arch, site_dir, now=None):
    snap = snapshot(sport, site_dir)
    if snap is None:
        return "no data"
    body = {k: snap[k] for k in ("gp_avg", "teams", "p")}
    if snap.get("games"):
        body["games"] = snap["games"]
    if snap.get("awards"):
        body["awards"] = snap["awards"]
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


def archive_nba_roster(arch, now=None):
    """Daily NBA roster snapshot (public ESPN roster file) when it changes: nba/rosters/<UTC date>.csv.gz + index.csv."""
    src = os.path.join(ROOT, "build", "nba_roster_today.csv")
    if not os.path.exists(src):
        return "no roster file"
    body = open(src, "rb").read()
    digest = hashlib.sha256(body).hexdigest()[:16]
    d = os.path.join(arch, "nba", "rosters")
    os.makedirs(d, exist_ok=True)
    idx = os.path.join(d, "index.csv")
    rows = list(csv.DictReader(open(idx))) if os.path.exists(idx) else []
    if rows and rows[-1]["hash"] == digest:
        return "unchanged"
    now = now or dt.datetime.now(dt.timezone.utc)
    name = now.strftime("%Y-%m-%dT%H%MZ") + ".csv.gz"
    with gzip.open(os.path.join(d, name), "wb") as f:
        f.write(body)
    with open(idx, "a", newline="") as f:
        w = csv.writer(f)
        if not rows:
            w.writerow(["file", "observed_utc", "hash"])
        w.writerow([name, now.isoformat(timespec="minutes"), digest])
    return "wrote " + name


def main(arch, site_dir=None):
    site_dir = site_dir or os.path.join(ROOT, "site")
    for sport in FIELDS:
        print("sport archive", sport, archive_one(sport, arch, site_dir))
    print("nba roster", archive_nba_roster(arch))


if __name__ == "__main__":
    main(*sys.argv[1:3])
