"""Rolling schedule difficulty (next 5 / next 10 / rest of season) and schedule-based season projections, all five sports.

Per game, from a team's point of view: expected margin against an average team in that game's context
(venue + rest, tuned in sos_tune.py and stored in sos_params.json) minus the opponent's rating. Difficulty is the mean
of that over a window; "schedule effect" is wins lost against a coin-flip schedule. The projection is wins so far plus
the sum of the team's own win probabilities in its remaining games (own rating, same context terms).

Fixtures: NFL games.csv, NHL club-schedule feed (cached by nhl_model), NBA ESPN schedule, NBL Rosetta feed,
AFL Squiggle (when no upcoming fixture exists the page shows last season's draw as a recap). Ratings are the ones the
futures simulations already use, so this page agrees with each sport's Futures page.
Writes site/<sport>/data/schedule.json and <sport>/outlook.html.
"""
import json
import math
import os
import re
import shutil
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
BUILD = os.path.join(ROOT, "build")
DATA = os.path.join(ROOT, "data")
SRC = os.path.join(ROOT, "site_src", "schedule")
PARAMS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sos_params.json")))
LABEL = {"nfl": "NFL", "nba": "NBA", "nhl": "NHL", "nbl": "NBL", "afl": "AFL"}
PAGE_DIR = {"nfl": SITE, "nba": os.path.join(SITE, "nba"), "nhl": os.path.join(SITE, "nhl"), "nbl": os.path.join(SITE, "nbl"),
            "afl": os.path.join(SITE, "afl")}
DATA_DIR = {"nfl": os.path.join(SITE, "data"), "nba": os.path.join(SITE, "nba", "data"), "nhl": os.path.join(SITE, "nhl", "data"),
            "nbl": os.path.join(SITE, "nbl", "data"), "afl": os.path.join(SITE, "afl", "data")}
UNIT = {"nfl": "pts", "nba": "pts", "nhl": "goals", "nbl": "pts", "afl": "pts"}
WIN_WORD = {"nfl": "wins", "nba": "wins", "nhl": "wins", "nbl": "wins", "afl": "wins"}


def log(*a):
    print("[sos]", *a, flush=True)


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ------------------------------------------------------------------ adapters: (season, fixture, ratings, names, recap)
# fixture columns: date (Timestamp), home, away, played (bool), hs, as_ (floats), neutral (bool)

def _fx(rows):
    f = pd.DataFrame(rows, columns=["date", "home", "away", "played", "hs", "as_", "neutral"])
    f["date"] = pd.to_datetime(f["date"]).dt.normalize()
    return f.sort_values(["date", "home"]).reset_index(drop=True)


def load_nfl():
    from common import FIX, NAMES
    j = json.load(open(os.path.join(BUILD, "futures.json")))
    ratings = {t: v["rating"] for t, v in j["teams"].items()}
    g = pd.read_csv(os.path.join(DATA, "games.csv"), low_memory=False)
    g = g[(g.season == int(j["season"])) & (g.game_type == "REG")]
    rows = []
    for r in g.itertuples():
        h, a = FIX.get(r.home_team, r.home_team), FIX.get(r.away_team, r.away_team)
        played = pd.notna(r.home_score) and pd.notna(r.away_score)
        rows.append((r.gameday, h, a, played, r.home_score if played else np.nan, r.away_score if played else np.nan,
                     getattr(r, "location", "") == "Neutral"))
    return int(j["season"]), _fx(rows), ratings, dict(NAMES)


def load_nhl():
    import nhl
    import nhl_model as M
    j = json.load(open(os.path.join(SITE, "nhl", "data", "futures.json")))
    teams = [t["team"] for t in j["teams"]]
    ratings = {t["team"]: t["rating"] for t in j["teams"]}
    names = {t["team"]: t["name"] for t in j["teams"]}
    y = nhl.start_year()
    try:
        M.fetch_schedule(teams, y)                     # fills the per-club cache (also used by the futures simulation)
    except Exception as e:  # noqa: BLE001
        log("nhl fetch", e)
    seen, rows = set(), []
    for t in teams:
        p = os.path.join(nhl.NHL_DATA, f"sched_{t}_{y}.json")
        if not os.path.exists(p):
            continue
        for g in json.load(open(p)).get("games", []):
            if g.get("gameType") != 2 or g["id"] in seen:
                continue
            seen.add(g["id"])
            h, a = g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]
            if h not in ratings or a not in ratings:
                continue
            played = g.get("gameState") in ("FINAL", "OFF")
            d = g.get("gameDate") or str(g.get("startTimeUTC", ""))[:10]
            rows.append((d, h, a, played, g["homeTeam"].get("score", np.nan) if played else np.nan,
                         g["awayTeam"].get("score", np.nan) if played else np.nan, False))
    if len(rows) < 500:
        raise RuntimeError(f"NHL schedule incomplete ({len(rows)} games)")
    return y, _fx(rows), ratings, names


def load_nba():
    import nba as N
    j = json.load(open(os.path.join(BUILD, "nba_ratings.json")))["rows"]
    ratings = {r["team"]: r["model_rating"] for r in j}
    names = {r["team"]: r["name"] for r in j}
    y = N.season_end_year()
    p = N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 2)
    d = pd.read_csv(p)
    d = d[(pd.to_numeric(d.season_type, errors="coerce") == 2) & d.home_abbreviation.isin(ratings) & d.away_abbreviation.isin(ratings)]
    rows = []
    for r in d.itertuples():
        played = bool(r.status_type_completed)
        rows.append((r.game_date, r.home_abbreviation, r.away_abbreviation, played, r.home_score if played else np.nan,
                     r.away_score if played else np.nan, bool(getattr(r, "neutral_site", False))))
    return y, _fx(rows), ratings, names


def load_nbl():
    import nbl_site as B
    j = json.load(open(os.path.join(BUILD, "nbl_site", "futures.json")))
    ratings = {t["team"]: t["rating"] for t in j["teams"]}
    names = {t["team"]: t["name"] for t in j["teams"]}
    y = int(j["season"])
    D = json.load(open(B.SRC))
    x, todo, reg_n = B.season_games(D["seasons"][str(y)])
    rows = []
    if len(x):
        reg = x[~x["fin"]] if "fin" in x else x
        for d, h, a, hs, as_ in zip(reg.date, reg.h, reg.a, reg.hs, reg["as"]):
            rows.append((d, h, a, True, hs, as_, False))
    for t in todo:
        rows.append((t["date"], t["home"], t["away"], False, np.nan, np.nan, False))
    return y, _fx(rows), ratings, names


def load_afl():
    import afl_site as A
    j = json.load(open(os.path.join(BUILD, "afl_site", "futures.json")))
    ratings = {t["team"]: t["rating"] for t in j["teams"]}
    names = {t["team"]: t["name"] for t in j["teams"]}
    y = int(j["season"])
    fx = A.fetch_fixture(y)
    if not fx or not any(g["date"] for g in fx):
        return y, None, ratings, names
    rows = [(g["date"], g["home"], g["away"], bool(g["complete"]), g.get("hscore") if g["complete"] else np.nan,
             g.get("ascore") if g["complete"] else np.nan, False) for g in fx if g["date"]]
    return y, _fx(rows), ratings, names


def recap(sport, season):
    """Last completed regular season as a played fixture (used when the next fixture is not out yet)."""
    import trends as T_
    G = T_.LOADERS[sport]()[0]
    G = G[G.season == G.season.max()]
    h = G[G.home]
    rows = [(r.date, r.team, r.opp, True, r.pf, r.pa, False) for r in h.itertuples()]
    return int(G.season.max()), _fx(rows)


LOADERS = {"nfl": load_nfl, "nhl": load_nhl, "nba": load_nba, "nbl": load_nbl, "afl": load_afl}


# ------------------------------------------------------------------ engine

BANDS = [(0.60, 1), (0.54, 2), (0.46, 3), (0.40, 4), (-1, 5)]     # by win chance of an average team: 1 easiest ... 5 hardest


def band(p0):
    for cut, b in BANDS:
        if p0 >= cut:
            return b
    return 5


def compute(sport, season, fx, ratings, names, is_recap=False):
    P = PARAMS[sport]
    thr_s, thr_l = P["thr"]
    sd, hfa, bs, bl = P["sd"], P["hfa"], P["b_short"], P["b_long"]
    mean_r = float(np.mean(list(ratings.values())))
    R = {t: v - mean_r for t, v in ratings.items()}
    fx = fx[fx.home.isin(R) & fx.away.isin(R)].copy()
    # one row per team per game, with rest measured from the team's previous game in this fixture
    L = []
    for r in fx.itertuples():
        L.append((r.home, r.away, True, r.date, r.played, r.hs, r.as_, r.neutral))
        L.append((r.away, r.home, False, r.date, r.played, r.as_, r.hs, r.neutral))
    T = pd.DataFrame(L, columns=["team", "opp", "home", "date", "played", "pf", "pa", "neutral"]).sort_values(["team", "date"], kind="stable")
    T["rest"] = T.groupby("team").date.diff().dt.days
    T["short"] = (T.rest <= thr_s).astype(float).where(T.rest.notna(), 0.0)
    T["long"] = (T.rest >= thr_l).astype(float).where(T.rest.notna(), 0.0)
    key = T.drop_duplicates(["team", "date"]).set_index(["team", "date"])
    # opponent's rest for the same game
    T["o_short"] = [key.short.get((o, d), 0.0) if (o, d) in key.index else 0.0 for o, d in zip(T.opp, T.date)]
    T["o_long"] = [key.long.get((o, d), 0.0) if (o, d) in key.index else 0.0 for o, d in zip(T.opp, T.date)]
    T["R"] = T.team.map(R)
    T["RO"] = T.opp.map(R)
    ven = np.where(T.neutral, 0.0, np.where(T.home, hfa, -hfa))
    ctx = ven + bs * (T.short - T.o_short) + bl * (T.long - T.o_long)
    T["M0"] = -T.RO + ctx                             # expected margin of an average team here
    T["M"] = T.R - T.RO + ctx                         # expected margin of this team here
    T["p0"] = [phi(m / sd) for m in T.M0]
    T["p"] = [phi(m / sd) for m in T.M]
    T["diff"] = -T.M0
    T["band"] = [band(p) for p in T.p0]
    T["eff"] = 0.5 - T.p0
    T["win"] = np.where(T.pf > T.pa, 1.0, np.where(T.pf == T.pa, 0.5, 0.0))

    out = []
    for t, g in T.groupby("team"):
        g = g.sort_values("date", kind="stable")
        done, todo = g[g.played], g[~g.played]
        row = dict(team=t, name=names.get(t, t), rating=round(float(R[t]), 2), gp=int(len(done)), left=int(len(todo)),
                   w=float(done.win.sum()), l=float(len(done) - done.win.sum()))
        row["past_opp"] = round(float(done.RO.mean()), 2) if len(done) else None
        row["past_eff"] = round(float(done.eff.sum()), 2) if len(done) else None
        row["past_diff"] = round(float(done["diff"].mean()), 2) if len(done) else None
        row["exp_left_w"] = round(float(todo.p.sum()), 2)
        row["proj_w"] = round(row["w"] + row["exp_left_w"], 1)
        row["rest_eff"] = round(float(todo.eff.sum()), 2) if len(todo) else None
        for n in (5, 10, 0):
            x = todo if n == 0 else todo.iloc[:n]
            key_ = "all" if n == 0 else str(n)
            if not len(x):
                row["w" + key_] = None
                continue
            row["w" + key_] = dict(n=int(len(x)), opp=round(float(x.RO.mean()), 2), diff=round(float(x["diff"].mean()), 2),
                                   eff=round(float(x.eff.sum()), 2), expw=round(float(x.p.sum()), 2), home=int(x.home.sum()),
                                   short=int((x.short > 0).sum()), long=int((x.long > 0).sum()))
        d = todo["diff"].values
        row["roll"] = [round(float(d[i:i + 5].mean()), 2) for i in range(0, max(0, len(d) - 4))] if len(d) >= 5 else []
        row["games"] = [[x.date.strftime("%Y-%m-%d"), x.opp, int(x.home), int(x.band), round(float(x.p0), 3), round(float(x.p), 3),
                         int(x.short > 0), int(x.long > 0), int(x.neutral)] for x in todo.iloc[:15].itertuples()]
        if is_recap:
            row["games"] = [[x.date.strftime("%Y-%m-%d"), x.opp, int(x.home), int(x.band), round(float(x.p0), 3), round(float(x.p), 3),
                             int(x.short > 0), int(x.long > 0), int(x.neutral)] for x in done.itertuples()]
        out.append(row)
    for k in ("5", "10", "all"):                      # 0-10 score: league percentile of mean difficulty (10 = hardest)
        vals = [(r["team"], r["w" + k]["diff"]) for r in out if r.get("w" + k)]
        if len(vals) > 1:
            order = sorted(v for _, v in vals)
            for r in out:
                if r.get("w" + k):
                    r["w" + k]["score"] = round(10 * sum(v < r["w" + k]["diff"] for v in order) / (len(order) - 1), 1)
    if is_recap:
        vals = sorted(r["past_diff"] for r in out if r["past_diff"] is not None)
        for r in out:
            r["past_score"] = round(10 * sum(v < r["past_diff"] for v in vals) / (len(vals) - 1), 1)
    return out


def build_sport(sport):
    season, fx, ratings, names = LOADERS[sport]()
    is_recap, label_season = False, season
    if fx is not None:
        up = int((~fx.played).sum())
        if up == 0:
            fx = None
    if fx is None:
        label_season, fx = recap(sport, season)
        is_recap = True
        fx = fx
    teams = compute(sport, label_season, fx, ratings, names, is_recap)
    P = PARAMS[sport]
    res = dict(sport=sport, season=label_season, recap=is_recap, updated_utc=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()),
               unit=UNIT[sport], sd=P["sd"], hfa=P["hfa"], b_short=P["b_short"], b_long=P["b_long"], terms=P["terms"],
               short_days=P["thr"][0], long_days=P["thr"][1], tuned_on=P["seasons"], gain_pct=P["gain_pct"],
               last_date=str(fx.date.max().date()), teams=teams, names={t["team"]: t["name"] for t in teams})
    os.makedirs(DATA_DIR[sport], exist_ok=True)
    with open(os.path.join(DATA_DIR[sport], "schedule.json"), "w") as f:
        json.dump(res, f, separators=(",", ":"), allow_nan=False)
    log(sport, "season", label_season, "recap" if is_recap else f"{sum(t['left'] for t in teams) // 2} games left", f"{len(teams)} teams")
    return res


def build_data(sports=("nfl", "nba", "nhl", "nbl", "afl")):
    for s in sports:
        try:
            build_sport(s)
        except Exception as e:  # noqa: BLE001 - one sport must not stop the rest
            import traceback
            traceback.print_exc()
            log(s, "failed", e)


# ------------------------------------------------------------------ pages

INTRO = ("How hard each team's next 5 and next 10 games are, and what the rest of the schedule does to the season. "
         "Opponent strength uses the same ratings as the Futures page, adjusted for home advantage and short rest.")


def _nav_link(html_text, active):
    if 'href="outlook.html"' in html_text:
        return html_text
    cur = ' aria-current="page"' if active else ""
    link = f'<a href="outlook.html"{cur}>Schedule outlook</a>'
    grp = re.search(r'(<nav class="nav[^"]*"[^>]*>\s*<div class="navgrp">.*?)(</div>)', html_text, flags=re.S)
    if grp:
        return html_text[:grp.end(1)] + link + html_text[grp.end(1):]
    return re.sub(r"(<nav class=\"nav[^\"]*\"[^>]*>.*?)(</nav>)", lambda m: m.group(1) + link + m.group(2), html_text, count=1, flags=re.S)


def build_site():
    for sport, d in PAGE_DIR.items():
        idx = os.path.join(d, "index.html")
        if not os.path.exists(idx) or not os.path.exists(os.path.join(DATA_DIR[sport], "schedule.json")):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".html") and fn != "outlook.html":
                p = os.path.join(d, fn)
                s = open(p, encoding="utf-8").read()
                s2 = _nav_link(s, False)
                if s2 != s:
                    open(p, "w", encoding="utf-8").write(s2)
        src = open(idx, encoding="utf-8").read()
        head_end = src.find("</header>")
        if head_end < 0:
            continue
        top = src[:head_end + len("</header>")]
        top = re.sub(r'\saria-current=("page"|page|\'page\')', "", top)
        lab = LABEL[sport]
        top = re.sub(rf'(<div class="sportbar">.*?)(<a href="[^"]*">{lab}</a>)',
                     lambda m: m.group(1) + m.group(2).replace("<a ", '<a aria-current="page" '), top, count=1, flags=re.S)
        top = top.replace('href="outlook.html">Schedule outlook', 'href="outlook.html" aria-current="page">Schedule outlook')
        top = re.sub(r"<title>.*?</title>", f"<title>{lab} schedule difficulty</title>", top, count=1, flags=re.S)
        top = re.sub(r'(<meta name="description" content=")[^"]*', rf"\1{lab} schedule difficulty: next 5 and 10 games and rest-of-season outlook.", top, count=1)
        body = f"""
<main class="page" id="main">
  <div class="page-head"><h1>{lab} schedule difficulty</h1><p>{INTRO}</p></div>
  <div id="sched" data-src="data/schedule.json"><p class="note">Loading…</p></div>
</main>
<footer class="stamp">Schedule difficulty is recalculated on every refresh. Probabilities and history only, not betting advice.</footer>
</div>
<link rel="stylesheet" href="schedule.css">
<script src="schedule.js"></script>
</body></html>"""
        if "<div class=\"wrap\">" not in top:
            body = body.replace("</div>\n<link", "<link", 1)
        open(os.path.join(d, "outlook.html"), "w", encoding="utf-8").write(top + body)
        for f in ("schedule.js", "schedule.css"):
            shutil.copy(os.path.join(SRC, f), os.path.join(d, f))
    log("pages written")


if __name__ == "__main__":
    build_data(tuple(sys.argv[1:]) or ("nfl", "nba", "nhl", "nbl", "afl"))
    build_site()
