"""Collection-only monitor of the official NFL injury report (https://www.nfl.com/injuries/).

Never imported by ratings, simulations or awards: it changes no projection. It keeps a dated record of what the public
report said each time it was checked, so an injury-aware challenger model can be validated later.

Rules (from the draft by GPT, kept):
  * Only facts printed in the table are stored. Observation time is when WE looked, not when the source published.
  * A blank game status is not "Active", and a player who stops being listed has not been shown to have recovered.
  * No return dates, diagnoses or probability adjustments are inferred. No odds, no paid news.
  * A failed or malformed check never replaces the last good report; every attempt is logged.
  * Changes are only compared within the same season/week; a week transition is not a recovery.

Storage is plain text so it can live on an append-only git branch (injury-monitor) across fresh CI runners:
  <store>/reports/<season>/week-<NN>/<observed>_<hash12>.json   one file per DISTINCT report content
  <store>/checks.csv      one line per attempt (ok or failed)
  <store>/changes.jsonl   within-week row changes (appeared / updated / no_longer_listed)
  <store>/state.json      pointer to the last good report
  <store>/summary.json    status summary (also written to build/injury_monitor.json for the site)
`python pipeline/nfl_injuries.py --sqlite out.sqlite --store DIR` rebuilds a SQLite index from the text history.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.nfl.com/injuries/"
NICK = dict(zip(
    "Cardinals Falcons Ravens Bills Panthers Bears Bengals Browns Cowboys Broncos Lions Packers Texans Colts Jaguars Chiefs "
    "Raiders Chargers Rams Dolphins Vikings Patriots Saints Giants Jets Eagles Steelers 49ers Seahawks Buccaneers Titans Commanders".split(),
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LA MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS".split()))
HEADERS = ["Player", "Position", "Injuries", "Practice Status", "Game Status"]
KNOWN_GAME = {"", "Out", "Doubtful", "Questionable"}
KNOWN_PRACTICE = {"", "Full Participation in Practice", "Limited Participation in Practice", "Did Not Participate In Practice"}
VOID = set("area base br col embed hr img input link meta param source track wbr".split())
STALE_HOURS = 6
CHECK_FIELDS = ["checked_at", "ok", "report_file", "season", "week", "teams", "rows", "error"]


# ------------------------------------------------------------------ parsing

class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return re.sub(r"\s+", " ", " ".join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk()


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def team_code(label):
    """'Cardinals' or 'Arizona Cardinals' -> 'ARI'; None when unrecognised."""
    label = (label or "").strip()
    for nick, code in NICK.items():
        if label == nick or label.endswith(" " + nick):
            return code
    return None


def parse_report(text):
    """HTML -> report dict. Raises ValueError when the page cannot be trusted (layout change, ambiguity, no data)."""
    doc = Document()
    doc.feed(text)
    headings = [n.text() for n in doc.root.walk() if n.tag in ("h1", "h2")]
    seasons = {int(y) for h in headings for y in re.findall(r"\b(20\d\d) NFL Injury Report\b", h)}
    weeks = {int(w) for h in headings for w in re.findall(r"Injuries\s*[-–—]\s*WEEK\s+(\d+)", h, re.I)}
    if len(seasons) != 1 or len(weeks) != 1:
        raise ValueError("Missing or ambiguous official report season/week")
    season, week = seasons.pop(), weeks.pop()
    if not 1 <= week <= 23:
        raise ValueError(f"Unexpected report week {week}")
    team, label, rows, covered, seen, warnings = None, None, [], set(), set(), []
    for node in doc.root.walk():
        classes = (node.attrs.get("class") or "").split()
        if "d3-o-section-sub-title" in classes:
            label = node.text()
            team = team_code(label)
        if node.tag != "table" or "d3-o-reports--detailed" not in classes:
            continue
        headers = [n.text() for n in node.walk() if n.tag == "th"]
        if headers != HEADERS:
            raise ValueError("Official injury table layout changed")
        if not team:
            raise ValueError(f"Unrecognised team label {label!r}")
        if team in covered:
            raise ValueError(f"Duplicate team injury table ({team})")
        covered.add(team)
        for tr in (n for n in node.walk() if n.tag == "tr"):
            cells = [n for n in tr.children if isinstance(n, Node) and n.tag == "td"]
            if not cells:
                continue
            if len(cells) != 5:
                raise ValueError("Unexpected injury row shape")
            values = [c.text() for c in cells]
            if not values[0] or not values[1]:
                raise ValueError("Player or position missing")
            links = [n.attrs.get("href", "") for n in cells[0].walk() if n.tag == "a"]
            paths = {urllib.parse.urlparse(p).path for p in links}
            paths = sorted(p for p in paths if re.fullmatch(r"/players/[a-z0-9-]+/?", p))
            if len(paths) != 1:
                raise ValueError("Player profile identifier missing or ambiguous")
            player_id = paths[0].strip("/").split("/")[-1]
            if (team, player_id) in seen:
                raise ValueError("Duplicate player/team row")
            seen.add((team, player_id))
            if values[4] not in KNOWN_GAME:
                warnings.append(f"Unrecognised game status kept as printed: {values[4]!r} ({team})")
            if values[3] not in KNOWN_PRACTICE:
                warnings.append(f"Unrecognised practice status kept as printed: {values[3]!r} ({team})")
            rows.append(dict(team=team, player_id=player_id, player=values[0], position=values[1], injury=values[2] or None,
                             practice_status=values[3] or None, game_status=values[4] or None,
                             player_url="https://www.nfl.com" + paths[0]))
    if not covered or not rows:
        raise ValueError("No team injury tables found")
    dates = []
    for h in headings:
        m = re.search(r"\b(JANUARY|FEBRUARY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{1,2})", h.upper())
        if m:
            year = season + (m[1] in ("JANUARY", "FEBRUARY"))
            dates.append(dt.date(year, dt.datetime.strptime(m[1], "%B").month, int(m[2])).isoformat())
    return dict(season=season, week=week, covered_teams=sorted(covered), source_game_dates=sorted(set(dates)),
                parse_warnings=sorted(set(warnings)), rows=sorted(rows, key=lambda r: (r["team"], r["player_id"])))


def fetch_report():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "NFLFuturesResearch/1.0 (private, official injury report collection)",
                                                  "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if urllib.parse.urlparse(r.url).hostname not in ("www.nfl.com", "nfl.com"):
            raise ValueError("Unexpected source redirect")
        if "html" not in r.headers.get("Content-Type", ""):
            raise ValueError("Unexpected source content type")
        raw = r.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("Source page exceeds size limit")
    return raw.decode("utf-8", errors="replace"), hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ storage (plain text, append-only)

def iso(when):
    return when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _append_check(store, **row):
    p = Path(store) / "checks.csv"
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CHECK_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in CHECK_FIELDS})


def read_checks(store):
    p = Path(store) / "checks.csv"
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_changes(store, limit=None):
    p = Path(store) / "changes.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    lines = lines[-limit:] if limit else lines
    return [json.loads(x) for x in lines if x.strip()]


def diff_rows(previous, report):
    """Within-week changes only. Returns a list of change dicts (empty across a season/week transition)."""
    if not previous or (previous["season"], previous["week"]) != (report["season"], report["week"]):
        return []
    old = {(r["team"], r["player_id"]): r for r in previous["rows"]}
    new = {(r["team"], r["player_id"]): r for r in report["rows"]}
    out = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if a and b:
            kind = "updated"
        elif b:
            kind = "appeared"
        else:
            kind = "no_longer_listed"
            if key[0] not in report["covered_teams"]:
                kind = "team_table_missing"            # the whole team table vanished: not a statement about the player
        out.append(dict(team=key[0], player_id=key[1], kind=kind, before=a, after=b))
    return out


def scheduled_teams(season, week, games_csv=None):
    """Teams with a game in that week (from nflverse games.csv), or None when unknown."""
    p = Path(games_csv) if games_csv else ROOT / "data" / "games.csv"
    if not p.exists():
        return None
    import pandas as pd
    from common import FIX
    g = pd.read_csv(p, usecols=["season", "week", "game_type", "home_team", "away_team"])
    g = g[(g.season == season) & (g.week == week)]
    if g.empty:
        return None
    return sorted(set(g.home_team.replace(FIX)) | set(g.away_team.replace(FIX)))


def summarise(store, now, expected_teams=None):
    checks = read_checks(store)
    state = _read_json(Path(store) / "state.json", {}) or {}
    report = _read_json(Path(store) / state["report_file"], {}) if state.get("report_file") else {}
    last = checks[-1] if checks else None
    good = [c for c in checks if c["ok"] == "1"]
    success = good[-1]["checked_at"] if good else None
    stale = not success or (now - dt.datetime.fromisoformat(success)).total_seconds() > STALE_HOURS * 3600
    warnings = []
    if not report:
        warnings.append("No report has been collected successfully yet.")
    if stale and report:
        warnings.append(f"No successful check in the last {STALE_HOURS} hours; do not assume this report is current.")
    if last and last["ok"] != "1":
        warnings.append("The latest check failed. The rows shown are from the last successful check.")
    covered = report.get("covered_teams", [])
    missing = None
    if report and expected_teams:
        missing = sorted(set(expected_teams) - set(covered))
        if missing:
            warnings.append(f"{len(missing)} team(s) playing this week are not on the report yet ({', '.join(missing)}). "
                            "Teams usually appear as their game approaches; absence does not mean healthy.")
    dates = report.get("source_game_dates", [])
    if dates and (now.date() - dt.date.fromisoformat(max(dates))).days > 7:
        warnings.append("The report is for a game week that ended more than a week ago.")
    warnings += report.get("parse_warnings", [])
    rows = report.get("rows", [])
    counts = {}
    for r in rows:
        k = r["game_status"] or "No game status"
        counts[k] = counts.get(k, 0) + 1
    status = "unavailable" if not report else "stale" if stale else "degraded" if last and last["ok"] != "1" else "ok"
    return dict(schema_version=2, source_url=SOURCE, generated_at=iso(now),
                last_attempt_at=last["checked_at"] if last else None, last_attempt_ok=bool(last and last["ok"] == "1"),
                last_error=(last["error"] or None) if last and last["ok"] != "1" else None,
                last_success_at=success, report_first_seen_at=state.get("observed_at"), collection_status=status,
                stale_after_hours=STALE_HOURS, report_season=report.get("season"), report_week=report.get("week"),
                covered_teams=covered, expected_teams=expected_teams, missing_teams=missing, source_game_dates=dates,
                status_counts=counts, rows=rows, recent_changes=list(reversed(read_changes(store, 40))),
                distinct_reports=state.get("distinct_reports", 0), checks=len(checks), failed_checks=len(checks) - len(good),
                warnings=warnings, projection_effect="none", return_timeline_coverage="not_collected",
                note="Collection only. These records do not change any rating or probability. Check times are when this site "
                     "looked at the report, not when the NFL published it. A blank game status is not an Active designation, and a "
                     "player who is no longer listed has not been shown to have recovered.")


def collect(store=None, now=None, fetcher=None, build_dir=None, games_csv=None):
    """One check. Returns (summary, ok). Never raises for source problems; they are logged as failed checks."""
    store = Path(store) if store else ROOT / "data" / "nfl_injury_monitor"
    store.mkdir(parents=True, exist_ok=True)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Collection time must include a timezone")
    stamp = iso(now)
    state = _read_json(store / "state.json", {}) or {}
    ok = False
    try:
        text, _source_hash = (fetcher or fetch_report)()
        report = parse_report(text)
        expected = now.year if now.month >= 8 else now.year - 1
        if report["season"] != expected:
            raise ValueError(f"Source season {report['season']} differs from expected {expected}")
    except Exception as e:  # noqa: BLE001 - every failure is recorded and the last good report kept
        _append_check(store, checked_at=stamp, ok=0, error=f"{type(e).__name__}: {e}"[:500])
    else:
        encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        if digest != state.get("digest"):
            rel = f"reports/{report['season']}/week-{report['week']:02d}/{stamp.replace(':', '')}_{digest[:12]}.json"
            previous = _read_json(store / state["report_file"]) if state.get("report_file") else None
            _write_json(store / rel, dict(observed_at=stamp, **report))
            ch = diff_rows(previous, report)
            if ch:
                with open(store / "changes.jsonl", "a", encoding="utf-8") as f:
                    for c in ch:
                        f.write(json.dumps(dict(observed_at=stamp, season=report["season"], week=report["week"], **c),
                                           ensure_ascii=False, separators=(",", ":")) + "\n")
            state = dict(report_file=rel, digest=digest, observed_at=stamp, distinct_reports=state.get("distinct_reports", 0) + 1)
            _write_json(store / "state.json", state)
        _append_check(store, checked_at=stamp, ok=1, report_file=state["report_file"], season=report["season"], week=report["week"],
                      teams=len(report["covered_teams"]), rows=len(report["rows"]))
        ok = True
    st = _read_json(store / "state.json", {}) or {}
    rep = _read_json(store / st["report_file"]) if st.get("report_file") else None
    try:
        expected_teams = scheduled_teams(rep["season"], rep["week"], games_csv) if rep else None
    except Exception:  # noqa: BLE001 - coverage context is optional
        expected_teams = None
    summary = summarise(store, now, expected_teams)
    _write_json(store / "summary.json", summary)
    _write_json(Path(build_dir or ROOT / "build") / "injury_monitor.json", summary)
    print(f"[injury monitor] {summary['collection_status']}: season {summary['report_season']} week {summary['report_week']}, "
          f"{len(summary['rows'])} rows, {len(summary['covered_teams'])} teams; last error: {summary['last_error']}; projections unchanged",
          flush=True)
    return summary, ok


def build_sqlite(store, out):
    """Rebuild a queryable SQLite index from the text history (for research; never committed)."""
    store = Path(store)
    out = Path(out)
    if out.exists():
        out.unlink()
    db = sqlite3.connect(out)
    db.executescript("""
        CREATE TABLE reports(file TEXT PRIMARY KEY, observed_at TEXT, season INT, week INT, teams INT, rows INT);
        CREATE TABLE report_rows(file TEXT, team TEXT, player_id TEXT, player TEXT, position TEXT, injury TEXT,
                                 practice_status TEXT, game_status TEXT);
        CREATE TABLE checks(checked_at TEXT, ok INT, report_file TEXT, season INT, week INT, teams INT, rows INT, error TEXT);
        CREATE TABLE changes(observed_at TEXT, season INT, week INT, team TEXT, player_id TEXT, kind TEXT, before_row TEXT, after_row TEXT);
    """)
    for p in sorted(store.glob("reports/*/*/*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        rel = str(p.relative_to(store)).replace(os.sep, "/")
        db.execute("INSERT INTO reports VALUES(?,?,?,?,?,?)", (rel, r["observed_at"], r["season"], r["week"], len(r["covered_teams"]), len(r["rows"])))
        db.executemany("INSERT INTO report_rows VALUES(?,?,?,?,?,?,?,?)",
                       [(rel, x["team"], x["player_id"], x["player"], x["position"], x["injury"], x["practice_status"], x["game_status"]) for x in r["rows"]])
    db.executemany("INSERT INTO checks VALUES(?,?,?,?,?,?,?,?)", [tuple(c[k] for k in CHECK_FIELDS) for c in read_checks(store)])
    db.executemany("INSERT INTO changes VALUES(?,?,?,?,?,?,?,?)",
                   [(c["observed_at"], c["season"], c["week"], c["team"], c["player_id"], c["kind"], json.dumps(c["before"]), json.dumps(c["after"]))
                    for c in read_changes(store)])
    db.commit()
    db.close()
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    ap = argparse.ArgumentParser(description="Collection-only NFL injury report monitor")
    ap.add_argument("--store", type=Path, help="history directory (default data/nfl_injury_monitor)")
    ap.add_argument("--sqlite", type=Path, help="rebuild a SQLite index from the store instead of collecting")
    a = ap.parse_args()
    if a.sqlite:
        print(build_sqlite(a.store or ROOT / "data" / "nfl_injury_monitor", a.sqlite))
    else:
        _, success = collect(a.store)
        raise SystemExit(0 if success else 1)
