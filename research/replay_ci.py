"""Calibration slope and intercept per market and stage, with season-cluster bootstrap intervals (whole seasons resampled, since
weeks within a season move together). Usage: python research/replay_ci.py <sport> [reps]   (reads model/replay/<sport>_*.csv)
Prints: stage, market, slope [90% CI], intercept [90% CI], seasons. A CI that spans 1 means the data cannot tell this apart from calibrated."""
import sys

import numpy as np

import replay_score as S
import replay_slope as L


def ci_rows(D, markets, stages, cluster, reps=200, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for lo, hi, name in stages:
        x = D[(D.frac >= lo) & (D.frac < hi)] if name != "preseason" else D[D.week == 0]
        x_all = x
        for m, (pc, yc) in markets.items():
            x = x_all
            if pc not in x or yc not in x or x[yc].isna().all() or x[yc].sum() < 3:
                continue
            x = x.dropna(subset=[pc, yc])
            groups = {k: g for k, g in x.groupby(cluster)}
            keys = list(groups)
            a, b, _ = L.fit(x[pc], x[yc])
            bs = []
            for _ in range(reps):
                pick = rng.choice(len(keys), len(keys))
                import pandas as pd
                z = pd.concat([groups[keys[i]] for i in pick])
                if z[yc].sum() < 2:
                    continue
                bs.append(L.fit(z[pc], z[yc])[:2])
            bs = np.array(bs)
            lo_, hi_ = np.percentile(bs, [5, 95], axis=0)
            out.append((name, m, b, lo_[1], hi_[1], a, lo_[0], hi_[0], len(keys)))
    return out


if __name__ == "__main__":
    D = S.load(sys.argv[1])
    for r in ci_rows(D, S.MARKETS, S.STAGES, "season", int(sys.argv[2]) if len(sys.argv) > 2 else 200):
        print(f"{r[0]:15s} {r[1]:8s} slope {r[2]:5.2f} [{r[3]:.2f},{r[4]:.2f}]  int {r[5]:+.2f} [{r[6]:+.2f},{r[7]:+.2f}]  seasons {r[8]}")
