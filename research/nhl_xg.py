"""Shot-quality (expected goals) model for NHL unblocked shots (research), fitted leave-one-season-out so a season's xG
never uses its own goals. Features: distance and angle to the net, shot type, rebound (same team shot within 3 s),
strength (power play / short-handed). Empty-net shots get xG from the empty-net goal rate.
Usage: python research/nhl_xg.py <shifts data dir>   -> writes shots_xg_<y>.csv.gz next to the inputs
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

TYPES = ["wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around", "poke", "bat", "between-legs", "cradle"]


def prep(S):
    S = S[S.type.isin(["shot-on-goal", "missed-shot", "goal"])].copy()
    S = S.sort_values(["game_id", "period", "t"])
    sit = S.situation.astype(str).str.zfill(4)
    ag, ask, hsk, hg = (sit.str[i].astype(int) for i in range(4))
    S["own_sk"] = np.where(S.home == 1, hsk, ask)
    S["opp_sk"] = np.where(S.home == 1, ask, hsk)
    S["empty_net"] = np.where(S.home == 1, ag, hg) == 0
    x = pd.to_numeric(S.x, errors="coerce").fillna(0.0)
    y = pd.to_numeric(S.y, errors="coerce").fillna(0.0)
    side = S.side.astype(str) if "side" in S else pd.Series("nan", index=S.index)
    # attacking toward +x if the shooting team defends the left net
    home_def_left = side == "left"
    attack_pos = np.where(S.home == 1, home_def_left, ~home_def_left)
    known = side.isin(["left", "right"])
    xa = pd.Series(np.where(known, np.where(attack_pos, x, -x), x.abs()), index=S.index)
    dx = (89 - xa).clip(lower=-10)
    S["dist"] = np.hypot(dx, y).clip(lower=1)
    S["angle"] = np.degrees(np.arctan2(y.abs(), dx.abs().clip(lower=0.5)))
    S["behind"] = (dx < 0).astype(float)
    prev_t = S.groupby(["game_id", "period"]).t.shift()
    prev_team = S.groupby(["game_id", "period"]).team.shift()
    S["rebound"] = ((S.t - prev_t <= 3) & (prev_team == S.team)).astype(float)
    S["pp"] = (S.own_sk > S.opp_sk).astype(float)
    S["sh"] = (S.own_sk < S.opp_sk).astype(float)
    S["goal"] = (S.type == "goal").astype(int)
    return S


def features(S):
    X = pd.DataFrame({"ld": np.log(S.dist), "d": S.dist / 50, "d2": (S.dist / 50) ** 2, "a": S.angle / 45, "a2": (S.angle / 45) ** 2,
                      "ad": S.angle / 45 * np.log(S.dist), "behind": S.behind, "reb": S.rebound, "reb_a": S.rebound * S.angle / 45,
                      "pp": S.pp, "sh": S.sh}, index=S.index)
    st = S.shot_type.astype(str).str.lower()
    for t in TYPES:
        X["t_" + t] = (st == t).astype(float)
    return X


def main(d):
    files = sorted(glob.glob(os.path.join(d, "shots_*.csv.gz")))
    files = [f for f in files if "_xg_" not in f]
    data = {int(os.path.basename(f)[6:10]): prep(pd.read_csv(f, low_memory=False)) for f in files}
    for y, S in data.items():
        tr = pd.concat([v for k, v in data.items() if k != y])
        tr = tr[~tr.empty_net]
        m = LogisticRegression(C=1.0, max_iter=2000).fit(features(tr), tr.goal)
        en_rate = pd.concat([v for k, v in data.items() if k != y]).query("empty_net").goal.mean()
        S = S.copy()
        S["xg"] = np.where(S.empty_net, en_rate, m.predict_proba(features(S))[:, 1])
        from sklearn.metrics import log_loss
        ne = S[~S.empty_net]
        print(y, len(S), "goals", int(S.goal.sum()), "xG", round(float(S.xg.sum()), 1),
              "logloss", round(log_loss(ne.goal, ne.xg), 4), "base", round(log_loss(ne.goal, np.full(len(ne), ne.goal.mean())), 4), flush=True)
        S[["game_id", "period", "t", "stint", "team", "home", "type", "shooter", "goalie", "own_sk", "opp_sk", "empty_net", "goal", "xg"]].to_csv(
            os.path.join(d, f"shots_xg_{y}.csv.gz"), index=False)


if __name__ == "__main__":
    main(sys.argv[1])
