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
                ("summaryshooting", "Shot attempts by score"), ("shottype", "Shot types"),
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
          "gs": "GS", "qs": "QS", "percentage": "%", "gsaa": "GSAA", "5v5": "5v5", "4v5": "4v5", "5v4": "5v4", "3v3": "3v3", "4v4": "4v4",
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
LO_PAT = re.compile(r"(against|giveaway|losses|missed|penaltyminutes|pim|minors?|majors?|misconducts?|attemptsblocked|^penalties$|^ga$|penaltiestaken|timesshorthanded)", re.I)
NOT_LO = re.compile(r"pct", re.I)


# ---------------------------------------------------------------- fetching

def start_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year if today.month >= 9 else today.year - 1


def sid(y: int) -> int:
    return y * 10000 + y + 1


def _fetch(kind: str, report: str, y: int, game: bool, cur: bool, gt: int = 2):
    """Rows of one report/season ([] if the report doesn't exist), or None if it failed and nothing is cached."""
    os.makedirs(NHL_DATA, exist_ok=True)
    path = os.path.join(NHL_DATA, f"{kind}_{report}_{y}{'_g' if game else ''}{'_po' if gt == 3 else ''}.json")
    max_age = 2 * 3600 if cur else 365 * 24 * 3600
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        return json.load(open(path))
    q = {"isAggregate": "false", "isGame": "true" if game else "false", "limit": "-1", "start": "0",
         "cayenneExp": f"seasonId={sid(y)} and gameTypeId={gt}"}
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

LABELS = {"gamesPlayed": "GP", "gamesStarted": "GS", "timeOnIcePerGame": "TOI/GP", "pointsPerGame": "P/GP", "plusMinus": "+/-",
          "shootingPct": "S%", "savePct": "SV%", "goalsAgainstAverage": "GAA", "penaltyMinutes": "PIM", "points": "PTS", "goals": "G",
          "assists": "A", "shots": "SOG", "wins": "W", "losses": "L", "otLosses": "OTL", "pointPct": "P%", "satPct": "SAT% (Corsi)",
          "usatPct": "USAT% (Fenwick)", "powerPlayPct": "PP%", "penaltyKillPct": "PK%", "faceoffWinPct": "FO%", "goalsFor": "GF",
          "goalsAgainst": "GA", "goalDiff": "GD", "regulationAndOtWins": "ROW", "shotsForPerGame": "SF/GP", "shotsAgainstPerGame": "SA/GP",
          "goalsForPerGame": "GF/GP", "goalsAgainstPerGame": "GA/GP", "savePct5v5": "SV% 5v5", "shootingPct5v5": "S% 5v5",
          "shootingPlusSavePct5v5": "PDO", "goalsForPct": "GF% 5v5", "zoneStartPct5v5": "OZ start% 5v5", "toiTotal": "TOI total (min)",
          "satFor": "Corsi For 5v5", "satAgainst": "Corsi Against 5v5", "usatFor": "Fenwick For 5v5", "usatAgainst": "Fenwick Against 5v5",
          "mp_shotAttemptsFor": "Corsi For (all sit.)", "mp_shotAttemptsAgainst": "Corsi Against (all sit.)",
          "mp_corsiPercentage": "Corsi % (all sit.)", "mp5v5_corsiPercentage": "Corsi % 5v5",
          "mp_highDangerShotsFor": "High-danger chances For", "mp_highDangerShotsAgainst": "High-danger chances Against",
          "mp5v5_highDangerShotsFor": "High-danger chances For 5v5", "mp5v5_highDangerShotsAgainst": "High-danger chances Against 5v5",
          "mp_highDangerxGoalsFor": "High-danger xG For", "mp_highDangerxGoalsAgainst": "High-danger xG Against",
          "mp_xGoalsFor": "xG For", "mp_xGoalsAgainst": "xG Against", "mp_xGoalsPercentage": "xG %", "mp5v5_xGoalsPercentage": "xG % 5v5",
          "mp5v5_xGoalsFor": "xG For 5v5", "mp5v5_xGoalsAgainst": "xG Against 5v5",
          "mp_xGDiff": "xG Diff", "mp_goalsAboveExp": "Goals For minus xG", "mp_goalsAgainstAboveExp": "Goals Against minus xG",
          "mp_gsax": "GSAx (xG faced minus goals allowed)", "mp_gsaxPerShot": "GSAx per shot", "mp_hdSavePct": "High-danger SV%",
          "mp_I_F_xGoals": "Individual xG", "mp_I_F_highDangerShots": "Individual high-danger shots", "mp_I_F_highDangerxGoals": "Individual high-danger xG",
          "mp_onIce_xGoalsPercentage": "On-ice xG %", "mp5v5_onIce_xGoalsPercentage": "On-ice xG % 5v5"}


def words(key: str) -> str:
    if key in LABELS:
        return LABELS[key]
    if key.startswith("mp"):
        lab = mp_label(key)
        if lab:
            return lab
    key = key.replace("xGoals", " \x01 ").replace("xG", " \x01 ")
    key = re.sub(r"(\d)(?:v|On)(\d)", "\\1\x00\\2", key)
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])", " ", key)
    out = []
    for t in s.split():
        out.append(TOKENS.get(t.lower(), t.capitalize() if t.islower() or t[:1].isupper() and t[1:].islower() else t))
    lab = " ".join(out).replace(" / ", "/").replace(" %", "%")
    return lab.replace("/ ", "/").replace("\x00", "v").replace("\x01", "xG").strip()


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
        return "sv"
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
        if c in KEEP_TEXT:
            meta.append({"k": c, "l": words(c), "g": groups.get(c, "Other"), "f": "text"})
            keep.append(c)
            continue
        if not pd.api.types.is_numeric_dtype(s) or not s.notna().any():
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

MP = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
MP_ALIAS = {"TB": "TBL", "NJ": "NJD", "SJ": "SJS", "LA": "LAK"}
MP_TEAM_KEEP = ["xGoalsPercentage", "corsiPercentage", "fenwickPercentage", "xGoalsFor", "xGoalsAgainst", "goalsFor", "goalsAgainst",
                "highDangerShotsFor", "highDangerShotsAgainst", "highDangerxGoalsFor", "highDangerxGoalsAgainst",
                "highDangerGoalsFor", "highDangerGoalsAgainst", "shotAttemptsFor", "shotAttemptsAgainst", "iceTime"]
MP_SIT = {"all": ("", "xG & danger (MoneyPuck)"), "5on5": ("5v5", "xG & danger 5v5 (MoneyPuck)"),
          "5on4": ("pp", "xG power play (MoneyPuck)"), "4on5": ("pk", "xG penalty kill (MoneyPuck)")}
MP_PARTS = {"I": "Ind", "F": "For", "A": "Against", "onIce": "On-ice", "OnIce": "On-ice", "offIce": "Off-ice", "OffIce": "Off-ice"}


def mp_label(key: str) -> str | None:
    m = re.match(r"mp(5v5|pp|pk)?_(.+)", key)
    if not m:
        return None
    suffix = {"5v5": " 5v5", "pp": " PP", "pk": " PK", None: ""}[m.group(1)]
    parts = [MP_PARTS.get(p) or words(p) for p in m.group(2).split("_")]
    return " ".join(parts).replace("  ", " ").strip() + suffix


def _mp_csv(kind: str, y: int, gt: int, cur: bool):
    os.makedirs(NHL_DATA, exist_ok=True)
    path = os.path.join(NHL_DATA, f"mp_{kind}_{y}{'_po' if gt == 3 else ''}.csv")
    max_age = 2 * 3600 if cur else 365 * 24 * 3600
    if not (os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age):
        url = f"{MP}/{y}/{'playoffs' if gt == 3 else 'regular'}/{kind}.csv"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r, open(path + ".part", "wb") as f:
                    shutil.copyfileobj(r, f)
                os.replace(path + ".part", path)
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    open(path, "w").close()
                    break
            except Exception:
                pass
            time.sleep(2 * (attempt + 1))
    if not os.path.exists(path) or os.path.getsize(path) < 50:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def mp_extras(kind: str, d: pd.DataFrame, key: str, y: int, gt: int, cur: bool, abbrs=None):
    """MoneyPuck xG tables as (group, frame) pairs ready for merge_reports. key = 'abbr' (teams) or 'playerId'."""
    m = _mp_csv(kind, y, gt, cur)
    if m.empty or "situation" not in m:
        return []
    ident = "team" if kind == "teams" else "playerId"
    if kind == "teams":
        m["k"] = m["team"].astype(str).str.replace(".", "", regex=False).map(lambda t: MP_ALIAS.get(t, t))
        if abbrs is not None and not m.k.isin(abbrs).any():
            return []
    else:
        m["k"] = m["playerId"]
    out = []
    for sit, (tag, grp) in MP_SIT.items():
        if kind != "teams" and sit != "all" and kind == "goalies":
            continue
        s = m[m.situation == sit]
        if s.empty:
            continue
        if "games_played" in s:
            s = s.sort_values("games_played", ascending=False)
        s = s.drop_duplicates("k").set_index("k")
        if kind == "teams":
            cols = [c for c in MP_TEAM_KEEP if c in s] if sit != "all" else [c for c in s.columns if pd.api.types.is_numeric_dtype(s[c]) and c not in ("season", "games_played")]
        elif sit == "all":
            cols = [c for c in s.columns if pd.api.types.is_numeric_dtype(s[c]) and c not in ("season", "playerId", "games_played")]
        else:
            cols = [c for c in s.columns if pd.api.types.is_numeric_dtype(s[c]) and re.search(r"xGoals|Percentage|gameScore|highDanger|icetime", c)
                    and c not in ("season", "playerId", "games_played")]
        t = s[cols].copy()
        t.columns = [f"mp{tag}_{c}" for c in cols]
        if kind == "goalies" and sit == "all":
            if "xGoals" in s and "goals" in s:
                t["mp_gsax"] = s["xGoals"] - s["goals"]
                t["mp_gsaxPerShot"] = t["mp_gsax"] / s["ongoal"].replace(0, np.nan)
                t["mp_hdSavePct"] = 1 - s["highDangerGoals"] / s["highDangerShots"].replace(0, np.nan)
        if kind == "teams" and sit == "all":
            t["mp_xGDiff"] = s["xGoalsFor"] - s["xGoalsAgainst"]
            t["mp_goalsAboveExp"] = s["goalsFor"] - s["xGoalsFor"]
            t["mp_goalsAgainstAboveExp"] = s["goalsAgainst"] - s["xGoalsAgainst"]
        out.append((grp, t))
    return out


def build_data():
    try:
        _build_data()
    except Exception as e:          # never let a data problem here stop the other sports
        log("nhl FAILED:", repr(e))
        import traceback
        traceback.print_exc()
        return
    try:
        import nhl_awards
        nhl_awards.build()
    except Exception as e:
        log("nhl awards FAILED:", repr(e))
        import traceback
        traceback.print_exc()


def _age(d, y, groups):
    if "birthDate" in d:
        by = pd.to_datetime(d.birthDate, errors="coerce")
        d["age"] = ((pd.Timestamp(year=y, month=10, day=1) - by).dt.days / 365.25).round(1)
        groups["age"] = "Bio"


def _order(meta, order):
    meta.sort(key=lambda m: (order.index(m["k"]) if m["k"] in order else 99))
    return meta


def _build_data():
    cur_y = start_year()
    seasons = list(range(FIRST, cur_y + 1))
    log("nhl seasons", seasons[0], "to", seasons[-1])

    jobs = []
    for y in seasons:
        c = y == cur_y
        for gt in (2, 3):
            jobs += [("team", r, y, False, c, gt) for r, _ in TEAM_REPORTS]
            jobs += [("team", r, y, True, c, gt) for r, _ in GAME_REPORTS]
            jobs += [("skater", r, y, False, c, gt) for r, _ in SKATER_REPORTS]
            jobs += [("goalie", r, y, False, c, gt) for r, _ in GOALIE_REPORTS]
    got = dict(zip([(j[0], j[1], j[2], j[3], j[5]) for j in jobs], fetch_many(jobs)))
    log("nhl fetched", len(jobs), "requests")

    def rep(kind, r, y, game=False, gt=2):
        return got.get((kind, r, y, game, gt)) or []

    tid2abbr = {}
    for y in seasons:
        by_game = {}
        for r in rep("team", "summary", y, True):
            by_game.setdefault(r["gameId"], []).append(r)
        for rows in by_game.values():
            if len(rows) == 2:
                a, b = rows
                tid2abbr[b["teamId"]] = a.get("opponentTeamAbbrev")
                tid2abbr[a["teamId"]] = b.get("opponentTeamAbbrev")
    log("nhl teams known", len(tid2abbr))

    slope = None
    played, po_played, xg_seasons = [], [], []
    for gt, suf in ((2, ""), (3, "p")):
        team_frames = {}
        for y in seasons:
            c = y == cur_y
            base = frame(rep("team", "summary", y, False, gt), "teamId")
            if base.empty or base.gamesPlayed.max() < 1:
                continue
            groups = {}
            extra = [(grp, frame(rep("team", r, y, False, gt), "teamId")) for r, grp in TEAM_REPORTS[1:]]
            d = merge_reports(base, extra, groups, "Results")
            d["abbr"] = [tid2abbr.get(i) or norm_name(base.loc[i, "teamFullName"])[:3].upper() for i in d.index]
            mp = mp_extras("teams", d, "abbr", y, gt, c, set(d.abbr))
            if mp:
                a = d.reset_index().set_index("abbr")
                for grp, t in mp:
                    new = t[[x for x in t.columns if x not in a.columns]]
                    for x in new.columns:
                        groups[x] = grp
                    a = a.join(new, how="left")
                d = a.reset_index().set_index("teamId")
                if gt == 2 and y not in xg_seasons:
                    xg_seasons.append(y)
            team_frames[y] = (d, groups)
        if gt == 2:
            xs, ys = [], []
            for y, (d, _) in team_frames.items():
                gp = num(d, "gamesPlayed")
                gdpg = (num(d, "goalsFor") - num(d, "goalsAgainst")) / gp
                xs += list(gdpg.dropna()); ys += list(((num(d, "points") / (2 * gp)) - 0.5)[gdpg.notna()])
            xs, ys = np.array(xs), np.array(ys)
            slope = float((xs * ys).sum() / (xs * xs).sum()) if len(xs) else 0.1
            log("nhl point% per goal of differential", round(slope, 4))
        if not team_frames:
            continue
        for y, (d, groups) in team_frames.items():
            gp = num(d, "gamesPlayed")
            d["goalDiff"] = num(d, "goalsFor") - num(d, "goalsAgainst")
            d["goalDiffPerGame"] = d.goalDiff / gp
            if gt == 2:
                d["ptsPace"] = num(d, "points") / gp * 82
                d["expPoints"] = (0.5 + slope * d.goalDiffPerGame) * gp * 2
                d["luck"] = num(d, "points") - d.expPoints
                for c in ("ptsPace", "expPoints", "luck"):
                    groups[c] = "Results"
            if "powerPlayPct" in d and "penaltyKillPct" in d:
                d["stIndex"] = num(d, "powerPlayPct") + num(d, "penaltyKillPct")
                groups["stIndex"] = "Special teams"
            for c in ("goalDiff", "goalDiffPerGame"):
                groups[c] = "Results"
            meta, _ = cols_meta(d, groups)
            meta = _order(meta, ["gamesPlayed", "wins", "losses", "otLosses", "points", "pointPct", "ptsPace", "expPoints", "luck", "goalsFor",
                                 "goalsAgainst", "goalDiff", "goalDiffPerGame"])
            meta = [m for m in meta if m["k"] != "abbr"]
            write(f"team_{y}{suf}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {"team": d.abbr.to_dict(), "name": d.teamFullName.to_dict()})})
            (played if gt == 2 else po_played).append(y)

        for y in seasons:
            c = y == cur_y
            base = frame(rep("skater", "summary", y, False, gt), "playerId")
            if not base.empty and base.gamesPlayed.max() >= 1:
                groups = {}
                extra = [(grp, frame(rep("skater", r, y, False, gt), "playerId")) for r, grp in SKATER_REPORTS[1:]]
                extra += mp_extras("skaters", base, "playerId", y, gt, c)
                d = merge_reports(base, extra, groups, "Scoring")
                gp = num(d, "gamesPlayed")
                d["toiTotal"] = num(d, "timeOnIcePerGame") * gp
                d["shotsPerGame"] = num(d, "shots") / gp
                groups["toiTotal"] = "Ice time"; groups["shotsPerGame"] = "Shooting"
                _age(d, y, groups)
                meta, _ = cols_meta(d, groups)
                meta = _order(meta, ["gamesPlayed", "goals", "assists", "points", "pointsPerGame", "plusMinus", "shots", "shootingPct", "timeOnIcePerGame"])
                write(f"skaters_{y}{suf}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {
                    "name": d.skaterFullName.to_dict(), "team": d.teamAbbrevs.to_dict(), "pos": d.positionCode.to_dict()})})
            gb = frame(rep("goalie", "summary", y, False, gt), "playerId")
            if not gb.empty and gb.gamesPlayed.max() >= 1:
                groups = {}
                extra = [(grp, frame(rep("goalie", r, y, False, gt), "playerId")) for r, grp in GOALIE_REPORTS[1:]]
                extra += mp_extras("goalies", gb, "playerId", y, gt, c)
                d = merge_reports(gb, extra, groups, "Basics")
                sa, sv = num(d, "shotsAgainst"), num(d, "saves")
                lg = float(sv.sum() / sa.sum()) if sa.sum() else float("nan")
                d["savesAboveAvg"] = sv - sa * lg
                hrs = (num(d, "timeOnIce") / 3600).replace(0, np.nan)
                d["savesAboveAvgPer60"] = d.savesAboveAvg / hrs
                d["shotsAgainstPer60"] = sa / hrs
                for c2 in ("savesAboveAvg", "savesAboveAvgPer60", "shotsAgainstPer60"):
                    groups[c2] = "Advanced"
                _age(d, y, groups)
                meta, _ = cols_meta(d, groups)
                meta = _order(meta, ["gamesPlayed", "gamesStarted", "wins", "losses", "otLosses", "savePct", "goalsAgainstAverage", "savesAboveAvg", "shutouts"])
                write(f"goalies_{y}{suf}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {
                    "name": d.goalieFullName.to_dict(), "team": d.teamAbbrevs.to_dict(), "pos": {i: "G" for i in d.index}})})

            gl = pd.DataFrame(rep("team", "summary", y, True, gt))
            if gl.empty:
                continue
            gl["key"] = gl.gameId.astype(str) + "_" + gl.teamId.astype(str)
            gl = gl.drop_duplicates("key").set_index("key")
            groups = {}
            extra = []
            for r, grp in GAME_REPORTS[1:]:
                e = pd.DataFrame(rep("team", r, y, True, gt))
                if e.empty or "gameId" not in e:
                    continue
                e["key"] = e.gameId.astype(str) + "_" + e.teamId.astype(str)
                extra.append((grp, e.drop_duplicates("key").set_index("key")))
            d = merge_reports(gl, extra, groups, "Result")
            d["abbr"] = d.teamId.map(tid2abbr)
            d["goalDiff"] = num(d, "goalsFor") - num(d, "goalsAgainst")
            groups["goalDiff"] = "Result"
            d["res"] = np.where(num(d, "wins") > 0, "W", np.where(num(d, "otLosses") > 0, "OTL", "L"))
            meta, _ = cols_meta(d, groups)
            drop = {"gamesPlayed", "wins", "losses", "otLosses", "ties", "abbr", "res", "winsInRegulation", "winsInShootout", "regulationAndOtWins",
                    "teamShutouts", "pointPct", "goalsForPerGame", "goalsAgainstPerGame", "shotsForPerGame", "shotsAgainstPerGame",
                    "penaltyKillNetPct", "powerPlayNetPct", "points"}
            meta = [m for m in meta if m["k"] not in drop] + [m for m in meta if m["k"] == "points"]
            d = d.sort_values(["gameDate", "gameId"])
            write(f"games_{y}{suf}.json", {"season": y, "cols": meta, "rows": rows_out(d, meta, {
                "date": d.gameDate.to_dict(), "team": d.abbr.to_dict(), "opp": d.opponentTeamAbbrev.to_dict(),
                "ha": d.homeRoad.to_dict(), "res": d.res.to_dict()})})

    if not played:
        raise RuntimeError("no NHL team data")
    names = {}
    for r in json.load(open(os.path.join(NHL_OUT, f"team_{played[-1]}.json")))["rows"]:
        names[r[0]] = r[1]
    meta = {"season": cur_y, "seasons": sorted(played, reverse=True), "po_seasons": sorted(po_played, reverse=True), "xg_seasons": sorted(xg_seasons, reverse=True),
            "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "slope": round(slope, 4), "divisions": DIVS, "conf": CONF, "div_from": 2021, "teams": names}
    write("meta.json", meta)
    log("nhl data done:", len(played), "regular seasons,", len(po_played), "playoff seasons, xG in", len(xg_seasons))


# ---------------------------------------------------------------- site

PAGES = [("index", "Standings", "NHL standings", "Points, pace, goal difference, and how lucky each team has been, by division, conference or league."),
         ("teams", "Team stats", "NHL team stats", "Every team stat the league publishes, shaded best to worst, plus a year-by-year view of how any stat changes for each team."),
         ("skaters", "Skaters", "NHL skaters", "Scoring, possession, shooting, ice time, power play and discipline for every skater. Any season or all seasons."),
         ("goalies", "Goalies", "NHL goalies", "Save percentage, saves above average, rest, strength splits and more for every goalie."),
         ("awards", "Awards", "NHL award futures", "Chance of winning the Hart, Vezina, Norris, Calder, Art Ross and Maurice Richard, with how the model has done on past seasons and what past winners looked like."),
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
