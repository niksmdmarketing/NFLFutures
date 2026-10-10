"""Point-in-time test of the NBA season model (rating engine + win projection) on past seasons.

For every past season and at five checkpoints (preseason, 20/40/60/80% of the games) ratings are fitted with nba._fit_ratings
using ONLY games played before the checkpoint, then the rest of that season is projected and compared with what happened.
Two unit conventions are compared: A = the original (rating per 100 possessions used as a per-game margin, fixed 2.2
home edge) and B = unit-consistent (rating x game pace / 100, home edge fitted in the same per-100 units).
The roster adjustment cannot be tested (no historical rosters), so this tests the rating engine only.
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba as N

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = (0.0, 0.2, 0.4, 0.6, 0.8)
FIRST_TEST = 2011


def phi(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def load_boxes(last):
    frames = []
    for y in range(2003, last + 1):
        p = N._download("espn_nba_team_boxscores", f"team_box_{y}.csv", 24 * 365, required=False)
        if p and os.path.exists(p):
            f = N._csv(p)
            if len(f):
                frames.append(f)
    return pd.concat(frames, ignore_index=True)


def season_games(boxes, y):
    """One row per regular-season game: date, home, away, home_win, margin."""
    d = boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & (pd.to_numeric(boxes.season_type, errors="coerce") == 2)
              & boxes.team_abbreviation.isin(N.TEAMS) & boxes.opponent_team_abbreviation.isin(N.TEAMS)].copy()
    d["team_score"] = pd.to_numeric(d.team_score, errors="coerce")
    d["opp_score"] = pd.to_numeric(d.opponent_team_score, errors="coerce")
    h = d[d.team_home_away == "home"].drop_duplicates("game_id")
    g = pd.DataFrame(dict(gid=h.game_id.values, date=pd.to_datetime(h.game_date).values, home=h.team_abbreviation.values,
                          away=h.opponent_team_abbreviation.values, margin=(h.team_score - h.opp_score).values))
    g = g.dropna().sort_values(["date", "gid"]).reset_index(drop=True)
    g["hw"] = (g.margin > 0).astype(float)
    return g


def project(ratings, hca, games, variant, sigma, tau):
    r = ratings.set_index("team")
    net, pace = r.raw_net, r.pace
    nh, na = net.reindex(games.home).to_numpy(), net.reindex(games.away).to_numpy()
    if variant == "A":
        m = nh - na + 2.2
    else:
        gp = (pace.reindex(games.home).to_numpy() + pace.reindex(games.away).to_numpy()) / 2
        m = (nh - na + hca) * gp / 100
    s = math.sqrt(sigma ** 2 + 2 * tau ** 2)
    return phi(m / s)


CONFIGS = {"previous": ((0.55, 24.0, 1.6), "A"), "current": ((0.2, 24.0, 4.0), "B")}


def run(sigma=12.2, tau=2.2):
    cur = N.season_end_year()
    boxes = load_boxes(cur - 1)
    out = []
    for y in range(FIRST_TEST, cur):
        g = season_games(boxes, y)
        if len(g) < 700:
            continue
        n = len(g)
        prev = season_games(boxes, y - 1)
        pw = {}
        for t in N.TEAMS:
            pw[t] = float(((prev.home == t) & (prev.hw == 1)).sum() + ((prev.away == t) & (prev.hw == 0)).sum()) if len(prev) else 41.0
        for c in CHECK:
            k = int(round(c * n))
            past, fut = g.iloc[:k], g.iloc[k:]
            tr = boxes[(pd.to_numeric(boxes.season, errors="coerce") < y)]
            if k:
                ids = set(past.gid)
                tr = pd.concat([tr, boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & boxes.game_id.isin(ids)]])
            teams = N.TEAMS
            wins_now = {t: float(((past.home == t) & (past.hw == 1)).sum() + ((past.away == t) & (past.hw == 0)).sum()) for t in teams}
            gp_now = {t: float(((past.home == t) | (past.away == t)).sum()) for t in teams}
            fin = {t: float(((g.home == t) & (g.hw == 1)).sum() + ((g.away == t) & (g.hw == 0)).sum()) for t in teams}
            gtot = {t: float(((g.home == t) | (g.away == t)).sum()) for t in teams}
            rem = {t: gtot[t] - gp_now[t] for t in teams}
            # baselines
            base = {"constant": {t: wins_now[t] + rem[t] * 0.5 for t in teams},
                    "last year": {t: wins_now[t] + rem[t] * (0.6 * pw[t] / max(1, 82) + 0.4 * 0.5) for t in teams},
                    "record so far": {t: wins_now[t] + rem[t] * (0.5 * (wins_now[t] / gp_now[t] if gp_now[t] else 0.5) + 0.25 + 0.0) for t in teams}}
            for label, (cfg, var) in CONFIGS.items():
                ratings, fit = N._fit_ratings(tr, y, *cfg)
                p = project(ratings, fit["home_offense_points_per_100"], fut, var, sigma, tau)
                exp = dict(wins_now)
                for hm, aw, pr in zip(fut.home, fut.away, p):
                    exp[hm] += pr
                    exp[aw] += 1 - pr
                err = np.array([exp[t] - fin[t] for t in teams])
                hw = fut.hw.to_numpy()
                ll = float(-np.mean(hw * np.log(np.clip(p, 1e-6, 1)) + (1 - hw) * np.log(np.clip(1 - p, 1e-6, 1)))) if len(fut) else None
                out.append(dict(season=y, check=c, model=label, mae=float(np.abs(err).mean()), rmse=float(np.sqrt((err ** 2).mean())),
                                logloss=ll, n=len(fut)))
            for name, pr in base.items():
                err = np.array([pr[t] - fin[t] for t in teams])
                out.append(dict(season=y, check=c, model=name, mae=float(np.abs(err).mean()), rmse=float(np.sqrt((err ** 2).mean())),
                                logloss=None, n=len(fut)))
        print("season", y, flush=True)
    return pd.DataFrame(out)


def summarise(R):
    seasons = sorted(R.season.unique())
    tab = R.groupby(["model", "check"]).mae.mean().unstack(0).round(2)
    return dict(seasons=f"{int(seasons[0])}-{int(seasons[-1])}", n_seasons=len(seasons), checkpoints=[float(c) for c in tab.index],
                mae={m: [float(v) for v in tab[m]] for m in tab.columns},
                logloss={m: round(float(R[R.model == m].logloss.mean()), 4) for m in CONFIGS})


if __name__ == "__main__":
    R = run()
    S = summarise(R)
    json.dump(S, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba_backtest_summary.json"), "w"), indent=1)
    print(json.dumps(S, indent=1))
