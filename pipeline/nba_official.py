"""Official NBA injury report (the league's PDF, published through the day) -> rows.

Statuses: Out, Doubtful, Questionable, Probable, Available. Reports are published at ak-static.cms.nba.com as
Injury-Report_YYYY-MM-DD_HH_MMAM|PM.pdf in US Eastern time; a missing report returns 403.
"""
import datetime as dt
import io
import re
import unicodedata
import urllib.request
from zoneinfo import ZoneInfo

BASE = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{}.pdf"
UA = {"User-Agent": "Mozilla/5.0 (SportsFutures)"}
ET = ZoneInfo("America/New_York")
STATUSES = ("Out", "Doubtful", "Questionable", "Probable", "Available")


def url_for(t):
    return BASE.format(t.strftime("%Y-%m-%d_%I_%M%p"))


def get(url, timeout=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.read()
    except Exception:  # noqa: BLE001
        return None


def latest(now=None, hours_back=30):
    """Most recent report at or before now (15-minute steps). Returns (url, bytes, eastern time) or (None, None, None)."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    t = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    for _ in range(int(hours_back * 4)):
        u = url_for(t)
        b = get(u, timeout=15)
        if b:
            return u, b, t
        t -= dt.timedelta(minutes=15)
    return None, None, None


def _norm(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


# Official three-letter codes -> full names (current franchises; older reports use the same codes)
OFFICIAL_TEAMS = {"ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics", "CHA": "Charlotte Hornets",
                  "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
                  "DET": "Detroit Pistons", "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
                  "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
                  "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans", "NYK": "New York Knicks",
                  "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
                  "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors",
                  "UTA": "Utah Jazz", "WAS": "Washington Wizards"}
ALIASES = {"losangelesclippers": "LAC"}
NOT_SUBMITTED = "NOT YET SUBMITTED"
COLS = ("game_date", "game_time", "matchup", "team", "player", "status", "reason")


def _header_columns(words):
    """Column left edges from the header line itself (Game Date | Game Time | Matchup | Team | Player Name |
    Current Status | Reason). Only words on that line are used, so body text such as 'Not With Team' cannot move a column."""
    lines = _lines(words)
    for ws in lines:
        texts = [w["text"] for w in ws]
        if "Matchup" in texts and "Reason" in texts:
            xs = {}
            games = [w["x0"] for w in ws if w["text"] in ("Game", "GameDate", "GameTime")]
            if len(games) >= 2:
                xs["game_date"], xs["game_time"] = games[0], games[1]
            elif games:
                xs["game_date"] = games[0]
            for w in ws:
                t = w["text"]
                if t == "Matchup":
                    xs["matchup"] = w["x0"]
                elif t == "Team":
                    xs["team"] = w["x0"]
                elif t in ("Player", "PlayerName") and "player" not in xs:
                    xs["player"] = w["x0"]
                elif t in ("Current", "CurrentStatus") and "status" not in xs:
                    xs["status"] = w["x0"]
                elif t == "Reason":
                    xs["reason"] = w["x0"]
                elif t == "Category":
                    xs["category"] = w["x0"]          # 2019-20 layout: Category | Reason
                elif t in ("Previous", "PreviousStatus"):
                    xs["previous"] = w["x0"]          # some layouts add a Previous Status column
            if {"matchup", "team", "player", "status", "reason"} <= set(xs):
                return sorted(xs.items(), key=lambda c: c[1]), ws[0]["top"]
    return None, None


def _lines(words, tol=2.5):
    """Group words into printed lines by vertical position."""
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(ws, key=lambda w: w["x0"]) for ws in out]


def _team_for(fragment, matchup):
    """Resolve a (possibly partial, wrapped) team cell against the two teams of the current matchup."""
    key = _norm(fragment)
    if not key:
        return None
    cands = []
    if matchup and "@" in matchup:
        cands = [a for a in matchup.split("@") if a in OFFICIAL_TEAMS]
    pool = cands or list(OFFICIAL_TEAMS)
    exact = [a for a in pool if _norm(OFFICIAL_TEAMS[a]) == key or ALIASES.get(key) == a]
    if exact:
        return exact[0]
    pref = [a for a in pool if _norm(OFFICIAL_TEAMS[a]).startswith(key)]
    return pref[0] if len(pref) == 1 else None


def parse(pdf_bytes, with_meta=False):
    """-> list of dict(game_date, game_time, matchup, team, team_code, player, status, reason).

    Game date, game time, matchup and team are carried from the row where they are printed to the rows below, across
    page breaks. A team cell is resolved only against the two teams of the current matchup (a wrapped name such as
    'Oklahoma City' / 'Thunder' is one team); a new matchup clears the team. A team marked NOT YET SUBMITTED gives a row
    with status 'NOT YET SUBMITTED' and no player (missing coverage, not a healthy team). Rows whose team cannot be
    resolved keep team None and are reported in the meta (never guessed).
    Player is 'Last, First' as printed; team_code is the league's three-letter code."""
    import pdfplumber
    rows, problems = [], []
    cur = {"game_date": None, "game_time": None, "matchup": None, "team": None, "team_code": None}
    team_buf = ""
    cols = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as P:
        for page in P.pages:
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
            c, head_top = _header_columns(words)
            if c:
                cols = c
            if not cols:
                continue
            for ws in _lines(words):
                if head_top is not None and abs(ws[0]["top"] - head_top) <= 2.5:
                    continue
                joined = " ".join(w["text"] for w in ws)
                if joined.startswith("Injury Report") or re.fullmatch(r"Page \d+ of \d+", joined) or re.match(r"Page\d+of\d+", joined):
                    continue
                cells = {}
                for w in ws:
                    name = cols[0][0]
                    for cname, x in cols:
                        if w["x0"] >= x - 3:
                            name = cname
                    cells.setdefault(name, []).append(w["text"])
                txt = {k: " ".join(v) for k, v in cells.items()}
                m = re.search(r"(\d\d/\d\d/\d{4})", txt.get("game_date", ""))
                if m:
                    cur["game_date"] = dt.datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
                    cur.update(matchup=None, team=None, team_code=None)
                    team_buf = ""
                tm = re.search(r"\d\d:\d\d\s*\(ET\)", txt.get("game_time", ""))
                if tm:
                    cur["game_time"] = tm.group(0)
                mu = re.match(r"([A-Z]{3})@([A-Z]{3})", txt.get("matchup", "").replace(" ", ""))
                if mu:
                    cur["matchup"] = mu.group(0)
                    cur.update(team=None, team_code=None)
                    team_buf = ""
                team_txt = txt.get("team", "").strip()
                if team_txt:
                    combined = (team_buf + " " + team_txt).strip()
                    if cur["team_code"] and _norm(OFFICIAL_TEAMS[cur["team_code"]]).startswith(_norm(combined)) and team_buf:
                        team_buf = combined                       # continuation of a wrapped team name
                    else:
                        code = _team_for(team_txt, cur["matchup"])
                        team_buf = team_txt
                        if code:
                            cur.update(team=OFFICIAL_TEAMS[code], team_code=code)
                        else:
                            cur.update(team=None, team_code=None)
                            problems.append({"game_date": cur["game_date"], "matchup": cur["matchup"], "team_text": team_txt})
                if txt.get("category"):
                    txt["reason"] = (txt["category"] + (" - " + txt["reason"] if txt.get("reason") else "")).strip()
                rest = " ".join(txt.get(k, "") for k in ("player", "status", "reason", "previous"))
                if NOT_SUBMITTED in rest:
                    rows.append(dict(cur, player=None, status=NOT_SUBMITTED, reason="", previous_status=None))
                    continue
                st = txt.get("status", "").split()
                if st and st[0] in STATUSES and txt.get("player"):
                    prev = txt.get("previous", "").split()
                    rows.append(dict(cur, player=txt["player"], status=st[0], reason=txt.get("reason", ""),
                                     previous_status=prev[0] if prev and prev[0] in STATUSES else None))
                elif rows and txt.get("reason") and not txt.get("player") and not st and rows[-1]["player"]:
                    rows[-1]["reason"] = (rows[-1]["reason"] + " " + txt["reason"]).strip()
    if with_meta:
        return rows, {"unresolved_team_cells": problems}
    return rows


def team_abbr(team_text, names):
    key = _norm(team_text)
    for abbr, full in names.items():
        if _norm(full) == key or (abbr == "LAC" and key in ("laclippers", "losangelesclippers")):
            return abbr
    return None


def player_key(printed):
    """'Last, First' or 'OubreJr., Kelly' -> normalised 'firstlast' without suffixes."""
    last, _, first = (printed if isinstance(printed, str) else "").partition(",")
    last = re.sub(r"(Jr\.?|Sr\.?|II|III|IV)$", "", last.strip())
    return _norm(first + last)


def name_key(display):
    return _norm(re.sub(r"\b(Jr\.?|Sr\.?|II|III|IV)\b", "", display if isinstance(display, str) else ""))
