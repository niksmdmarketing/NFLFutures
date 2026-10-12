"""Compare replay variants: mean log loss per market over all checkpoints, and in how many seasons each variant beats the first.
Usage: python research/replay_compare.py <sport> <baseline_dir> <variant_dir> [<variant_dir> ...]"""
import glob
import sys

import numpy as np
import pandas as pd

import replay_score as S


def load(d, sport):
    return pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{d}/{sport}_[0-9]*.csv"))], ignore_index=True)


def per_season(D, pc, yc):
    return D.assign(l=-(D[yc] * np.log(D[pc].clip(.002, .998)) + (1 - D[yc]) * np.log(1 - D[pc].clip(.002, .998)))).groupby("season").l.mean()


if __name__ == "__main__":
    sport, base, *vars_ = sys.argv[1:]
    dirs = [base] + vars_
    D = {d: load(d, sport) for d in dirs}
    for m, (pc, yc) in S.MARKETS.items():
        if pc not in D[base] or D[base][yc].isna().all():
            continue
        b = per_season(D[base], pc, yc)
        line = f"{m:8s} base {b.mean():.4f}"
        for d in vars_:
            v = per_season(D[d], pc, yc)
            line += f" | {d.split('/')[-1]} {v.mean():.4f} ({int((v < b).sum())}/{len(b)} seasons better)"
        print(line)
