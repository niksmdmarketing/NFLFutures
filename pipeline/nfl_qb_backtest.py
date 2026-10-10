"""Point-in-time test of the NFL quarterback layer (run offline: python pipeline/nfl_qb_backtest.py).

The live model shifts a team's rating by lambda x (value of the expected starter - value of the QB behind this season's
numbers). Past depth charts as they stood each week are not available, so the test uses the QB who took the team's first
dropback of each game as the "expected starter" (known before kickoff in nearly every case).
For every regular-season game from week 2 on, 2019-2025: team strength and QB values are rebuilt from play-by-play before
that week only, then the game margin is predicted with and without the QB layer.
Writes model/qb_backtest.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ratings
from common import FIX, MODEL, TEAMS, games, load_pbp, scrimmage

SEASONS = range(int(os.environ.get("QB_FIRST", "2019")), int(os.environ.get("QB_LAST", "2025")) + 1)
LAMBDAS = (0.0, 0.25, 0.5, 0.75, 1.0)


def starters(pbp):
    """(game_id, team) -> QB id who took the first dropback."""
    s = scrimmage(pbp)
    s = s[s.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    s = s.sort_values(["game_id", "play_id"])
    return s.groupby(["game_id", "posteam"]).qb.first().to_dict()


def main_qb(pbp):
    s = scrimmage(pbp)
    s = s[s.qb_dropback == 1].assign(qb=lambda x: x.passer_player_id.fillna(x.rusher_player_id)).dropna(subset=["qb"])
    return s.groupby("posteam").qb.agg(lambda x: x.value_counts().index[0]).to_dict()


def run():
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    S = ratings.S
    scale, hfa = S["sim"].get("rating_scale", 1.0), S["sim"]["hfa"]
    rows = []
    for y in SEASONS:
        cur_all, pri, pri2 = load_pbp(y), load_pbp(y - 1), load_pbp(y - 2)
        st = starters(cur_all)
        pri_main = main_qb(pri)
        reg = g[(g.season == y) & (g.game_type == "REG") & g.result.notna()]
        for w in sorted(reg.week.unique()):
            if w < 2:
                continue
            cur = cur_all[cur_all.week < w]
            gg = g.copy()
            gg.loc[(gg.season == y) & (gg.week >= w), "result"] = np.nan
            base, _ = ratings.base_ratings(cur, pri, gg, y)
            vals, low, _ = ratings.qb_values(cur, pri, pri2)
            ref = {**pri_main, **main_qb(cur)}
            B = dict(zip(TEAMS, base))
            for r in reg[reg.week == w].itertuples():
                d = {}
                for side, t in (("h", r.home_team), ("a", r.away_team)):
                    s_id, r_id = st.get((r.game_id, t)), ref.get(t)
                    d[side] = vals.get(s_id, low) - vals.get(r_id, low) if s_id and r_id and s_id != r_id else 0.0
                rows.append(dict(season=y, week=w, game=r.game_id, result=r.result, base=scale * (B[r.home_team] - B[r.away_team]) + hfa,
                                 qdiff=scale * (d["h"] - d["a"]), change=int(d["h"] != 0 or d["a"] != 0)))
        print("season", y, flush=True)
    return pd.DataFrame(rows)


def score(D):
    out = {"seasons": f"{min(SEASONS)}-{max(SEASONS)}", "games": int(len(D)), "games_with_qb_change": int(D.change.sum()), "by_lambda": {}}
    for lam in LAMBDAS:
        p = D.base + lam * D.qdiff
        e = D.result - p
        ch = D.change == 1
        out["by_lambda"][str(lam)] = {"rmse_all": round(float(np.sqrt((e ** 2).mean())), 3),
                                      "rmse_changed": round(float(np.sqrt((e[ch] ** 2).mean())), 3),
                                      "winner_right_changed": round(float(((p[ch] > 0) == (D.result[ch] > 0)).mean()), 3)}
    # out-of-sample lambda: fit on earlier seasons, score later ones
    ch = D[D.change == 1]
    early, late = ch[ch.season <= 2021], ch[ch.season >= 2022]
    best = min(LAMBDAS, key=lambda l: float(((early.result - early.base - l * early.qdiff) ** 2).mean()))
    out["oos"] = {"lambda_fit_2019_2021": best,
                  "rmse_2022_2025_no_layer": round(float(np.sqrt(((late.result - late.base) ** 2).mean())), 3),
                  "rmse_2022_2025_fitted": round(float(np.sqrt(((late.result - late.base - best * late.qdiff) ** 2).mean())), 3),
                  "rmse_2022_2025_live_0.5": round(float(np.sqrt(((late.result - late.base - 0.5 * late.qdiff) ** 2).mean())), 3),
                  "games": int(len(late))}
    # free fit of the slope on changed games, with its standard error
    x, r = ch.qdiff.values, (ch.result - ch.base).values
    b = float((x * r).sum() / (x * x).sum())
    se = float(np.sqrt(((r - b * x) ** 2).sum() / (len(x) - 1) / (x * x).sum()))
    out["free_slope"] = {"lambda": round(b, 3), "se": round(se, 3)}
    return out


if __name__ == "__main__":
    D = run()
    D.to_csv(os.path.join(os.environ.get("TMPDIR", "/tmp"), "qb_bt.csv"), index=False)
    R = score(D)
    json.dump(R, open(os.path.join(MODEL, "qb_backtest.json"), "w"), indent=1)
    print(json.dumps(R, indent=1))
