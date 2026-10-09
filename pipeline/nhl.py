"""NHL stats: every report the league publishes (api.nhle.com/stats/rest) for teams, skaters and goalies, plus team game logs.

Columns are discovered from the data rather than hard-coded, so a report that gains a column shows up on the next
refresh. Completed seasons are cached for a year, the current season for two hours (so every 3-hourly run is fresh).
Everything is non-fatal: a report that is missing or failing is skipped and the rest of the site still builds.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from common import DATA, OUT, ROOT, log

API = "https://api.nhle.com/stats/rest/en"
FIRST = 2010                      # first season start year (2010-11); puck-possession reports start well before this
NHL_DATA = os.path.join(DATA, "nhl")
NHL_OUT = os.path.join(OUT, "nhl")
NHL_SRC = os.path.join(ROOT, "site_src", "nhl")
NHL_SITE = os.path.join(ROOT, "site", "nhl")

# (report, group label). Order is the order the column groups appear in on the site.
TEAM_REPORTS = [("summary", "Results"), ("percentages", "Possession & luck"), ("realtime", "Hits, blocks, giveaways"),
                ("summaryshooting", "Shot quality & types"), ("shottype", "Shot types"),
                ("powerplay", "Power play"), ("powerplaytime", "Power play time"), ("penaltykill", "Penalty kill"),
                ("penaltykilltime", "Penalty kill time"), ("penalties", "Discipline"),
                ("faceoffpercentages", "Faceoffs"), ("faceoffwins", "Faceoffs"), ("shootout", "Shootout"),
                ("leadingtrailing", "Score effects"), ("scoretrailfirst", "Score effects"),
                ("goalsforbystrength", "Goals by strength"), ("goalsagainstbystrength", "Goals by strength"),
                ("goalsbyperiod", "Goals by period"), ("outshootoutshotby", "Outshot / outshooting"),
                ("daysbetweengames", "Rest")]
SKATER_REPORTS = [("summary", "Scoring"), ("scoringRates", "Scoring rates"), ("scoringpergame", "Scoring rates"),
                  ("puckPossessions", "Possession"), ("summaryshooting", "Shooting"), ("shottype", "Shot types"),
                  ("goalsForAgainst", "On-ice goals"), ("realtime", "Hits, blocks, giveaways"),
                  ("powerplay", "Power play"), ("penaltykill", "Penalty kill"), ("penalties", "Discipline"),
                  ("faceoffpercentages", "Faceoffs"), ("faceoffwins", "Faceoffs"), ("timeonice", "Ice time"),
                  ("shootout", "Shootout"), ("penaltyShots", "Penalty shots"), ("bios", "Bio")]
GOALIE_REPORTS = [("summary", "Basics"), ("advanced", "Advanced"), ("savesByStrength", "Saves by strength"),
                  ("startedVsRelieved", "Started vs relieved"), ("daysrest", "Rest"), ("shootout", "Shootout"),
                  ("penaltyShots", "Penalty shots"), ("bios", "Bio")]
GAME_REPORTS = [("summary", "Result"), ("percentages", "Possession"), ("realtime", "Hits, blocks, giveaways"),
                ("penalties", "Discipline"), ("faceoffpercentages", "Faceoffs")]

HIDE = {"playerId", "teamId", "seasonId", "lastName", "skaterFullName", "goalieFullName", "teamFullName", "teamAbbrevs",
        "positionCode", "gameId", "gameDate", "homeRoad", "opponentTeamAbbrev", "birthDate", "firstName", "id",
        "currentTeamAbbrev", "skaterId", "goalieId", "gamesPlayed_dup", "playerName"}
KEEP_TEXT = {"nationalityCode", "shootsCatches", "birthCountryCode", "birthStateProvinceCode"}

# Current alignment (NHL tri-codes as the API reports them). Used for divisions from 2021-22 onwards.
DIVS = {"Atlantic": ["BOS", "BUF", "DET", "FLA", "MTL", "OTT", "TBL", "TOR"],
        "Metropolitan": ["CAR", "CBJ", "NJD", "NYI", "NYR", "PHI", "PIT", "WSH"],
        "Central": ["CHI", "COL", "DAL", "MIN", "NSH", "STL", "UTA", "WPG"],
        "Pacific": ["ANA", "CGY", "EDM", "LAK", "SEA", "SJS", "VAN", "VGK"]}
CONF = {"Atlantic": "East", "Metropolitan": "East", "Central": "West", "Pacific": "West"}

TOKENS = {"pp": "PP", "pk": "PK", "sh": "SH", "ev": "EV", "sat": "SAT", "usat": "USAT", "toi": "TOI", "gp": "GP", "ot": "OT",
          "so": "SO", "ga": "GA", "gf": "GF", "pct": "%", "pctg": "%", "per": "/", "pim": "PIM", "xg": "xG", "pdo": "PDO",
          "gs": "GS", "qs": "QS", "gsaa": "GSAA", "5v5": "5v5", "4v5": "4v5", "5v4": "5v4", "3v3": "3v3", "4v4": "4v4",
          "5v3": "5v3", "3v5": "3v5", "4v3": "4v3", "3v4": "3v4"}
GLOSS = {
    "satPct": "Corsi share: all shot attempts for / (for + against), 5v5.",
    "usatPct": "Fenwick share: unblocked shot attempts for / (for + against), 5v5.",
    "goalsForPct": "Share of 5v5 goals scored by the team.",
    "shootingPlusSavePct5v5": "PDO: 5v5 shooting % plus save %. Regresses toward 100.",
    "zoneStartPct5v5": "Share of 5v5 shifts starting in the offensive zone (neutral zone excluded).",
    "luck": "Actual points minus the points the team's goal difference usually earns.",
    "expPoints": "Points expected from goal difference (relationship fitted on every loaded season).",
    "ptsPace": "Points per game x 82.",
    "savesAboveAvg": "Saves minus what a league-average goalie would have saved on the same shots (no shot quality).",
    "stIndex": "Power play % plus penalty kill %.",
}
FMT_FIX = {"expPoints": "num1", "luck": "num1", "ptsPace": "num1", "savesAboveAvg": "num1", "savesAboveAvgPer60": "num2",
           "shotsAgainstPer60": "num1", "goalDiffPerGame": "num2", "toiTotal": "mins", "age": "num1", "shotsPerGame": "num2",
           "stIndex": "pdo"}
LO_PAT = re.compile(r"(against|giveaway|losses|missed|penaltyminutes|pim|minors?|majors?|misconducts?|attemptsblocked|^penalties$|^ga$)", re.I)
NOT_LO = re.compile(r"(pct|net)", re.I)


# ---------------------------------------------------------------- fetching

def start_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year if today.month >= 9 else today.year - 1


def sid(y: int) -> int:
    return y * 10000 + y + 1


def _fetch(kind: str, report: str, y: int, game: bool, cur: bool):
    """Rows of one report/season ([] if the report doesn't exist), or None if it failed and nothing is cached."""
    os.makedirs(NHL_DATA, exist_ok=True)
    path = os.path.join(NHL_DATA, f"{kind}_{report}_{y}{'_g' if game else ''}.json")
    max_age = 2 * 3600 if cur else 365 * 24 * 3600
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        return json.load(open(path))
    q = {"isAggregate": "false", "isGame": "true" if game else "false", "limit": "-1", "start": "0",
         "cayenneExp": f"seasonId={sid(y)} and gameTypeId=2"}
    url = f"{API}/{kind}/{report}?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                rows = json.load(r).get("data", [])
            with open(path, "w") as f:
                json.dump(rows, f, separators=(",", ":"))
            return rows
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):          # no such report (or none for that season): remember it
                with open(path, "w") as f:
                    f.write("[]")
                return []
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return json.load(open(path)) if os.path.exists(path) else None


def fetch_many(jobs):
    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(lambda j: _fetch(*j), jobs))


# ---------------------------------------------------------------- helpers

def words(key: str) -> str:
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])", " ", key)
    out = []
    for t in s.split():
        out.append(TOKENS.get(t.lower(), t.capitalize() if t.islower() or t[:1].isupper() and t[1:].islower() else t))
    lab = " ".join(out).replace(" / ", "/").replace(" %", "%")
    return lab.replace("/ ", "/").strip()


def fmt_for(key: str, s: pd.Series) -> str:
    k = key.lower()
    v = s.dropna()
    if v.empty:
        return "num2"
    mx = float(v.abs().max())
    if "timeonice" in k or k.startswith("toi"):
        return "mmss" if ("pergame" in k or "pershift" in k) else "mins"
    if "shootingplussave" in k:
        return "pdo"
    if "savepct" in k:
        return "sv" if "plus" not in k else "pdo"
    if re.search(r"(pct|pctg|share|rate)$|pct\d|pct[a-z]", k) and mx <= 1.5:
        return "pct"
    if (v == v.round()).all():
        return "int"
    return "num1" if mx >= 100 else "num2"


def norm_name(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


def frame(rows, idkey):
    d = pd.DataFrame(rows)
    if d.empty or idkey not in d:
        return pd.DataFrame()
    if d[idkey].duplicated().any():      # traded players can be split by team: keep the biggest line
        d = d.sort_values("gamesPlayed", ascending=False, na_position="last") if "gamesPlayed" in d else d
        d = d.drop_duplicates(idkey)
    return d.set_index(idkey)


def merge_reports(base: pd.DataFrame, extra: list[tuple[str, pd.DataFrame]], groups: dict, first_group: str):
    """Left-join every report's new numeric columns onto base, remembering which group each column came from."""
    for c in base.columns:
        groups.setdefault(c, first_group)
    for grp, d in extra:
        if d.empty:
            continue
        keep = {}
        for c in d.columns:
            if c in base.columns or c in HIDE and c not in KEEP_TEXT:
                continue
            if c in KEEP_TEXT:
                keep[c] = d[c]
                continue
            col = pd.to_numeric(d[c], errors="coerce")
            if col.notna().any():
                keep[c] = col
        if keep:
            add = pd.DataFrame(keep)
            for c in add.columns:
                groups[c] = grp
            base = base.join(add, how="left")
    return base


def cols_meta(df: pd.DataFrame, groups: dict, skip=()):
    meta, keep = [], []
    for c in df.columns:
        if c in skip or c in HIDE and c not in KEEP_TEXT:
            continue
        s = df[c]
        if c in KEEP_TEXT or not pd.api.types.is_numeric_dtype(s):
            meta.append({"k": c, "l": words(c), "g": groups.get(c, "Other"), "f": "text"})
            keep.append(c)
            continue
        if not s.notna().any():
            continue
        m = {"k": c, "l": words(c), "g": groups.get(c, "Other"), "f": FMT_FIX.get(c) or fmt_for(c, s)}
        if LO_PAT.search(c) and not NOT_LO.search(c):
            m["lo"] = 1
        if c in GLOSS:
            m["t"] = GLOSS[c]
        meta.append(m)
        keep.append(c)
    return meta, keep


def rows_out(df: pd.DataFrame, meta, idcols: dict):
    """Columnar rows: identity columns first, then each meta column, numbers rounded."""
    out = []
    ks = [m["k"] for m in meta]
    fs = [m["f"] for m in meta]
    for idx, r in df.iterrows():
        row = [idcols[c][idx] for c in idcols]
        for k, f in zip(ks, fs):
            v = r[k]
            if f == "text":
                row.append(None if v is None or (isinstance(v, float) and v != v) else str(v))
            elif v is None or (isinstance(v, float) and not math.isfinite(v)) or pd.isna(v):
                row.append(None)
            elif f == "int":
                row.append(int(round(float(v))))
            else:
                row.append(round(float(v), 4))
        out.append(row)
    return out


def num(d, c):
    return pd.to_numeric(d[c], errors="coerce") if c in d else pd.Series(np.nan, index=d.index)


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    return o


def write(name: str, obj):
    os.makedirs(NHL_OUT, exist_ok=True)
    with open(os.path.join(NHL_OUT, name), "w") as f:
        json.dump(_clean(obj), f, separators=(",", ":"), allow_nan=False)


# ---------------------------------------------------------------- build

def build_data():
    try:
        _build_data()
    except Exception as e:          # never let a data problem here stop the other sports
        log("nhl FAILED:", repr(e))
        import traceback
        traceback.print_exc()


def _build_data():
    cur_y = start_year()
    seasons = list(range(FIRST, cur_y + 1))
    log("nhl seasons", seasons[0], "to", seasons[-1])

    jobs = []
    for y in seasons:
        c = y == cur_y
        jobs += [("team", r, y, False, c) for r, _ in TEAM_REPORTS]
        jobs += [("team", r, y, True, c) for r, _ in GAME_REPORTS]
        jobs += [("skater", r, y, False, c) for r, _ in SKATER_REPORTS]
        jobs += [("goalie", r, y, False, c) for r, _ in GOALIE_REPORTS]
    got = dict(zip([(j[0], j[1], j[2], j[3]) for j in jobs], fetch_many(jobs)))
    log("nhl fetched", len(jobs), "requests")

    def rep(kind, r, y, game=False):
        return got.get((kind, r, y, game)) or []

    # team id -> tri-code, learned from the game logs (each row names the opponent's code)
    tid2abbr = {}
    for y in seasons:
        g = rep("team", "summary", y, True)
        by_game = {}
        for r in g:
            by_game.setdefault(r["gameId"], []).append(r)
        for rows in by_game.values():
            if len(rows) == 2:
                a, b = rows
                tid2abbr[b["teamId"]] = a.get("opponentTeamAbbrev")
                tid2abbr[a["teamId"]] = b.get("opponentTeamAbbrev")
    log("nhl teams known", len(tid2abbr))

    team_frames, played = {}, []
    for y in seasons:
        base = frame(rep("team", "summary", y), "teamId")
        if base.empty or base.gamesPlayed.max() < 1:
            continue
        groups = {}
        extra = [(grp, frame(rep("team", r, y), "teamId")) for r, grp in TEAM_REPORTS[1:]]
        d = merge_reports(base, extra, groups, "Results")
        d["abbr"] = [tid2abbr.get(i) or norm_name(base.loc[i, "teamFullName"])[:3].upper() for i in d.index]
        team_frames[y] = (d, groups)
        played.append(y)
    if not played:
        raise RuntimeError("no NHL team data")

    # goal difference -> points: fitted on every season so 'luck' has a fixed meaning
    xs, ys = [], []
    for y, (d, _) in team_frames.items():
        gp = num(d, "gamesPlayed")
        gdpg = (num(d, "goalsFor") - num(d, "goalsAgainst")) / gp
        xs += list(gdpg.dropna()); ys += list(((num(d, "points") / (2 * gp)) - 0.5)[gdpg.notna()])
    xs, ys = np.array(xs), np.array(ys)
    slope = float((xs * ys).sum() / (xs * xs).sum()) if len(xs) else 0.1
    log("nhl point% per goal of differential", round(slope, 4))

    for y in played:
        d, groups = team_frames[y]
        gp = num(d, "gamesPlayed")
        d["goalDiff"] = num(d, "goalsFor") - num(d, "goalsAgainst")
        d["goalDiffPerGame"] = d.goalDiff / gp
        d["ptsPace"] = num(d, "points") / gp * 82
        d["expPoints"] = (0.5 + slope * d.goalDiffPerGame) * gp * 2
        d["luck"] = num(d, "points") - d.expPoints
        if "powerPlayPct" in d and "penaltyKillPct" in d:
            d["stIndex"] = num(d, "powerPlayPct") + num(d, "penaltyKillPct")
            groups["stIndex"] = "Special teams"
        for c, g in (("goalDiff", "Results"), ("goalDiffPerGame", "Results"), ("ptsPace", "Results"),
                     ("expPoints", "Results"), ("luck", "Results")):
            groups[c] = g
        meta, keep = cols_meta(d, groups)
        order = ["gamesPlayed", "wins", "losses", "otLosses", "points", "pointPct", "ptsPace", "expPoints", "luck", "goalsFor",
                 "goalsAgainst", "goalDiff", "goalDiffPerGame"]
        meta.sort(key=lambda m: (order.index(m["k"]) if m["k"] in order else 99))
        meta = [m for m in meta if m["k"] != "abbr"]
        write(f"team_{y}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {"team": d.abbr.to_dict(), "name": d.teamFullName.to_dict()})})

    # ---- skaters / goalies
    for y in seasons:
        base = frame(rep("skater", "summary", y), "playerId")
        if not base.empty and base.gamesPlayed.max() >= 1:
            groups = {}
            extra = [(grp, frame(rep("skater", r, y), "playerId")) for r, grp in SKATER_REPORTS[1:]]
            d = merge_reports(base, extra, groups, "Scoring")
            gp = num(d, "gamesPlayed")
            toi = num(d, "timeOnIcePerGame")
            d["toiTotal"] = toi * gp
            groups["toiTotal"] = "Ice time"
            d["shotsPerGame"] = num(d, "shots") / gp
            groups["shotsPerGame"] = "Shooting"
            if "birthDate" in d:
                by = pd.to_datetime(d.birthDate, errors="coerce")
                d["age"] = ((pd.Timestamp(year=y, month=10, day=1) - by).dt.days / 365.25).round(1)
                groups["age"] = "Bio"
            meta, keep = cols_meta(d, groups)
            order = ["gamesPlayed", "goals", "assists", "points", "pointsPerGame", "plusMinus", "shots", "shootingPct", "timeOnIcePerGame"]
            meta.sort(key=lambda m: (order.index(m["k"]) if m["k"] in order else 99))
            write(f"skaters_{y}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {
                "name": d.skaterFullName.to_dict(), "team": d.teamAbbrevs.to_dict(), "pos": d.positionCode.to_dict()})})
        gb = frame(rep("goalie", "summary", y), "playerId")
        if not gb.empty and gb.gamesPlayed.max() >= 1:
            groups = {}
            extra = [(grp, frame(rep("goalie", r, y), "playerId")) for r, grp in GOALIE_REPORTS[1:]]
            d = merge_reports(gb, extra, groups, "Basics")
            sa, sv = num(d, "shotsAgainst"), num(d, "saves")
            lg = float(sv.sum() / sa.sum()) if sa.sum() else float("nan")
            d["savesAboveAvg"] = sv - sa * lg
            d["savesAboveAvgPer60"] = d.savesAboveAvg / (num(d, "timeOnIce") / 3600)
            d["shotsAgainstPer60"] = sa / (num(d, "timeOnIce") / 3600)
            for c in ("savesAboveAvg", "savesAboveAvgPer60", "shotsAgainstPer60"):
                groups[c] = "Advanced"
            if "birthDate" in d:
                by = pd.to_datetime(d.birthDate, errors="coerce")
                d["age"] = ((pd.Timestamp(year=y, month=10, day=1) - by).dt.days / 365.25).round(1)
                groups["age"] = "Bio"
            meta, keep = cols_meta(d, groups)
            order = ["gamesPlayed", "gamesStarted", "wins", "losses", "otLosses", "savePct", "goalsAgainstAverage", "savesAboveAvg", "shutouts"]
            meta.sort(key=lambda m: (order.index(m["k"]) if m["k"] in order else 99))
            write(f"goalies_{y}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {
                "name": d.goalieFullName.to_dict(), "team": d.teamAbbrevs.to_dict(), "pos": {i: "G" for i in d.index}})})

        # ---- team game log (one row per team per game)
        gb = pd.DataFrame(rep("team", "summary", y, True))
        if gb.empty:
            continue
        gb["key"] = gb.gameId.astype(str) + "_" + gb.teamId.astype(str)
        gb = gb.drop_duplicates("key").set_index("key")
        groups = {}
        extra = []
        for r, grp in GAME_REPORTS[1:]:
            e = pd.DataFrame(rep("team", r, y, True))
            if e.empty or "gameId" not in e:
                continue
            e["key"] = e.gameId.astype(str) + "_" + e.teamId.astype(str)
            extra.append((grp, e.drop_duplicates("key").set_index("key")))
        d = merge_reports(gb, extra, groups, "Result")
        d["abbr"] = d.teamId.map(tid2abbr)
        d["goalDiff"] = num(d, "goalsFor") - num(d, "goalsAgainst")
        groups["goalDiff"] = "Result"
        d["res"] = np.where(num(d, "wins") > 0, "W", np.where(num(d, "otLosses") > 0, "OTL", "L"))
        meta, keep = cols_meta(d, groups)
        meta = [m for m in meta if m["k"] not in ("gamesPlayed", "wins", "losses", "otLosses", "ties", "abbr", "res", "winsInRegulation",
                                                   "winsInShootout", "regulationAndOtWins", "teamShutouts", "pointPct", "goalsForPerGame",
                                                   "goalsAgainstPerGame", "shotsForPerGame", "shotsAgainstPerGame", "penaltyKillNetPct",
                                                   "powerPlayNetPct", "points")] + \
               [m for m in meta if m["k"] == "points"]
        d = d.sort_values(["gameDate", "gameId"])
        write(f"games_{y}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {
            "date": d.gameDate.to_dict(), "team": d.abbr.to_dict(), "opp": d.opponentTeamAbbrev.to_dict(),
            "ha": d.homeRoad.to_dict(), "res": d.res.to_dict()})})

    meta = {"season": cur_y, "seasons": [y for y in played if y <= cur_y][::-1],
            "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "slope": round(slope, 4), "divisions": DIVS, "conf": CONF, "div_from": 2021,
            "teams": {t["abbr"]: t["name"] for _, t in pd.DataFrame(
                [{"abbr": team_frames[played[-1]][0].loc[i, "abbr"], "name": team_frames[played[-1]][0].loc[i, "teamFullName"]}
                 for i in team_frames[played[-1]][0].index]).iterrows()}}
    write("meta.json", meta)
    log("nhl data done:", len(played), "seasons")


# ---------------------------------------------------------------- site

PAGES = [("index", "Standings", "NHL standings", "Points, pace, goal difference, and how lucky each team has been, by division, conference or league."),
         ("teams", "Team stats", "NHL team stats", "Every team stat the league publishes, shaded best to worst, plus a year-by-year view of how any stat changes for each team."),
         ("skaters", "Skaters", "NHL skaters", "Scoring, possession, shooting, ice time, power play and discipline for every skater. Any season or all seasons."),
         ("goalies", "Goalies", "NHL goalies", "Save percentage, saves above average, rest, strength splits and more for every goalie."),
         ("games", "Games", "NHL team game log", "Every team game since 2010-11: shots, possession, hits, faceoffs and special teams, searchable by team and season.")]


def _page(slug, label, title, intro):
    nav = "".join(f'<a href="{"./" if s == "index" else s + ".html"}"{" aria-current=page" if s == slug else ""}>{html.escape(l)}</a>' for s, l, *_ in PAGES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{html.escape(title)} · NHL</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Public+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="../style.css"><link rel="stylesheet" href="nhl.css"></head>
<body data-page="{slug}"><div class="wrap">
<header class="site-head"><div class="sportbar"><span>SPORT</span><a href="../">NFL</a><a href="../nba/">NBA</a><a href="../nbl/">NBL</a><a href="./" aria-current="page">NHL</a></div>
<div class="brand"><a class="brand-name" href="./">NHL<span>Stats</span></a><span class="stamp" id="stamp">Loading latest update…</span></div>
<nav class="nav nav-simple" aria-label="NHL sections">{nav}</nav></header>
<main class="page" id="main"><div class="page-head"><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p></div>
<div id="app" class="page"><p class="loading">Loading…</p></div></main>
<footer class="stamp">Official NHL statistics (api.nhle.com), refreshed every few hours. Independent stats research, not betting advice.</footer></div>
<script src="../js/common.js"></script><script src="nhl.js"></script></body></html>
"""


def build_site():
    os.makedirs(os.path.join(NHL_SITE, "data"), exist_ok=True)
    for slug, label, title, intro in PAGES:
        with open(os.path.join(NHL_SITE, "index.html" if slug == "index" else f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(_page(slug, label, title, intro))
    for n in ("nhl.js", "nhl.css"):
        shutil.copy(os.path.join(NHL_SRC, n), NHL_SITE)
    if os.path.isdir(NHL_OUT):
        for f in os.listdir(NHL_OUT):
            shutil.copy(os.path.join(NHL_OUT, f), os.path.join(NHL_SITE, "data", f))


if __name__ == "__main__":
    build_data()
    build_site()
