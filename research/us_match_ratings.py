"""Point-in-time pre-game home win probabilities from our NBA and NHL rating engines (research).
NBA: nba._fit_ratings refitted weekly on games before each week (live settings, pace-scaled margins).
NHL: the model's in-season rating (prior from earlier seasons blended with the season-to-date 60% goals / 40% xG rate),
     every setting estimated from earlier seasons only. Output: CSV per sport in $TMPDIR."""
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import match_vs_market as M  # noqa: E402

TMP = os.environ.get("TMPDIR", "/tmp")


def nba(first=2008, last=2026):
    import nba as N
    import nba_backtest as B
    boxes = B.load_boxes(last)
    s_eff = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
    rows = []
    for y in range(first, last + 1):
        g = B.season_games(boxes, y)
        if len(g) < 500:
            continue
        g["wk"] = ((g.date - g.date.min()).dt.days // 7).astype(int)
        nw = g.wk.max() + 1
        prior_boxes = boxes[pd.to_numeric(boxes.season, errors="coerce") < y]
        cur_boxes = boxes[pd.to_numeric(boxes.season, errors="coerce") == y]
        for w in range(nw):
            past_ids = set(g[g.wk < w].gid)
            tr = pd.concat([prior_boxes, cur_boxes[cur_boxes.game_id.isin(past_ids)]]) if past_ids else prior_boxes
            R, fit = N._fit_ratings(tr, y)
            hca = fit["home_offense_points_per_100"] if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
            r = R.set_index("team")
            for x in g[g.wk == w].itertuples():
                if x.home not in r.index or x.away not in r.index:
                    continue
                pace = (r.pace[x.home] + r.pace[x.away]) / 200
                m = (r.raw_net[x.home] - r.raw_net[x.away] + hca) * pace
                rows.append(dict(season=y, date=x.date, home=x.home, away=x.away, frac=w / nw, y=float(x.margin > 0), p_model=float(M.phi(m / s_eff))))
        print("nba", y, flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(TMP, "ratings_nba.csv"), index=False)


def nhl():
    import nhl as H
    import nhl_model as NM
    cur = H.start_year()
    TT, GG = {}, {}
    for y in range(H.FIRST, cur + 1):
        t, g = NM.read_team(y), NM.read_games(y)
        if not t.empty:
            TT[y] = t
        if not g.empty:
            GG[y] = g
    done = [y for y in TT if y < cur and y in GG and GG[y].groupby("team").size().min() >= 40]
    fit_years = [y for y in done if y - 1 in TT]
    rows = []
    for y in done:
        if y - 1 not in TT or y < H.FIRST + 5:
            continue
        beta, k, tau, total, hfa = NM.params_before(TT, GG, fit_years, done, y)
        prior = pd.Series(NM.prior_features(y, TT).values @ beta, index=NM.prior_features(y, TT).index)
        g = GG[y].copy()
        g["gd"] = NM.numcol(g, "goalsFor") - NM.numcol(g, "goalsAgainst")
        xf, xa = NM.numcol(g, "mp_xGoalsFor"), NM.numcol(g, "mp_xGoalsAgainst")
        g["xgd"] = np.where(xf > 0, xf - xa, g.gd)
        g["date"] = pd.to_datetime(g.date)
        g = g.sort_values("date")
        days = sorted(g.date.unique())
        sd = math.sqrt(NM.GAME_SD ** 2)
        for i, d in enumerate(days):
            past = g[g.date < d]
            n = past.groupby("team").size()
            rate = (0.6 * past.groupby("team").gd.mean() + 0.4 * past.groupby("team").xgd.mean())
            rate = rate - rate.mean() if len(rate) else rate
            for x in g[(g.date == d) & (g.ha == "H")].itertuples():
                def rt(t):
                    nn = float(n.get(t, 0))
                    return (nn * float(rate.get(t, 0.0)) + k * float(prior.get(t, 0.0))) / (nn + k)
                ta = NM.tau_at(tau, float(n.mean()) if len(n) else 0)
                m = rt(x.team) - rt(x.opp) + hfa
                rows.append(dict(season=y, date=d, home=x.team, away=x.opp, frac=i / len(days), y=float(x.res == "W"),
                                 p_model=float(M.phi(m / math.sqrt(sd ** 2 + 2 * ta ** 2)))))
        print("nhl", y, flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(TMP, "ratings_nhl.csv"), index=False)


if __name__ == "__main__":
    {"nba": nba, "nhl": nhl}[sys.argv[1]]()
