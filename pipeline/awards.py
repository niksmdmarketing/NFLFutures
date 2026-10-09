"""Award probabilities from frozen conditional-logit models (trained on AP winners 2010-2025).

Each candidate's final regular-season line = stats to date + remaining games x blended per-game rate, with
availability: listed Out on the latest injury report -> misses the next game; on a reserve list (IR, PUP,
etc.) -> 25% chance of playing each remaining game; otherwise 90%. Team win% comes from the season simulation,
so team success and award chances move together.
"""
import json
import os
import re

import numpy as np
import pandas as pd
from scipy.special import logsumexp

from common import FIX, MODEL, TEAMS, TIX, current_season_cached, download, log

S = json.load(open(os.path.join(MODEL, "settings.json")))
AW = S["awards"]
COUNT = ["attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries", "rushing_yards", "rushing_tds",
         "receptions", "receiving_yards", "receiving_tds", "def_sacks", "def_interceptions", "def_tackles_for_loss",
         "def_pass_defended", "def_fumbles_forced", "def_tackles_solo", "def_tackle_assists", "def_qb_hits"]
EPA = ["passing_epa", "rushing_epa", "receiving_epa"]
RATE_SD, P_AVAIL, PRIOR_G = 0.22, 0.9, 6.0
NAMES = {"MVP": "Most Valuable Player", "OPOY": "Offensive Player of the Year", "DPOY": "Defensive Player of the Year",
         "OROY": "Offensive Rookie of the Year", "DROY": "Defensive Rookie of the Year",
         "CPOY": "Comeback Player of the Year", "COY": "Coach of the Year"}


def season_stats(y):
    path = download(f"stats_player/stats_player_week_{y}.csv", max_age_h=2 if y >= current_season_cached() else 24 * 365)
    d = pd.read_csv(path, low_memory=False)
    d = d[d.season_type == "REG"].copy()
    d["team"] = d.team.replace(FIX)
    for c in COUNT + EPA:
        if c not in d.columns:
            d[c] = 0.0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    a = d.groupby("player_id").agg(name=("player_display_name", "first"), pos=("position", "first"),
                                   grp=("position_group", "first"), team=("team", lambda s: s.iloc[-1]),
                                   games=("week", "nunique"), **{c: (c, "sum") for c in COUNT + EPA}).reset_index()
    a["is_qb"] = (a.pos == "QB").astype(float)
    a["scrim"] = a.rushing_yards + a.receiving_yards
    a["tds"] = a.passing_tds + a.rushing_tds + a.receiving_tds
    a["epa"] = a.passing_epa + a.rushing_epa + a.receiving_epa
    a["tackles"] = a.def_tackles_solo + a.def_tackle_assists
    a["is_def"] = a.grp.isin(["DL", "LB", "DB"]).astype(float)
    a["nonqb_scrim"] = a.scrim * (1 - a.is_qb)
    return a


def roster_info(y):
    path = download(f"rosters/roster_{y}.csv", required=False)
    if not path:
        return set(), {}
    r = pd.read_csv(path, low_memory=False)
    rook = set(r[(r.get("rookie_year") == y)].gsis_id.dropna()) if "rookie_year" in r else set()
    if "years_exp" in r:
        rook |= set(r[r.years_exp == 0].gsis_id.dropna())
    status = {}
    if "status" in r.columns:
        last = r.sort_values("week").drop_duplicates("gsis_id", keep="last") if "week" in r else r
        status = dict(zip(last.gsis_id, last.status.fillna("")))
    return rook, status


def pool(a, award, s=0.6):
    off = ((a.is_qb == 1) & (a.attempts >= 250 * s)) | ((a.is_qb == 0) & (a.is_def == 0) & ((a.scrim >= 1000 * s) | (a.tds >= 10 * s)))
    dfn = (a.is_def == 1) & ((a.def_sacks >= 6 * s) | (a.def_interceptions >= 4 * s) | (a.def_tackles_for_loss >= 12 * s) | (a.tackles >= 100 * s))
    if award in ("MVP", "OPOY"):
        return a[off]
    if award == "DPOY":
        return a[dfn]
    if award == "OROY":
        return a[(a.rookie == 1) & (a.is_def == 0) & (((a.is_qb == 1) & (a.attempts >= 150 * s)) | ((a.is_qb == 0) & (a.scrim >= 400 * s)))]
    if award == "DROY":
        return a[(a.rookie == 1) & (a.is_def == 1) & ((a.def_sacks >= 3 * s) | (a.def_interceptions >= 2 * s) | (a.tackles >= 50 * s) | (a.def_tackles_for_loss >= 6 * s))]
    if award == "CPOY":
        return a[(off | dfn) & (a.prev_games <= 10) & (a.rookie == 0)]


def project(c, ctx, NS, rng):
    prev = ctx["prev"]
    n = len(c)
    rem = np.array([max(ctx["games"][t] - ctx["played"][t], 0) for t in c.team])
    out_now = c.out_now.values.astype(int)
    p_av = np.where(c.reserve.values == 1, 0.25, P_AVAIL)
    mult = np.exp(rng.normal(0, RATE_SD, (n, NS)) - RATE_SD ** 2 / 2)
    gp = rng.binomial(np.maximum(rem - out_now, 0)[:, None].repeat(NS, 1), p_av[:, None])
    sim = {}
    for col in COUNT + EPA:
        cr = c[col].values / np.maximum(c.games.values, 1)
        pv = c.player_id.map(prev[col] / prev.games.clip(lower=1)).values.astype(float)
        pg = c.player_id.map(prev.games).fillna(0).values
        has = ~np.isnan(pv) & (pg >= 6)
        rate = np.where(has, (c.games.values * cr + PRIOR_G * np.nan_to_num(pv)) / (c.games.values + PRIOR_G), 0.9 * cr)
        sim[col] = c[col].values[:, None] + rate[:, None] * mult * gp
    o = dict(sim)
    o["scrim"] = sim["rushing_yards"] + sim["receiving_yards"]
    o["tds"] = sim["passing_tds"] + sim["rushing_tds"] + sim["receiving_tds"]
    o["epa"] = sim["passing_epa"] + sim["rushing_epa"] + sim["receiving_epa"]
    o["tackles"] = sim["def_tackles_solo"] + sim["def_tackle_assists"]
    o["nonqb_scrim"] = o["scrim"] * (1 - c.is_qb.values[:, None])
    o["wpct"] = ctx["WPCT"][:NS, [TIX[t] for t in c.team]].T
    for k in ("is_qb", "is_def", "prev_games"):
        o[k] = np.repeat(c[k].values[:, None], NS, 1)
    return o


def detail(r):
    if r.is_def == 1:
        return f"{r.def_sacks:.1f} sacks, {int(r.def_interceptions)} INT, {int(r.def_tackles_for_loss)} TFL, {int(r.tackles)} tackles"
    if r.is_qb == 1:
        return f"{int(r.passing_yards)} pass yds, {int(r.passing_tds)} TD, {int(r.passing_interceptions)} INT, {int(r.rushing_yards)} rush yds"
    return f"{int(r.rushing_yards + r.receiving_yards)} scrimmage yds, {int(r.rushing_tds + r.receiving_tds)} TD, {int(r.receptions)} rec"


def team_record(games, y):
    g = games[(games.season == y) & (games.game_type == "REG") & games.result.notna()]
    w = {t: 0.0 for t in TEAMS}; n = {t: 0 for t in TEAMS}
    for h, a, r in zip(g.home_team, g.away_team, g.result):
        if h not in w or a not in w:
            continue
        n[h] += 1; n[a] += 1
        if r > 0: w[h] += 1
        elif r < 0: w[a] += 1
        else: w[h] += .5; w[a] += .5
    return {t: (w[t] / n[t] if n[t] else 0.5) for t in TEAMS}, w


def build(season, games, sim_res, injuries):
    rng = np.random.default_rng(11)
    W = sim_res["wins"][:4000].astype(float)
    gpt = sim_res["games_per_team"]
    WPCT = W / np.maximum(gpt, 1)[None, :]
    g = games[(games.season == season) & (games.game_type == "REG")]
    played = {t: int((((g.home_team == t) | (g.away_team == t)) & g.result.notna()).sum()) for t in TEAMS}
    ngames = {t: int(((g.home_team == t) | (g.away_team == t)).sum()) for t in TEAMS}
    cur = season_stats(season)
    cur = cur[cur.team.isin(TIX)].reset_index(drop=True)
    prev = season_stats(season - 1).set_index("player_id")
    rook, status = roster_info(season)
    cur["prev_games"] = cur.player_id.map(prev.games).fillna(0.0)
    cur["rookie"] = cur.player_id.isin(rook).astype(float)
    cur["reserve"] = cur.player_id.map(lambda p: int(str(status.get(p, "")).upper() in ("RES", "PUP", "NON", "SUS", "INA"))).astype(int)
    out_ids = set()
    if injuries is not None and not injuries.empty:
        wk = injuries.week.max()
        out_ids = set(injuries[(injuries.week == wk) & (injuries.report_status == "Out")].gsis_id)
    cur["out_now"] = cur.player_id.isin(out_ids).astype(int)
    ctx = {"prev": prev, "games": ngames, "played": played, "WPCT": WPCT}
    result = {}
    for a in ["MVP", "OPOY", "DPOY", "OROY", "DROY", "CPOY"]:
        p = AW[a]
        light = project(cur, ctx, 150, rng)
        e = cur.copy()
        for k in ("attempts", "def_sacks", "def_interceptions", "def_tackles_for_loss", "passing_yards"):
            e[k] = light[k].mean(1)
        e["scrim"], e["tds"], e["tackles"] = light["scrim"].mean(1), light["tds"].mean(1), light["tackles"].mean(1)
        c = cur.loc[pool(e, a).index].reset_index(drop=True)
        if c.empty:
            result[a] = {"title": NAMES[a], "candidates": [], "field": 1.0}
            continue
        sim = project(c, ctx, W.shape[0], rng)
        X = np.stack([(sim[f] - p["mu"][i]) / p["sd"][i] for i, f in enumerate(p["feats"])], axis=-1)
        eta = (X @ np.array(p["b"])) / p["T"]
        prob = np.exp(eta - logsumexp(eta, axis=0, keepdims=True)).mean(1)
        c["prob"] = prob
        c = c.sort_values("prob", ascending=False)
        result[a] = {"title": NAMES[a], "eval": S["awards_eval"].get(a),
                     "candidates": [{"name": r["name"], "team": r.team, "pos": r.pos, "prob": round(float(r.prob), 4),
                                     "detail": detail(r) + (" · listed Out this week" if r.out_now else "") + (" · on a reserve list" if r.reserve else "")}
                                    for _, r in c.head(15).iterrows()],
                     "field": round(float(c.prob.iloc[15:].sum()), 4)}
        log("award", a, result[a]["candidates"][0]["name"] if result[a]["candidates"] else "-")
    # Coach of the Year
    p = AW["COY"]
    prev_pct, _ = team_record(games, season - 1)
    exp = np.array([0.5 + 0.5 * (prev_pct[t] - 0.5) for t in TEAMS])
    X = np.stack([(WPCT - p["mu"][0]) / p["sd"][0], (WPCT - exp[None, :] - p["mu"][1]) / p["sd"][1]], axis=-1)
    eta = (X @ np.array(p["b"])) / p["T"]
    prob = np.exp(eta - logsumexp(eta, axis=1, keepdims=True)).mean(0)
    coach = {}
    for _, r in g.sort_values("week").iterrows():
        coach[r.home_team] = r.home_coach; coach[r.away_team] = r.away_coach
    cands = sorted(({"name": coach.get(t, t), "team": t, "pos": "HC", "prob": round(float(prob[TIX[t]]), 4),
                     "detail": f"{W[:, TIX[t]].mean():.1f} projected wins (last season {prev_pct[t] * ngames[t]:.0f})"}
                    for t in TEAMS), key=lambda x: -x["prob"])
    result["COY"] = {"title": NAMES["COY"], "eval": S["awards_eval"].get("COY"), "candidates": cands[:15],
                     "field": round(float(sum(x["prob"] for x in cands[15:])), 4)}
    return result
