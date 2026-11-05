"""Hyperparameter and scale selection for the joint model (Rule section 'Selection of hyperparameters', Amendment 1).
For selection season s (2014..2025, not the 2020 bubble) and the checkpoints nearest 0, 20 and 41 games, every combination
(w_c, lambda_tau, rho) of the fixed grid gives a pre-scalar team rating; its error against each team's rest-of-season net rating
per 100 is recorded. For test season Y the combination with the lowest summed mean absolute error over seasons 2014..Y-1 wins
(ties: larger lambda_tau, then smaller rho) and scale = least-squares slope (through the origin) of the rest-of-season net
rating on the rating, over the same seasons, checkpoints and teams. Nothing from season Y or later is used for Y.
Output: model/replay/nba_joint_select_table.csv and model/replay/nba_joint_params.json.
Usage: python research/nba_joint_select.py [first_selection_season] [last_selection_season]"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba_joint as J  # noqa: E402
import nba_backtest as B  # noqa: E402
N = J.N
ROOT = J.ROOT
OUT = os.path.join(ROOT, "model", "replay")
TARGETS = (0.0, 20.0, 41.0)
TEST_SEASONS = [y for y in range(2016, 2027) if y != 2020]


def weekly_cuts(g):
    first, last = g.date.min(), g.date.max()
    cuts = [first - pd.Timedelta(days=1)]
    d = first + pd.Timedelta(days=6)
    while d < last - pd.Timedelta(days=6):
        cuts.append(d)
        d += pd.Timedelta(days=7)
    return cuts


def rest_net(reg, K, cutoff):
    """Per team mean of (own - opponent) rating per 100 over games after the cutoff, centred."""
    d = reg[reg.season == K][["game_id", "team_abbreviation", "ortg", "game_date"]].copy()
    d["date"] = pd.to_datetime(d.game_date.astype(str).str[:10])
    tot = d.groupby("game_id").ortg.transform("sum")
    d["net"] = d.ortg - (tot - d.ortg)
    x = d[d.date > cutoff].groupby("team_abbreviation").net.mean().reindex(N.TEAMS)
    return x - x.mean()


def run(first=2014, last=2025):
    boxes = B.load_boxes(last)
    reg = N._regular_boxes(boxes)
    rows = []
    for s in range(first, last + 1):
        if s == 2020:
            continue
        g = B.season_games(boxes, s)
        cuts = weekly_cuts(g)
        gp = [2 * int((g.date <= c).sum()) / 30 for c in cuts]
        pick = [int(np.argmin([abs(x - t) for x in gp])) for t in TARGETS]
        ctx = J.season_context(s)
        f = J.get_fit(s)
        for ti, w in zip(TARGETS, pick):
            c = cuts[w]
            ros = J.roster_v2(s, c, g)
            mt = J.minutes_table(s, c, ros, ctx["rv"])
            truth = rest_net(reg, s, c)
            for hp in J.GRID:
                beta, tauK, _ = f.solve(c, *hp, ctx["mu"])
                S, _ = J.team_strength(mt, J.player_values(s, beta))
                tau = pd.Series({ctx["tid2abbr"].get(t): v for t, v in tauK.items()}).reindex(N.TEAMS).fillna(0.0)
                r = S.reindex(N.TEAMS).fillna(0.0) + tau
                r = r - r.mean()
                for t in N.TEAMS:
                    rows.append((s, ti, w, hp[0], hp[1], hp[2], t, float(r[t]), float(truth[t])))
        J._FITS.pop(s - 2, None)
        print("selection season", s, "done", flush=True)
    T = pd.DataFrame(rows, columns=["season", "target", "week", "wc", "lam_tau", "rho", "team", "rating", "truth"])
    T = T.dropna(subset=["truth"])
    T.to_csv(os.path.join(OUT, "nba_joint_select_table.csv"), index=False)
    return T


def choose(T, tests=TEST_SEASONS):
    params = {}
    for Y in tests:
        D = T[T.season < Y]
        if D.empty:
            continue
        D = D.assign(ae=(D.rating - D.truth).abs())
        mae = D.groupby(["wc", "lam_tau", "rho", "season", "target"]).ae.mean().groupby(["wc", "lam_tau", "rho"]).sum().reset_index(name="score")
        mae = mae.sort_values(["score", "lam_tau", "rho"], ascending=[True, False, True])
        best = mae.iloc[0]
        sel = D[(D.wc == best.wc) & (D.lam_tau == best.lam_tau) & (D.rho == best.rho)]
        scale = float((sel.rating * sel.truth).sum() / (sel.rating ** 2).sum())
        params[str(Y)] = dict(wc=float(best.wc), lam_tau=float(best.lam_tau), rho=float(best.rho), scale=round(scale, 4),
                              selection_seasons=sorted(int(x) for x in D.season.unique()), score=round(float(best.score), 4),
                              runner_up=mae.iloc[1][["wc", "lam_tau", "rho", "score"]].round(4).tolist())
    return params


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2014
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    T = run(first, last)
    P = choose(T)
    json.dump(P, open(os.path.join(OUT, "nba_joint_params.json"), "w"), indent=1)
    for y, p in P.items():
        print(y, p)
