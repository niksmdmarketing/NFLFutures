"""Score replayed futures probabilities (model/replay/<sport>_<season>.csv) per market and per stage of the season.

Columns used: p_<market> and y_<market>. 'p_conf' is stored as the Finals probability and scored against y_finals.
Per market and stage: log loss, the same for a base-rate forecast (every team gets the league-wide frequency), the
log-loss gain over base, the mean probability given to the eventual winner(s), and a 6-bin reliability table.
Usage: python research/replay_score.py <sport> [out.json]
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKETS = {"title": ("p_title", "y_title"), "finals": ("p_conf", "y_finals"), "div": ("p_div", "y_div"),
           "seed1": ("p_seed1", "y_seed1"), "playoff": ("p_playoff", "y_playoff"), "top8": ("p_top8", "y_top8"), "pf": ("p_pf", "y_pf"),
           "r2": ("p_r2", "y_r2"), "cf": ("p_cf", "y_cf"), "r3": ("p_r3", "y_r3"), "pres": ("p_pres", "y_pres"),
           "top6": ("p_top6", "y_top6"), "playin": ("p_playin", "y_playin"), "semi": ("p_semi", "y_semi")}
STAGES = [(0, 0.001, "preseason"), (0.001, 0.25, "first quarter"), (0.25, 0.5, "second quarter"), (0.5, 0.75, "third quarter"),
          (0.75, 1.01, "last quarter")]


def ll(p, y, lo=0.002):
    p = np.clip(np.asarray(p, float), lo, 1 - lo)
    y = np.asarray(y, float)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def load(sport):
    fs = sorted(glob.glob(os.path.join(ROOT, "model", "replay", f"{sport}_*.csv")))
    D = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    D["frac"] = D.groupby("season").week.transform(lambda w: w / max(w.max(), 1))
    return D


def score(D):
    res = {}
    for lo, hi, name in STAGES:
        x = D[(D.frac >= lo) & (D.frac < hi)] if name != "preseason" else D[D.week == 0]
        if x.empty:
            continue
        r = {"seasons": int(x.season.nunique()), "checkpoints": int(x.groupby(["season", "week"]).ngroups)}
        for m, (pc, yc) in MARKETS.items():
            if pc not in x or yc not in x or x[yc].isna().all():
                continue
            x_all = x
            x = x.dropna(subset=[pc, yc])   # a market may cover only some seasons (e.g. NBL semi-finals: play-in era only)
            base = x[yc].mean()
            r[m] = {"logloss": round(ll(x[pc], x[yc]), 4), "base": round(ll(np.full(len(x), base), x[yc]), 4),
                    "winner_p": round(float(x[x[yc] == 1][pc].mean()), 3)}
            r[m]["gain"] = round(r[m]["base"] - r[m]["logloss"], 4)
            bins = pd.cut(x[pc], [0, .05, .15, .35, .6, .85, 1.0], include_lowest=True)
            r[m]["calibration"] = [{"bin": str(b), "pred": round(float(v[pc].mean()), 3), "actual": round(float(v[yc].mean()), 3), "n": int(len(v))}
                                   for b, v in x.groupby(bins, observed=True)]
            r[m]["seasons"] = int(x.season.nunique())
            x = x_all
        res[name] = r
    return res


if __name__ == "__main__":
    out = score(load(sys.argv[1]))
    if len(sys.argv) > 2:
        json.dump(out, open(sys.argv[2], "w"), indent=1)
    for st, r in out.items():
        print(st, f"({r['seasons']} seasons, {r['checkpoints']} checkpoints)")
        for m in MARKETS:
            if m in r:
                print(f"  {m:8s} ll {r[m]['logloss']:.4f} base {r[m]['base']:.4f} gain {r[m]['gain']:+.4f} winner_p {r[m]['winner_p']}")
