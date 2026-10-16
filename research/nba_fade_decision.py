"""Scores the NBA roster-fade variants against model/replay/NBA_ROSTER_FADE_RULE.md (research).
Per season and variant: combined race log loss (mean of title, conference, division over all checkpoints) and the binary log loss of every p_/y_ market.
Reports for main (full v f05, f10) and NOLEAK (noleak v nf05, nf10): gain by season, majority, preseason, nested leave-one-season-out choice, with and without 2020-21.
Usage: python research/nba_fade_decision.py <dir with full noleak f05 f10 nf05 nf10 teamonly>"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba_race_score as R  # noqa: E402


def load(d):
    parts = []
    for f in sorted(glob.glob(os.path.join(d, "nba_*.csv"))):
        D = pd.read_csv(f)
        parts.append(D)
    A = pd.concat(parts, ignore_index=True)
    A["conf"] = A.team.map(R.CONF)
    A["div"] = A.team.map(R.DIV)
    return A


def per_season(A, pre):
    out = {}
    for s, g in A.groupby("season"):
        g = g[g.week == 0] if pre else g[g.week > 0]
        vals = []
        for grp, p, y in (("season", "p_title", "y_title"), ("conf", "p_conf", "y_finals"), ("div", "p_div", "y_div")):
            r = R.race(g, [grp], p, y)
            vals.append(np.mean([v for _, v, _ in r]))
        out[s] = float(np.mean(vals))
    return pd.Series(out)


def binll(A, pre):
    res = {}
    for pc in [c for c in A.columns if c.startswith("p_")]:
        yc = "y_" + pc[2:] if pc != "p_conf" else "y_finals"
        if yc not in A:
            continue
        g = A[A.week == 0] if pre else A[A.week > 0]
        z = g.dropna(subset=[pc, yc])
        p = np.clip(z[pc].values, 0.002, 0.998)
        res[pc] = z.assign(l=-(z[yc] * np.log(p) + (1 - z[yc]) * np.log(1 - p))).groupby("season").l.mean()
    return pd.DataFrame(res)


def main(root):
    runs = {k: load(os.path.join(root, k)) for k in ("teamonly", "full", "f05", "f10", "noleak", "nf05", "nf10")}
    allp = {k: per_season(v, False) for k, v in runs.items()}
    pre = {k: per_season(v, True) for k, v in runs.items()}
    bl = {k: binll(v, False).mean(axis=1) for k, v in runs.items()}
    print("combined race log loss by season (all checkpoints after the opener), lower is better")
    print(pd.DataFrame(allp).round(3).to_string())
    for label, base, vs in (("MAIN", "full", ("f05", "f10")), ("NOLEAK", "noleak", ("nf05", "nf10"))):
        for drop in ((2021,), ()):
            yrs = [s for s in allp[base].index if s not in drop]
            print(f"\n{label} {'primary (no 2020-21)' if drop else 'with 2020-21'}: mean over {len(yrs)} seasons")
            for v in vs:
                d = (allp[base] - allp[v]).loc[yrs]
                dp = (pre[base] - pre[v]).loc[yrs]
                db = (bl[base] - bl[v]).loc[yrs]
                print(f"  {v}: race gain {d.mean():+.4f} (better in {int((d > 0).sum())}/{len(d)}); preseason race gain {dp.mean():+.4f}; binary-market gain {db.mean():+.5f}")
            # nested leave-one-season-out choice among {live (0), fade values}
            names = (base,) + tuple(vs)
            tot = pd.DataFrame({n: allp[n] for n in names}).loc[yrs]
            gains = []
            picks = []
            for y in yrs:
                best = tot.drop(index=y).mean().idxmin()
                picks.append(best)
                gains.append(tot.loc[y, base] - tot.loc[y, best])
            print(f"  nested choice picks {picks}; held-out gain over live {np.mean(gains):+.4f}, better in {sum(g > 0 for g in gains)}/{len(gains)}")
    print("\nroster layer v team-only (race loss, all checkpoints):", f"main {np.mean([allp['teamonly'][s] - allp['full'][s] for s in allp['full'].index if s != 2021]):+.4f}",
          f"noleak {np.mean([allp['teamonly'][s] - allp['noleak'][s] for s in allp['full'].index if s != 2021]):+.4f}")


if __name__ == "__main__":
    main(sys.argv[1])
