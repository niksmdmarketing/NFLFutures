"""NFL player ratings from play-level participation (research): ridge regression of each scrimmage play's EPA on the 11
offensive players (offense effects) and 11 defensive players (defense effects, EPA allowed), with an intercept.
Point in time: ratings for week w of season Y use plays from earlier seasons (weight DECAY ** years back) and from Y before
week w (weight 1). For every regular-season game of 2018-2025 the player-based team strength is
   net = sum(offense effect x expected snap share) - sum(defense effect x expected snap share)   (EPA per play, x 11)
where the expected players are those who took at least one snap in that game (lineups are public at kickoff) and each is
weighted by his share of the team's snaps in earlier games (this season, else last season, else 0.5).
Writes <out>/player_feature.csv: game_id, season, week, home, away, home_net, away_net, plus fitted ratings per checkpoint.
Usage: python research/nfl_player_ratings.py <plays dir> <out dir> [lam] [decay]
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy import sparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))


def load(d):
    fr = []
    for f in sorted(os.listdir(d)):
        if f.startswith("plays_") and f.endswith(".parquet"):
            fr.append(pd.read_parquet(os.path.join(d, f)))
    P = pd.concat(fr, ignore_index=True)
    P["off_l"] = P["off"].str.split(";")
    P["def_l"] = P["def"].str.split(";")
    return P


def fit(P, w, lam):
    ids = pd.unique(np.concatenate([np.concatenate(P.off_l.values), np.concatenate(P.def_l.values)]))
    ix = {a: i for i, a in enumerate(ids)}
    m = len(ids)
    n = len(P)
    rows = np.repeat(np.arange(n), 22)
    cols = np.empty(n * 22, dtype=np.int64)
    for j, (o, d) in enumerate(zip(P.off_l.values, P.def_l.values)):
        cols[j * 22:j * 22 + 11] = [ix[a] for a in o]
        cols[j * 22 + 11:j * 22 + 22] = [m + ix[a] for a in d]
    X = sparse.csr_matrix((np.ones(n * 22), (rows, cols)), shape=(n, 2 * m))
    y = P.epa.to_numpy(float)
    mu = np.average(y, weights=w)
    XtW = X.T.multiply(w).tocsr()
    A = (XtW @ X).tocsc()
    A = A + sparse.identity(2 * m, format="csc") * lam
    b = XtW @ (y - mu)
    from scipy.sparse.linalg import spsolve
    sol = spsolve(A, b)
    return {a: sol[i] for a, i in ix.items()}, {a: sol[m + i] for a, i in ix.items()}


PREGAME = os.environ.get("NP_PREGAME") == "1"
INJ = None


def main(plays_dir, out, lam=3000.0, decay=0.5, first=2018, last=2025):
    global INJ
    if PREGAME:
        from common import DATA, FIX
        INJ = pd.concat([pd.read_csv(os.path.join(DATA, f"injuries_{yy}.csv"), low_memory=False) for yy in range(2016, 2026)])
        INJ = INJ[INJ.game_type == "REG"] if "game_type" in INJ else INJ
        INJ["team"] = INJ.team.replace(FIX)
    P = load(plays_dir)
    # snap shares per team-game
    snaps = []
    for side, col, team in (("off", "off_l", "posteam"), ("def", "def_l", "defteam")):
        e = P[["game_id", "season", "week", team, col]].rename(columns={team: "team", col: "pl"}).explode("pl")
        c = e.groupby(["season", "week", "game_id", "team", "pl"]).size().rename("n").reset_index()
        tot = P.groupby(["game_id", team]).size().rename("tot").reset_index().rename(columns={team: "team"})
        c = c.merge(tot, on=["game_id", "team"])
        c["share"] = c.n / c.tot
        c["side"] = side
        snaps.append(c)
    S = pd.concat(snaps, ignore_index=True)
    rows = []
    for y in range(first, last + 1):
        weeks = sorted(P[P.season == y].week.unique())
        for wk in weeks:
            past = P[(P.season < y) | ((P.season == y) & (P.week < wk))]
            past = past[past.season >= y - 4]
            wts = np.where(past.season == y, 1.0, decay ** (y - past.season)).astype(float)
            off_r, def_r = fit(past, wts, lam)
            prev = S[((S.season == y) & (S.week < wk))]
            last_s = S[S.season == y - 1]
            share_cur = prev.groupby(["team", "side", "pl"]).share.sum() / prev.groupby(["team", "side"]).game_id.nunique().reindex(
                prev.groupby(["team", "side", "pl"]).share.sum().index.droplevel(2)).values if len(prev) else prev.groupby(["team", "side", "pl"]).share.mean()
            usual_idx = set(share_cur.index.droplevel(2)) if len(share_cur) else set()
            share_last = last_s.groupby(["side", "pl"]).share.mean()
            games = S[(S.season == y) & (S.week == wk)]
            if PREGAME:
                # lineup known before kickoff: players who played in the team's previous game this season, minus players
                # listed Out or Doubtful on this week's official injury report
                inj = INJ[(INJ.season == y) & (INJ.week == wk) & INJ.report_status.isin(["Out", "Doubtful"])]
                out_ids = set(zip(inj.team, inj.gsis_id))
                rows_pg = []
                for (gid, team, side), g in games.groupby(["game_id", "team", "side"]):
                    pt = prev[(prev.team == team) & (prev.side == side)]
                    if not len(pt):
                        continue
                    last_wk = pt.week.max()
                    pool = pt[pt.week == last_wk].pl.unique()
                    recent = pt[pt.week >= last_wk - 2].groupby("pl").share.mean()
                    pool = [pl for pl in pool if (team, pl) not in out_ids]
                    rows_pg.append((gid, team, side, pool, recent))
                games_iter = rows_pg
            else:
                games_iter = [(gid, team, side, list(g.pl), None) for (gid, team, side), g in games.groupby(["game_id", "team", "side"])]
            for gid, team, side, pls, recent in games_iter:
                g = pd.DataFrame({"pl": pls})
                tot = 0.0
                rat = off_r if side == "off" else def_r
                for pl in g.pl:
                    sh = recent.get(pl, np.nan) if recent is not None else share_cur.get((team, side, pl), np.nan)
                    if np.isnan(sh):
                        sh = share_last.get((side, pl), 0.5)
                    tot += sh * rat.get(pl, 0.0)
                # usual lineup: everyone who played for the team this season so far, by average share (scaled to 11)
                if (team, side) in usual_idx:
                    u = share_cur.loc[(team, side)]
                    u = u * (11.0 / max(u.sum(), 1e-9)) if u.sum() > 11 else u
                    full = float(sum(sh * rat.get(pl, 0.0) for pl, sh in u.items()))
                else:
                    full = np.nan
                rows.append(dict(game_id=gid, season=y, week=int(wk), team=team, side=side, val=tot, usual=full))
            print(y, wk, flush=True)
    R = pd.DataFrame(rows)
    T = R.pivot_table(index=["game_id", "season", "week", "team"], columns="side", values=["val", "usual"])
    T.columns = [f"{a}_{b}" for a, b in T.columns]
    T = T.reset_index()
    T["net"] = T.val_off - T.val_def
    T["usual"] = T.usual_off - T.usual_def
    T["inj"] = T.net - T.usual
    os.makedirs(out, exist_ok=True)
    T.to_csv(os.path.join(out, f"player_feature_lam{int(lam)}_d{decay}{'_pre' if PREGAME else ''}.csv"), index=False)


if __name__ == "__main__":
    lam = float(sys.argv[3]) if len(sys.argv) > 3 else 3000
    dec = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    main(sys.argv[1], sys.argv[2], lam, dec)
