"""Walk-forward check of a replay setting. Usage: python research/replay_walkforward.py <dir containing one sub-folder of replay CSVs per setting> <default setting name>
Per season: mean log loss over all scored markets and checkpoints for each setting. Then for each season from the third on, pick the setting that was best on the
earlier seasons (pooled) and score it on that season, next to the default. Also paired (setting - default) with a season bootstrap interval."""
import glob, os, sys
import numpy as np, pandas as pd
import replay_score as S
root, default = sys.argv[1], sys.argv[2]
names = sorted((os.path.basename(d) for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d)), key=lambda s: float("".join(c for c in s if c.isdigit() or c == ".") or 0))
rows = []
for nm in names:
    for f in glob.glob(os.path.join(root, nm, "*.csv")):
        D = pd.read_csv(f)
        v = []
        for m, (pc, yc) in S.MARKETS.items():
            if pc in D and yc in D and not D[yc].isna().all():
                v.append(S.ll(D[pc], D[yc]))
        rows.append({"setting": nm, "season": int(D.season.iloc[0]), "ll": np.mean(v)})
P = pd.DataFrame(rows).pivot_table(index="season", columns="setting", values="ll")
print("mean log loss by setting:\n", P.mean().round(5).to_string())
rng = np.random.default_rng(1)
for nm in names:
    if nm == default: continue
    d = (P[nm] - P[default]).dropna()
    bs = [d.sample(frac=1, replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(2000)]
    print(f"{nm} minus {default}: {d.mean():+.5f} [{np.percentile(bs,5):+.5f}, {np.percentile(bs,95):+.5f}] better in {(d<0).mean():.0%} of {len(d)} seasons")
w, dflt = [], []
for i, s in enumerate(P.index[2:], start=2):
    best = P.iloc[:i].mean().idxmin()
    w.append(P.loc[s, best]); dflt.append(P.loc[s, default])
    print(s, "chosen", best, f"walk {P.loc[s,best]:.5f} default {P.loc[s,default]:.5f}")
print("walk-forward mean", round(float(np.mean(w)), 5), "default mean", round(float(np.mean(dflt)), 5))
