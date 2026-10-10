"""Frozen challenger for NBA return durations (prospective test only; nothing here changes a projection).

The live recovery rule (nba_avail._days_until) restarts its countdown at every report and, without an ESPN return date,
assumes a 14-day median (90 days for season / ACL / Achilles / surgery). On 2019-26 official reports it was badly
calibrated (research/nba_return_test.py, model/availability_nba_returns.json): a frozen empirical table by injury class
x games already missed was far more accurate. GPT's review and TypeSafe: freeze it and score it prospectively before
any live change.

Each refresh appends, for every rotation player listed Out on ESPN's report, the probability that he is still out at
his team's 1st, 3rd, 5th, 10th and 20th next game under (a) the live rule and (b) the frozen table, to
<store>/nba/returns_challenger.jsonl (only when the report changed). Outcomes come later from box scores.
"""
import datetime as dt
import json
import math
import os
import re

import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "nba_return_table.json")
BUCKETS = ((0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, 10 ** 6))


def klass(text, long_re):
    r = text if isinstance(text, str) else ""
    if long_re.search(r):
        return "long"
    if re.search(r"rest|personal|suspension|not with team|g league|two-way|protocol", r, re.I):
        return "non_injury"
    return "injury"


def record(store, injuries, values, players, schedule, end_year, today=None):
    import nba_avail as A
    if not store or not injuries or not os.path.exists(TABLE):
        return 0
    tab = json.load(open(TABLE))
    today = today or dt.date.today()
    d = players[(pd.to_numeric(players.season, errors="coerce") == end_year) & (pd.to_numeric(players.season_type, errors="coerce") == 2)].copy()
    played = set()
    team_games = {}
    if len(d):
        d["athlete_id"] = d.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
        d["min"] = pd.to_numeric(d.minutes, errors="coerce").fillna(0)
        played = set(zip(d[d["min"] > 0].game_id.astype(str), d[d["min"] > 0].athlete_id))
        g = d.drop_duplicates(["game_id", "team_abbreviation"]).sort_values("game_date")
        team_games = {t: list(x.game_id.astype(str)) for t, x in g.groupby("team_abbreviation")}
    rem = schedule[~schedule.completed.astype(bool)]
    rows = []
    for r in injuries:
        if r.get("status") != "Out":
            continue
        v = values.get(str(r.get("athlete_id")))
        if not v:
            continue
        team = v["team"]
        streak = 0
        for gid in reversed(team_games.get(team, [])):
            if (gid, str(r["athlete_id"])) in played:
                break
            streak += 1
        b = next(i for i, (lo, hi) in enumerate(BUCKETS) if lo <= streak <= hi)
        cls = klass(r.get("injury"), A.LONG_TERM)
        med, sig = A._days_until(r, today)
        fut = rem[(rem.home_abbreviation == team) | (rem.away_abbreviation == team)].sort_values("game_date")
        hz = {}
        for h in tab["horizons"]:
            if len(fut) < h:
                break
            gdate = dt.date.fromisoformat(str(fut.iloc[h - 1].game_date)[:10])
            days = max((gdate - today).days, 0)
            live = 1.0 - norm.cdf((math.log(max(days, 1e-6)) - math.log(med)) / sig)
            hz[str(h)] = {"game_date": str(gdate), "live": round(float(live), 4), "frozen": tab["p_still_out"][cls][str(b)][str(h)]}
        rows.append({"athlete_id": str(r["athlete_id"]), "player": v["name"], "team": team, "class": cls, "games_already_missed": streak,
                     "espn_return_date": r.get("return_date"), "live_dated": bool(r.get("return_date")), "horizons": hz})
    rows.sort(key=lambda x: (x["team"], x["player"]))
    path = os.path.join(store, "nba", "returns_challenger.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    last = None
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                last = line
    key = json.dumps([(x["athlete_id"], x["games_already_missed"], x["espn_return_date"]) for x in rows])
    if last and json.loads(last).get("key") == key:
        return 0
    with open(path, "a") as f:
        f.write(json.dumps({"collected_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "table": tab["version"],
                            "as_of_date": str(today), "key": key, "rows": rows}) + "\n")
    return len(rows)
