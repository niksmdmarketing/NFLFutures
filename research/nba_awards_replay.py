"""Point-in-time replay of NBA award chances (MVP, DPOY, ROY, Sixth Man), and the forward-simulation candidate.

For every season (end year) and a checkpoint every 14 days, using only box scores on or before the checkpoint:
  live    : the current site method: conditional logit (award_model) on stats to date, pool = top-N to date.
  sim     : candidate: each candidate's season is simulated forward (rates shrunk to last season, availability from his
            share of team games, talent and health noise), final per-game lines and team win% are scored by the same
            logit, and the 65-game eligibility rule (2023-24 on) zeroes ineligible players in each simulation.
The logit weights are fitted leave-one-season-out on final season lines (the test season never trains its own weights).
Score: -log(probability given to the eventual winner), by stage of the season.
Usage: python research/nba_awards_replay.py [first_end_year] [last_end_year]   (env AW_SIMS default 300)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import award_model as AM  # noqa: E402
from nba_site import AM_norm  # noqa: E402
from nba_award_sim import *  # noqa: E402,F401,F403
import nba_award_sim as SIM  # noqa: E402
from trends_awards import NBA_AW  # noqa: E402

def final_tables(years):
    """End-of-season candidate pools with the winner flagged, for fitting the logit."""
    out = {}
    seen = set()
    for y in years:
        b = boxes(y)
        if b is None:
            continue
        a = season_lines(b)
        ids = set(a.index)
        a["rookie"] = [i not in seen for i in a.index]
        seen |= ids
        a["wp"] = a.tw / a.tg
        L = float(a.tg.max())
        f = features(a, L)
        D = a.assign(**{k: np.asarray(v, float) for k, v in f.items()})
        D["bench"] = (D.start / D.gp) < .5
        D["season"] = y
        out[y] = (b, D, L)
    return out


def pool(D, award, y):
    poolf, rank, n, feats = SPECS[award]
    P = D[poolf(D)].sort_values(rank, ascending=False).head(n).copy()
    win = AM_norm(NBA_AW[award].get(y, ""))
    P["win"] = [float(AM_norm(nm) == win) for nm in P.name]
    P["season"] = y
    return P


def logit_probs(P, feats, beta):
    X = P[feats].astype(float)
    X = ((X - X.mean()) / X.std().replace(0, np.nan)).fillna(0).values
    e = X @ beta
    e = np.exp(e - e.max())
    return e / e.sum()


def replay(first, last):
    years = list(range(first - 1, last + 1))
    FT = final_tables(list(range(2003, last + 1)))
    rows = []
    for y in range(first, last + 1):
        if y not in FT or (y - 1) not in FT:
            continue
        b, Dfin, L = FT[y]
        prev = FT[y - 1][1]
        start, end = b.date.min(), b.date.max()
        cuts = list(pd.date_range(start + pd.Timedelta(days=21), end - pd.Timedelta(days=3), freq="14D"))
        rookies = set(Dfin.index[Dfin.rookie])
        for award in SPECS:
            if y not in NBA_AW[award]:
                continue
            feats = SPECS[award][3]
            train = pd.concat([pool(FT[z][1], award, z) for z in FT if z != y and z in NBA_AW[award] and z >= 2003], ignore_index=True)
            train[feats] = train[feats].fillna(train[feats].median())
            beta = AM.fit(train, feats)
            win = AM_norm(NBA_AW[award][y])
            for ci, cut in enumerate(cuts):
                a = season_lines(b, cut)
                a["rookie"] = a.index.isin(rookies)
                a["wp"] = a.tw / a.tg.clip(lower=1)
                Lc = float(a.tg.max())
                frac = Lc / L
                # ---- live method: stats to date
                f = features(a, Lc)
                D = a.assign(**{k: np.asarray(v, float) for k, v in f.items()})
                D["bench"] = (D.start / D.gp) < .5
                P = pool(D, award, y)
                P[feats] = P[feats].fillna(P[feats].median())
                p_live = dict(zip(P.name.map(AM_norm), logit_probs(P, feats, beta)))
                # ---- candidate: forward simulation
                p_sim = simulate(a, prev, D, award, feats, beta, L, y)
                for meth, pm in (("live", p_live), ("sim", p_sim)):
                    pw = pm.get(win, 0.0)
                    fav = max(pm.values()) if pm else 0.0
                    rows.append(dict(season=y, award=award, ck=ci, frac=round(frac, 3), method=meth, p_winner=pw, fav=fav,
                                     fav_won=int(bool(pm) and max(pm, key=pm.get) == win), nll=-np.log(max(pw, 0.002))))
            print(y, award, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2010
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    R = replay(first, last)
    out = os.environ.get("AW_OUT") or os.path.join(ROOT, "model", "replay", "nba_awards_replay.csv")
    R.to_csv(out, index=False)
    R["stage"] = pd.cut(R.frac, [0, .25, .5, .75, 1.01], labels=["Q1", "Q2", "Q3", "Q4"])
    print(R.groupby(["award", "method"]).nll.mean().unstack().round(3).to_string())
    print(R.groupby(["stage", "method"], observed=True).nll.mean().unstack().round(3).to_string())
