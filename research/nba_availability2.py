"""NBA availability layer, version 2 test (research). Responds to the external review of version 1.

Every input is built from games strictly before the predicted game:
- team membership: a player counts for a team if he has a box-score row (played or listed DNP) for it this season and
  his latest row is for that team, so a player traded away stops counting for his old team once he has appeared for
  the new one (fixes v1's bug of counting traded players as 'missing' for up to 10 games). Players hurt all season
  never appear, so the test cannot see those absences (the live injury report can) - conservative;
- player ability (per-36 game score, shrunk) and replacement level (previous season) use earlier games only;
- baseline: the share of the team's earlier games (same season weights as the team rating: 4 / 1 / 0.2 / 0.04)
  in which that member was missing. The adjustment is value x (missing now - baseline), so an absence the rating
  already reflects costs about nothing and a return gives an uplift (fixes double counting).
Variants:
  v1        version-1 values (this + 60% last season; usual minutes = team's last 10 games incl. zeros), no fixes
  v1_trade  v1 + membership fix
  v1_base   v1 + membership fix + baseline
  v2_base   ability and availability separated: ability from three seasons (1 / 0.6 / 0.36), minutes = average of his
            last 10 games played (any team) + membership fix + baseline
Usage: python research/nba_availability2.py <ratings_nba.csv> [<match_nba.csv>]
"""
import collections
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import match_vs_market as M  # noqa: E402
import nba as N  # noqa: E402

FIRST, LAST = 2005, N.season_end_year() - 1
ROT_MIN, ROT_GAMES, SHRINK_MIN = 12.0, 10, 400.0
RATING_W = {0: 4.0, 1: 1.0, 2: 0.2, 3: 0.04, 4: 0.008}
ABILITY_W = {"v1": {0: 1.0, 1: 0.6}, "v2": {0: 1.0, 1: 0.6, 2: 0.36}}


def load():
    frames = []
    for y in range(FIRST - 3, LAST + 1):
        p = N._download("espn_nba_player_boxscores", f"player_box_{y}.csv", 24 * 365, required=False)
        if not p:
            continue
        d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in {
            "game_id", "season", "season_type", "game_date", "athlete_id", "team_abbreviation", "minutes", "field_goals_made",
            "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds", "defensive_rebounds",
            "assists", "steals", "blocks", "turnovers", "fouls", "points", "did_not_play"})
        frames.append(d[pd.to_numeric(d.season_type, errors="coerce") == 2])
    d = pd.concat(frames, ignore_index=True)
    d = d[d.team_abbreviation.isin(N.TEAMS)].copy()
    for c in ("minutes", "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
              "defensive_rebounds", "assists", "steals", "blocks", "turnovers", "fouls", "points"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["played"] = (d.minutes > 0) & ~d.did_not_play.astype(str).str.lower().eq("true")
    d["gmsc"] = (d.points + .4 * d.field_goals_made - .7 * d.field_goals_attempted - .4 * (d.free_throws_attempted - d.free_throws_made)
                 + .7 * d.offensive_rebounds + .3 * d.defensive_rebounds + d.steals + .7 * d.assists + .7 * d.blocks - .4 * d.fouls - d.turnovers)
    d["date"] = pd.to_datetime(d.game_date)
    d["season"] = pd.to_numeric(d.season, errors="coerce").astype(int)
    d["athlete_id"] = d.athlete_id.astype(str)
    return d.sort_values(["date", "game_id"])


def run(d):
    played = d[d.played]
    rep = played.groupby("season").apply(lambda x: np.nanpercentile((x.gmsc / x.minutes * 36)[x.minutes >= 10], 30), include_groups=False)
    sums = collections.defaultdict(lambda: [0.0, 0.0])          # (pid, season) -> [gmsc, minutes] played
    last_team = {}                                               # pid -> team of latest row
    last_mins = collections.defaultdict(lambda: collections.deque(maxlen=ROT_GAMES))   # minutes in games played
    team_hist = collections.defaultdict(list)                    # team -> list of {pid: minutes} for v1 usual minutes
    season_members = collections.defaultdict(set)              # (team, season) -> players with a row this season
    base = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))  # (pid,team) -> season -> [member, missed]
    out = []
    for gid, G in d.groupby("game_id", sort=False):
        y = int(G.season.iloc[0])
        r = float(rep.get(y - 1, rep.median()))
        if y >= FIRST:
            for team, x in G.groupby("team_abbreviation"):
                present = set(x[x.played].athlete_id)
                row = dict(game_id=gid, team=team, season=y, date=x.date.iloc[0])

                def ability(pid, mode):
                    g = m = 0.0
                    for k, w in ABILITY_W[mode].items():
                        s = sums.get((pid, y - k))
                        if s:
                            g += w * s[0]
                            m += w * s[1]
                    return (g + r / 36 * SHRINK_MIN) / (m + SHRINK_MIN) * 36 - r

                def baseline(pid):
                    h = base.get((pid, team))
                    if not h:
                        return 0.0
                    num = sum(RATING_W[y - s] * v[1] for s, v in h.items() if 0 <= y - s <= 4)
                    den = sum(RATING_W[y - s] * v[0] for s, v in h.items() if 0 <= y - s <= 4)
                    return num / den if den else 0.0

                # v1 usual minutes: team's previous 10 games, missed games count as zero
                hist = team_hist[team][-ROT_GAMES:]
                usual = collections.Counter()
                for h in hist:
                    usual.update(h)
                n_h = max(1, len(hist))
                v1_rot = {p: mins / n_h for p, mins in usual.items() if mins / n_h >= ROT_MIN}
                members = {p for p in season_members[(team, y)] if last_team.get(p) == team}
                res = {"v1": 0.0, "v1_trade": 0.0, "v1_base": 0.0, "v2_base": 0.0}
                for p, mins in v1_rot.items():
                    val = ability(p, "v1") * mins / 48
                    miss = p not in present
                    res["v1"] += val * miss
                    if p in members:
                        res["v1_trade"] += val * miss
                        res["v1_base"] += val * (miss - baseline(p))
                for p in members:
                    lm = last_mins.get(p)
                    if not lm:
                        continue
                    mins = sum(lm) / len(lm)
                    if mins < ROT_MIN:
                        continue
                    miss = p not in present
                    res["v2_base"] += ability(p, "v2") * mins / 48 * (miss - baseline(p))
                row.update(res)
                out.append(row)
                # update baselines for members of this game
                for p in members | set(x.athlete_id):
                    b = base[(p, team)][y]
                    b[0] += 1
                    b[1] += p not in present
        # update state after the game
        for team, x in G.groupby("team_abbreviation"):
            team_hist[team].append(dict(zip(x[x.played].athlete_id, x[x.played].minutes)))
        for rr in G.itertuples():
            last_team[rr.athlete_id] = rr.team_abbreviation
            season_members[(rr.team_abbreviation, rr.season)].add(rr.athlete_id)
            if rr.played:
                s = sums[(rr.athlete_id, rr.season)]
                s[0] += rr.gmsc
                s[1] += rr.minutes
                last_mins[rr.athlete_id].append(rr.minutes)
        if G.date.iloc[0].month == 4 and G.date.iloc[0].day == 1:
            print("through", y, flush=True)
    return pd.DataFrame(out)


def test(A, ratings_csv, market_csv=None):
    R = pd.read_csv(ratings_csv, parse_dates=["date"])
    s_eff = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
    from scipy.stats import norm
    R["m"] = norm.ppf(R.p_model.clip(1e-4, 1 - 1e-4)) * s_eff
    A["date"] = pd.to_datetime(A.date).dt.normalize()
    variants = ["v1", "v1_trade", "v1_base", "v2_base"]
    h = A.rename(columns={"team": "home", **{v: v + "_h" for v in variants}})[["date", "home"] + [v + "_h" for v in variants]]
    a = A.rename(columns={"team": "away", **{v: v + "_a" for v in variants}})[["date", "away"] + [v + "_a" for v in variants]]
    R = R.merge(h, on=["date", "home"], how="left").merge(a, on=["date", "away"], how="left").fillna(0)
    R = R.dropna(subset=["m", "y"])
    seasons = sorted(R.season.unique())
    res = {}
    K = None
    if market_csv and os.path.exists(market_csv):
        K = pd.read_csv(market_csv, parse_dates=["date"])[["date", "home", "away", "p_market"]].dropna()
    for v in variants:
        R["d"] = R[v + "_h"] - R[v + "_a"]
        rows = []
        for y in seasons[3:]:
            tr, te = R[R.season < y], R[R.season == y]
            best = max(np.arange(0, 2.01, 0.05), key=lambda b: -M.ll(M.phi((tr.m - b * tr.d) / s_eff), tr.y.values))
            p = M.phi((te.m - best * te.d) / s_eff)
            R.loc[te.index, "p_" + v] = p
            rows.append(dict(season=y, beta=float(best), n=len(te), base=M.ll(M.phi(te.m / s_eff), te.y.values), adj=M.ll(p, te.y.values)))
        T = pd.DataFrame(rows)
        res[v] = {"test_seasons": f"{int(T.season.min())}-{int(T.season.max())}", "games": int(T.n.sum()),
                  "no_adjustment": round(float((T.base * T.n).sum() / T.n.sum()), 4),
                  "with_adjustment": round(float((T.adj * T.n).sum() / T.n.sum()), 4),
                  "seasons_better": f"{int((T.adj < T.base).sum())} of {len(T)}", "beta_latest": float(T.beta.iloc[-1])}
        sub = R[R.season >= seasons[3]]
        late = sub[sub.frac >= 0.5]
        res[v]["second_half_of_season"] = {"no_adjustment": round(M.ll(late.p_model.values, late.y.values), 4),
                                           "with_adjustment": round(M.ll(late["p_" + v].values, late.y.values), 4)}
        if K is not None:
            J = sub.merge(K, on=["date", "home", "away"], how="inner")
            res[v]["vs_closing_odds"] = {"games": int(len(J)), "ours": round(M.ll(J["p_" + v].values, J.y.values), 4),
                                         "ours_no_adjustment": round(M.ll(J.p_model.values, J.y.values), 4),
                                         "market": round(M.ll(J.p_market.values, J.y.values), 4)}
    return res, R


if __name__ == "__main__":
    tmp = os.environ.get("TMPDIR", "/tmp")
    cache = os.path.join(tmp, "nba_missing_v2.csv")
    if os.path.exists(cache):
        A = pd.read_csv(cache)
    else:
        A = run(load())
        A.to_csv(cache, index=False)
    res, R = test(A, sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    R.to_csv(os.path.join(tmp, "nba_avail2_games.csv"), index=False)
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(ROOT, "model", "availability_nba_v2.json"), "w"), indent=1)
