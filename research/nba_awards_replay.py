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
from nba_site import AM_norm, cup_finals  # noqa: E402
from nba_award_sim import *  # noqa: E402,F401,F403
import nba_award_sim as SIM  # noqa: E402
from trends_awards import NBA_AW  # noqa: E402
from nba_award_early_tools import CHECKPOINT_DAYS, scheduled_games, validate_distribution, blend

EARLY = os.environ.get("AW_EARLY") == "1"

def final_tables(years):
    """End-of-season candidate pools with the winner flagged, for fitting the logit."""
    out = {}
    seen = set()
    for y in years:
        b = boxes(y, replay=EARLY)
        if b is None:
            continue
        final_b = b
        if EARLY and y >= 2024:
            # Completed prior/training seasons may identify their Cup final. The checkpoint
            # input b remains untouched; every registered early checkpoint precedes that final.
            t = b.drop_duplicates(["game_id", "team"]).rename(columns={"team":"team_abbreviation", "date":"game_date"}).assign(season_type=2)
            final_b = b[~b.game_id.isin(cup_finals(t))]
        a = season_lines(final_b)
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


TEMPS = [float(t) for t in os.environ.get("AW_TEMPS", "1").split(",")]
LATE_ONLY = float(os.environ.get("AW_LATE_ONLY", "0"))   # research: skip checkpoints before this share of the season


PRE_CACHE = {}


def replay(first, last):
    if EARLY:
        required = {"AW_TEMPS":"1", "AW_RETURN":"0", "AW_CURTEAM":"0", "AW_LATE_ONLY":"0", "AW_PRE_ONLY":"0", "AW_RULE65":"1", "AW_SIMS":"300"}
        for key,value in required.items():
            if os.environ.get(key,value) != value:
                raise ValueError(f"Frozen early test requires {key}={value}")
    PRE_CACHE.clear()
    FT = final_tables(list(range(2003, last + 1)))
    rows = []
    for y in range(first, last + 1):
        if y not in FT or (y - 1) not in FT:
            continue
        b, Dfin, L = FT[y]
        if EARLY:L = float(scheduled_games(y))
        prev = FT[y - 1][1]
        start, end = b.date.min(), b.date.max()
        cuts = list(pd.date_range(start + pd.Timedelta(days=21), end - pd.Timedelta(days=3), freq="14D"))
        if EARLY:   # research/NBA_AWARD_EARLY_SHRINK_RULE.md: early checkpoints only
            cuts = [start + pd.Timedelta(days=d) for d in CHECKPOINT_DAYS]
        rookies = set(Dfin.index[Dfin.rookie])
        seen_before = set().union(*(set(FT[z][1].index) for z in FT if z < y)) if EARLY else set()
        for award in SPECS:
            if y not in NBA_AW[award]:
                continue
            feats = SPECS[award][3]
            train = pd.concat([pool(FT[z][1], award, z) for z in FT if z != y and z in NBA_AW[award] and z >= 2003], ignore_index=True)
            train[feats] = train[feats].fillna(train[feats].median())
            beta = AM.fit(train, feats)
            win = AM_norm(NBA_AW[award][y])
            # preseason: last season's final lines scored by the logit ("live" stand-in) vs the simulated season
            if award != "ROY" and LATE_ONLY == 0:
                Pp = pool(prev.assign(season=y), award, y)
                Pp[feats] = Pp[feats].fillna(Pp[feats].median())
                p_live = dict(zip(Pp.name.map(AM_norm), logit_probs(Pp, feats, beta)))
                ct = None
                if os.environ.get("AW_CURTEAM") == "1":   # team a player opens the season with (known by opening night)
                    bb = b.sort_values("date")
                    ct = {str(k): v for k, v in bb.groupby("athlete_id").team.first().items()}
                prev2 = FT[y - 2][1] if (y - 2) in FT else None
                p_sim = SIM.preseason_probs(prev, award, feats, beta, L, y, prev2=prev2, cur_team=ct, replay=EARLY)
                for meth, pm in (("live", p_live), ("sim", p_sim)):
                    pw = pm.get(win, 0.0)
                    rows.append(dict(season=y, award=award, ck=-1, frac=0.0, method=meth, p_winner=pw, fav=max(pm.values()) if pm else 0.0,
                                     fav_won=int(bool(pm) and max(pm, key=pm.get) == win), nll=-np.log(max(pw, 0.002))))
            for ci, cut in enumerate([] if os.environ.get("AW_PRE_ONLY") == "1" else cuts):
                a = season_lines(b, cut)
                a["rookie"] = ~a.index.isin(seen_before) if EARLY else a.index.isin(rookies)
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
                if frac < LATE_ONLY:
                    continue
                # ---- candidate: forward simulation (TEMPS: logit temperatures, 1 = live)
                diagnostics = {}
                sims = [(("sim" if T == 1.0 else f"simT{T}"), simulate(a, prev, D, award, feats, beta / T, L, y, replay=EARLY, diagnostics=diagnostics)) for T in TEMPS]
                extra = []
                if EARLY:
                    ps = sims[0][1]
                    pp = None
                    if award != "ROY":
                        if (y, award) not in PRE_CACHE:
                            PRE_CACHE[(y, award)] = SIM.preseason_probs(prev, award, feats, beta, L, y, replay=True)
                        pp = PRE_CACHE[(y, award)]
                    pb = blend(ps, pp, Lc)
                    extra = [("shrink", pb)]
                for meth, pm in [("live", p_live)] + sims + extra:
                    if EARLY:validate_distribution(pm)
                    pw = pm.get(win, 0.0)
                    fav = max(pm.values()) if pm else 0.0
                    rows.append(dict(season=y, award=award, ck=ci, frac=frac if EARLY else round(frac, 3), L=L, team_games=Lc, checkpoint_days=(cut-start).days, cutoff=cut.isoformat(), invalid_draws=diagnostics.get("invalid_draws",0), probability_mass=sum(pm.values()), support=len(pm), winner_in_support=win in pm and pm.get(win,0)>0, method=meth, p_winner=pw, fav=fav,
                                     fav_won=int(bool(pm) and max(pm, key=pm.get) == win), nll=-np.log(max(pw, 0.002))))
            print(y, award, flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2010
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    R = replay(first, last)
    out = os.environ.get("AW_OUT") or os.path.join(ROOT, "model", "replay", "nba_awards_replay.csv")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    R.to_csv(out, index=False)
    R["stage"] = pd.cut(R.frac, [0, .25, .5, .75, 1.01], labels=["Q1", "Q2", "Q3", "Q4"])
    print(R.groupby(["award", "method"]).nll.mean().unstack().round(3).to_string())
    print(R.groupby(["stage", "method"], observed=True).nll.mean().unstack().round(3).to_string())
