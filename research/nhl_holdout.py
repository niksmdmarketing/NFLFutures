"""Nested leave-one-season-out check of the NHL replay settings (research).

Reads weekly replays written with different settings (research/replay_nhl.py with BT_OUTDIR=<dir>, one directory per setting;
the first directory given is the live setting). Per season and market it computes the mean log loss over all checkpoints, then:
  1. gain of every setting over live per market and on the combined score (mean of the markets), with a 90% bootstrap over seasons;
  2. leave-one-season-out: the setting with the best combined score on the OTHER seasons is chosen and scored on the held-out season.
Usage: python research/nhl_holdout.py <live_dir> <setting_dir> [<setting_dir> ...]
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

MK = {"playoff": ("p_playoff", "y_playoff"), "div": ("p_div", "y_div"), "pres": ("p_pres", "y_pres"), "r2": ("p_r2", "y_r2"),
      "r3": ("p_r3", "y_r3"), "final": ("p_conf", "y_finals"), "title": ("p_title", "y_title")}


def ll(p, y):
    p = np.clip(np.asarray(p, float), 0.002, 0.998)
    y = np.asarray(y, float)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def per_season(d):
    rows = {}
    for f in sorted(glob.glob(os.path.join(d, "nhl_*.csv"))):
        D = pd.read_csv(f)
        y = int(D.season.iloc[0])
        r = {}
        for m, (pc, yc) in MK.items():
            z = D.dropna(subset=[pc, yc])
            r[m] = ll(z[pc], z[yc]) if len(z) else np.nan
        rows[y] = r
    return pd.DataFrame(rows).T


def boot(x, n=4000, seed=1):
    rng = np.random.default_rng(seed)
    x = np.asarray(x.dropna(), float)
    if not len(x):
        return np.nan, np.nan, np.nan
    m = [rng.choice(x, len(x)).mean() for _ in range(n)]
    return float(x.mean()), float(np.percentile(m, 5)), float(np.percentile(m, 95))


def main(dirs):
    names = [os.path.basename(d.rstrip("/")) for d in dirs]
    T = {n: per_season(d) for n, d in zip(names, dirs)}
    live = T[names[0]]
    yrs = sorted(live.index)
    print("Gain over live (log loss, positive = better), mean over seasons, 90% bootstrap over seasons, better in n/N")
    for n in names[1:]:
        t = T[n].reindex(live.index)
        line = f"{n:8s}"
        for m in MK:
            d = live[m] - t[m]
            mean, lo, hi = boot(d)
            line += f" | {m} {mean:+.4f} ({lo:+.4f},{hi:+.4f}) {int((d > 0).sum())}/{int(d.notna().sum())}"
        print(line)
        c = live[list(MK)].mean(axis=1) - t[list(MK)].mean(axis=1)
        mean, lo, hi = boot(c)
        print(f"{'':8s} combined {mean:+.4f} ({lo:+.4f},{hi:+.4f}) better in {int((c > 0).sum())}/{int(c.notna().sum())} seasons")
    print("\nLeave-one-season-out: setting chosen on the other seasons, scored on the held-out season")
    comb = {n: T[n].reindex(live.index)[list(MK)].mean(axis=1) for n in names}
    gains, picks = [], []
    for y in yrs:
        others = [z for z in yrs if z != y]
        best = min(names, key=lambda n: comb[n][others].mean())
        picks.append(f"{y}:{best}")
        gains.append(comb[names[0]][y] - comb[best][y])
    g = np.array(gains)
    print("picks:", ", ".join(picks))
    print(f"held-out gain of the chosen setting over live: mean {g.mean():+.4f}, better in {(g > 0).sum()}/{len(g)} seasons")


if __name__ == "__main__":
    main(sys.argv[1:])
