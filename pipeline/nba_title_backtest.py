"""Point-in-time test of the NBA season simulation's futures probabilities (title, conference, No. 1 seed, playoffs).

For each past season and checkpoint (preseason, 20/40/60/80% of games) ratings are fitted with nba._fit_ratings on games
before the checkpoint only, the real schedule is replayed with later results hidden, and nba._simulate produces the same
probabilities the Futures page shows. The roster adjustment is left out (no historical rosters).
Writes model/nba_title_backtest.csv (per team/checkpoint) for scoring and for the market comparison.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba as N
import nba_backtest as B
from common import MODEL

CHECK = (0.0, 0.2, 0.4, 0.6, 0.8)
SIMS = int(os.environ.get("BT_SIMS", "3000"))


def outcomes(boxes, y):
    """Champion and finalists from that season's playoff games."""
    d = boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & (pd.to_numeric(boxes.season_type, errors="coerce") == 3)
              & boxes.team_abbreviation.isin(N.TEAMS) & boxes.opponent_team_abbreviation.isin(N.TEAMS)].copy()
    if d.empty:
        return None
    d["date"] = pd.to_datetime(d.game_date)
    last = d[d.date == d.date.max()].iloc[0]
    finalists = {last.team_abbreviation, last.opponent_team_abbreviation}
    fin = d[d.team_abbreviation.isin(finalists) & d.opponent_team_abbreviation.isin(finalists)]
    wins = fin[fin.team_winner.astype(str).str.lower() == "true"].groupby("team_abbreviation").size()
    champ = wins.idxmax()
    playoff_teams = set(d.team_abbreviation)
    return dict(champ=champ, finalists=finalists, playoffs=playoff_teams)


def run(seasons):
    boxes = B.load_boxes(max(seasons))
    rows = []
    for y in seasons:
        out = outcomes(boxes, y)
        if out is None:
            continue
        p = N._download("espn_nba_schedules", f"nba_schedule_{y}.csv", 24 * 365, required=False)
        if not p:
            continue
        sched = N._schedule(N._csv(p))
        g = B.season_games(boxes, y)
        n = len(g)
        for c in CHECK:
            k = int(round(c * n))
            cutoff = g.date.iloc[k - 1] if k else g.date.min() - pd.Timedelta(days=1)
            tr = boxes[pd.to_numeric(boxes.season, errors="coerce") < y]
            if k:
                tr = pd.concat([tr, boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & boxes.game_id.isin(set(g.gid.iloc[:k]))]])
            ratings, fit = N._fit_ratings(tr, y)
            N.HFA = float(fit["home_offense_points_per_100"]) if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
            N.PACE = ratings.set_index("team").pace.reindex(N.TEAMS).fillna(100.0).to_numpy(float)
            ratings["rating"] = ratings.raw_net - ratings.raw_net.mean()
            s = sched.copy()
            s["completed"] = s.completed & (pd.to_datetime(s.game_date) <= cutoff)
            res = N._simulate(s, ratings, SIMS)
            for t, v in res.items():
                rows.append(dict(season=y, check=c, date=str(cutoff.date()), team=t, p_title=v["p_title"], p_conf=v["p_conf"],
                                 p_seed1=v["p_seed1"], p_playoff=v["p_playoff"], mean_wins=v["mean_wins"],
                                 y_title=int(t == out["champ"]), y_conf=int(t in out["finalists"]), y_playoff=int(t in out["playoffs"])))
        print("season", y, "champ", out["champ"], flush=True)
    return pd.DataFrame(rows)


def score(D):
    res = {}
    for c, x in D.groupby("check"):
        r = {}
        for k in ("title", "conf", "playoff"):
            p = x["p_" + k].clip(0.002, 0.998)
            yv = x["y_" + k]
            r[k] = dict(logloss=round(float(-(yv * np.log(p) + (1 - yv) * np.log(1 - p)).mean()), 4),
                        winner_p=round(float(x[yv == 1]["p_" + k].mean()), 3))
        res[c] = r
    return res


if __name__ == "__main__":
    first = int(os.environ.get("BT_FIRST", "2013"))
    D = run(range(first, N.season_end_year()))
    D.to_csv(os.path.join(MODEL, "nba_title_backtest.csv"), index=False)
    import json
    print(json.dumps(score(D), indent=1))
