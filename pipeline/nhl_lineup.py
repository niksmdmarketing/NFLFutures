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
