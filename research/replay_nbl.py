"""Weekly point-in-time replay of the NBL futures model (research / archive builder).

Per season (2013-14 onward; the first season has no prior) and per weekly checkpoint (before the first game, then every 7
days of the regular season) the rating is nbl_site.srs(games before the checkpoint, prior=PRIOR_REG * last season's rating),
the real remaining regular-season fixture is replayed and nbl_site.simulate gives the probabilities the Futures page uses.
Format by era, read from the data: 4 finalists = top four with 1v4 / 2v3 best-of-three semi-finals (no play-in);
6 finalists = the play-in format. Champion = winner of the last game; Grand Finalists = the two teams in it.
Outputs model/replay/nbl_<season>.csv (season = start year): p_playoff (make finals: top 4 or top 6 by era), p_div (top 2),
p_seed1 (minor premiers), p_conf (Grand Final), p_title (champions), and 0/1 outcomes. No imports/injuries.
Usage: python research/replay_nbl.py [first] [last]    (env BT_SIMS, default 3000)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nbl_site as N  # noqa: E402

SIMS = int(os.environ.get("BT_SIMS", "3000"))
N.TAU0 = float(os.environ.get("BT_TAU0", N.TAU0))
N.TAU_FLOOR = float(os.environ.get("BT_TAU_FLOOR", N.TAU_FLOOR))
N.GAME_SD = float(os.environ.get("BT_GAME_SD", N.GAME_SD))
OUT = os.environ.get("BT_OUTDIR") or os.path.join(ROOT, "model", "replay")


def run_season(S, y, prev_rows):
    x, _, reg_n = N.season_games(S[str(y)])
    if x.empty or not x.fin.any():
        return None, None
    reg = x[~x.fin].copy()
    fin = x[x.fin].sort_values("date")
    teams = sorted(reg_n)
    rows_all = N.team_rows(reg)
    # final ladder: wins, then point differential
    fl = rows_all.groupby("team").agg(w=("win", "sum"), pd_=("margin", "sum")).reindex(teams)
    order = list((fl.w * 1e4 + fl.pd_).sort_values(ascending=False).index)
    pos = {t: i for i, t in enumerate(order)}
    finalists = set(fin.h) | set(fin.a)
    top4 = len(finalists) == 4
    last = fin.iloc[-1]
    champ = last.h if last.hs > last["as"] else last.a
    gf = {last.h, last.a}
    prior = {t: N.PRIOR_REG * v for t, v in N.srs(prev_rows).items()} if prev_rows is not None and len(prev_rows) else {}
    first, lastd = pd.Timestamp(reg.date.min()), pd.Timestamp(reg.date.max())
    cuts = [first]
    d = first + pd.Timedelta(days=7)
    while d < lastd - pd.Timedelta(days=6):
        cuts.append(d)
        d += pd.Timedelta(days=7)
    reg["dt"] = pd.to_datetime(reg.date)
    out = []
    for wk, cut in enumerate(cuts):
        pl, rem = reg[reg.dt < cut], reg[reg.dt >= cut]
        g = N.team_rows(pl) if len(pl) else pd.DataFrame(columns=["team", "win", "margin"])
        rating = N.srs(g, prior=prior) if len(g) else dict(prior)
        W0 = g.groupby("team").win.sum().to_dict() if len(g) else {}
        L0 = (g.groupby("team").size() - g.groupby("team").win.sum()).to_dict() if len(g) else {}
        PD0 = g.groupby("team").margin.sum().to_dict() if len(g) else {}
        todo = [{"date": r.date, "home": r.h, "away": r.a} for r in rem.itertuples()]
        gp = float(np.mean([W0.get(t, 0) + L0.get(t, 0) for t in teams]))
        total = gp + 2 * len(todo) / max(len(teams), 1)
        tau = N.TAU0 * max(N.TAU_FLOOR, 1 - gp / max(total, 1))
        res = N.simulate(teams, W0, L0, PD0, todo, rating, tau, n=SIMS, seed=11, top4=top4)
        for t in teams:
            r = res[t]
            out.append(dict(season=y, week=wk, date=str(cut.date()), gp_avg=round(gp, 1), team=t, p_playoff=r["p4"] if top4 else r["p6"], p_div=r["p2"],
                            p_seed1=r["p1"], p_conf=r["gf"], p_title=r["champ"], y_playoff=int(t in finalists), y_div=int(pos[t] < 2), y_seed1=int(pos[t] == 0),
                            y_finals=int(t in gf), y_title=int(t == champ)))
    return pd.DataFrame(out), N.team_rows(reg)


if __name__ == "__main__":
    S = json.load(open(N.SRC))["seasons"]
    ys = sorted(int(k) for k in S)
    first = int(sys.argv[1]) if len(sys.argv) > 1 else ys[0] + 1
    last = int(sys.argv[2]) if len(sys.argv) > 2 else ys[-1]
    os.makedirs(OUT, exist_ok=True)
    prev = None
    for y in ys:
        D, rows = (None, None)
        x, _, rn = N.season_games(S[str(y)])
        if x.empty:
            continue
        if first <= y <= last:
            D, rows = run_season(S, y, prev)
            if D is not None:
                D.to_csv(os.path.join(OUT, f"nbl_{y}.csv"), index=False)
                print("season", y, "weeks", D.week.nunique(), flush=True)
        prev = N.team_rows(x[~x.fin]) if x.fin.any() else prev
