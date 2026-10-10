"""Availability / news collection layer for NFL, NBA, NHL, NBL and AFL (collection and validation only).

Nothing here feeds a published projection. Every refresh appends what changed to the injury-monitor branch under
availability/ and rewrites the current picture, the source register and a validation report.

Three kinds of information are kept apart in every record (field `layer`):
  official  - league/club reports and transactions (participation status, designations, IR, line-ups)
  reported  - reporter/specialist expectations (return ranges, reassessment dates, restrictions, replacements),
              extracted by conservative rules; only the extracted fact, the headline and the link are stored,
              never article text
  projected - projections that are not confirmations (Daily Faceoff goalies/lines, NHL projected line-ups)
Model assumptions are not made here.

Record fields: league, team, player, player_key, player_id (source id), layer, kind, status, practice,
return_low / return_high (dates or rounds as printed, e.g. "R5"), return_text_class (weeks/season/test/tbc/...),
reassess_date, restriction, replacement, confirmation, affected_game, source, source_url, headline,
published_utc, first_seen_utc, collected_utc.
Return ranges and reassessment dates are separate fields; "Test" and "TBC" stay uncertain (no invented dates).

Access: the user chose to collect for private, non-commercial use, at low volume. robots.txt is honoured for every
URL, requests are spaced per host, nothing behind a login or block is attempted, and X/Twitter is not used.
A failed source marks its records stale ("information uncertain"), never "healthy".
Usage: python pipeline/avail_collect.py <store dir>   (store = injury-monitor worktree)
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

UA = "SportsFuturesPrivate/1.0 (personal non-commercial; low volume)"
NOW = dt.datetime.now(dt.timezone.utc)
SPACING_S = 1.5
MAX_ARTICLES_PER_SOURCE = 8
ARTICLE_MAX_AGE_DAYS = 10
LIST_MAX_AGE_DAYS = 120       # a full injury list stays the latest picture until a newer list replaces it (off-season)
LIST_URL = re.compile(r"medical-room|injury-list|injury-updates|injuries-list", re.I)

# ------------------------------------------------------------------ teams

NFL_TEAMS = {"Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
             "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
             "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
             "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
             "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
             "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
             "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
             "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS"}
NBA_TEAMS = {"Atlanta Hawks": "ATL", "Brooklyn Nets": "BKN", "Boston Celtics": "BOS", "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI",
             "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
             "Golden State Warriors": "GS", "Houston Rockets": "HOU", "Indiana Pacers": "IND", "LA Clippers": "LAC",
             "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
             "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NO", "New York Knicks": "NY",
             "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
             "Portland Trail Blazers": "POR", "San Antonio Spurs": "SA", "Sacramento Kings": "SAC", "Toronto Raptors": "TOR",
             "Utah Jazz": "UTAH", "Washington Wizards": "WSH"}
NHL_TEAMS = {"Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Calgary Flames": "CGY",
             "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ",
             "Dallas Stars": "DAL", "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA",
             "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL", "Montréal Canadiens": "MTL",
             "Nashville Predators": "NSH", "New Jersey Devils": "NJD", "New York Islanders": "NYI", "New York Rangers": "NYR",
             "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS",
             "Seattle Kraken": "SEA", "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
             "Utah Mammoth": "UTA", "Utah Hockey Club": "UTA", "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK",
             "Washington Capitals": "WSH", "Winnipeg Jets": "WPG"}
NBL_TEAMS = {"Adelaide 36ers": "ADL", "Brisbane Bullets": "BRI", "Cairns Taipans": "CNS", "Illawarra Hawks": "ILL",
             "Melbourne United": "MEL", "New Zealand Breakers": "NZL", "Perth Wildcats": "PER",
             "South East Melbourne Phoenix": "SEM", "Sydney Kings": "SYD", "Tasmania JackJumpers": "TAS"}
NBL_NICK = {"36ers": "ADL", "Bullets": "BRI", "Taipans": "CNS", "Hawks": "ILL", "United": "MEL", "Breakers": "NZL",
            "Wildcats": "PER", "Phoenix": "SEM", "Kings": "SYD", "JackJumpers": "TAS", "Jackjumpers": "TAS"}
AFL_TEAMS = {"Adelaide": "ADE", "Adelaide Crows": "ADE", "Brisbane Lions": "BRI", "Brisbane": "BRI", "Carlton": "CAR",
             "Collingwood": "COL", "Essendon": "ESS", "Fremantle": "FRE", "Geelong": "GEE", "Geelong Cats": "GEE", "Gold Coast": "GCS",
             "Gold Coast Suns": "GCS", "Greater Western Sydney": "GWS", "GWS Giants": "GWS", "GWS": "GWS", "Hawthorn": "HAW",
             "Melbourne": "MEL", "North Melbourne": "NTH", "Port Adelaide": "PTA", "Richmond": "RIC", "St Kilda": "STK",
             "Sydney": "SYD", "Sydney Swans": "SYD", "West Coast": "WCE", "West Coast Eagles": "WCE", "Western Bulldogs": "WBD"}
AFL_NICK = {"Crows": "ADE", "Lions": "BRI", "Blues": "CAR", "Magpies": "COL", "Bombers": "ESS", "Dockers": "FRE", "Cats": "GEE",
            "Suns": "GCS", "Giants": "GWS", "Hawks": "HAW", "Demons": "MEL", "Kangaroos": "NTH", "Power": "PTA", "Tigers": "RIC",
            "Saints": "STK", "Swans": "SYD", "Eagles": "WCE", "Bulldogs": "WBD"}
TEAMS = {"nfl": NFL_TEAMS, "nba": NBA_TEAMS, "nhl": NHL_TEAMS, "nbl": NBL_TEAMS, "afl": AFL_TEAMS}
NICKS = {"nbl": NBL_NICK, "afl": AFL_NICK}


def team_code(league, label):
    label = (label or "").strip()
    if not label:
        return None
    T = TEAMS[league]
    if label in T:
        return T[label]
    if label.upper() in set(T.values()):
        return label.upper()
    for full, code in T.items():
        if norm(full) == norm(label):
            return code
    for nick, code in NICKS.get(league, {}).items():
        if label == nick or label.endswith(" " + nick):
            return code
    if league in ("nfl", "nba", "nhl"):
        for full, code in T.items():
            if label.endswith(" " + full.split()[-1]) or label == full.split()[-1]:
                return code
    return None


def norm(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def player_key(name):
    name = re.sub(r"\b(Jr\.?|Sr\.?|II|III|IV)\b", "", name or "")
    if "," in name:
        last, _, first = name.partition(",")
        name = f"{first} {last}"
    return norm(name)


def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds") if t else None


def parse_time(s):
    """ISO strings, plus the short printed dates some sites put in JSON-LD ('Oct 10, 2026', '10 October 2026').
    A date without a time is taken as 00:00 UTC (marked by the caller as date-only precision where it matters)."""
    if not s:
        return None
    s = str(s).strip()
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        pass
    for f in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return dt.datetime.strptime(s, f).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ polite fetching

_robots, _last = {}, {}


class Blocked(Exception):
    pass


class NotExpected(Exception):
    """The source has nothing to publish right now (e.g. the NBA's official report outside the regular season)."""


def allowed(url):
    p = urllib.parse.urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    if root not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            with urllib.request.urlopen(urllib.request.Request(root + "/robots.txt", headers={"User-Agent": UA}), timeout=20) as r:
                rp.parse(r.read().decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            # RFC 9309: robots.txt unavailable (4xx) -> no restrictions; server error (5xx) -> assume full disallow
            rp.parse([] if 400 <= e.code < 500 else ["User-agent: *", "Disallow: /"])
        except Exception:  # noqa: BLE001
            rp.parse(["User-agent: *", "Disallow: /"])
        _robots[root] = rp
    return _robots[root].can_fetch(UA, url)


def fetch(url, binary=False, timeout=30):
    if not allowed(url):
        raise Blocked("robots.txt disallows " + url)
    host = urllib.parse.urlparse(url).netloc
    wait = SPACING_S - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"}), timeout=timeout) as r:
        body = r.read()
        meta = {"last_modified": r.headers.get("Last-Modified"), "status": r.status}
    return (body if binary else body.decode("utf-8", "replace")), meta


def fetch_json(url):
    body, meta = fetch(url)
    return json.loads(body), meta


# ------------------------------------------------------------------ HTML helpers (text only, nothing stored)

class Text(HTMLParser):
    """Blocks of visible text with their tag (h1-h4, p, li, td/th rows) and links; scripts and styles skipped."""
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "tr", "figcaption", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.cur, self.tag, self.skip, self.links, self.cells, self.in_cell = [], [], None, 0, [], [], False
        self.scripts = []
        self._script = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
            if tag == "script":
                self._script = (a.get("type") or "", a.get("id") or "", [])
            return
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in self.BLOCK:
            self.flush()
            self.tag = tag
            if tag == "tr":
                self.cells = []
        if tag in ("td", "th"):
            self.in_cell = True
            self.cells.append("")
        if tag == "br":
            self.cur.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
            if tag == "script" and self._script:
                self.scripts.append((self._script[0], self._script[1], "".join(self._script[2])))
                self._script = None
            return
        if tag in ("td", "th"):
            self.in_cell = False
        if tag in self.BLOCK:
            self.flush()

    def handle_data(self, d):
        if self.skip:
            if self._script is not None:
                self._script[2].append(d)
            return
        self.cur.append(d)
        if self.in_cell and self.cells:
            self.cells[-1] += d

    def flush(self):
        t = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        if t and self.tag:
            self.blocks.append({"tag": self.tag, "text": t, "cells": [re.sub(r"\s+", " ", c).strip() for c in self.cells] if self.tag == "tr" else None})
        self.cur = []
        self.tag = None


def page(html):
    p = Text()
    p.feed(html)
    p.flush()
    ld = []
    for typ, _id, body in p.scripts:
        if "ld+json" in typ:
            try:
                j = json.loads(body)
                ld.extend(j if isinstance(j, list) else j.get("@graph", [j]) if isinstance(j, dict) else [])
            except ValueError:
                pass
    nxt = None
    for typ, _id, body in p.scripts:
        if _id == "__NEXT_DATA__":
            try:
                nxt = json.loads(body)
            except ValueError:
                pass
    return p.blocks, p.links, ld, nxt


def article_meta(ld, html):
    """headline, published, modified from JSON-LD (NewsArticle/Article) or meta tags."""
    for x in ld:
        if isinstance(x, dict) and str(x.get("@type", "")).endswith("Article"):
            return x.get("headline"), parse_time(x.get("datePublished")), parse_time(x.get("dateModified"))
    pub = re.search(r'property="article:published_time" content="([^"]+)"', html)
    mod = re.search(r'property="article:modified_time" content="([^"]+)"', html)
    head = re.search(r'property="og:title" content="([^"]+)"', html)
    return (head.group(1) if head else None, parse_time(pub.group(1)) if pub else None, parse_time(mod.group(1)) if mod else None)


# ------------------------------------------------------------------ rule-based facts (reporter text)

NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
       "eleven": 11, "twelve": 12, "a": 1, "an": 1, "couple of": 2, "few": 3}
N_RE = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a|an|a couple of|a few)"


def _n(x):
    x = (x or "").lower().replace("a couple of", "couple of").replace("a few", "few")
    return int(x) if x.isdigit() else NUM.get(x)


RULES = [
    ("season", re.compile(r"\b(out for|miss|sidelined for|ruled out for|done for) (the )?(rest of the|remainder of the|entire|whole)? ?season\b|\bseason[- ]ending\b", re.I)),
    ("weeks", re.compile(r"\b(miss|out|sidelined|expected to miss|will miss|ruled out)\b[^.;]{0,40}?\b" + N_RE + r"(?:\s*(?:to|-|–|or)\s*" + N_RE + r")?\s+(weeks?|months?|games?|matches|rounds?)\b", re.I)),
    ("reassess", re.compile(r"\bre-?(?:evaluat|assess|examin)\w*\b[^.;]{0,30}?\b(?:in|after)\s+" + N_RE + r"\s+(days?|weeks?)\b", re.I)),
    ("day_to_day", re.compile(r"\bday[- ]to[- ]day\b", re.I)),
    ("week_to_week", re.compile(r"\bweek[- ]to[- ]week\b", re.I)),
    ("game_time", re.compile(r"\bgame[- ]time decision\b", re.I)),
    ("will_play", re.compile(r"\b(will|is expected to|expects to|set to|cleared to|plans to) (play|return|suit up|start|make (his|her) return)\b", re.I)),
    ("will_not_play", re.compile(r"\b(will not|won't|is not expected to|isn't expected to) (play|return|suit up|start)\b|(?<!was )(?<!were )\bruled out\b", re.I)),
    ("restriction", re.compile(r"\b(minutes restriction|minutes limit|minute restriction|limited minutes|snap count|pitch count|managed minutes|load management|managed\b|limited workload|restricted minutes)\b", re.I)),
    ("ir", re.compile(r"\b(placed on|moved to|landed on|going on) (injured reserve|IR|the injured list|long-term injured reserve|LTIR)\b", re.I)),
    ("activated", re.compile(r"\b(activated|designated to return|returned to practice|cleared)\b", re.I)),
    ("replacement", re.compile(r"\b(injury replacement|replacement player|signed .{0,30} as (a|an) (injury )?replacement|nominated replacement)\b", re.I)),
    ("test", re.compile(r"\b(?:is|remains|listed as|rated) (?:a |an )?(test|tbc|tba|indefinite|unknown)\b|^(test|tbc|tba|indefinite)$", re.I)),
    ("vfl_return", re.compile(r"\b(VFL|SANFL|WAFL|NBL1|AHL|G League)\b", re.I)),
]


def facts_from_text(text, published=None):
    """-> list of (kind, details) found in one sentence/short block. Dates are left relative unless explicit."""
    out = []
    for kind, rx in RULES:
        for m in rx.finditer(text):
            d = {}
            if kind == "weeks":
                lo, hi, unit = _n(m.group(2)), _n(m.group(3)) or _n(m.group(2)), m.group(4).lower().rstrip("s")
                if lo is None:
                    continue
                d = {"low": lo, "high": hi, "unit": unit}
                if published and unit in ("week", "month"):
                    days = 7 if unit == "week" else 30
                    d["return_low"] = (published + dt.timedelta(days=days * lo)).date().isoformat()
                    d["return_high"] = (published + dt.timedelta(days=days * hi)).date().isoformat()
            elif kind == "reassess":
                n, unit = _n(m.group(1)), m.group(2).lower()
                if n is None:
                    continue
                d = {"in": n, "unit": unit}
                if published:
                    d["reassess_date"] = (published + dt.timedelta(days=n * (7 if unit.startswith("week") else 1))).date().isoformat()
            elif kind == "test":
                d = {"value": (m.group(1) or m.group(2) or "").lower()}
            elif kind == "vfl_return":
                d = {"league": m.group(1)}
            out.append((kind, d))
            break
    if any(k == "vfl_return" for k, _ in out):       # returning through a lower league is not playing for the team
        out = [x for x in out if x[0] != "will_play"]
    return out


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text) if s.strip()]


class Names:
    """Known player names per league -> (canonical name, team); used to attribute reporter facts."""

    def __init__(self):
        self.by_league = {}

    def add(self, league, name, team=None, pid=None):
        if not name or len(name.split()) < 2:
            return
        self.by_league.setdefault(league, {})[player_key(name)] = (name, team, pid)

    def find(self, league, text):
        hits = []
        known = self.by_league.get(league, {})
        for m in re.finditer(r"\b([A-Z][a-zA-Z'\-\.]+(?:\s+(?:de|van|der|De|Van|Le|La|St\.?|Mc|O')?\s*[A-Z][a-zA-Z'\-\.]+){1,2})\b", text):
            k = player_key(m.group(1))
            if k in known:
                hits.append(known[k])
        return hits


# ------------------------------------------------------------------ records

def rec(league, layer, kind, source, source_url, **kw):
    r = dict(league=league, team=None, player=None, player_key=None, player_id=None, layer=layer, kind=kind, status=None,
             practice=None, injury=None, return_low=None, return_high=None, return_text_class=None, reassess_date=None,
             restriction=None, replacement=None, confirmation={"official": "official", "reported": "reported",
                                                               "projected": "projected"}[layer],
             affected_game=None, source=source, source_url=source_url, headline=None, published_utc=None,
             collected_utc=iso(NOW))
    r.update({k: v for k, v in kw.items() if v is not None})
    if r["player"] and not r["player_key"]:
        r["player_key"] = player_key(r["player"])
    return r


def apply_facts(r, facts):
    for kind, d in facts:
        if kind == "season":
            r["return_text_class"] = "season"
        elif kind == "weeks":
            r["return_text_class"] = f"{d['low']}-{d['high']} {d['unit']}s"
            r["return_low"], r["return_high"] = d.get("return_low"), d.get("return_high")
        elif kind == "reassess":
            r["reassess_date"] = d.get("reassess_date") or f"in {d['in']} {d['unit']}"
        elif kind in ("day_to_day", "week_to_week", "game_time"):
            r["return_text_class"] = r["return_text_class"] or kind
        elif kind == "will_play":
            r["status"] = r["status"] or "expected to play"
        elif kind == "will_not_play":
            r["status"] = r["status"] or "expected out"
        elif kind == "restriction":
            r["restriction"] = "workload restriction reported"
        elif kind == "ir":
            r["status"] = r["status"] or "injured reserve / list (reported)"
        elif kind == "activated":
            r["status"] = r["status"] or "activated/cleared (reported)"
        elif kind == "replacement":
            r["replacement"] = "replacement signing reported"
        elif kind == "test":
            r["return_text_class"] = d["value"]
        elif kind == "vfl_return":
            r["restriction"] = (r["restriction"] or "") + f" returning via {d['league']} (not the top team)"
    return r


# ------------------------------------------------------------------ collectors

class Run:
    def __init__(self, store):
        self.store = store
        self.records = {lg: [] for lg in TEAMS}
        self.status = []          # per source attempt
        self.names = Names()
        self.seen = _read(os.path.join(store, "availability", "seen_articles.json"), {})
        self.season = {}          # league -> {"state": in_season/off_season/unknown, "why": ...}

    def source(self, league, name, kind, url, fn, primary=True, team_scope="all"):
        t0 = time.time()
        try:
            n = fn()
            self.status.append(dict(league=league, source=name, kind=kind, url=url, primary=primary, team_scope=team_scope,
                                    ok=True, records=n, seconds=round(time.time() - t0, 1), checked_utc=iso(NOW)))
        except NotExpected as e:
            self.status.append(dict(league=league, source=name, kind=kind, url=url, primary=primary, team_scope=team_scope,
                                    ok=True, records=0, note="not expected: " + str(e)[:160], seconds=round(time.time() - t0, 1),
                                    checked_utc=iso(NOW)))
        except Blocked as e:
            self.status.append(dict(league=league, source=name, kind=kind, url=url, primary=primary, team_scope=team_scope,
                                    ok=False, error="blocked by robots.txt: not collected", checked_utc=iso(NOW)))
            print("blocked", name, e, flush=True)
        except Exception as e:  # noqa: BLE001
            self.status.append(dict(league=league, source=name, kind=kind, url=url, primary=primary, team_scope=team_scope,
                                    ok=False, error=f"{type(e).__name__}: {str(e)[:160]}", checked_utc=iso(NOW)))
            print("failed", name, type(e).__name__, str(e)[:160], flush=True)

    def add(self, r):
        self.records[r["league"]].append(r)

    # ---------- ESPN structured feeds (NFL, NBA, NHL)
    def espn_injuries(self, league, path):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/injuries"

        def go():
            j, _ = fetch_json(url)
            n = 0
            for t in j.get("injuries") or []:
                team = team_code(league, t.get("displayName"))
                for i in t.get("injuries") or []:
                    a = i.get("athlete") or {}
                    href = " ".join(l.get("href", "") for l in a.get("links") or [])
                    m = re.search(r"/id/(\d+)", href)
                    det = i.get("details") or {}
                    name = a.get("displayName")
                    self.names.add(league, name, team, m.group(1) if m else None)
                    r = rec(league, "official", "injury_status", "ESPN injuries feed", url, team=team, player=name,
                            player_id=("espn:" + m.group(1)) if m else None, status=i.get("status"),
                            injury=" ".join(x for x in (det.get("side"), det.get("type"), det.get("detail")) if x and x != "Not Specified") or None,
                            published_utc=iso(parse_time(i.get("date"))))
                    r["confirmation"] = "aggregated (ESPN, from team/league reports)"
                    if det.get("returnDate"):
                        r["return_low"] = r["return_high"] = str(det["returnDate"])[:10]
                        r["return_text_class"] = "ESPN estimated return date"
                    self.add(r)
                    n += 1
                    # ESPN's own comment: reporter-style context -> facts only, never the text. Notes on players listed
                    # Active describe the past (how they came back), so they are skipped.
                    for c in ((i.get("shortComment"), i.get("longComment")) if (i.get("status") or "").lower() != "active" else ()):
                        if not c:
                            continue
                        f = [x for s in sentences(c) for x in facts_from_text(s, parse_time(i.get("date")))]
                        if f:
                            rr = rec(league, "reported", "context", "ESPN injury note", url, team=team, player=name,
                                     player_id=r["player_id"], published_utc=r["published_utc"])
                            self.add(apply_facts(rr, f))
                            break
            return n
        self.source(league, "ESPN injuries feed", "structured", url, go)

    def espn_transactions(self, league, path):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/transactions"

        def go():
            j, _ = fetch_json(url)
            n = 0
            for t in j.get("transactions") or []:
                d = t.get("description") or ""
                when = parse_time(t.get("date"))
                if when and (NOW - when).days > 21:
                    continue
                team = team_code(league, (t.get("team") or {}).get("displayName") or (t.get("team") or {}).get("abbreviation"))
                kind = ("injured_list" if re.search(r"injured reserve|injured list|\bIR\b|LTIR", d, re.I) else
                        "activation" if re.search(r"activated|reinstated|designated .* to return", d, re.I) else
                        "signing" if re.search(r"\bsigned\b|\bsigns\b|claimed", d, re.I) else
                        "release" if re.search(r"waived|released|placed on waivers", d, re.I) else
                        "assignment" if re.search(r"assigned|recalled|sent", d, re.I) else "other")
                pl = re.search(r"(?:[A-Z]{1,3}\s)?([A-Z][a-zA-Z'\.\-]+(?:\s[A-Z][a-zA-Z'\.\-]+){1,2})", d)
                self.add(rec(league, "official", "transaction:" + kind, "ESPN transactions feed", url, team=team,
                             player=pl.group(1) if pl else None, published_utc=iso(when),
                             digest=hashlib.sha1(d.encode()).hexdigest()[:12]))
                n += 1
            return n
        self.source(league, "ESPN transactions feed", "structured", url, go)

    def espn_news(self, league, path):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/news?limit=50"

        def go():
            j, _ = fetch_json(url)
            n = 0
            for a in j.get("articles") or []:
                pub = parse_time(a.get("published"))
                if not pub or (NOW - pub).days > ARTICLE_MAX_AGE_DAYS:
                    continue
                text = " ".join(x for x in (a.get("headline"), a.get("description")) if x)
                ath = [c for c in a.get("categories") or [] if c.get("type") == "athlete"]
                link = ((a.get("links") or {}).get("web") or {}).get("href")
                f = [x for s in sentences(text) for x in facts_from_text(s, pub)]
                if not f or not ath:
                    continue
                if len(ath) > 1:
                    continue        # several players named: attribution ambiguous, skip
                c = ath[0]
                r = rec(league, "reported", "context", "ESPN news", link or url, player=c.get("description"),
                        player_id=f"espn:{c.get('athleteId') or (c.get('athlete') or {}).get('id')}",
                        headline=a.get("headline"), published_utc=iso(pub))
                self.add(apply_facts(r, f))
                self._seen(link, pub)
                n += 1
            return n
        self.source(league, "ESPN news (headline + summary)", "context", url, go)

    def _seen(self, url, pub):
        if url and url not in self.seen:
            self.seen[url] = {"first_seen_utc": iso(NOW), "published_utc": iso(pub)}

    # ---------- NFL
    def nfl_official(self):
        path = os.path.join(self.store, "state.json")
        url = "https://www.nfl.com/injuries/"

        def go():
            st = _read(path, {})
            rep = _read(os.path.join(self.store, st.get("report_file", "")), None) if st.get("report_file") else None
            if not rep:
                raise RuntimeError("no NFL official report collected yet")
            obs = parse_time(rep.get("observed_at"))
            n = 0
            for r in rep.get("rows", []):
                self.names.add("nfl", r.get("player"), r.get("team"))
                self.add(rec("nfl", "official", "injury_report", "NFL official injury report (nfl.com)", url, team=r.get("team"),
                             player=r.get("player"), player_id="nfl:" + str(r.get("player_id")), status=r.get("game_status") or "no designation",
                             practice=r.get("practice_status"), injury=r.get("injury"), published_utc=iso(obs),
                             affected_game=f"{rep.get('season')} week {rep.get('week')}"))
                n += 1
            if obs and (NOW - obs).total_seconds() > 36 * 3600:
                raise RuntimeError(f"NFL official report is {round((NOW - obs).total_seconds() / 3600)} h old")
            return n
        self.source("nfl", "NFL official injury report (nfl.com, via injury monitor)", "official", url, go)

    def nflverse_injuries(self):
        season = NOW.year if NOW.month >= 3 else NOW.year - 1
        url = f"https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"

        def go():
            import csv
            import io
            body, meta = fetch(url)   # github release asset (openly distributed); robots is for crawlers of github.com pages
            rows = list(csv.DictReader(io.StringIO(body)))
            wk = max((int(r["week"]) for r in rows if r.get("week", "").isdigit()), default=None)
            n = 0
            for r in rows:
                if not r.get("week", "").isdigit() or int(r["week"]) != wk:
                    continue
                self.add(rec("nfl", "official", "injury_report", "nflverse injuries (official reports)", url, team=team_code("nfl", r["team"]) or r["team"],
                             player=r.get("full_name"), player_id="gsis:" + r.get("gsis_id", ""), status=r.get("report_status") or "no designation",
                             practice=r.get("practice_status"), injury=r.get("report_primary_injury") or None,
                             published_utc=iso(parse_time(r.get("date_modified"))), affected_game=f"{season} week {wk}"))
                n += 1
            return n
        global allowed
        orig = allowed
        allowed = lambda u: True if u.startswith("https://github.com/nflverse/") else orig(u)   # noqa: E731
        try:
            self.source("nfl", "nflverse injuries (official reports, CC-BY)", "official", url, go, primary=False)
        finally:
            allowed = orig

    def nfl_reporters(self):
        for name, url in (("Ian Rapoport (NFL Network)", "https://www.nfl.com/author/ian-rapoport-talent"),
                          ("Tom Pelissero (NFL Network)", "https://www.nfl.com/author/tom-pelissero-0ap3000000820340")):
            self.source("nfl", name, "context", url, lambda u=url, nm=name: self.articles("nfl", nm, u, r"/news/[a-z0-9\-]+"))

    # ---------- generic article lists (author pages, news categories)
    def articles(self, league, source_name, index_url, pattern, max_n=MAX_ARTICLES_PER_SOURCE):
        html, _ = fetch(index_url)
        _, links, _, _ = page(html)
        base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(index_url))
        seen_here, urls = set(), []
        for l in links:
            l = urllib.parse.urljoin(base, l.split("#")[0])
            if re.search(pattern, urllib.parse.urlparse(l).path) and l not in seen_here and l != index_url:
                seen_here.add(l)
                urls.append(l)
        lists = [u for u in urls if LIST_URL.search(u)]
        urls = [u for u in urls if u not in lists[1:]]      # only the newest full injury list; older lists are superseded
        n = 0
        for u in urls[:max_n]:
            n += self.article(league, source_name, u)
        return n

    def article(self, league, source_name, url):
        """Fetch once while the article is unchanged; later runs re-use the extracted facts (no re-download)."""
        e = self.seen.get(url)
        if e and e.get("parsed") and "records" in e:
            pub = parse_time(e.get("modified_utc") or e.get("published_utc"))
            if pub and (NOW - pub).days > (LIST_MAX_AGE_DAYS if LIST_URL.search(url) else ARTICLE_MAX_AGE_DAYS):
                return 0
            for r in e["records"]:
                self.add(dict(r, collected_utc=iso(NOW)))
            return len(e["records"])
        before = len(self.records[league])
        n = self._article(league, source_name, url)
        self.seen[url]["records"] = self.records[league][before:]
        return n

    def _article(self, league, source_name, url):
        html, _ = fetch(url)
        blocks, _, ld, _ = page(html)
        head, pub, mod = article_meta(ld, html)
        self.seen[url] = {"first_seen_utc": self.seen.get(url, {}).get("first_seen_utc", iso(NOW)), "published_utc": iso(pub),
                          "modified_utc": iso(mod), "parsed": True, "headline": head}
        if not pub and not mod:
            self.seen[url]["skipped"] = "no publication time: facts not usable"
            return 0
        max_age = LIST_MAX_AGE_DAYS if LIST_URL.search(url) else ARTICLE_MAX_AGE_DAYS
        if pub and (NOW - pub).days > max_age and not (mod and (NOW - mod).days <= max_age):
            return 0
        when = mod or pub
        game = None
        m = re.search(r"game-preview-([a-z]+)-(\d{1,2})-(\d{4})", url)
        if m:   # NHL previews: verify the game date; an old preview is not today's line-up
            try:
                gd = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
            except ValueError:
                gd = None
            if gd and gd < (NOW - dt.timedelta(hours=30)).date():
                self.seen[url]["skipped"] = f"preview for a past game ({gd})"
                return 0
            game = str(gd) if gd else None
        n = 0
        cur_team = None
        for b in blocks:
            if b["tag"] in ("h2", "h3", "h4"):
                cur_team = team_code(league, b["text"]) or cur_team
            if b["tag"] == "tr" and b["cells"] and len(b["cells"]) >= 2:
                n += self._table_row(league, source_name, url, head, when, b["cells"], cur_team)
                continue
            for s in sentences(b["text"]):
                f = facts_from_text(s, when)
                if not f:
                    continue
                who = self.names.find(league, s)
                if len(who) != 1:
                    who = self._name_from_line(league, s) if b["tag"] in ("li", "h3", "h4", "p") else []
                if len(who) != 1 and league in ("nbl", "afl"):
                    who = self._single_candidate(league, s)
                if len(who) != 1:
                    continue
                name, team, pid = who[0]
                r = rec(league, "reported", "context", source_name, url, team=team or cur_team, player=name, player_id=pid,
                        headline=head, published_utc=iso(when), affected_game=game)
                self.add(apply_facts(r, f))
                n += 1
        return n

    def _name_from_line(self, league, s):
        """List entries like 'Player Name (Club) - hamstring - 2-3 weeks': the leading name is the subject."""
        m = re.match(r"^([A-Z][a-zA-Z'\-]+(?:\s[A-Z][a-zA-Z'\-]+){1,2})\s*(?:\(([^)]+)\))?\s*[:\-–—,]", s)
        if not m:
            return []
        return [(m.group(1), team_code(league, m.group(2)) if m.group(2) else None, None)]

    STOP = set("The A An He She They His Her It This That Round Rounds Week Weeks Coach Head Kings Club Team NBL AFL VFL "
               "Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August "
               "September October November December Medical Room In Mix Grand Final Opening".split())

    def _single_candidate(self, league, s):
        """Exactly one person-like name (two or three capitalised words, not a club/team/calendar word) in the sentence."""
        team_words = {w for t in list(TEAMS[league]) + list(NICKS.get(league, {})) for w in t.split()}
        cands = set()
        for m in re.finditer(r"\b([A-Z][a-z'\-]+(?:\s[A-Z][a-zA-Z'\-]+){1,2})\b", s):
            words = m.group(1).split()
            if any(w in self.STOP or w in team_words for w in words):
                continue
            cands.add(m.group(1))
        return [(c, None, None) for c in cands] if len(cands) == 1 else []

    def _table_row(self, league, source_name, url, head, when, cells, cur_team):
        """Injury-list tables: Player | Injury | Estimated return (AFL Medical Room and similar)."""
        if not re.match(r"^[A-Z][a-zA-Z'\-]+(?:\s[A-Z][a-zA-Z'\-]+){1,2}$", cells[0] or ""):
            return 0
        if norm(cells[0]) in ("player", "name"):
            return 0
        est = cells[-1].strip()
        r = rec(league, "reported", "injury_list", source_name, url, team=cur_team, player=cells[0],
                injury=cells[1] if len(cells) > 2 else None, headline=head, published_utc=iso(when))
        e = est.lower()
        if e in ("test", "tbc", "tba", "indefinite", "season", "unknown"):
            r["return_text_class"] = e
        elif re.fullmatch(r"(\d+)(?:\s*[-–]\s*(\d+))?\s*(weeks?|rounds?|games?|matches|months?)", e):
            m = re.fullmatch(r"(\d+)(?:\s*[-–]\s*(\d+))?\s*(weeks?|rounds?|games?|matches|months?)", e)
            r["return_text_class"] = f"{m.group(1)}-{m.group(2) or m.group(1)} {m.group(3)}"
            if when and m.group(3).startswith(("week", "month")):
                k = 7 if m.group(3).startswith("week") else 30
                r["return_low"] = (when + dt.timedelta(days=k * int(m.group(1)))).date().isoformat()
                r["return_high"] = (when + dt.timedelta(days=k * int(m.group(2) or m.group(1)))).date().isoformat()
        elif re.fullmatch(r"(round|rd|r)\s*(\d+)", e):
            r["return_low"] = r["return_high"] = "R" + re.fullmatch(r"(round|rd|r)\s*(\d+)", e).group(2)
            r["return_text_class"] = "round"
        else:
            r["return_text_class"] = "other (as printed: " + est[:20] + ")"
        self.add(r)
        return 1

    # ---------- season state (is coverage expected right now?)
    def season_states(self):
        """in_season when a competitive game (regular season or finals) is within the last 7 / next 10 days."""
        today = NOW.date()
        lo, hi = today - dt.timedelta(days=7), today + dt.timedelta(days=10)
        for lg, path in (("nfl", "football/nfl"), ("nba", "basketball/nba"), ("nhl", "hockey/nhl")):
            try:
                base_u = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
                try:
                    events = fetch_json(f"{base_u}?dates={lo:%Y%m%d}-{hi:%Y%m%d}")[0].get("events") or []
                except urllib.error.HTTPError:
                    events = []      # range not accepted: fall back to a few single days around today
                    for k in (-1, 0, 1, 2, 3):
                        events += fetch_json(f"{base_u}?dates={today + dt.timedelta(days=k):%Y%m%d}")[0].get("events") or []
                types = [((e.get("season") or {}).get("type")) for e in events]
                comp = [t for t in types if t in (2, 3)]
                self.season[lg] = {"state": "in_season" if comp else "off_season",
                                   "why": f"{len(comp)} regular-season/playoff and {len(types) - len(comp)} other games {lo}..{hi}"}
            except Exception as e:  # noqa: BLE001
                self.season[lg] = {"state": "unknown", "why": f"{type(e).__name__}: {str(e)[:80]}"}
        try:
            req = urllib.request.Request(f"https://api.squiggle.com.au/?q=games;year={today.year}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                games = json.load(r).get("games") or []
            near = [g for g in games if lo.isoformat() <= str(g.get("date") or "")[:10] <= hi.isoformat()]
            self.season["afl"] = {"state": "in_season" if near else "off_season",
                                  "why": f"{len(near)} AFL games {lo}..{hi} (Squiggle fixture)"}
        except Exception as e:  # noqa: BLE001
            self.season["afl"] = {"state": "unknown", "why": f"{type(e).__name__}: {str(e)[:80]}"}
        try:
            import nbl as NB
            seasons = NB._data(NB._get("nbl/seasons", "seasons.json", 24)[0])
            yr = max(int(x["year"]) for x in seasons if isinstance(x, dict) and str(x.get("year", "")).isdigit())
            n = 0
            for stype in ("regular", "finals"):
                try:
                    payload = NB._get(f"nbl/matches/in/season/{yr}/{stype}?limit=500&offset=0", f"avail_{yr}_{stype}_games.json", 6)[0]
                except Exception:  # noqa: BLE001
                    continue
                for g in NB._data(payload):
                    d = str(g.get("match_time_utc") or g.get("date") or g.get("start_time") or g.get("utc_start_time") or "")[:10] if isinstance(g, dict) else ""
                    n += lo.isoformat() <= d <= hi.isoformat()
            self.season["nbl"] = {"state": "in_season" if n else "off_season", "why": f"{n} NBL games {lo}..{hi} (NBL fixture, season {yr})"}
        except Exception as e:  # noqa: BLE001
            self.season["nbl"] = {"state": "unknown", "why": f"{type(e).__name__}: {str(e)[:80]}"}

    # ---------- NBA official PDF
    def nba_official(self):
        def go():
            import nba_official as O
            u, b, t_et = O.latest(hours_back=30)
            if not b:
                st = self.season.get("nba", {})
                if st.get("state") == "off_season":
                    raise NotExpected("no regular-season or playoff games in the window (" + st.get("why", "") + ")")
                raise RuntimeError("no official report found in the last 30 hours")
            rows = O.parse(b)
            for r in rows:
                self.add(rec("nba", "official", "injury_report", "NBA official injury report (PDF)", u,
                             team=team_code("nba", r.get("team")), player=O.player_key(r["player"]) and _display(r["player"]),
                             status=r["status"], injury=r.get("reason"), published_utc=iso(t_et),
                             affected_game=f"{r.get('game_date')} {r.get('matchup')}"))
            return len(rows)
        self.source("nba", "NBA official injury report (PDF, file-name time)", "official", "https://ak-static.cms.nba.com/referee/injury/", go)

    # ---------- NHL
    def dfo_goalies(self):
        url = "https://www.dailyfaceoff.com/starting-goalies"

        def go():
            html, _ = fetch(url)
            _, _, _, nxt = page(html)
            if not nxt:
                raise RuntimeError("no __NEXT_DATA__ on page (layout changed?)")
            n = 0
            for g in _walk_dicts(nxt):
                keys = set(g)
                for side in ("home", "away"):
                    name = g.get(f"{side}GoalieName")
                    if not name:
                        continue
                    team = team_code("nhl", g.get(f"{side}TeamName") or "")
                    status = g.get(f"{side}NewsStrengthName") or g.get(f"{side}GoalieStatus")
                    date = g.get("date") or g.get("gameDate") or g.get("dateGmt")
                    r = rec("nhl", "projected", "starting_goalie", "Daily Faceoff starting goalies", url, team=team, player=name,
                            status=f"projected starter ({status or 'unconfirmed'})", affected_game=str(date)[:10] if date else None,
                            published_utc=iso(parse_time(g.get(f"{side}NewsCreatedAt") or g.get("updatedAt"))))
                    r["confirmation"] = "confirmed (per Daily Faceoff)" if status and "confirm" in status.lower() else "projected / unconfirmed"
                    if date and str(date)[:10] < (NOW - dt.timedelta(hours=12)).date().isoformat():
                        r["stale_date"] = True
                    self.add(r)
                    n += 1
                if keys & {"homeGoalieName", "awayGoalieName"}:
                    continue
            if n == 0:
                raise RuntimeError("starting-goalie entries not found (layout changed?)")
            return n
        self.source("nhl", "Daily Faceoff starting goalies", "projected", url, go)

    def nhl_projected(self):
        url = "https://www.nhl.com/news/topic/game-previews/nhl-projected-lineup-projections"
        self.source("nhl", "NHL.com game previews (projected lineups, status report)", "projected", url,
                    lambda: self.articles("nhl", "NHL.com game previews", url, r"/news/.*game-preview", max_n=10))

    def dfo_lines(self):
        """Projected line combinations for all 32 teams (forward lines, defence pairs, power play, goalies, injuries).
        Fetched once a day; other runs carry the last result forward."""
        meta = self.seen.get("__dfo_lines__", {})
        last = parse_time(meta.get("fetched_utc"))
        url = "https://www.dailyfaceoff.com/teams/{}/line-combinations"

        def go():
            if last and (NOW - last).total_seconds() < 20 * 3600 and meta.get("records"):
                for r in meta["records"]:
                    self.add(dict(r, collected_utc=iso(NOW)))
                return len(meta["records"])
            recs = []
            for full, code in sorted(set((k, v) for k, v in NHL_TEAMS.items() if k not in ("Montréal Canadiens", "Utah Hockey Club"))):
                slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", full).encode("ascii", "ignore").decode().lower()).strip("-")
                try:
                    html, _ = fetch(url.format(slug))
                except Exception as e:  # noqa: BLE001
                    print("dfo lines", slug, e, flush=True)
                    continue
                _, _, _, nxt = page(html)
                c = (((nxt or {}).get("props") or {}).get("pageProps") or {}).get("combinations") or {}
                upd = parse_time(c.get("updatedAt"))
                for pl in c.get("players") or []:
                    r = rec("nhl", "projected", "line_combination", "Daily Faceoff line combinations", url.format(slug), team=code,
                            player=pl.get("name"), status=f"{pl.get('groupName') or ''}: {pl.get('positionName') or ''}".strip(": "),
                            injury={"ir": "injured reserve", "out": "out", "dtd": "day-to-day"}.get(pl.get("injuryStatus")),
                            published_utc=iso(upd))
                    r["confirmation"] = "projected (Daily Faceoff" + (f", source: {c.get('sourceName')}" if c.get("sourceName") else "") + ")"
                    if pl.get("gameTimeDecision"):
                        r["return_text_class"] = "game_time"
                    recs.append(r)
                    self.add(r)
            if not recs:
                raise RuntimeError("no line combinations parsed")
            self.seen["__dfo_lines__"] = {"fetched_utc": iso(NOW), "records": recs}
            return len(recs)
        self.source("nhl", "Daily Faceoff line combinations (32 teams, daily)", "projected", url.format("{team}"), go)

    # ---------- NBL
    def nbl(self):
        cat = "https://www.nbl.com.au/news-categories/injury"

        def go():
            html, _ = fetch(cat)
            _, links, _, _ = page(html)
            urls = []
            for l in links:
                l = urllib.parse.urljoin("https://www.nbl.com.au", l.split("#")[0])
                if "/news/" in l and l not in urls:
                    urls.append(l)
            # the latest injury list: prefer a link whose slug says injury-updates/injury-list; season label may lag
            lists = [u for u in urls if re.search(r"injur(y|ies)-(updates|list)", u)]
            n = 0
            for u in (lists[:1] + [u for u in urls if u not in lists][:MAX_ARTICLES_PER_SOURCE]):
                n += self.article("nbl", "NBL.com.au injury coverage", u)
            return n
        self.source("nbl", "NBL.com.au injury coverage + latest injury list", "official", cat, go)

    # ---------- AFL
    def afl(self):
        cat = "https://www.afl.com.au/news/injury-news?page=1"
        self.source("afl", "AFL.com.au injury news (Medical Room, In the Mix)", "context", cat,
                    lambda: self.articles("afl", "AFL.com.au injury news", cat, r"/news/\d+/", max_n=MAX_ARTICLES_PER_SOURCE))


def _display(printed):
    last, _, first = (printed or "").partition(",")
    return f"{first.strip()} {last.strip()}".strip() if first else printed


def _walk_dicts(j):
    if isinstance(j, dict):
        yield j
        for v in j.values():
            yield from _walk_dicts(v)
    elif isinstance(j, list):
        for v in j:
            yield from _walk_dicts(v)


def _read(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ archive, register, validation

KEY_FIELDS = ("status", "practice", "injury", "return_low", "return_high", "return_text_class", "reassess_date", "restriction",
              "replacement", "affected_game", "confirmation")


def rkey(r):
    parts = [r["league"], r["source"], r["layer"], r["kind"], r.get("team"), r.get("player_id") or r.get("player_key"), r.get("digest")]
    if r["layer"] != "official":
        parts.append(r.get("source_url"))
    return "|".join(str(x or "") for x in parts)


def archive(run):
    root = os.path.join(run.store, "availability")
    os.makedirs(root, exist_ok=True)
    ok_sources = {(s["league"], s["source"]) for s in run.status if s["ok"]}
    summary = {}
    for lg, recs in run.records.items():
        d = os.path.join(root, lg)
        os.makedirs(d, exist_ok=True)
        prev = {rkey(r): r for r in _read(os.path.join(d, "latest.json"), {"records": []})["records"]}
        cur, changes = {}, []
        for r in recs:
            k = rkey(r)
            p = prev.get(k)
            r["first_seen_utc"] = p.get("first_seen_utc") if p else iso(NOW)
            if not p or any(p.get(f) != r.get(f) for f in KEY_FIELDS):
                changes.append(dict(r, change="new" if not p else "changed",
                                    before={f: p.get(f) for f in KEY_FIELDS if p.get(f) != r.get(f)} if p else None))
            cur[k] = r
        # sources that failed this run: keep their last records, flagged stale (information uncertain, not healthy)
        for k, p in prev.items():
            if k in cur:
                continue
            if (lg, p["source"]) not in ok_sources:
                cur[k] = dict(p, stale=True)
            else:
                changes.append(dict(p, change="removed", collected_utc=iso(NOW)))
        with open(os.path.join(d, "latest.json"), "w") as f:
            json.dump({"collected_utc": iso(NOW), "records": list(cur.values())}, f, indent=0)
        if changes:
            with open(os.path.join(d, "changes.jsonl"), "a") as f:
                for c in changes:
                    f.write(json.dumps(c) + "\n")
        summary[lg] = {"records": len(cur), "changes": len(changes), "stale": sum(1 for r in cur.values() if r.get("stale"))}
    with open(os.path.join(root, "seen_articles.json"), "w") as f:
        json.dump(dict(sorted(run.seen.items(), key=lambda kv: kv[1].get("first_seen_utc") or "")[-3000:]), f, indent=0)
    return summary


SOURCE_PLAN = {   # documented primary/fallback per league; club sites are not automated (listed for manual use)
    "nfl": {"primary": ["NFL official injury report (nfl.com)"], "fallback": ["nflverse injuries (official reports)", "ESPN injuries feed"],
            "transactions": ["ESPN transactions feed"], "context": ["Ian Rapoport", "Tom Pelissero", "ESPN news"],
            "manual": "club injury reports, game-day inactives (club sites/X are not automated)"},
    "nba": {"primary": ["NBA official injury report (PDF)"], "fallback": ["ESPN injuries feed"],
            "transactions": ["ESPN transactions feed"], "context": ["ESPN news (incl. Shams Charania stories)", "ESPN injury notes"],
            "manual": "team announcements, coach press conferences, beat reporters"},
    "nhl": {"primary": ["ESPN injuries feed (aggregated from club announcements)"], "fallback": [],
            "transactions": ["ESPN transactions feed"], "projected": ["Daily Faceoff starting goalies", "NHL.com projected lineups"],
            "context": ["ESPN news"], "manual": "club announcements, Daily Faceoff line combinations per team"},
    "nbl": {"primary": ["NBL.com.au injury coverage + latest injury list"], "fallback": [],
            "context": ["NBL.com.au reporting (Chris Pike, Dan Woods)"], "manual": "club announcements, ESPN (Olgun Uluc)"},
    "afl": {"primary": ["AFL.com.au injury news (Medical Room)"], "fallback": [],
            "context": ["AFL.com.au In the Mix"], "manual": "club medical updates, official team line-ups and late changes (page is script-rendered)"},
}


def register(run):
    path = os.path.join(run.store, "availability", "sources.json")
    reg = _read(path, {"sources": {}})
    for s in run.status:
        k = f"{s['league']}|{s['source']}"
        e = reg["sources"].setdefault(k, {"league": s["league"], "source": s["source"], "kind": s["kind"], "url": s["url"],
                                          "primary": s.get("primary", True), "team_scope": s.get("team_scope", "all"),
                                          "method": "JSON feed" if "api" in s["url"] or s["url"].endswith((".csv", "/injuries", "/transactions")) else "HTML page",
                                          "successes": 0, "failures": 0, "consecutive_failures": 0})
        e["last_checked_utc"] = s["checked_utc"]
        if s["ok"]:
            e["successes"] += 1
            e["consecutive_failures"] = 0
            e["last_ok_utc"] = s["checked_utc"]
            e["last_records"] = s.get("records")
            e["last_note"] = s.get("note")
        else:
            e["failures"] += 1
            e["consecutive_failures"] += 1
            e["last_error"] = s.get("error")
            e["last_fail_utc"] = s["checked_utc"]
        lo = parse_time(e.get("last_ok_utc"))
        e["freshness_hours"] = round((NOW - lo).total_seconds() / 3600, 1) if lo else None
    reg["teams"] = {lg: sorted(set(T.values())) for lg, T in TEAMS.items()}
    reg["plan"] = SOURCE_PLAN
    reg["updated_utc"] = iso(NOW)
    with open(path, "w") as f:
        json.dump(reg, f, indent=1)
    return reg


def validate(run):
    out = {"checked_utc": iso(NOW), "leagues": {}}
    for lg, recs in run.records.items():
        T = set(TEAMS[lg].values())
        v = {"records": len(recs), "by_layer": {}, "unknown_team": 0, "no_player": 0, "future_published": 0,
             "teams_covered_official": sorted({r["team"] for r in recs if r["layer"] == "official" and r["team"] in T}),
             "conflicts": [], "stale_projection_dates": 0}
        for r in recs:
            v["by_layer"][r["layer"]] = v["by_layer"].get(r["layer"], 0) + 1
            if r["team"] and r["team"] not in T:
                v["unknown_team"] += 1
            if not r["player"] and not r["kind"].startswith("transaction"):
                v["no_player"] += 1
            p = parse_time(r.get("published_utc"))
            if p and p > NOW + dt.timedelta(minutes=10):
                v["future_published"] += 1
            if r.get("stale_date"):
                v["stale_projection_dates"] += 1
        v["teams_missing_official"] = sorted(T - set(v["teams_covered_official"]))
        v["season_state"] = run.season.get(lg, {"state": "unknown"})
        v["coverage_expected"] = v["season_state"].get("state") != "off_season"
        if not v["coverage_expected"]:
            v["teams_missing_official_note"] = "off-season: no official coverage expected"
        # conflicts: official Out vs reported "expected to play" (or the reverse) for the same player
        off = {}
        for r in recs:
            if r["layer"] == "official" and r["player_key"]:
                off.setdefault(r["player_key"], set()).add((r["status"] or "").lower())
        for r in recs:
            if r["layer"] != "official" and r["player_key"] in off:
                st = off[r["player_key"]]
                if (r.get("status") == "expected to play" and "out" in st) or (r.get("status") == "expected out" and st & {"active", "available", "probable"}):
                    v["conflicts"].append({"player": r["player"], "official": sorted(st), "other": r["status"], "source": r["source"]})
        by_head = {}
        for r in recs:
            if r.get("headline"):
                by_head.setdefault(norm(r["headline"])[:60], set()).add(r["source_url"])
        v["syndicated_headlines"] = sum(1 for u in by_head.values() if len(u) > 1)   # same story on several URLs: not independent
        # matching: reported facts attributed to players present in official/structured lists
        rep = [r for r in recs if r["layer"] == "reported"]
        known = {r["player_key"] for r in recs if r["layer"] == "official"}
        v["reported_matched_to_official_list"] = f"{sum(1 for r in rep if r['player_key'] in known)}/{len(rep)}"
        out["leagues"][lg] = v
    out["sources_failed"] = [f"{s['league']}: {s['source']} - {s.get('error')}" for s in run.status if not s["ok"]]
    out["sources_not_expected"] = [f"{s['league']}: {s['source']} - {s.get('note')}" for s in run.status if s.get("note")]
    with open(os.path.join(run.store, "availability", "validation.json"), "w") as f:
        json.dump(out, f, indent=1)
    return out


def main(store):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    run = Run(store)
    run.season_states()
    # structured first (they also seed the name lists used to attribute reporter facts)
    run.nfl_official()
    run.nflverse_injuries()
    for lg, path in (("nfl", "football/nfl"), ("nba", "basketball/nba"), ("nhl", "hockey/nhl")):
        run.espn_injuries(lg, path)
        run.espn_transactions(lg, path)
    run.nba_official()
    for lg, path in (("nfl", "football/nfl"), ("nba", "basketball/nba"), ("nhl", "hockey/nhl")):
        run.espn_news(lg, path)
    run.nfl_reporters()
    run.dfo_goalies()
    run.dfo_lines()
    run.nhl_projected()
    run.nbl()
    run.afl()
    os.makedirs(os.path.join(store, "availability"), exist_ok=True)
    summary = archive(run)
    register(run)
    val = validate(run)
    print(json.dumps({"summary": summary, "failed": val["sources_failed"]}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
