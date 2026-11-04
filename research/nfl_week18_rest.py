"""Stage 1 of research/NFL_WEEK18_REST_RULE.md: do clubs with a locked seed underperform in the final regular-season week?

Usage: python research/nfl_week18_rest.py   -> research/nfl_week18_rest_results.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import DIVS, TEAMS, TIX, games  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402

HFA = 1.8
DIV_OF = {t: d for d, ts in DIVS.items() for t in ts}
CONF_OF = {t: d.split()[0] for t, d in DIV_OF.items()}


def srs(g):
    X = np.zeros((len(g), len(TEAMS)))
    X[np.arange(len(g)), g.home_team.map(TIX).values] = 1
    X[np.arange(len(g)), g.away_team.map(TIX).values] = -1
    m = Ridge(alpha=1.0, fit_intercept=True).fit(X, g.result.values)
    c = m.coef_ - m.coef_.mean()
    return dict(zip(TEAMS, c))


def wins(g):
    w = {t: 0.0 for t in TEAMS}
    for h, a, r in zip(g.home_team, g.away_team, g.result):
        w[h] += 1.0 if r > 0 else 0.5 if r == 0 else 0.0
        w[a] += 1.0 if r < 0 else 0.5 if r == 0 else 0.0
    return w


def locked(w):
    """Clubs whose division title and place among division winners cannot change with one game left (rule definition)."""
    lead = {}
    for d, ts in DIVS.items():
        lead[d] = max(w[t] for t in ts)
    contenders = {t for t in TEAMS if w[t] >= lead[DIV_OF[t]] - 1.0}       # could still win their division
    out = set()
    for t in TEAMS:
        rivals = [u for u in DIVS[DIV_OF[t]] if u != t]
        if not all(w[t] - w[u] > 1.0 for u in rivals):
            continue
        others = [u for u in contenders if CONF_OF[u] == CONF_OF[t] and DIV_OF[u] != DIV_OF[t]]
        if all(abs(w[t] - w[u]) > 1.0 for u in others):
            out.add(t)
    return out


def main():
    g = games()
    g = g[(g.game_type == "REG") & g.result.notna() & (g.season >= 2002) & (g.season <= 2025)]
    rows = []
    for y, gy in g.groupby("season"):
        last = gy.week.max()
        before, fin = gy[gy.week < last], gy[gy.week == last]
        w, s = wins(before), srs(before)
        L = locked(w)
        for r in fin.itertuples():
            neutral = str(getattr(r, "location", "Home")).lower() == "neutral"
            exp = s[r.home_team] - s[r.away_team] + (0.0 if neutral else HFA)
            res = r.result - exp
            lh, la = r.home_team in L, r.away_team in L
            if lh and la:
                kind, side = "both", np.nan
            elif lh:
                kind, side = "locked", res
            elif la:
                kind, side = "locked", -res
            else:
                kind, side = "control", res
            rows.append(dict(season=y, week=last, home=r.home_team, away=r.away_team, kind=kind, resid=res, locked_side=side,
                             locked_team=r.home_team if lh and not la else (r.away_team if la and not lh else None)))
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(ROOT, "research", "nfl_week18_rest_rows.csv"), index=False)
    loc = D[D.kind == "locked"]
    ctl = D[D.kind == "control"]
    rng = np.random.default_rng(1)
    seasons = sorted(D.season.unique())
    by = loc.groupby("season").locked_side.agg(["sum", "count"]).reindex(seasons).fillna(0)
    boots = []
    for _ in range(4000):
        pick = rng.choice(seasons, len(seasons))
        s_, n_ = by.loc[pick, "sum"].sum(), by.loc[pick, "count"].sum()
        boots.append(s_ / n_ if n_ else np.nan)
    lo, hi = np.nanpercentile(boots, [5, 95])
    out = {"rule": "research/NFL_WEEK18_REST_RULE.md", "n_locked_games": int(len(loc)), "n_control": int(len(ctl)),
           "n_both": int((D.kind == "both").sum()), "effect_mean": round(float(loc.locked_side.mean()), 3),
           "effect_90": [round(float(lo), 3), round(float(hi), 3)], "control_mean": round(float(ctl.resid.mean()), 3),
           "locked_by_season": loc.groupby("season").size().to_dict(),
           "stage1": "pass" if hi < 0 else "fail"}
    json.dump(out, open(os.path.join(ROOT, "research", "nfl_week18_rest_results.json"), "w"), indent=1, default=int)
    print(json.dumps(out, indent=1, default=int))
    print(loc[["season", "locked_team", "home", "away", "locked_side"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
