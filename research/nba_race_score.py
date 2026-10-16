"""Race log loss for the NBA replay (research): -log P(actual winner) for the title, each conference and each division.

Each checkpoint's probabilities are renormalised inside the race (30 teams for the title, 15 per conference, 5 per division) and
the loss is the log of the winner's share, so the winner's probability is not diluted by the 29 other binary events.
Primary: seasons without 2020-21 (72 games, unusual environment); sensitivity: with 2020-21. The 2019-20 bubble is never replayed.
Usage: python research/nba_race_score.py <replay_dir>    (CSVs nba_<season>.csv written by research/replay_nba.py)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402

STAGES = [(0, 0.001, "preseason"), (0.001, 0.25, "first quarter"), (0.25, 0.5, "second quarter"), (0.5, 0.75, "third quarter"), (0.75, 1.01, "last quarter")]
CONF = {t: "E" for t in N.EAST} | {t: "W" for t in N.WEST}
DIV = {t: d for d, ts in N.DIVS.items() for t in ts}


def race(df, group, pcol, ycol):
    """Mean -log(share of the winner) per checkpoint, averaged over the races (groups) at that checkpoint."""
    out = []
    for (wk,), g in df.groupby(["week"]):
        for _, r in g.groupby(group):
            s = r[pcol].sum()
            w = r[r[ycol] == 1]
            if s <= 0 or w.empty:
                continue
            out.append((wk, float(-np.log(max(w[pcol].iloc[0] / s, 1e-4))), len(r)))
    return out


def main(d):
    parts = []
    for f in sorted(glob.glob(os.path.join(d, "nba_*.csv"))):
        D = pd.read_csv(f)
        D["frac"] = D.week / max(D.week.max(), 1)
        parts.append(D)
    A = pd.concat(parts, ignore_index=True)
    A["conf"] = A.team.map(CONF)
    A["div"] = A.team.map(DIV)
    for label, drop in (("PRIMARY (without 2020-21)", {2021}), ("SENSITIVITY (with 2020-21)", set())):
        X = A[~A.season.isin(drop)]
        print(f"\n{label}: seasons {sorted(X.season.unique())}")
        print(f"{'stage':15s} {'title':>14s} {'conference':>14s} {'division':>14s}   (race log loss, uniform in brackets)")
        for lo, hi, name in STAGES:
            x = X[X.week == 0] if name == "preseason" else X[(X.frac >= lo) & (X.frac < hi) & (X.week > 0)]
            cells = []
            for grp, p, y, k in (("season", "p_title", "y_title", 30), ("conf", "p_conf", "y_finals", 15), ("div", "p_div", "y_div", 5)):
                vals = []
                for s_, g in x.groupby("season"):
                    g = g.copy()
                    r = race(g, [grp] if grp != "season" else ["season"], p, y)
                    vals += [v for _, v, _ in r]
                cells.append(f"{np.mean(vals):.3f} ({np.log(k):.2f})" if vals else "n/a")
            print(f"{name:15s} {cells[0]:>14s} {cells[1]:>14s} {cells[2]:>14s}")


if __name__ == "__main__":
    main(sys.argv[1])
