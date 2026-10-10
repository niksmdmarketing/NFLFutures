"""NBA availability layer (version 2) for the live model: player values in points, who is out, and for how long.

Research: research/nba_availability2.py -> model/availability_nba_v2.json (2011-2026 walk-forward, 18,967 games):
log-loss 0.6195 without adjustment -> 0.6078 with it, better in 16 of 16 seasons; against closing odds 0.6192 -> 0.6088
(market 0.592). Version 2 answers an external review of version 1:
- ability is separated from availability: ability = game score per 36 over three seasons (1 / 0.6 / 0.36), shrunk toward
  replacement; minutes = his average in his last 10 games played (so a star back from a lost season keeps his value);
- adjustments are relative to the team rating: each player's 'baseline' is the share of his team's games (weighted
  like the rating: this season 4, last season 1, then 0.2...) in which he was missing. Cost = value x (expected
  missing now - baseline), so an absence the rating already reflects costs about nothing and a return is an uplift;
- players with no report entry keep the availability the rating already reflects (cost 0): predicting a return to
  their longer-run typical rate was tested and added nothing (variant v2_typ);
- return dates are uncertain: each simulation draws a return date around ESPN's estimate (lognormal), and long-term
  injuries that reach the playoffs weaken the team there too;
- a failed feed keeps the last known report (see fetch_injuries).
Value (points of margin per game) = BETA x (ability per 36 - replacement) x minutes / 48.
"""
import datetime as dt
import json
import os
import re
import urllib.request

import numpy as np
import pandas as pd

BETA = 0.45           # points per unit, fitted walk-forward (latest season, version 2)
SHRINK_MIN = 400.0
ABILITY_W = {0: 1.0, 1: 0.6, 2: 0.36}
RATING_W = {0: 4.0, 1: 1.0, 2: 0.2, 3: 0.04, 4: 0.008}
ROTATION_MIN = 12.0
TYPICAL_PRIOR_GAMES = 20.0
NO_DATE_DAYS = 14     # Out with no estimated return: median 14 days, wide spread
RETURN_SIGMA = 0.45   # lognormal spread around ESPN's estimated return (dated)
NO_DATE_SIGMA = 0.9   # ... and around the 14-day default when no date is given
LONG_TERM = re.compile(r"season|acl|achilles|surgery", re.I)
LONG_TERM_DAYS = 90   # undated but clearly long-term injuries
# probability of missing the game by status (ESPN 'Day-To-Day' and official statuses); official ones calibrated in
# nba_avail_params.json when available
P_MISS = {"Out": 1.0, "Doubtful": 0.9, "Questionable": 0.45, "Probable": 0.05, "Available": 0.0, "Day-To-Day": 0.4}
DTD_DAYS = 3
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
_pp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba_avail_params.json")
if os.path.exists(_pp):
    P_MISS.update(json.load(open(_pp)).get("p_miss", {}))


def _gmsc(d):
    return (d.points + .4 * d.field_goals_made - .7 * d.field_goals_attempted - .4 * (d.free_throws_attempted - d.free_throws_made)
            + .7 * d.offensive_rebounds + .3 * d.defensive_rebounds + d.steals + .7 * d.assists + .7 * d.blocks - .4 * d.fouls - d.turnovers)


def player_values(players, end_year, roster=None, today=None):
    """athlete_id -> dict(name, team, mpg, ability, value, baseline, typical) for players on the current roster
    (or, without a roster, on the team of their latest game)."""
    today = pd.Timestamp(today or dt.date.today())
    d = players[pd.to_numeric(players.season_type, errors="coerce") == 2].copy()
    cols = ["minutes", "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
            "defensive_rebounds", "assists", "steals", "blocks", "turnovers", "fouls", "points"]
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["season"] = pd.to_numeric(d.season, errors="coerce")
    d = d[d.season >= end_year - 4]
    if d.empty:
        return {}
    d["athlete_id"] = d.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    d["date"] = pd.to_datetime(d.game_date)
    d["played"] = (d.minutes > 0) & ~d.get("did_not_play", pd.Series(False, index=d.index)).astype(str).str.lower().eq("true")
    d["gmsc"] = _gmsc(d)
    pl = d[d.played]
    ref = pl[pl.season == end_year - 1] if (pl.season == end_year - 1).any() else pl[pl.season == pl.season.max()]
    rep = float(np.nanpercentile((ref.gmsc / ref.minutes * 36)[ref.minutes >= 10], 30))
    # ability
    w = pl.season.map(lambda s: ABILITY_W.get(end_year - s, 0.0))
    ab = pl.assign(g=pl.gmsc * w, m=pl.minutes * w).groupby("athlete_id")[["g", "m"]].sum()
    ab["v36"] = (ab.g + rep / 36 * SHRINK_MIN) / (ab.m + SHRINK_MIN) * 36 - rep
    mins = pl.sort_values("date").groupby("athlete_id").minutes.apply(lambda x: x.tail(10).mean())
    name = d.sort_values("date").groupby("athlete_id").athlete_display_name.last()
    latest_team = d.sort_values("date").groupby("athlete_id").team_abbreviation.last()
    # membership spells (player, team, season): team games between his first and last row; extended to the season's
    # end (or today) if that team was his last team that season
    tg = d.drop_duplicates(["game_id", "team_abbreviation"])[["game_id", "team_abbreviation", "season", "date"]]
    last_of_season = d.sort_values("date").groupby(["athlete_id", "season"]).team_abbreviation.last()
    sp = d.groupby(["athlete_id", "team_abbreviation", "season"]).agg(first=("date", "min"), last=("date", "max"), played=("played", "sum")).reset_index()
    member, missed = [], []
    tg_by = {k: v.date.sort_values().to_numpy() for k, v in tg.groupby(["team_abbreviation", "season"])}
    for r in sp.itertuples():
        dates = tg_by.get((r.team_abbreviation, r.season))
        end = r.last
        if last_of_season.get((r.athlete_id, r.season)) == r.team_abbreviation:
            end = today if r.season == end_year else pd.Timestamp.max
        n = int(((dates >= r.first) & (dates <= end)).sum()) if dates is not None else 0
        member.append(n)
        missed.append(max(0, n - int(r.played)))
    sp["member"], sp["missed"] = member, missed
    league_rate = float(sp.missed.sum() / max(1, sp.member.sum()))
    sp["rw"] = sp.season.map(lambda s: RATING_W.get(end_year - s, 0.0))
    sp["tw"] = sp.season.map(lambda s: ABILITY_W.get(end_year - s, 0.0))
    if roster is not None and len(roster):
        r = roster[roster.team_abbreviation.notna()].copy()
        r["athlete_id"] = r.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
        team_of = dict(zip(r.athlete_id, r.team_abbreviation))
        name = name.combine_first(pd.Series(dict(zip(r.athlete_id, r.display_name))))
    else:
        team_of = latest_team.to_dict()
    sp_team = sp.set_index(["athlete_id", "team_abbreviation"])
    typ = sp.assign(m=sp.member * sp.tw, x=sp.missed * sp.tw).groupby("athlete_id")[["m", "x"]].sum()
    out = {}
    for pid, team in team_of.items():
        if pid not in ab.index or pid not in mins.index:
            continue
        mp = float(mins[pid])
        if mp < ROTATION_MIN:
            continue
        t = typ.loc[pid] if pid in typ.index else None
        typical = float((t.x + TYPICAL_PRIOR_GAMES * league_rate) / (t.m + TYPICAL_PRIOR_GAMES)) if t is not None else league_rate
        try:
            h = sp_team.loc[[(pid, team)]]
            den = float((h.member * h.rw).sum())
        except KeyError:
            h, den = None, 0.0
        # New to the team: the rating does not contain him; the roster adjustment adds him using last season's minutes,
        # which already reflect how often he played, so his baseline is his typical rate.
        base = float((h.missed * h.rw).sum()) / den if den else typical
        value = BETA * float(ab.v36[pid]) * mp / 48
        out[pid] = dict(name=str(name.get(pid, pid)), team=team, mpg=round(mp, 1), ability=round(float(ab.v36[pid]), 2),
                        value=round(value, 2), baseline=round(base, 3), typical=round(typical, 3))
    return out


def _rows_from_espn(j):
    rows = []
    for t in j.get("injuries") or []:
        for i in t.get("injuries") or []:
            a = i.get("athlete") or {}
            href = " ".join(l.get("href", "") for l in a.get("links") or [])
            m = re.search(r"/id/(\d+)/", href)
            det = i.get("details") or {}
            rows.append(dict(athlete_id=m.group(1) if m else None, name=a.get("displayName"), team_name=t.get("displayName"),
                             status=i.get("status"), return_date=det.get("returnDate"),
                             injury=" ".join(x for x in (det.get("side"), det.get("type"), det.get("detail")) if x), updated=i.get("date")))
    return rows


STALE_FULL_H = 24      # a report this fresh is used as is
STALE_MAX_DAYS = 21    # beyond this nothing is used


def fetch_injuries(cache_dir, store=None, now=None):
    """-> (rows, meta). If the feed fails, the last known report is kept: within 24 hours as is; older (up to 21 days)
    only confirmed Out players whose estimated return is still ahead (or, with no date, a report under 14 days old);
    short-term statuses are dropped. meta says whether the report is stale and how old it is."""
    now = now or dt.datetime.now(dt.timezone.utc)
    path = os.path.join(cache_dir, "nba_injuries_latest.json")
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "SportsFutures/1.0"}), timeout=30) as r:
            j = json.load(r)
        os.makedirs(cache_dir, exist_ok=True)
        json.dump({"collected_utc": now.isoformat(), "feed": j}, open(path, "w"))
        return _rows_from_espn(j), {"stale": False, "age_hours": 0.0, "feed_time": j.get("timestamp")}
    except Exception as e:  # noqa: BLE001
        print("[nba avail] injuries feed unavailable:", e, flush=True)
    found = []
    if os.path.exists(path):
        c = json.load(open(path))
        if "feed" in c:
            found.append((dt.datetime.fromisoformat(c["collected_utc"]), _rows_from_espn(c["feed"]), c["feed"].get("timestamp")))
    if store and os.path.exists(os.path.join(store, "nba", "latest.json")):
        c = json.load(open(os.path.join(store, "nba", "latest.json")))
        t = dt.datetime.strptime(c["collected_utc"], "%Y-%m-%dT%H%MZ").replace(tzinfo=dt.timezone.utc)
        found.append((t, c["rows"], c.get("feed_timestamp")))
    if not found:
        return None, {"stale": True, "age_hours": None}
    t, rows, stamp = max(found, key=lambda f: f[0])
    age_h = (now - t).total_seconds() / 3600
    meta = {"stale": age_h > STALE_FULL_H, "age_hours": round(age_h, 1), "feed_time": stamp}
    if age_h <= STALE_FULL_H:
        return rows, meta
    if age_h > STALE_MAX_DAYS * 24:
        return None, meta
    today = now.date()
    keep = []
    for r in rows:
        if r["status"] != "Out":
            continue
        if r.get("return_date"):
            try:
                if dt.date.fromisoformat(str(r["return_date"])[:10]) > today:
                    keep.append(r)
            except ValueError:
                pass
        elif age_h <= NO_DATE_DAYS * 24:
            keep.append(r)
    return keep, meta


def _days_until(r, today):
    """Median days out and lognormal spread for an Out player."""
    if r.get("return_date"):
        try:
            k = (dt.date.fromisoformat(str(r["return_date"])[:10]) - today).days
            return max(1, k), RETURN_SIGMA
        except ValueError:
            pass
    if LONG_TERM.search(r.get("injury") or ""):
        return LONG_TERM_DAYS, NO_DATE_SIGMA
    return NO_DATE_DAYS, NO_DATE_SIGMA


def plan(schedule, injuries, values, names, today=None, official=None):
    """Turn the report into simulation inputs.
    Returns dict(
      fixed: (game_date, home, away) -> points to subtract from the home margin that do not depend on recovery paths
             (everyone's typical availability vs the rating's baseline, plus game-day statuses),
      episodes: list of dict(team, games=[(index into remaining-game keys)], days=[days ahead], cost_out, cost_back,
             median_days, sigma) for players listed Out, to be drawn per simulation,
      listed: rows for the page)."""
    today = today or dt.date.today()
    full = {v: k for k, v in names.items()}
    full["Los Angeles Clippers"] = "LAC"
    left = schedule[~schedule.completed.astype(bool)].copy()
    left["d"] = pd.to_datetime(left.game_date).dt.date
    keys = [(str(g.game_date)[:10], g.home_abbreviation, g.away_abbreviation) for g in left.itertuples()]
    days = np.array([(x - today).days for x in left.d])
    team_games = {t: np.flatnonzero((left.home_abbreviation == t).to_numpy() | (left.away_abbreviation == t).to_numpy()) for t in names}
    sign = {t: np.where(left.home_abbreviation.to_numpy() == t, 1.0, -1.0) for t in names}
    fixed = np.zeros(len(left))
    listed_by = {}
    for r in injuries or []:
        v = values.get(str(r.get("athlete_id")))
        team = full.get(r.get("team_name")) or (v or {}).get("team")
        if v and team in names:
            listed_by[str(r["athlete_id"])] = (team, r)
    # game-day official statuses override for that day's game: {(athlete_id, game_date): status}
    official = official or {}
    episodes, listed = [], []
    for pid, v in values.items():
        team = listed_by.get(pid, (v["team"], None))[0]
        if team not in names:
            continue
        g = team_games[team]
        # Without game-day information a player is assumed to keep missing games at the rate the rating already
        # reflects (cost 0). Tested: predicting a return to his longer-run typical rate instead added nothing
        # (research variant v2_typ, fitted scale 0 in 16 of 16 seasons).
        per_game = np.zeros(len(g))
        r = listed_by.get(pid, (None, None))[1]
        if r is not None and r["status"] == "Day-To-Day":
            near = days[g] < DTD_DAYS
            per_game[near] = v["value"] * (P_MISS["Day-To-Day"] - v["baseline"])
        for gi, (gd, h, a) in enumerate(keys[i] for i in g):
            st = official.get((pid, gd))
            if st in P_MISS:
                per_game[gi] = v["value"] * (P_MISS[st] - v["baseline"])
        if r is not None and r["status"] == "Out":
            med, sig = _days_until(r, today)
            episodes.append(dict(team=team, games=g, days=days[g], sign=sign[team][g], cost_out=v["value"] * (1 - v["baseline"]),
                                 cost_back=per_game, median_days=med, sigma=sig))
        else:
            fixed[g] += per_game * sign[team][g]
        if r is not None:
            med = _days_until(r, today)[0] if r["status"] == "Out" else DTD_DAYS
            n = int((days[g] < med).sum())
            pmiss = 1.0 if r["status"] == "Out" else P_MISS["Day-To-Day"]
            listed.append(dict(team=team, player=v["name"], status=r["status"], est_return=str(r.get("return_date") or "")[:10] or None,
                               injury=r.get("injury"), points=round(v["value"] * (pmiss - v["baseline"]), 1), value=v["value"],
                               baseline=v["baseline"], mpg=v["mpg"], games=n))
    listed.sort(key=lambda x: (-(x["games"] > 0), -x["points"]))
    return dict(keys=keys, fixed=fixed, episodes=episodes, listed=listed, days=days)


def draw_adjustments(P, rng, size):
    """(size x games) matrix of points to subtract from the home margin, one recovery path per simulation row,
    plus per-simulation cost still owed at the end of the regular season by team (for the playoffs)."""
    adj = np.tile(P["fixed"], (size, 1))
    playoff = {}
    horizon = int(P["days"].max()) + 1 if len(P["days"]) else 0
    for e in P["episodes"]:
        back = e["median_days"] * np.exp(rng.normal(0, e["sigma"], size))
        out = e["days"][None, :] < back[:, None]
        cost = np.where(out, e["cost_out"], e["cost_back"][None, :])
        adj[:, e["games"]] += cost * e["sign"][None, :]
        playoff.setdefault(e["team"], np.zeros(size))
        playoff[e["team"]] += np.where(back > horizon, e["cost_out"], 0.0)
    return adj, playoff


def expected_adjustments(P):
    """Median recovery path: (game_date, home, away) -> points, for the game-by-game page."""
    adj = P["fixed"].copy()
    for e in P["episodes"]:
        out = e["days"] < e["median_days"]
        adj[e["games"]] += np.where(out, e["cost_out"], e["cost_back"]) * e["sign"]
    return {k: float(a) for k, a in zip(P["keys"], adj) if a}


def archive(store, injuries, stamp):
    """Append the feed snapshot to a history folder (the injury-monitor branch in CI) when anything changed."""
    d = os.path.join(store, "nba")
    os.makedirs(d, exist_ok=True)
    latest = os.path.join(d, "latest.json")
    rows = sorted(injuries, key=lambda r: (r["team_name"] or "", r["name"] or ""))
    key = [{k: r[k] for k in ("athlete_id", "status", "return_date", "injury")} for r in rows]
    if os.path.exists(latest) and json.load(open(latest)).get("key") == key:
        return False
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    snap = {"collected_utc": now, "feed_timestamp": stamp, "source": URL, "key": key, "rows": rows}
    json.dump(snap, open(latest, "w"), indent=0)
    with open(os.path.join(d, "history.jsonl"), "a") as f:
        f.write(json.dumps({"collected_utc": now, "feed_timestamp": stamp, "rows": rows}) + "\n")
    return True
