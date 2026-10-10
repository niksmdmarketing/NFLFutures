"""Rough futures-level test of the NBA availability layer (research).

Same point-in-time replay as pipeline/nba_title_backtest.py (ratings from games before each checkpoint, real schedule,
later results hidden), run twice: without availability, and with the live layer (nba_avail.plan + per-simulation
recovery draws). Historical injury reports with return dates are not available, so the 'report' at each checkpoint is
built from box scores before it: a rotation player who missed his team's last 5 games is listed Out with no return date
(the live default: median 14 days, wide spread), or as a long-term absence (median 90 days) if he has missed 15+.
That is cruder than the live feed, so this is a lower bound on what the layer can do for futures, not its live accuracy.
Usage: python research/nba_avail_futures_test.py [first_end_year]
Writes model/availability_nba_futures.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402
import nba_avail as A  # noqa: E402
import nba_backtest as B  # noqa: E402
import nba_title_backtest as T  # noqa: E402

CHECK = (0.2, 0.4, 0.6, 0.8)    # preseason has no in-season absences to read from box scores
SIMS = int(os.environ.get("BT_SIMS", "3000"))


def players_for(y):
    frames = []
    for s in range(y - 4, y + 1):
        p = N._download("espn_nba_player_boxscores", f"player_box_{s}.csv", 24 * 365, required=False)
        if p:
            frames.append(pd.read_csv(p, low_memory=False))
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d.game_date)
    return d


def synthetic_report(P, cutoff, y):
    """Rotation players who missed their team's last 5+ games before the cutoff."""
    d = P[(P.date <= cutoff) & (pd.to_numeric(P.season, errors="coerce") == y) & (pd.to_numeric(P.season_type, errors="coerce") == 2)].copy()
    d["athlete_id"] = d.athlete_id.astype(str)
    d["played"] = pd.to_numeric(d.minutes, errors="coerce").fillna(0) > 0
    games = d.drop_duplicates(["game_id", "team_abbreviation"]).sort_values("date")
    last_played = d[d.played].groupby("athlete_id").date.max()
    last_team = d.sort_values("date").groupby("athlete_id").team_abbreviation.last()
    rows = []
    for pid, team in last_team.items():
        if team not in N.TEAMS:
            continue
        tg = games[games.team_abbreviation == team].date
        lp = last_played.get(pid)
        missed = int((tg > lp).sum()) if lp is not None else len(tg)
        if missed >= 5:
            rows.append(dict(athlete_id=pid, name=pid, team_name=N.NAMES[team], status="Out", return_date=None,
                             injury="season surgery" if missed >= 15 else "", updated=None))
    return rows


def run(seasons):
    boxes = B.load_boxes(max(seasons))
    rows = []
    for y in seasons:
        out = T.outcomes(boxes, y)
        p = N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 24 * 365, required=False)
        if out is None or not p:
            continue
        sched = N._schedule(N._csv(p))
        g = B.season_games(boxes, y)
        P = players_for(y)
        n = len(g)
        for c in CHECK:
            k = int(round(c * n))
            cutoff = g.date.iloc[k - 1]
            tr = pd.concat([boxes[pd.to_numeric(boxes.season, errors="coerce") < y],
                            boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & boxes.game_id.isin(set(g.gid.iloc[:k]))]])
            ratings, fit = N._fit_ratings(tr, y)
            N.HFA = float(fit["home_offense_points_per_100"]) if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
            N.PACE = ratings.set_index("team").pace.reindex(N.TEAMS).fillna(100.0).to_numpy(float)
            ratings["rating"] = ratings.raw_net - ratings.raw_net.mean()
            s = sched.copy()
            s["completed"] = s.completed & (pd.to_datetime(s.game_date) <= cutoff)
            values = A.player_values(P[P.date <= cutoff], y, None, today=cutoff.date())
            report = synthetic_report(P, cutoff, y)
            plan = A.plan(s, report, values, N.NAMES, today=cutoff.date())
            base = N._simulate(s, ratings, SIMS)
            withav = N._simulate(s, ratings, SIMS, plan)
            for t in N.TEAMS:
                for tag, res in (("without", base), ("with", withav)):
                    v = res[t]
                    rows.append(dict(season=y, check=c, team=t, variant=tag, p_title=v["p_title"], p_conf=v["p_conf"],
                                     p_playoff=v["p_playoff"], mean_wins=v["mean_wins"], y_title=int(t == out["champ"]),
                                     y_conf=int(t in out["finalists"]), y_playoff=int(t in out["playoffs"]), n_out=len(plan["episodes"])))
        print("season", y, flush=True)
    return pd.DataFrame(rows)


def score(D):
    res = {}
    for (c, var), x in D.groupby(["check", "variant"]):
        r = {}
        for k in ("title", "conf", "playoff"):
            p = x["p_" + k].clip(0.002, 0.998)
            yv = x["y_" + k]
            r[k] = round(float(-(yv * np.log(p) + (1 - yv) * np.log(1 - p)).mean()), 4)
        res.setdefault(str(c), {})[var] = r
    tot = {}
    for var, x in D.groupby("variant"):
        tot[var] = {}
        for k in ("title", "conf", "playoff"):
            p = x["p_" + k].clip(0.002, 0.998)
            yv = x["y_" + k]
            tot[var][k] = round(float(-(yv * np.log(p) + (1 - yv) * np.log(1 - p)).mean()), 4)
    res["all_checkpoints"] = tot
    # seasons where 'with' beats 'without' on title log-loss
    per = []
    for y, x in D.groupby("season"):
        ll = {}
        for var, z in x.groupby("variant"):
            p = z.p_title.clip(0.002, 0.998)
            ll[var] = float(-(z.y_title * np.log(p) + (1 - z.y_title) * np.log(1 - p)).mean())
        per.append(ll["with"] < ll["without"])
    res["seasons_title_better"] = f"{sum(per)} of {len(per)}"
    return res


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2013
    D = run(range(first, N.season_end_year()))
    D.to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), "nba_avail_futures.csv"), index=False)
    res = score(D)
    res["note"] = ("Point-in-time futures replay at 20/40/60/80% of each season, 2013-2026; absences read from box scores before each "
                   "checkpoint (missed last 5+ games), no return dates. Log-loss, lower is better.")
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(ROOT, "model", "availability_nba_futures.json"), "w"), indent=1)
