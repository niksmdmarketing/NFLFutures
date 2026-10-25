"""NFL props injury-status calibration per research/nfl_games_props/STATUS_CALIBRATION_RULE.md.
Inputs: the research player rows (build.py -> players.parquet; IDs, pre-game appearance features, appearance label with unknowns as NaN)
and nflverse weekly injury reports (data/injuries_<year>.csv). Output: research/nfl_games_props/status_calibration_results.json.
Disclosed implementation details (fixed before scoring): the player rows start in 2018, so fitting seasons are 2018..s-1 rather than
2015..s-1; probabilities are clipped to [0.001, 0.999] for log loss in both versions; the base appearance model is the props model's
logistic form (APP_FEATURES) refitted walk-forward on earlier seasons with train-only standardisation.
Usage: python status_calibration_test.py <players.parquet> <data_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

HERE = Path(__file__).resolve().parent
APP = ["app_rate", "last_snap_share", "mean_snap_share", "miss_streak", "is_qb"]
CURRENT = {"Out": 0.0, "Doubtful": 0.10, "Questionable": 0.80}     # Questionable is a multiplier on the base probability
PSEUDO = 20.0
TEST = [2021, 2022, 2023, 2024, 2025]


def group(pos):
    return "QB" if pos == "QB" else "WR/TE" if pos in ("WR", "TE") else "RB/FB"


def statuses(data_dir):
    frames = []
    for y in range(2018, 2026):
        d = pd.read_csv(Path(data_dir) / f"injuries_{y}.csv", low_memory=False)
        d = d[d.game_type == "REG"]
        if "date_modified" in d:
            d = d.sort_values("date_modified")
        d = d.drop_duplicates(["season", "week", "team", "gsis_id"], keep="last")
        frames.append(d[["season", "week", "team", "gsis_id", "report_status"]])
    s = pd.concat(frames, ignore_index=True)
    s["team"] = s.team.replace({"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "JAC": "JAX"})
    return s.rename(columns={"gsis_id": "aid"})


def ll(p, y):
    p = np.clip(p, 0.001, 0.999)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main(players_path, data_dir):
    P = pd.read_parquet(players_path)
    P = P[P.season <= 2025].copy()
    S = statuses(data_dir)
    P = P.merge(S, on=["season", "week", "team", "aid"], how="left")
    P["status"] = P.report_status.where(P.report_status.isin(list(CURRENT)), None)
    P["grp"] = P.position.map(group)
    known = P.app.notna()
    res = {"rule": "research/nfl_games_props/STATUS_CALIBRATION_RULE.md", "coverage": {
        "player_weeks": int(len(P)), "appearance_unknown": int((~known).sum()),
        "with_status": {k: int((P.status == k).sum()) for k in CURRENT}}, "seasons": {}}
    rows = []
    for y in TEST:
        tr = P[(P.season < y) & known]
        te = P[(P.season == y) & known].copy()
        mu, sd = tr[APP].mean(), tr[APP].std().replace(0, 1)
        lr = LogisticRegression(C=1.0, max_iter=1000).fit((tr[APP] - mu) / sd, tr.app.astype(int))
        base_tr = lr.predict_proba((tr[APP] - mu) / sd)[:, 1]
        te["base"] = lr.predict_proba((te[APP] - mu) / sd)[:, 1]
        tr = tr.assign(base=base_tr)
        table = {}
        for st in CURRENT:
            a = tr[tr.status == st]
            overall = a.app.mean() if len(a) else 0.5
            for g in ("QB", "WR/TE", "RB/FB"):
                b = a[a.grp == g]
                shrunk = (b.app.sum() + PSEUDO * overall) / (len(b) + PSEUDO)
                if st == "Questionable":
                    mb = b.base.mean() if len(b) else a.base.mean()
                    table[(st, g)] = float(np.clip(shrunk / mb, 0, 1.5))
                else:
                    table[(st, g)] = float(shrunk)
        res["seasons"][int(y)] = {"table": {f"{k[0]}|{k[1]}": round(v, 4) for k, v in table.items()}}
        cur = te.base.copy()
        cal = te.base.copy()
        for st in CURRENT:
            m = te.status == st
            if st == "Questionable":
                cur[m] = te.base[m] * CURRENT[st]
                cal[m] = np.clip(te.base[m] * te.grp[m].map(lambda g: table[(st, g)]), 0, 1)
            else:
                cur[m] = CURRENT[st]
                cal[m] = te.grp[m].map(lambda g: table[(st, g)])
        te["p_cur"], te["p_cal"] = cur, cal
        rows.append(te[te.status.notna()])
    X = pd.concat(rows, ignore_index=True)
    y = X.app.to_numpy(float)
    d = ll(X.p_cur.to_numpy(), y) - ll(X.p_cal.to_numpy(), y)        # positive = calibrated better
    by = {int(s): round(float(d[X.season.to_numpy() == s].mean()), 5) for s in TEST}
    rng = np.random.default_rng(7)
    per = {s: d[X.season.to_numpy() == s] for s in TEST}
    bs = [np.concatenate([per[s] for s in rng.choice(TEST, len(TEST))]).mean() for _ in range(2000)]
    cells = {}
    worst_ok = True
    for (st, g), Z in X.groupby(["status", "grp"]):
        yy = Z.app.to_numpy(float)
        lc, lk = float(ll(Z.p_cur.to_numpy(), yy).mean()), float(ll(Z.p_cal.to_numpy(), yy).mean())
        cells[f"{st}|{g}"] = {"n": int(len(Z)), "played": round(float(yy.mean()), 4), "mean_p_current": round(float(Z.p_cur.mean()), 4),
                              "mean_p_calibrated": round(float(Z.p_cal.mean()), 4), "logloss_current": round(lc, 4), "logloss_calibrated": round(lk, 4)}
        if len(Z) >= 200 and lk > lc + 0.01:
            worst_ok = False
    res.update({
        "status_player_weeks_scored": int(len(X)),
        "logloss": {"current": round(float(ll(X.p_cur.to_numpy(), y).mean()), 5), "calibrated": round(float(ll(X.p_cal.to_numpy(), y).mean()), 5)},
        "brier": {"current": round(float(((X.p_cur - y) ** 2).mean()), 5), "calibrated": round(float(((X.p_cal - y) ** 2).mean()), 5)},
        "gain": round(float(d.mean()), 5), "lower95_one_sided": round(float(np.percentile(bs, 5)), 5), "by_season": by, "cells": cells})
    res["gates"] = {"1_overall_bound": bool(d.mean() > 0 and np.percentile(bs, 5) > 0),
                    "2_four_of_five_seasons": bool(sum(v > 0 for v in by.values()) >= 4),
                    "3_no_large_cell_worse_by_0.01": bool(worst_ok)}
    res["passes"] = bool(all(res["gates"].values()))
    (HERE / "status_calibration_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "seasons"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
