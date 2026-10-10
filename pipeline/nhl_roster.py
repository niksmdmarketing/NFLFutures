"""Roster-based preseason strength for the NHL model.

For season y, every player on a team's roster is valued on what he did the season before (y-1), wherever he played:
  skaters: on-ice minus off-ice expected-goal differential per 60 (MoneyPuck, all situations), shrunk toward 0 for small ice time
  goalies: goals saved above expected per 60 (MoneyPuck GSAx), shrunk the same way
and weighted by his previous-season ice time, so off-season trades and signings move a team's starting rating.
Rookies and players with no NHL ice time last season count as average (0).

Roster for a past season = the first team each player appeared for that season (team lists are chronological), which is
the closest public stand-in for the opening-night roster. For the current season it is the same once games are played;
before opening night it comes from the NHL roster endpoint.

Result (Oct 2026): tested and NOT adopted. Rolling out-of-sample prediction of season goal difference per game, 2015-2025
(344 team-seasons): current model RMSE 0.4598; best variant (abs, two seasons of history) 0.4581, better in 7 of 11
seasons, t about -1.2 (not significant). Full-simulation back-test 2021-2025 moved preseason points error 11.41 -> 11.38.
TypeSafe chose not to adopt (96%). Switched off by default (nhl_model.ROSTER = "none"); kept for re-testing.
Reproduce: NHL_ROSTER=abs python pipeline/nhl_model.py, or set nhl_model.ROSTER / nhl_roster.YEARS in a test script.
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd

import nhl

SHRINK_H = 10.0          # hours of ice time at which a player's rate counts half


def _load(kind, y):
    p = os.path.join(nhl.NHL_OUT, f"{kind}_{y}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    return pd.DataFrame(d["rows"], columns=["name", "team", "pos"] + [c["k"] for c in d["cols"]])


def _num(d, c):
    return pd.to_numeric(d[c], errors="coerce") if c in d else pd.Series(np.nan, index=d.index)


def _key(d, goalie):
    grp = "G" if goalie else d.pos.map(lambda p: "D" if p == "D" else "F")
    return d.name.astype(str).str.strip().str.lower() + "|" + grp


def player_values(y, mode="mix"):
    """Per-player value and ice time in season y: DataFrame key -> value (goals per 60), hours.
    mode: rel = on-ice minus off-ice (pure individual effect), abs = on-ice rate (includes his old team's quality),
    mix = half of each."""
    out = []
    s = _load("skaters", y)
    if s is not None and len(s):
        on_h = _num(s, "mp_icetime") / 3600
        gp = _num(s, "gamesPlayed")
        off_h = (gp * 60 / 60 - on_h).clip(lower=1)          # hours of team play while he was off the ice (games he played)
        on = (_num(s, "mp_OnIce_F_xGoals") - _num(s, "mp_OnIce_A_xGoals")) / on_h.clip(lower=0.1)
        off = (_num(s, "mp_OffIce_F_xGoals") - _num(s, "mp_OffIce_A_xGoals")) / off_h
        rel = (on - off).fillna(0)
        val = {"rel": rel, "abs": on.fillna(0), "mix": 0.5 * rel + 0.5 * on.fillna(0)}[mode]
        out.append(pd.DataFrame({"key": _key(s, False), "value": val * on_h / (on_h + SHRINK_H), "hours": on_h.fillna(0), "g": 0}))
    g = _load("goalies", y)
    if g is not None and len(g):
        h = _num(g, "mp_icetime") / 3600
        gsax60 = (_num(g, "mp_gsax") / h.clip(lower=0.1)).fillna(0)
        out.append(pd.DataFrame({"key": _key(g, True), "value": gsax60 * h / (h + SHRINK_H), "hours": h.fillna(0), "g": 1}))
    if not out:
        return None
    v = pd.concat(out, ignore_index=True)
    return v.groupby("key").agg(value=("value", "mean"), hours=("hours", "sum"), g=("g", "max"))


def season_rosters(y):
    """key -> team for season y (first team listed), from the season's player tables."""
    rows = []
    for kind, goalie in (("skaters", False), ("goalies", True)):
        d = _load(kind, y)
        if d is None or not len(d):
            continue
        rows.append(pd.DataFrame({"key": _key(d, goalie), "team": d.team.astype(str).str.split(",").str[0].str.strip()}))
    if not rows:
        return None
    return pd.concat(rows).drop_duplicates("key").set_index("key").team


def live_rosters(teams):
    """Opening-night rosters from the NHL roster endpoint (used only before the current season's first games)."""
    rows = []
    for t in teams:
        try:
            req = urllib.request.Request(f"https://api-web.nhle.com/v1/roster/{t}/current", headers={"User-Agent": "SportsFutures/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
        except Exception:  # noqa: BLE001
            continue
        for grp, code in (("forwards", "F"), ("defensemen", "D"), ("goalies", "G")):
            for p in d.get(grp, []):
                name = f"{p.get('firstName', {}).get('default', '')} {p.get('lastName', {}).get('default', '')}".strip().lower()
                rows.append((f"{name}|{code}", t))
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["key", "team"]).drop_duplicates("key").set_index("key").team


_CACHE = {}


def roster_features(y, teams, current=None, mode="mix"):
    """DataFrame (index team) with rsk (skater value) and rg (goalie value), centred on the league, from season y-1 values."""
    k = (y, mode, tuple(sorted(teams)))
    if k not in _CACHE:
        _CACHE[k] = _roster_features(y, list(teams), current, mode)
    return _CACHE[k].copy()


YEARS = 1                # seasons of player history (1 = last season; 2 = last two, weighted 2:1)


def _values(y, mode):
    v1 = player_values(y - 1, mode)
    if YEARS < 2 or v1 is None:
        return v1
    v2 = player_values(y - 2, mode)
    if v2 is None:
        return v1
    j = v1.join(v2, how="outer", rsuffix="2")
    w1, w2 = 2 * j.hours.fillna(0), j.hours2.fillna(0)
    val = (j.value.fillna(0) * w1 + j.value2.fillna(0) * w2) / (w1 + w2).where(w1 + w2 > 0, 1)
    return pd.DataFrame({"value": val, "hours": j.hours.fillna(0).where(j.hours.fillna(0) > 0, j.hours2.fillna(0) * 0.5),
                         "g": j.g.fillna(j.g2)})


def _roster_features(y, teams, current, mode):
    vals = _values(y, mode)
    ros = season_rosters(y)
    if (ros is None or ros.empty) and current == y:
        ros = live_rosters(teams)
    out = pd.DataFrame(0.0, index=list(teams), columns=["rsk", "rg"])
    if vals is None or ros is None or ros.empty:
        return out
    m = vals.join(ros.rename("team"), how="inner")
    m = m[m.team.isin(out.index)]
    for t, x in m.groupby("team"):
        sk, gk = x[x.g == 0], x[x.g == 1]
        if sk.hours.sum() > 0:
            out.loc[t, "rsk"] = float((sk.value * sk.hours).sum() / sk.hours.sum())
        if gk.hours.sum() > 0:
            out.loc[t, "rg"] = float((gk.value * gk.hours).sum() / gk.hours.sum())
    return out - out.mean()
