"""Injured players in the live NHL model: how much each absence costs a team, and for which games.

Player values come from the two previous seasons, weighted 2:1 by ice time: skaters = points per 60 minus the position
average, shrunk toward 0 (half weight at 20 hours); goalies = goals saved above expected per 60 (MoneyPuck), shrunk the
same way at 30 hours. A missing skater costs  SCALE_SK x usual hours per game x (his value - replacement value);
a missing goalie changes the team's start-weighted goalie value (his starts go to the other goalies and a call-up).
SCALE_SK and SCALE_G turn those raw values into goals per game; they were fitted on 2015-2025 games, comparing results
with who actually played (research/nhl_absence_test.py), because raw on/off values overstate a player's real effect.
Games missed: the injury list's "out until at least <date>" (remaining games before that date), "day-to-day" = 1 game,
"out for the season" = every remaining game plus the playoffs, IR with no date = IR_DEFAULT games.
"""
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

import nhl_injuries
import nhl_roster as R

# Fitted on 12,572 games 2015-2025 (research/nhl_absence_test.py, NA_SK=pts NA_GSH=30): skaters 0.341 (se 0.089),
# goalies 0.438 (se 0.176); walk-forward game log loss better in 6 of 9 seasons.
SCALE_SK = 0.341
SCALE_G = 0.438
REPL_SK = -0.04         # value of skaters with <25 games for the team that season (call-ups), same units
REPL_G = -0.035         # value of a team's third-string / short-stint goalies
SK_SHRINK_H = 20.0
G_SHRINK_H = 30.0
CALLUP_SHARE = 0.3      # share of a missing goalie's starts that go to a call-up rather than the existing backup
IR_DEFAULT = 7
DTD_GAMES = 1


def values(y):
    """key ('name|F/D/G') -> value per 60 as of the start of season y (seasons y-1 and y-2 weighted 2:1 by hours)."""
    parts = []
    for k, w in ((1, 2.0), (2, 1.0)):
        g = R._load("goalies", y - k)
        if g is not None and len(g):
            h = R._num(g, "mp_icetime") / 3600
            gsax60 = (R._num(g, "mp_gsax") / h.clip(lower=0.1)).fillna(0)
            parts.append(pd.DataFrame({"key": R._key(g, True), "value": gsax60 * h / (h + G_SHRINK_H), "w": w * h.fillna(0)}))
        d = R._load("skaters", y - k)
        if d is not None and len(d):
            h = R._num(d, "toiTotal") / 3600
            p60 = R._num(d, "points") / h.clip(lower=0.1)
            grp = d.pos.map(lambda x: "D" if x == "D" else "F")
            dev = p60 - p60.where(h > 5).groupby(grp).transform("mean")
            parts.append(pd.DataFrame({"key": R._key(d, False), "value": (dev * h / (h + SK_SHRINK_H)).fillna(0), "w": w * h.fillna(0)}))
    if not parts:
        return pd.Series(dtype=float)
    a = pd.concat(parts)
    a["vw"] = a.value * a.w
    s = a.groupby("key").agg(vw=("vw", "sum"), w=("w", "sum"))
    return (s.vw / s.w.where(s.w > 0, 1)).fillna(0)


def _grp(pos):
    p = str(pos).upper()
    return "G" if p == "G" else ("D" if p == "D" else "F")


def _usage(y):
    """Usual ice time (hours per game) for skaters and goalie starts by team, current season blended with last season."""
    toi, starts = {}, {}
    for yy, w in ((y - 1, 1.0), (y, 3.0)):
        s = R._load("skaters", yy)
        if s is not None and len(s):
            gp = R._num(s, "gamesPlayed")
            tpg = (R._num(s, "toiTotal") / gp.where(gp > 0)) / 3600
            for nm, pos, t, g in zip(s.name, s.pos, tpg, gp):
                if pd.notna(t) and g > 0:
                    k = f"{str(nm).strip().lower()}|{_grp(pos)}"
                    a, b = toi.get(k, (0.0, 0.0))
                    toi[k] = (a + w * g * t, b + w * g)
        gt = R._load("goalies", yy)
        if gt is not None and len(gt):
            for nm, team, gs in zip(gt.name, gt.team, R._num(gt, "gamesStarted").fillna(0)):
                k = f"{str(nm).strip().lower()}|G"
                team = str(team).split(",")[-1].strip()
                if yy == y:
                    starts.setdefault(team, {})
                    starts[team][k] = starts[team].get(k, 0.0) + w * gs
                else:
                    starts.setdefault("_last", {})[k] = starts.get("_last", {}).get(k, 0.0) + w * gs
    hours = {k: a / b for k, (a, b) in toi.items() if b > 0}
    return hours, starts


def _plain(name):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(name)) if not unicodedata.combining(c)).strip().lower()


def player_costs(y, inj, val, hours, starts):
    """Per injured player: goals per game the team loses while he is out (positive = team weaker)."""
    out = []
    last = starts.get("_last", {})
    alias = {}
    plain = {}
    for kk in list(val.index) + list(hours):
        nm, gg = kk.rsplit("|", 1)
        plain.setdefault(f"{_plain(nm)}|{gg}", kk)
        parts = _plain(nm).split()
        if len(parts) >= 2:
            alias.setdefault((parts[0][0], parts[-1], gg), set()).add(kk)
    for r in inj.itertuples():
        g = _grp(r.pos)
        k = f"{r.name.strip().lower()}|{g}"
        if k not in val.index and k not in hours:
            k = plain.get(f"{_plain(r.name)}|{g}", k)      # accents: CBS 'Isac Lundestrom' vs NHL 'Isac Lundeström'
        if k not in val.index and k not in hours:
            parts = _plain(r.name).split()
            cand = alias.get((parts[0][0], parts[-1], g), set()) if len(parts) >= 2 else set()
            if len(cand) == 1:          # same first initial and last name (Chris / Christopher)
                k = next(iter(cand))
        v = float(val.get(k, 0.0))
        if g != "G":
            h = hours.get(k, 0.0)
            cost = SCALE_SK * h * (v - REPL_SK)
        else:
            team_g = dict(starts.get(r.team, {}))
            for kk in list(team_g) + [k]:
                team_g[kk] = team_g.get(kk, 0.0) + 0.5 * last.get(kk, 0.0) + 1.0
            tot = sum(team_g.values())
            share = {kk: s / tot for kk, s in team_g.items()}
            usual = sum(share[kk] * float(val.get(kk, 0.0)) for kk in share)
            sh_out = share.get(k, 0.0)
            rest = {kk: s for kk, s in share.items() if kk != k}
            rt = sum(rest.values())
            # his starts: CALLUP_SHARE to a call-up, the rest to the team's other goalies in proportion to their starts
            others = sum((s / rt) * float(val.get(kk, 0.0)) for kk, s in rest.items()) if rt > 0 else REPL_G
            new = (1 - sh_out * CALLUP_SHARE) * others + sh_out * CALLUP_SHARE * REPL_G
            cost = SCALE_G * (usual - new)
        out.append({"team": r.team, "name": r.name, "pos": r.pos, "status": r.status, "ret": r.ret,
                    "season_out": bool(r.season_out), "dtd": bool(r.dtd), "ir": bool(r.ir), "value": v, "cost": float(cost)})
    return pd.DataFrame(out)


def _with_overrides(inj):
    """Owner overrides (model/nhl_overrides.json) replace or add injury-list rows, e.g. a suspended player with no return date."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model", "nhl_overrides.json")
    try:
        ov = json.load(open(p)).get("injuries", [])
    except (OSError, ValueError):
        return inj
    if not ov:
        return inj
    rows = pd.DataFrame([{"team": o["team"], "name": o["name"], "pos": o.get("pos", ""), "status": o.get("status", "Out (owner override)"),
                          "ir": True, "ret": None, "season_out": bool(o.get("season_out", True)), "dtd": False} for o in ov])
    if inj is None or not len(inj):
        return rows
    keep = ~inj.name.str.strip().str.lower().isin(rows.name.str.strip().str.lower())
    return pd.concat([inj[keep], rows], ignore_index=True)


def adjustments(y, teams, games, dates, today=None):
    """games: remaining (home, away) list; dates: matching game dates. Returns (game_adj [len(games)], po_adj {team: goals},
    table of absences with games missed). game_adj is added to the home-minus-away margin."""
    today = today or dt.date.today()
    inj = _with_overrides(nhl_injuries.current(y))
    if inj is None or (SCALE_SK == 0 and SCALE_G == 0):
        return np.zeros(len(games)), {}, None
    inj = inj[inj.team.isin(teams)]
    val = values(y)
    hours, starts = _usage(y)
    C = player_costs(y, inj, val, hours, starts)
    dates = [pd.Timestamp(d).date() for d in dates]
    team_games = {t: [i for i, (h, a) in enumerate(games) if t in (h, a)] for t in teams}
    adj = np.zeros(len(games))
    po = {}
    missed = []
    for r in C.itertuples():
        idx = team_games.get(r.team, [])
        if r.season_out:
            miss = idx
        elif r.ret is not None and not pd.isna(r.ret):
            miss = [i for i in idx if dates[i] < r.ret]
        elif r.dtd:
            miss = idx[:DTD_GAMES]
        else:
            miss = idx[:IR_DEFAULT]
        for i in miss:
            adj[i] += -r.cost if games[i][0] == r.team else r.cost
        if r.season_out:
            po[r.team] = po.get(r.team, 0.0) - r.cost
        missed.append(len(miss))
    C["games_missed"] = missed
    C["season_goals"] = C.cost * C.games_missed
    return adj, po, C
