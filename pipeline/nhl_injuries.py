"""NHL injury list for the live model: who is out and until when.

Source: CBS Sports NHL injuries page (robots.txt allows it), fetched once per pipeline run and cached for 1.5 hours. Each
row gives the team, player, position and a status such as "IR. Expected to be out until at least Nov 25" or "Day-to-Day".
Nothing here is used for markets; it only says which players will miss which games.
"""
import datetime as dt
import html as html_mod
import os
import re
import time
import urllib.request

import pandas as pd

import nhl

URL = "https://www.cbssports.com/nhl/injuries/"
CBS_TEAM = {"CLB": "CBJ", "LA": "LAK", "LV": "VGK", "MON": "MTL", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "WAS": "WSH"}
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def fetch(max_age_h=None):
    """Raw HTML (cached), or None if unavailable. Cache age NHL_INJ_MAX_AGE_H (default 1.5 h, so every 2-hourly run reads a fresh list)."""
    if max_age_h is None:
        max_age_h = float(os.environ.get("NHL_INJ_MAX_AGE_H", "1.5"))
    os.makedirs(nhl.NHL_DATA, exist_ok=True)
    path = os.path.join(nhl.NHL_DATA, "injuries_cbs.html")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        return open(path, encoding="utf-8", errors="ignore").read()
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "SportsFutures/1.0 (private research; low volume)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            html = r.read().decode("utf-8", errors="ignore")
        open(path, "w", encoding="utf-8").write(html)
        return html
    except Exception:  # noqa: BLE001
        return open(path, encoding="utf-8", errors="ignore").read() if os.path.exists(path) else None


def _date(txt, season):
    m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2})\b", txt)
    if not m:
        return None
    mo = MONTHS[m.group(1)]
    return dt.date(season if mo >= 8 else season + 1, mo, int(m.group(2)))


def parse(html, season):
    """DataFrame: team, name, pos, status, ir, ret (date the player is expected back at the earliest, or None),
    season_out (bool), dtd (day-to-day)."""
    rows = []
    blocks = html.split("TableBase-title")[1:]
    for b in blocks:
        m = re.search(r'href="/nhl/teams/([A-Z]+)/', b)
        if not m or "<table" not in b:
            continue
        team = CBS_TEAM.get(m.group(1), m.group(1))
        tbl = b[b.find("<table"):b.find("</table>") + 8]
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, flags=re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
            if len(cells) < 5:
                continue
            nm = re.search(r'CellPlayerName--long"><span[^>]*><a[^>]*>([^<]+)</a>', cells[0])
            if not nm:
                continue
            txt = [html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip() for c in cells]
            st = txt[4]
            low = st.lower()
            rows.append({"team": team, "name": html_mod.unescape(nm.group(1)).strip(), "pos": txt[1], "status": st,
                         "ir": low.startswith("ir") or " ir" in low or "injured reserve" in low,
                         "ret": _date(st, season), "season_out": "season" in low,
                         "dtd": "day-to-day" in low or "game time" in low})
    return pd.DataFrame(rows, columns=["team", "name", "pos", "status", "ir", "ret", "season_out", "dtd"])


def current(season):
    html = fetch()
    if not html:
        return None
    d = parse(html, season)
    return d if len(d) else None
