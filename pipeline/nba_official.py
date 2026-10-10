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


def parse(pdf_bytes):
    """-> list of dict(game_date, matchup, team, player, status, reason). Player is 'Last, First' as printed."""
    import pdfplumber
    rows = []
    cur = {"game_date": None, "matchup": None, "team": None}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as P:
        cols = None
        for page in P.pages:
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
            head = {w["text"]: w["x0"] for w in words if w["text"] in ("GameDate", "Game", "GameTime", "Matchup", "Team", "PlayerName",
                                                                       "Player", "CurrentStatus", "Current", "Reason")}
            if "Matchup" in head and "Reason" in head:
                cols = [("game_date", head.get("GameDate", head.get("Game", 0))), ("game_time", head.get("GameTime", 0)),
                        ("matchup", head["Matchup"]), ("team", head["Team"]), ("player", head.get("PlayerName", head.get("Player"))),
                        ("status", head.get("CurrentStatus", head.get("Current"))), ("reason", head["Reason"])]
                cols = sorted(cols, key=lambda c: c[1])
            if not cols:
                continue
            lines = {}
            for w in words:
                if w["text"].startswith(("Injury Report", "Page")) or re.match(r"Page\d+of\d+", w["text"]):
                    continue
                lines.setdefault(round(w["top"] / 3), []).append(w)
            for _, ws in sorted(lines.items()):
                cells = {}
                for w in sorted(ws, key=lambda w: w["x0"]):
                    name = cols[0][0]
                    for c, x in cols:
                        if w["x0"] >= x - 2:
                            name = c
                    cells.setdefault(name, []).append(w["text"])
                txt = {k: " ".join(v) for k, v in cells.items()}
                if "Matchup" in txt.get("matchup", "") or "Report:" in " ".join(txt.values()):
                    continue
                m = re.search(r"(\d\d/\d\d/\d{4})", " ".join(txt.values()))
                if m:
                    cur["game_date"] = dt.datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
                if re.match(r"[A-Z]{2,3}@[A-Z]{2,3}", txt.get("matchup", "")):
                    cur["matchup"] = txt["matchup"].split()[0]
                tm = txt.get("team", "")
                if re.fullmatch(r"[A-Z][A-Za-z0-9. ]+ [A-Z][A-Za-z0-9]+", tm) and "Page" not in tm and tm != "Team":
                    cur["team"] = txt["team"]
                st = txt.get("status", "").split()
                if st and st[0] in STATUSES and txt.get("player"):
                    rows.append(dict(cur, player=txt["player"], status=st[0], reason=txt.get("reason", "")))
                elif rows and txt.get("reason") and not txt.get("player"):
                    rows[-1]["reason"] = (rows[-1]["reason"] + " " + txt["reason"]).strip()
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
