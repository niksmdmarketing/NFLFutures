"""NBA/NHL award evaluation against a uniform pool baseline (research/NBA_NHL_AWARD_EVAL_RULE.md).
Reads the existing replays; writes model/award_eval_nba_nhl.json. Usage: python research/nba_nhl_award_eval.py"""
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = {"nba": {"MVP": 25, "DPOY": 20, "ROY": 15, "6MOY": 15},
        "nhl": {"Hart": 26, "Vezina": 10, "Norris": 12, "Calder": 16, "ArtRoss": 15, "Richard": 15}}
METHOD = {"nba": "sim", "nhl": "T1.0"}
CLIP = -np.log(0.002)


def boot_ci(d, n=4000, seed=1):
    """90% season-bootstrap interval of mean(fav - fav_won) over rows, resampling seasons."""
    rng = np.random.default_rng(seed)
    seasons = d.season.unique()
    g = {s: d[d.season == s] for s in seasons}
    out = []
    for _ in range(n):
        z = pd.concat([g[s] for s in rng.choice(seasons, len(seasons))])
        out.append(float((z.fav - z.fav_won).mean()))
    return [float(np.quantile(out, .05)), float(np.quantile(out, .95))]


def evaluate():
    res = {}
    for sport, pools in POOL.items():
        R = pd.read_csv(os.path.join(ROOT, "model", "replay", f"{sport}_awards_replay.csv"))
        R = R[(R.method == METHOD[sport]) & (R.frac >= 0.10) & (R.frac <= 0.90)]
        for award, n in pools.items():
            d = R[R.award == award].copy()
            if d.empty:
                continue
            inpool = d.p_winner > 0
            d["base"] = np.where(inpool, np.log(n), CLIP)
            d["model"] = np.minimum(d.nll, CLIP)
            thirds = pd.cut(d.frac, [0, 1 / 3, 2 / 3, 1.01], labels=["early", "mid", "late"], right=False)
            by = d.groupby(thirds, observed=False)[["model", "base"]].mean()
            ci = boot_ci(d)
            fails = []
            if not d.model.mean() < d.base.mean():
                fails.append("log loss not below baseline")
            for k, r in by.iterrows():
                if not r.model < r.base:
                    fails.append(f"not below baseline in the {k} third")
            if ci[0] > 0:
                fails.append("favourite overconfident")
            res[f"{sport}:{award}"] = {
                "seasons": int(d.season.nunique()), "rows": int(len(d)), "log_loss": round(float(d.model.mean()), 3),
                "baseline_log_loss": round(float(d.base.mean()), 3), "by_third": {k: [round(float(r.model), 3), round(float(r.base), 3)] for k, r in by.iterrows()},
                "mean_p_winner": round(float(d.p_winner.mean()), 3), "winner_in_pool": round(float(inpool.mean()), 3),
                "fav_said": round(float(d.fav.mean()), 3), "fav_won": round(float(d.fav_won.mean()), 3), "fav_gap_ci90": [round(x, 3) for x in ci],
                "pass": not fails, "fails": fails, "method": METHOD[sport], "rule": "research/NBA_NHL_AWARD_EVAL_RULE.md",
                "basis": "in-season checkpoints (10-90% of the season), uniform pool baseline"}
    return res


if __name__ == "__main__":
    r = evaluate()
    json.dump(r, open(os.path.join(ROOT, "model", "award_eval_nba_nhl.json"), "w"), indent=1)
    for k, v in r.items():
        print(f"{k:12s} pass={v['pass']!s:5s} ll {v['log_loss']:.3f} vs base {v['baseline_log_loss']:.3f}  p(winner) {v['mean_p_winner']:.3f}  "
              f"fav said {v['fav_said']:.3f} won {v['fav_won']:.3f} {v['fav_gap_ci90']}  {'; '.join(v['fails'])}")
