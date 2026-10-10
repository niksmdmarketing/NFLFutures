"""NBA availability: unshrunk vs shrunk absence baselines on identical, timestamp-safe pre-game observations.

Observations: for every regular-season game, the latest official NBA injury report published (by file-name time and
upload time) at least 60 minutes before tip-off (research/nba_official_pregame.py output, market-data branch).
Everything else (player ability, minutes, membership, baselines) is built from games strictly before the predicted game.

For each team-game the adjustment is the sum over rotation members (12+ minutes in their last 10 games played) of
    value x (expected miss - baseline)
with value = ability per 36 above replacement x minutes / 48. Variants differ ONLY in the baseline and in what an
unlisted player counts as:
  R-unshrunk  research rule: unlisted = expected miss 0; baseline = weighted share of the team's earlier games he
              missed (rating weights 4/1/0.2/0.04), 0 when he has no history with the team
  R-shrunk    research rule; baseline shrunk toward the league absence rate with 20 current-season games of weight
  L-live      live rule: unlisted players cost 0 (their availability is what the rating already reflects); listed
              players cost value x (p_miss - baseline), baseline unshrunk, new-to-team players get their typical rate
              (three seasons, shrunk with 20 games toward the league rate) - exactly pipeline/nba_avail.py
  L-shrunk    live rule with the shrunk baseline for everyone
Status miss chances: calibrated walk-forward from the same pre-game reports (earlier seasons only; the first test
season uses the first collected season as calibration only). The points scale is also fitted walk-forward on earlier
pre-game seasons. Scored by season, overall, and on two subsets of games: a long-term absence on either team (a member
worth 1+ point listed Out who had already missed 10+ straight team games) and a returning player on either team (a
member worth 1+ point who missed 3+ straight games before and is not listed Out/Doubtful).
Usage: python research/nba_shrink_compare.py <ratings_nba.csv> <dir with pregame_*.csv.gz> <out.json>
"""
import collections
import glob
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
import nba_availability2 as V2  # noqa: E402
import nba_official as O  # noqa: E402

RATING_W = V2.RATING_W
ABILITY_W = V2.ABILITY_W["v2"]
PRIOR_GAMES = 20.0
VARIANTS = ["R-unshrunk", "R-shrunk", "L-live", "L-shrunk"]
STATUSES = ("Out", "Doubtful", "Questionable", "Probable", "Available")


def load_pregame(d, folder):
    files = sorted(glob.glob(os.path.join(folder, "pregame_*.csv.gz")))
    P = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    names = d.drop_duplicates(["season", "athlete_id"])
    key = collections.defaultdict(set)
    for r in names.itertuples():
        key[(r.season, O.name_key(r.athlete_display_name))].add(r.athlete_id)
    rep = {}            # game_id -> {"teams": {team: {pid: status}}, "report_et":...}
    hit = miss = 0
    for r in P.itertuples():
        gid = str(r.game_id)
        e = rep.setdefault(gid, {"teams": collections.defaultdict(dict), "report": getattr(r, "report_et", None)})
        if not isinstance(getattr(r, "player", None), str) or r.status not in STATUSES:
            continue
        ids = key.get((int(r.season), O.player_key(r.player)), set())
        if len(ids) == 1:
            e["teams"][r.team][next(iter(ids))] = r.status
            hit += 1
        else:
            miss += 1
    covered = {g for g, e in rep.items() if isinstance(e["report"], str)}
    print("pre-game report rows matched", hit, "unmatched", miss, "games with a report", len(covered), flush=True)
    return rep, covered, {"rows_matched": hit, "rows_unmatched": miss, "games_with_report": len(covered),
                          "seasons": sorted(int(s) for s in P.season.unique())}


def run(d, rep, covered):
    played = d[d.played]
    replv = played.groupby("season").apply(lambda x: np.nanpercentile((x.gmsc / x.minutes * 36)[x.minutes >= 10], 30), include_groups=False)
    sums = collections.defaultdict(lambda: [0.0, 0.0])
    last_team, season_members = {}, collections.defaultdict(set)
    last_mins = collections.defaultdict(lambda: collections.deque(maxlen=10))
    base = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))     # (pid, team) -> season -> [member, missed]
    alln = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))     # pid -> season -> [member, missed]
    streak = collections.defaultdict(int)                                                   # (pid, team) -> straight games missed
    league = [0.0, 0.0]
    obs = []          # one row per member in covered games: inputs needed by every variant + status calibration
    for gid, G in d.groupby("game_id", sort=False):
        y = int(G.season.iloc[0])
        r = float(replv.get(y - 1, replv.median()))
        if str(gid) in covered:
            lr = league[1] / league[0] if league[0] else 0.12
            for team, x in G.groupby("team_abbreviation"):
                present = set(x[x.played].athlete_id)
                listed = rep[str(gid)]["teams"].get(team, {})
                for p in season_members[(team, y)]:
                    if last_team.get(p) != team or not last_mins.get(p):
                        continue
                    mins = sum(last_mins[p]) / len(last_mins[p])
                    if mins < V2.ROT_MIN:
                        continue
                    g = m = 0.0
                    for k, w in ABILITY_W.items():
                        s = sums.get((p, y - k))
                        if s:
                            g += w * s[0]
                            m += w * s[1]
                    ability = (g + r / 36 * V2.SHRINK_MIN) / (m + V2.SHRINK_MIN) * 36 - r
                    h = base.get((p, team), {})
                    num = sum(RATING_W[y - s] * v[1] for s, v in h.items() if 0 <= y - s <= 4)
                    den = sum(RATING_W[y - s] * v[0] for s, v in h.items() if 0 <= y - s <= 4)
                    a = alln.get(p, {})
                    tm = sum(ABILITY_W.get(y - s, 0) * v[0] for s, v in a.items())
                    tx = sum(ABILITY_W.get(y - s, 0) * v[1] for s, v in a.items())
                    typical = (tx + PRIOR_GAMES * lr) / (tm + PRIOR_GAMES)
                    obs.append(dict(game_id=str(gid), season=y, date=x.date.iloc[0], team=team, pid=p,
                                    value=ability * mins / 48, num=num, den=den, lr=lr, typical=typical,
                                    status=listed.get(p), missed=int(p not in present), streak=streak[(p, team)]))
        for team, x in G.groupby("team_abbreviation"):
            present = set(x[x.played].athlete_id)
            members = {p for p in season_members[(team, y)] if last_team.get(p) == team}
            for p in members | set(x.athlete_id):
                b = base[(p, team)][y]
                b[0] += 1
                b[1] += p not in present
                c = alln[p][y]
                c[0] += 1
                c[1] += p not in present
                league[0] += 1
                league[1] += p not in present
                streak[(p, team)] = streak[(p, team)] + 1 if p not in present else 0
        for rr in G.itertuples():
            last_team[rr.athlete_id] = rr.team_abbreviation
            season_members[(rr.team_abbreviation, rr.season)].add(rr.athlete_id)
            if rr.played:
                s = sums[(rr.athlete_id, rr.season)]
                s[0] += rr.gmsc
                s[1] += rr.minutes
                last_mins[rr.athlete_id].append(rr.minutes)
    return pd.DataFrame(obs)


def p_miss_table(O_, seasons):
    """Miss chance by status from earlier pre-game seasons only."""
    x = O_[O_.season.isin(seasons) & O_.status.notna()]
    t = x.groupby("status").missed.agg(["mean", "size"])
    return {s: float(t.loc[s, "mean"]) if s in t.index and t.loc[s, "size"] >= 30 else None for s in STATUSES}


def team_adjust(O_, pm):
    o = O_.copy()
    o["pm"] = o.status.map(lambda s: pm.get(s) if isinstance(s, str) else None)
    o["pm"] = o.pm.astype(float)
    unshr = np.where(o.den > 0, o.num / o.den.where(o.den > 0, 1), 0.0)
    shr = (o.num + PRIOR_GAMES * RATING_W[0] * o.lr) / (o.den + PRIOR_GAMES * RATING_W[0])
    live = np.where(o.den > 0, unshr, o.typical)
    listed = o.pm.notna()
    exp_r = o.pm.fillna(0.0)
    o["R-unshrunk"] = o.value * (exp_r - unshr)
    o["R-shrunk"] = o.value * (exp_r - shr)
    o["L-live"] = np.where(listed, o.value * (o.pm.fillna(0) - live), 0.0)
    o["L-shrunk"] = np.where(listed, o.value * (o.pm.fillna(0) - shr), 0.0)
    big = o.value >= 1.0                                   # players worth a point or more
    o["long_term"] = big & (o.status == "Out") & (o.streak >= 10)
    o["returning"] = big & (o.streak >= 3) & ~o.status.isin(["Out", "Doubtful"])
    return o.groupby(["game_id", "team"]).agg(**{v: (v, "sum") for v in VARIANTS},
                                              long_term=("long_term", "any"), returning=("returning", "any")).reset_index()


def main(ratings_csv, folder, out_path):
    d = V2.load()
    d["athlete_id"] = d.athlete_id.astype(str)
    rep, covered, meta = load_pregame(d, folder)
    Ob = run(d, rep, covered)
    seasons = sorted(Ob.season.unique())
    R = pd.read_csv(ratings_csv, parse_dates=["date"])
    from scipy.stats import norm
    s_eff = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
    R["m"] = norm.ppf(R.p_model.clip(1e-4, 1 - 1e-4)) * s_eff
    games = d.drop_duplicates("game_id")[["game_id", "date"]].assign(game_id=lambda x: x.game_id.astype(str))
    rows = []
    calib = {}
    for y in seasons[1:]:                    # first collected season is calibration only
        pm = p_miss_table(Ob, [s for s in seasons if s < y])
        calib[int(y)] = pm
        A = team_adjust(Ob[Ob.season <= y], pm).merge(games, on="game_id")
        A["date"] = pd.to_datetime(A.date).dt.normalize()
        h = A.rename(columns={"team": "home"}).rename(columns={v: v + "_h" for v in VARIANTS + ["long_term", "returning"]})
        a = A.rename(columns={"team": "away"}).rename(columns={v: v + "_a" for v in VARIANTS + ["long_term", "returning"]}).drop(columns="date")
        J = R.merge(h, on=["date", "home"]).merge(a, on=["game_id", "away"])
        J = J.dropna(subset=["m", "y"])
        J["long_term"] = J.long_term_h.astype(bool) | J.long_term_a.astype(bool)
        J["returning"] = J.returning_h.astype(bool) | J.returning_a.astype(bool)
        J["season_t"] = J.season
        rows.append(J.assign(test_season=y))
    T = pd.concat(rows)
    # each season scored with variant tables built from its own walk-forward calibration
    T = T[T.season == T.test_season]
    res = {"data": meta, "status_miss_by_test_season": calib, "variants": {}, "note": __doc__.split("Usage")[0].strip()}
    for v in VARIANTS:
        T["d"] = T[v + "_h"] - T[v + "_a"]
        per = []
        for y in sorted(T.season.unique()):
            tr, te = T[T.season < y], T[T.season == y]
            beta = 0.45 if not len(tr) else max(np.arange(0, 2.01, 0.05), key=lambda b: -M.ll(M.phi((tr.m - b * tr.d) / s_eff), tr.y.values))
            p = M.phi((te.m - beta * te.d) / s_eff)
            T.loc[te.index, "p_" + v] = p
            per.append(dict(season=int(y), beta=float(beta), games=int(len(te)),
                            no_adjustment=round(M.ll(M.phi(te.m / s_eff), te.y.values), 4), with_adjustment=round(M.ll(p, te.y.values), 4)))
        res["variants"][v] = {"by_season": per}
    out = {}
    for name, mask in (("all", np.ones(len(T), bool)), ("long_term_absence", T.long_term.values), ("returning_player", T.returning.values)):
        x = T[mask]
        e = {"games": int(len(x)), "no_adjustment": round(M.ll(M.phi(x.m / s_eff), x.y.values), 4)}
        for v in VARIANTS:
            e[v] = round(M.ll(x["p_" + v].values, x.y.values), 4)
        e["by_season"] = {int(s): {"games": int(len(z)), "no_adjustment": round(M.ll(M.phi(z.m / s_eff), z.y.values), 4),
                                   **{v: round(M.ll(z["p_" + v].values, z.y.values), 4) for v in VARIANTS}}
                          for s, z in x.groupby("season")}
        out[name] = e
    res["scores"] = out
    res["beta_note"] = "points scale fitted on earlier pre-game seasons only; the first scored season uses 0.45 (fitted on box-score history)"
    json.dump(res, open(out_path, "w"), indent=1)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "by_season"} for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
