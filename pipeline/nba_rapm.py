"""Player ratings (RAPM) for the NBA preseason rating.

Lineup stints are rebuilt from ESPN play-by-play (sportsdataverse espn_nba_pbp): starters from the box score, each
substitution swaps the player leaving for the one entering, and at the start of periods 2+ the five per team are the players
who act (or are subbed out) before being subbed in, topped up from the previous period's closing five. Season minutes from
the rebuilt lineups match box scores (r 0.9995 in 2024-25).
RAPM: ridge regression of each stint's point margin per 100 possessions on the ten players (home +1, away -1, home-court
intercept), weighted by possessions; last season at weight 1, the season before at 0.5; each player is pulled toward
2.5 x his box-score value (nba._roster_values) with ridge 3000.
Team strength = sum(rating x projected minutes) / (82 x 48) over a 12-man rotation; players with no rating (rookies) -1.
Replay 2014-2026 (research/nba_player_replay.py): preseason rating = 60% team rating + 40% this strength, MAE vs the
season's net rating 2.967 -> 2.865 (better 10/13; mixing weight chosen leave-one-season-out 0.4 in 11/13, +0.092);
no gain at 20 or 41 games, so the share fades to 0 by game 20.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse

LAM, W2, K_BOX, ROOKIE = 3000.0, 0.5, 2.5, -1.0
MIX, MIX_GAMES = 0.4, 20.0
DEV_YOUNG, DEV_YEARS = 1.0, 4   # +1 point per 100 for each season short of 4 played (young players improve)
# Development (14 Oct 2026): experience = seasons since first NBA minutes; +1.0 per season below 4 improved the 2014-2026
# preseason replay 2.865 -> 2.807 (better 9/13); a decline term for veterans made it worse; a late-season tank/drop term and
# last season's level gave nothing.


def _id(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def game_stints(ev: pd.DataFrame, box: pd.DataFrame):
    home, away = int(ev.home_team_id.iloc[0]), int(ev.away_team_id.iloc[0])
    team_of = dict(zip(box.athlete_id, box.team_id))
    starters = {t: [a for a, tt, s in zip(box.athlete_id, box.team_id, box.starter) if tt == t and s] for t in (home, away)}
    if any(len(v) != 5 for v in starters.values()):
        return None
    rows = []
    closing = {t: list(starters[t]) for t in (home, away)}
    for per, pe in ev.groupby("period_number", sort=True):
        if per == 1:
            on = {t: list(starters[t]) for t in (home, away)}
        else:
            on = {home: [], away: []}
            entered = set()
            for typ, a1, a2, a3 in zip(pe.type_text, pe.a1, pe.a2, pe.a3):
                if typ == "Substitution":
                    if a2 is not None and a2 not in entered:
                        t = team_of.get(a2)
                        if t in on and a2 not in on[t]:
                            on[t].append(a2)
                    if a1 is not None:
                        entered.add(a1)
                    continue
                for a in (a1, a2, a3):
                    if a is not None and a not in entered:
                        t = team_of.get(a)
                        if t in on and a not in on[t]:
                            on[t].append(a)
            for t in (home, away):
                for a in closing[t]:
                    if len(on[t]) >= 5:
                        break
                    if a not in on[t] and a not in entered:
                        on[t].append(a)
                on[t] = on[t][:5]
        if any(len(on[t]) != 5 for t in (home, away)):
            return None
        acc = {"pts": {home: 0, away: 0}, "fga": {home: 0, away: 0}, "orb": {home: 0, away: 0}, "tov": {home: 0, away: 0},
               "fta": {home: 0, away: 0}}

        def flush():
            if not any(acc["fga"].values()) and not any(acc["fta"].values()) and not any(acc["tov"].values()):
                return
            poss = ((acc["fga"][home] - acc["orb"][home] + acc["tov"][home] + .44 * acc["fta"][home])
                    + (acc["fga"][away] - acc["orb"][away] + acc["tov"][away] + .44 * acc["fta"][away])) / 2
            rows.append((tuple(on[home]), tuple(on[away]), acc["pts"][home] - acc["pts"][away], poss))
        for r in pe.itertuples(index=False):
            if r.type_text == "Substitution":
                t = team_of.get(r.a1) or team_of.get(r.a2)
                if t in on and r.a2 in on[t] and r.a1 is not None and r.a1 not in on[t]:
                    flush()
                    for k in acc:
                        acc[k] = {home: 0, away: 0}
                    on[t] = [r.a1 if a == r.a2 else a for a in on[t]]
                continue
            t = _id(r.team_id)
            if t not in (home, away):
                continue
            typ = str(r.type_text)
            if "Free Throw" in typ:
                acc["fta"][t] += 1
            elif r.shooting_play:
                acc["fga"][t] += 1
            if typ.startswith("Offensive Rebound"):
                acc["orb"][t] += 1
            if "Turnover" in typ:
                acc["tov"][t] += 1
            if r.scoring_play and r.score_value == r.score_value:
                acc["pts"][t] += int(r.score_value)
        flush()
        closing = {t: list(on[t]) for t in (home, away)}
    return rows


def season_stints(pbp: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Stints (home five, away five, home margin, possessions) for one regular season."""
    ev = pbp[pd.to_numeric(pbp.season_type, errors="coerce") == 2].copy()
    for c, n in (("athlete_id_1", "a1"), ("athlete_id_2", "a2"), ("athlete_id_3", "a3")):
        ev[n] = pd.Series([_id(x) for x in ev[c]], index=ev.index, dtype=object)
    ev["seq"] = pd.to_numeric(ev.sequence_number, errors="coerce")
    ev = ev.sort_values(["game_id", "period_number", "seq"])
    box = players[pd.to_numeric(players.season_type, errors="coerce") == 2][["game_id", "athlete_id", "team_id", "starter"]].copy()
    box["athlete_id"] = pd.Series([_id(x) for x in box.athlete_id], index=box.index, dtype=object)
    box["team_id"] = pd.to_numeric(box.team_id, errors="coerce")
    box["starter"] = box.starter.astype(str).str.lower().eq("true")
    box["game_id"] = pd.to_numeric(box.game_id, errors="coerce")
    boxes = {g: b for g, b in box.groupby("game_id")}
    out = []
    for gid, g in ev.groupby("game_id", sort=False):
        b = boxes.get(pd.to_numeric(gid, errors="coerce"))
        res = game_stints(g, b) if b is not None else None
        if res:
            out.extend(res)
    S = pd.DataFrame(out, columns=["home5", "away5", "margin", "poss"])
    return S[S.poss > 0.5]


def fit(stints: list[tuple[pd.DataFrame, float]], prior: dict[int, float]) -> dict[int, float]:
    """stints: [(frame, weight)]. Returns athlete_id -> points per 100 possessions vs an average player."""
    S = pd.concat([f.assign(w=w) for f, w in stints if len(f)], ignore_index=True)
    ids = sorted({a for t in S.home5 for a in t} | {a for t in S.away5 for a in t})
    ix = {a: i for i, a in enumerate(ids)}
    n, m = len(S), len(ids)
    rows = np.repeat(np.arange(n), 11)
    cols = np.empty(n * 11, dtype=np.int64)
    vals = np.empty(n * 11)
    for j, (h, a) in enumerate(zip(S.home5, S.away5)):
        cols[j * 11:j * 11 + 5] = [ix[x] for x in h]
        cols[j * 11 + 5:j * 11 + 10] = [ix[x] for x in a]
        cols[j * 11 + 10] = m
        vals[j * 11:j * 11 + 5] = 1.0
        vals[j * 11 + 5:j * 11 + 10] = -1.0
        vals[j * 11 + 10] = 1.0
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(n, m + 1))
    y = 100 * S.margin.to_numpy(float) / S.poss.to_numpy(float)
    wt = S.poss.to_numpy(float) * S.w.to_numpy(float)
    XtW = X.T.multiply(wt).tocsr()
    A = (XtW @ X).toarray()
    b = XtW @ y
    pr = np.array([prior.get(a, 0.0) for a in ids])
    A[np.arange(m), np.arange(m)] += LAM
    b[:m] += LAM * pr
    sol = np.linalg.solve(A, b)
    return dict(zip(ids, sol[:m]))


def develop(rating: dict[int, float], first_season: dict[int, int], season: int) -> dict[int, float]:
    return {a: v + DEV_YOUNG * max(0, DEV_YEARS - (season - first_season.get(a, season))) for a, v in rating.items()}


def team_strength(current_roster: pd.DataFrame, rv: pd.DataFrame, rating: dict[int, float], teams: list[str]) -> pd.Series:
    """Projected team strength (centered) from current rosters, roster-step minutes (rv: athlete_id, minutes) and ratings."""
    r = current_roster[current_roster.team_abbreviation.isin(teams)].drop_duplicates(["team_abbreviation", "athlete_id"]).copy()
    r["aid"] = [_id(x) for x in r.athlete_id]
    mins = dict(zip([_id(x) for x in rv.athlete_id], rv.minutes))
    r["m"] = [min(float(mins.get(a, 0.0)), 2600.0) for a in r.aid]
    r["v"] = [rating.get(a, ROOKIE) for a in r.aid]
    r = r.sort_values(["team_abbreviation", "m"], ascending=[True, False]).groupby("team_abbreviation").head(12)

    def one(g):
        mm = g.m.to_numpy(float)
        if mm.sum() > 82 * 240:
            mm = mm * (82 * 240) / mm.sum()
        return float(np.sum(g.v.to_numpy(float) * mm) / (82 * 48))
    s = r.groupby("team_abbreviation").apply(one, include_groups=False).reindex(teams).fillna(0.0)
    return s - s.mean()


PO_K, PO_GAMMA, PO_CAP = 1.0, 1.5, 42 / 240
# Playoff rotation (14 Oct 2026, research/replay_nba.py BT_PO_K/BT_PO_GAMMA, 14 seasons 2013-2026): in playoff series each team
# plays at its regular rating + (top-8 rotation strength with minutes concentrated on the best-used players, power 1.5, cap
# 42 mpg - regular rotation strength). Futures log loss +0.0031 (90% -0.0003 to +0.0066, better 8/14); title 0.0907 -> 0.0827,
# conference 0.1808 -> 0.1729. TypeSafe 68% (over k 1.0 / power 1.0 and k 0.5).


def playoff_ratio(last_season_players: pd.DataFrame) -> dict[int, float]:
    """Last season's playoff / regular-season minutes per game (4+ playoff games, 20+ regular), clipped to [0.5, 1.5].
    Replay: scaling the playoff rotation's minutes by it +0.0011 (10/14; title 0.0827 -> 0.0800); e.g. managed stars
    (Wembanyama 28.6 regular, 34.1 playoff mpg) count for more in the playoffs."""
    d = last_season_players.copy()
    d["m"] = pd.to_numeric(d.minutes, errors="coerce")
    d["st"] = pd.to_numeric(d.season_type, errors="coerce")
    d = d[d.m > 0]
    d["aid"] = [_id(a) for a in d.athlete_id]
    po = d[d.st == 3].groupby("aid").m.agg(["mean", "size"])
    rs = d[d.st == 2].groupby("aid").m.agg(["mean", "size"])
    j = po.join(rs, lsuffix="_po", rsuffix="_rs", how="inner")
    j = j[(j.size_po >= 4) & (j.size_rs >= 20)]
    return (j.mean_po / j.mean_rs).clip(0.5, 1.5).to_dict()


def playoff_delta(mins: pd.DataFrame, rating: dict[int, float], teams: list[str], reg_minutes=None) -> pd.Series:
    """mins: team_abbreviation, athlete_id, m (playoff-role minutes); reg_minutes: regular-season minutes (default m).
    Returns centred per-team playoff strength change (points per 100)."""
    mins = mins.assign(reg=mins.m if reg_minutes is None else np.asarray(reg_minutes, float))
    out = {}
    for t, g in mins.groupby("team_abbreviation"):
        if t not in teams or g.m.sum() <= 0:
            continue
        r_all = np.array([rating.get(_id(a), ROOKIE) for a in g.athlete_id])
        reg = 5 * float(np.sum(g.reg.to_numpy(float) / max(g.reg.sum(), 1e-9) * r_all))
        g = g.sort_values("m", ascending=False)
        r = np.array([rating.get(_id(a), ROOKIE) for a in g.athlete_id])
        sh = g.m.to_numpy(float) / g.m.sum()
        top = sh[:8] ** PO_GAMMA
        top = top / top.sum()
        for _ in range(5):
            top = np.minimum(top, PO_CAP)
            top = top / top.sum()
        out[t] = PO_K * (5 * float(np.sum(top * r[:8])) - reg)
    s = pd.Series(out).reindex(teams).fillna(0.0)
    return s - s.mean()
