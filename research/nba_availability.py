"""NBA player-value layer, built and tested on history (research).

Player value: game score per 36 minutes (box-score production, Hollinger) relative to a replacement-level rotation
player, from games BEFORE each date only: current season to date blended with last season, shrunk toward replacement
for small samples.
Team adjustment for a game: for every rotation player (averaging 12+ minutes over the team's previous 10 games) who did
not play, add (his value - replacement) x his usual minutes / 48. "Did not play" comes from the box score, which is close
to the pre-game injury report / lineup (the live version will use the official injury report).
Test: home-win probability = Phi((our rating margin - beta x (home missing - away missing)) / s), beta fitted on earlier
seasons only, scored on later seasons against outcomes and against closing odds.
Usage: python research/nba_availability.py <ratings_nba.csv> [<match_nba.csv with p_market>]
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import match_vs_market as M  # noqa: E402
import nba as N  # noqa: E402

FIRST, LAST = 2004, N.season_end_year() - 1
ROT_MIN, ROT_GAMES = 12.0, 10
SHRINK_MIN = 400.0


def load():
    frames = []
    for y in range(FIRST - 1, LAST + 1):
        p = N._download("espn_nba_player_boxscores", f"player_box_{y}.csv", 24 * 365, required=False)
        if not p:
            continue
        d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in {
            "game_id", "season", "season_type", "game_date", "athlete_id", "athlete_display_name", "team_abbreviation", "minutes",
            "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
            "defensive_rebounds", "assists", "steals", "blocks", "turnovers", "fouls", "points", "did_not_play", "reason"})
        frames.append(d[pd.to_numeric(d.season_type, errors="coerce") == 2])
    d = pd.concat(frames, ignore_index=True)
    d["team"] = d.team_abbreviation
    d = d[d.team.isin(N.TEAMS)].copy()
    for c in ("minutes", "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
              "defensive_rebounds", "assists", "steals", "blocks", "turnovers", "fouls", "points"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["played"] = (d.minutes > 0) & ~d.did_not_play.astype(str).str.lower().eq("true")
    d["gmsc"] = (d.points + .4 * d.field_goals_made - .7 * d.field_goals_attempted - .4 * (d.free_throws_attempted - d.free_throws_made)
                 + .7 * d.offensive_rebounds + .3 * d.defensive_rebounds + d.steals + .7 * d.assists + .7 * d.blocks - .4 * d.fouls - d.turnovers)
    d["date"] = pd.to_datetime(d.game_date)
    d["season"] = pd.to_numeric(d.season, errors="coerce").astype(int)
    return d.sort_values(["date", "game_id"])


def adjustments(d):
    """team-game -> missing value (in gmsc36 x minute-share units) using only earlier games."""
    out = []
    played = d[d.played]
    rep = played.groupby("season").apply(lambda x: np.nanpercentile((x.gmsc / x.minutes * 36)[x.minutes >= 10], 30), include_groups=False)
    for y in range(FIRST, LAST + 1):
        cur = d[d.season == y]
        prev = played[played.season == y - 1]
        pv = prev.groupby("athlete_id").agg(g=("gmsc", "sum"), m=("minutes", "sum"))
        r = float(rep.get(y - 1, rep.median()))
        cum = pv.copy()
        cum["g"] *= 0.6      # last season counts 60%
        cum["m"] *= 0.6
        team_games = {}
        for gid, G in cur.groupby("game_id", sort=False):
            for team, x in G.groupby("team"):
                hist = team_games.get(team, [])
                miss = 0.0
                if hist:
                    recent = pd.concat(hist[-ROT_GAMES:])
                    usual = recent.groupby("athlete_id").minutes.sum() / min(len(hist), ROT_GAMES)
                    rot = usual[usual >= ROT_MIN]
                    present = set(x[x.played].athlete_id)
                    for pid, mins in rot.items():
                        if pid in present:
                            continue
                        g, m = (cum.g.get(pid, 0.0), cum.m.get(pid, 0.0)) if pid in cum.index else (0.0, 0.0)
                        v = (g + r / 36 * SHRINK_MIN) / (m + SHRINK_MIN) * 36       # shrunk gmsc36
                        miss += (v - r) * mins / 48
                out.append(dict(game_id=gid, team=team, season=y, date=x.date.iloc[0], missing=miss))
                team_games.setdefault(team, []).append(x[x.played][["athlete_id", "minutes"]])
            # update player cumulative totals after the game
            pl = G[G.played].groupby("athlete_id").agg(g=("gmsc", "sum"), m=("minutes", "sum"))
            cum = cum.add(pl, fill_value=0)
        print("season", y, flush=True)
    return pd.DataFrame(out)


def test(A, ratings_csv, market_csv=None):
    import nba_backtest as B
    R = pd.read_csv(ratings_csv, parse_dates=["date"])
    s_eff = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
    R["m"] = norm.ppf(R.p_model.clip(1e-4, 1 - 1e-4)) * s_eff
    A["date"] = pd.to_datetime(A.date).dt.normalize()
    h = A.rename(columns={"team": "home", "missing": "miss_h"})[["date", "home", "miss_h"]]
    a = A.rename(columns={"team": "away", "missing": "miss_a"})[["date", "away", "miss_a"]]
    R = R.merge(h, on=["date", "home"], how="left").merge(a, on=["date", "away"], how="left").fillna({"miss_h": 0, "miss_a": 0})
    R["d"] = R.miss_h - R.miss_a
    R = R.dropna(subset=["m", "d", "y"])
    res, rows = {}, []
    seasons = sorted(R.season.unique())
    for y in seasons[3:]:
        tr, te = R[R.season < y], R[R.season == y]
        best = max(np.arange(0, 2.01, 0.1), key=lambda b: -M.ll(M.phi((tr.m - b * tr.d) / s_eff), tr.y.values))
        rows.append(dict(season=y, beta=float(best), n=len(te), base=M.ll(M.phi(te.m / s_eff), te.y.values),
                         adj=M.ll(M.phi((te.m - best * te.d) / s_eff), te.y.values)))
    T = pd.DataFrame(rows)
    res["chronological"] = {"seasons": f"{int(T.season.min())}-{int(T.season.max())}", "games": int(T.n.sum()),
                            "base": round(float((T.base * T.n).sum() / T.n.sum()), 4), "with_availability": round(float((T.adj * T.n).sum() / T.n.sum()), 4),
                            "seasons_better": int((T.adj < T.base).sum()), "seasons": int(len(T)), "beta_latest": float(T.beta.iloc[-1])}
    beta = float(T.beta.iloc[-1])
    R["p_adj"] = M.phi((R.m - beta * R.d) / s_eff)
    # stage view and the biggest-absence games
    R["stage"] = R.frac.map(M.stage_of)
    res["by_stage"] = {st: {"base": round(M.ll(x.p_model.values, x.y.values), 4), "with_availability": round(M.ll(x.p_adj.values, x.y.values), 4), "games": int(len(x))}
                       for st, x in R[R.season >= seasons[3]].groupby("stage")}
    big = R[(R.d.abs() > R.d.abs().quantile(0.9)) & (R.season >= seasons[3])]
    res["games_with_big_absences"] = {"base": round(M.ll(big.p_model.values, big.y.values), 4), "with_availability": round(M.ll(big.p_adj.values, big.y.values), 4), "games": int(len(big))}
    if market_csv and os.path.exists(market_csv):
        K = pd.read_csv(market_csv, parse_dates=["date"])[["date", "home", "away", "p_market"]]
        J = R.merge(K, on=["date", "home", "away"], how="inner").dropna(subset=["p_market"])
        J = J[J.season >= seasons[3]]
        out, _ = M.analyse(J.assign(p_model=J.p_adj)[["season", "frac", "y", "p_model", "p_market"]])
        res["vs_market_with_availability"] = {"games": int(len(J)), "ours_before": round(M.ll(J.p_model.values, J.y.values), 4),
                                              "ours_after": round(M.ll(J.p_adj.values, J.y.values), 4), "market": round(M.ll(J.p_market.values, J.y.values), 4),
                                              "pooled": out.get("overall"), "weight_on_ours_by_stage": {k: v["weight_on_model"] for k, v in out["by_stage"].items()}}
    # points scale: gmsc-based units -> points of margin
    res["points_per_unit"] = round(beta, 2)
    return res, R


if __name__ == "__main__":
    tmp = os.environ.get("TMPDIR", "/tmp")
    cache = os.path.join(tmp, "nba_missing.csv")
    if os.path.exists(cache):
        A = pd.read_csv(cache)
    else:
        A = adjustments(load())
        A.to_csv(cache, index=False)
    res, R = test(A, sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    R.to_csv(os.path.join(tmp, "nba_avail_games.csv"), index=False)
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(ROOT, "model", "availability_nba.json"), "w"), indent=1)
