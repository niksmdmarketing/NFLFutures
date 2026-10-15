"""Team lineup strength from who actually played (NHL).

Each game's lineup value (goals per game vs an average lineup) =
   nhl_absence.SCALE_SK x sum over skaters of (ice-time share of 5 skater-hours) x player value
 + nhl_absence.SCALE_G  x starting goalie's value
with player values as of the start of the season (nhl_absence.values: two previous seasons). The scales were fitted on
12,572 games (research/nhl_absence_test.py), so a lineup value is already in rating units.

Roster term for a team at a date: how its recent lineups (last N games) compare with the lineups behind the results the
rating already uses: this season's games so far (weight gp/(gp+k)) and last season's games (weight k/(gp+k), the part of
the rating that is still the preseason prior). Trades, call-ups and players returning from injury show up here at once.
"""
import os

import numpy as np
import pandas as pd

import nhl_absence as A

LINEUP_N = 5            # recent games that define the current lineup


def _key(name, pos):
    p = pos.astype(str).str.upper()
    return name.astype(str).str.strip().str.lower() + "|" + np.where(p == "G", "G", np.where(p == "D", "D", "F"))


def game_values(S, G, val):
    """S, G: per-game skater / goalie rows (game_id, date, team, name, pos, toi[, started]). Returns date, team, game_id, lv."""
    S = S.copy()
    S["v"] = _key(S.name, S.pos).map(val).fillna(0.0)
    S["toi"] = pd.to_numeric(S.toi, errors="coerce").fillna(0.0)
    tot = S.groupby(["game_id", "team"]).toi.transform("sum")
    S["hv"] = S.v * 5.0 * S.toi / tot.where(tot > 0, 1.0)
    sk = S.groupby(["game_id", "date", "team"]).hv.sum().rename("sk")
    g = G[G.started == 1].copy()
    g["v"] = _key(g.name, pd.Series("G", index=g.index)).map(val).fillna(0.0)
    gk = g.groupby(["game_id", "team"]).v.mean().rename("gk")
    out = sk.reset_index().merge(gk.reset_index(), on=["game_id", "team"], how="left")
    out["gk"] = out.gk.fillna(0.0)
    out["lv"] = A.SCALE_SK * out.sk + A.SCALE_G * out.gk
    out["date"] = pd.to_datetime(out.date)
    return out.sort_values(["date", "game_id"])


def load_lineups(d, y):
    s = os.path.join(d, f"skaters_{y}.csv.gz")
    g = os.path.join(d, f"goalies_{y}.csv.gz")
    if not (os.path.exists(s) and os.path.exists(g)):
        return None, None
    return pd.read_csv(s), pd.read_csv(g)


def roster_term(cur_lv, last_lv, teams, cut, k, n=LINEUP_N, opening=None, pre=True, min_gp=0):
    """Rating adjustment by team at date `cut` (goals per game, centred on the league).
    cur_lv: this season's game values; last_lv: last season's game values (same player values); opening: game values of
    each team's first game (used for the current lineup before any game is played)."""
    before = cur_lv[cur_lv.date < cut]
    out = pd.Series(0.0, index=teams)
    last_avg = last_lv.groupby("team").lv.mean() if last_lv is not None and len(last_lv) else pd.Series(dtype=float)
    for t in teams:
        b = before[before.team == t]
        gp = len(b)
        if gp < min_gp:
            continue
        if gp:
            now = b.lv.iloc[-n:].mean()
            avg = b.lv.mean()
        elif opening is not None and t in opening.index:
            now, avg = float(opening[t]), 0.0
        else:
            continue
        w_cur = gp / (gp + k)
        adj = w_cur * (now - avg)
        if pre and t in last_avg.index:
            adj += (1 - w_cur) * (now - last_avg[t])
        out[t] = adj
    return out - out.mean()


# ---------------------------------------------------------------- live

API = "https://api.nhle.com/stats/rest/en"
LIVE_C = 1.0            # 15-season-weekly replay (research/replay_nhl.py NHL_LINEUP_C=1 NHL_LINEUP_PRE=0): see WORKLOG


def _get(kind, y, a, b):
    import json
    import time
    import urllib.parse
    import urllib.request
    q = {"isAggregate": "false", "isGame": "true", "limit": "10000", "start": "0", "sort": "gameId",
         "cayenneExp": f'seasonId={y * 10000 + y + 1} and gameTypeId=2 and gameDate>="{a}" and gameDate<"{b}"'}
    url = f"{API}/{kind}/summary?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r).get("data", [])
        except Exception:  # noqa: BLE001
            time.sleep(3 * (attempt + 1))
    return None


def fetch_season(y, today=None, max_age_h=2.0):
    """This season's per-game skater and goalie rows from the NHL stats API (half-month windows), cached."""
    import datetime as dt
    import time
    import nhl
    os.makedirs(nhl.NHL_DATA, exist_ok=True)
    paths = {k: os.path.join(nhl.NHL_DATA, f"lineups_{k}s_{y}.csv.gz") for k in ("skater", "goalie")}
    if all(os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age_h * 3600 for p in paths.values()):
        return pd.read_csv(paths["skater"]), pd.read_csv(paths["goalie"])
    today = today or dt.date.today()
    wins = []
    d = dt.date(y, 9, 1)
    while d <= today:
        e = d.replace(day=16) if d.day == 1 else (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        wins.append((d.isoformat(), e.isoformat()))
        d = e
    out = {}
    for kind in ("skater", "goalie"):
        rows = []
        for a, b in wins:
            part = _get(kind, y, a, b)
            if part is None:
                return (pd.read_csv(paths["skater"]), pd.read_csv(paths["goalie"])) if all(os.path.exists(p) for p in paths.values()) else (None, None)
            rows += part
        R = pd.DataFrame(rows)
        if R.empty:
            return None, None
        name = "skaterFullName" if kind == "skater" else "goalieFullName"
        o = pd.DataFrame({"game_id": R.gameId, "date": R.gameDate, "team": R.teamAbbrev, "player_id": R.playerId, "name": R[name],
                          "pos": R.positionCode if "positionCode" in R else "G",
                          "toi": R.timeOnIcePerGame if kind == "skater" else R.timeOnIce})
        if kind == "goalie":
            o["started"] = R.gamesStarted.fillna(0).astype(int)
        o.to_csv(paths[kind], index=False)
        out[kind] = o
    return out["skater"], out["goalie"]


def ratings_file(y):
    """Skater ratings for season y (model/nhl_player_ratings_<y>.csv: player_id, off, def), built from seasons before y by
    research/nhl_rapm.py (RAPM_LAM=300000 RAPM_KBOX=1). Replay: roster term with these values +0.0003 vs points/GSAx
    values, +0.0008 vs no roster term (90% +0.0001 to +0.0014, 8/10); TypeSafe 80%."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model", f"nhl_player_ratings_{y}.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p).set_index("player_id")[["off", "def"]]


def live_term(y, teams, k, absences=None, n=LINEUP_N, today=None):
    """Live roster term (pre=False). Players on the injury list are counted back into the current lineup for the recent
    games they missed, because the injury adjustment already charges their absence game by game."""
    import datetime as dt
    S, G = fetch_season(y, today)
    if S is None or not len(S):
        return pd.Series(0.0, index=teams), None
    rp = ratings_file(y)
    if rp is not None and "player_id" in S:
        lv = game_values_ratings(S, rp)
    else:
        lv = game_values(S, G, A.values(y))
    cut = pd.Timestamp(today or dt.date.today()) + pd.Timedelta(days=1)
    term = roster_term(lv, None, list(teams), cut, k, n, None, pre=False)
    if absences is not None and len(absences):
        played = set(zip(S.game_id, S.team, S.name.str.strip().str.lower())) | set(zip(G.game_id, G.team, G.name.str.strip().str.lower()))
        back = pd.Series(0.0, index=list(teams))
        for r in absences.itertuples():
            if r.team not in back.index:
                continue
            tg = lv[(lv.team == r.team) & (lv.date < cut)]
            recent = tg.game_id.iloc[-n:]
            if not len(recent):
                continue
            missed = sum((gid, r.team, r.name.strip().lower()) not in played for gid in recent)
            gp = len(tg)
            back[r.team] += (gp / (gp + k)) * r.cost * missed / len(recent)
        term = term + back - back.mean()
    term = LIVE_C * term
    return term, lv


def game_values_ratings(S, sk, gk=None, g_scale=0.0, G=None, shots_against=40.0):
    """Lineup value per game from player ratings (research/nhl_rapm.py): sum of (off - def) x ice-time share of 5
    skater-hours, plus optionally g_scale x starter GSAx/shot x shots against. S needs player_id."""
    S = S.copy()
    net = (sk["off"] - sk["def"]) if sk is not None else pd.Series(dtype=float)
    S["v"] = S.player_id.map(net).fillna(0.0)
    S["toi"] = pd.to_numeric(S.toi, errors="coerce").fillna(0.0)
    tot = S.groupby(["game_id", "team"]).toi.transform("sum")
    S["hv"] = S.v * 5.0 * S.toi / tot.where(tot > 0, 1.0)
    out = S.groupby(["game_id", "date", "team"]).hv.sum().rename("lv").reset_index()
    if g_scale and gk is not None and G is not None:
        g = G[G.started == 1].copy()
        g["v"] = g.player_id.map(gk["gsax_shot"]).fillna(0.0) * shots_against
        out = out.merge(g.groupby(["game_id", "team"]).v.mean().rename("gv").reset_index(), on=["game_id", "team"], how="left")
        out["lv"] = out.lv + g_scale * out.gv.fillna(0.0)
        out = out.drop(columns="gv")
    out["date"] = pd.to_datetime(out.date)
    return out.sort_values(["date", "game_id"])
