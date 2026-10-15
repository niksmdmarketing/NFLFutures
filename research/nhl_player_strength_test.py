"""Preseason test (research): does player-based team strength predict season goal difference per game better than the
live model's preseason prior? Walk-forward: for season y, combine = a + b1 x prior + b2 x player strength fitted on
earlier seasons only. Player strength = opening lineups (players in the team's first 5 games, their average ice time
there) rated with research/nhl_rapm.ratings(y) (seasons before y only), plus the goalies who started those games.
Usage: python research/nhl_player_strength_test.py <published nhl/data dir> [first] [last]
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "pipeline"), os.path.join(ROOT, "research")]
import nhl  # noqa: E402
import nhl_model as M  # noqa: E402
import nhl_rapm as RP  # noqa: E402

nhl.NHL_OUT = M.nhl.NHL_OUT = sys.argv[1]
LIN = os.path.join(ROOT, "data", "research", "nhl_lineups")
PARTS = {}
OPEN_N = int(os.environ.get("PS_OPEN_N", "5"))


def opening_strength(y, teams):
    sk, gk = RP.ratings(y)
    S = pd.read_csv(os.path.join(LIN, f"skaters_{y}.csv.gz"))
    G = pd.read_csv(os.path.join(LIN, f"goalies_{y}.csv.gz"))
    S["date"] = pd.to_datetime(S.date)
    out = {}
    cov = {}
    for t in teams:
        st = S[S.team == t]
        first = sorted(st.game_id.unique())[:OPEN_N]
        x = st[st.game_id.isin(first)]
        h = x.groupby("player_id").toi.sum() / 3600 / len(first)
        h = h * 5.0 / h.sum()
        g = G[(G.team == t) & G.game_id.isin(first) & (G.started == 1)].player_id.value_counts(normalize=True)
        out[t] = RP.lineup_strength(sk, gk, list(h.index), list(h.values), g.to_dict())
        PARTS[(y, t)] = (RP.lineup_strength(sk, None, list(h.index), list(h.values), {}), RP.lineup_strength(None, gk, [], [], g.to_dict()))
        cov[t] = float(h[[p in sk.index for p in h.index]].sum() / 5.0) if sk is not None else 0.0
    return pd.Series(out), pd.Series(cov)


def last_season_strength(y, teams):
    """Same ratings (as of season y) applied to each team's lineups of season y-1 (ice-time weighted over the season)."""
    sk, gk = RP.ratings(y)
    p = os.path.join(LIN, f"skaters_{y - 1}.csv.gz")
    if not os.path.exists(p) or sk is None:
        return pd.Series(np.nan, index=teams)
    S = pd.read_csv(p)
    out = {}
    for t in teams:
        x = S[S.team == t]
        if not len(x):
            out[t] = np.nan
            continue
        ng = x.game_id.nunique()
        h = x.groupby("player_id").toi.sum() / 3600 / ng
        h = h * 5.0 / h.sum()
        out[t] = RP.lineup_strength(sk, None, list(h.index), list(h.values), {})
    return pd.Series(out)


def main(first, last):
    cur = nhl.start_year()
    TT, GG = {}, {}
    for y in range(nhl.FIRST, cur + 1):
        t = M.read_team(y)
        if not t.empty:
            TT[y] = t
        g = M.read_games(y)
        if not g.empty:
            GG[y] = g
    done = [y for y in TT if y < cur and y in GG and GG[y].groupby("team").size().min() >= 40]
    fit_years = [y for y in done if y - 1 in TT]
    rows = []
    for y in range(first, last + 1):
        if y not in done or RP.load(y - 1) is None:
            continue
        beta = M.fit_prior(TT, [z for z in fit_years if z < y])[0]
        teams = sorted(TT[y].index)
        prior = pd.Series(M.prior_features(y, TT).reindex(teams).fillna(0).values @ beta, index=teams)
        ps, cov = opening_strength(y, teams)
        last_ps = last_season_strength(y, teams)
        g = GG[y]
        gd = ((M.numcol(g, "goalsFor") - M.numcol(g, "goalsAgainst")).groupby(g.team).mean()).reindex(teams)
        for t in teams:
            rows.append(dict(season=y, team=t, gd=gd[t] - gd.mean(), prior=prior[t] - prior.mean(), ps=ps[t] - ps.mean(), cov=cov[t],
                             sk=PARTS[(y, t)][0], gk=PARTS[(y, t)][1], last=last_ps[t]))
        print(y, "coverage", round(float(cov.mean()), 3), "corr prior", round(float(np.corrcoef(prior, gd)[0, 1]), 3),
              "corr players", round(float(np.corrcoef(ps, gd)[0, 1]), 3), flush=True)
    D = pd.DataFrame(rows)
    out = []
    for y in sorted(D.season.unique()):
        tr, te = D[D.season < y], D[D.season == y]
        if tr.season.nunique() < 2:
            continue
        X = np.c_[np.ones(len(tr)), tr.prior, tr.ps]
        b = np.linalg.lstsq(X, tr.gd, rcond=None)[0]
        b1 = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr.prior], tr.gd, rcond=None)[0]
        p_c = np.c_[np.ones(len(te)), te.prior, te.ps] @ b
        p_p = np.c_[np.ones(len(te)), te.prior] @ b1
        out.append(dict(season=y, rmse_prior=float(np.sqrt(np.mean((te.gd - p_p) ** 2))), rmse_comb=float(np.sqrt(np.mean((te.gd - p_c) ** 2))),
                        b_prior=b[1], b_players=b[2]))
    O = pd.DataFrame(out)
    print(O.round(4).to_string(index=False))
    print("mean rmse prior %.4f combined %.4f, better %d/%d" % (O.rmse_prior.mean(), O.rmse_comb.mean(), (O.rmse_comb < O.rmse_prior).sum(), len(O)))
    X = np.c_[np.ones(len(D)), D.prior, D.ps]
    print("all-season fit (intercept, prior, players):", np.round(np.linalg.lstsq(X, D.gd, rcond=None)[0], 3))
    for c in ("sk", "gk"):
        D[c] = D[c] - D.groupby("season")[c].transform("mean")
    X = np.c_[np.ones(len(D)), D.prior, D.sk, D.gk]
    b, res, *_ = np.linalg.lstsq(X, D.gd, rcond=None)
    r = D.gd - X @ b
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * r.var())
    print("all-season fit (int, prior, skaters, goalies):", np.round(b, 3), "se", np.round(se, 3))
    print("corr skaters", round(float(np.corrcoef(D.sk, D.gd)[0, 1]), 3), "goalies", round(float(np.corrcoef(D.gk, D.gd)[0, 1]), 3), "sd", round(float(D.sk.std()), 3), round(float(D.gk.std()), 3))
    D["delta"] = (D.sk - D["last"]).fillna(0.0)
    D["delta"] = D.delta - D.groupby("season").delta.transform("mean")
    X = np.c_[np.ones(len(D)), D.prior, D.delta]
    b = np.linalg.lstsq(X, D.gd, rcond=None)[0]; r = D.gd - X @ b
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * r.var())
    print("roster change: fit (int, prior, delta):", np.round(b, 3), "se", np.round(se, 3), "sd delta", round(float(D.delta.std()), 3))
    o2 = []
    for y in sorted(D.season.unique()):
        tr, te = D[D.season < y], D[D.season == y]
        if tr.season.nunique() < 2:
            continue
        b1 = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr.prior], tr.gd, rcond=None)[0]
        b2 = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr.prior, tr.delta], tr.gd, rcond=None)[0]
        o2.append((y, float(np.sqrt(np.mean((te.gd - np.c_[np.ones(len(te)), te.prior] @ b1) ** 2))),
                   float(np.sqrt(np.mean((te.gd - np.c_[np.ones(len(te)), te.prior, te.delta] @ b2) ** 2))), b2[2]))
    o2 = pd.DataFrame(o2, columns=["season", "rmse_prior", "rmse_delta", "b_delta"])
    print(o2.round(4).to_string(index=False))
    print("roster change walk-forward: rmse prior %.4f with delta %.4f, better %d/%d" % (o2.rmse_prior.mean(), o2.rmse_delta.mean(), (o2.rmse_delta < o2.rmse_prior).sum(), len(o2)))
    D.to_csv(os.environ.get("PS_OUT", "/tmp/ps.csv"), index=False)


if __name__ == "__main__":
    a = sys.argv[2:]
    main(int(a[0]) if a else 2015, int(a[1]) if len(a) > 1 else 2025)
