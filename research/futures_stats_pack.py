"""Stats pack for DeepSeek (relay 013 ask): per sport, stage, market: seasons, rows, positives, mean p, slope/intercept with season-cluster 90% CI,
implied probabilities at p=.02/.05/.10/.30/.50, and realised frequency by probability bucket. Usage: python research/futures_stats_pack.py > pack.md"""
import sys, glob, os, numpy as np, pandas as pd
sys.path.insert(0, "research")
import replay_score as S, replay_slope as L
def load(sp):
    D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"model/replay/{sp}_[0-9]*.csv"))], ignore_index=True)
    D["frac"] = D.groupby("season").week.transform(lambda w: w / max(w.max(), 1)); return D
rng = np.random.default_rng(1)
def fit_ci(x, pc, yc, B=300):
    z = x.dropna(subset=[pc, yc]); a, b, _ = L.fit(z[pc], z[yc]); seas = sorted(z.season.unique()); bs = []
    for _ in range(B):
        pick = rng.choice(seas, len(seas)); Z = pd.concat([z[z.season == s] for s in pick])
        try: bs.append(L.fit(Z[pc], Z[yc])[:2])
        except Exception: pass
    bs = np.array(bs); return a, b, np.percentile(bs[:, 1], [5, 95]), np.percentile(bs[:, 0], [5, 95]), z
print("# Futures stats pack (replay CSVs in model/replay; slope > 1 = too flat, < 1 = too extreme; 150-300 season-cluster bootstrap draws, seed 1)\n")
MK = ["title", "finals", "div", "seed1", "playoff", "top8", "pf", "semi", "pres", "r2", "r3"]
for sp in ("nba", "nhl", "afl", "nbl", "nfl"):
    D = load(sp); print(f"## {sp}: seasons {int(D.season.min())}-{int(D.season.max())} ({D.season.nunique()}), checkpoints per season about {int(D.groupby('season').week.nunique().mean())}")
    for lo, hi, name in S.STAGES:
        if name not in ("preseason", "first quarter", "third quarter", "last quarter"): continue
        x = D[D.week == 0] if name == "preseason" else D[(D.frac >= lo) & (D.frac < hi)]
        for m in MK:
            pc, yc = S.MARKETS[m]
            if pc not in x or yc not in x or x[yc].isna().all(): continue
            try: a, b, bci, aci, z = fit_ci(x, pc, yc)
            except Exception as e: continue
            pos = z.groupby("season")[yc].sum().sum() if name == "preseason" else z[yc].sum() / max(z.groupby("season").week.nunique().mean(), 1)
            imp = {p: 1 / (1 + np.exp(-(a + b * np.log(p / (1 - p))))) for p in (.02, .05, .10, .30, .50)}
            print(f"- {sp} | {name} | {m}: rows {len(z)}, seasons {z.season.nunique()}, outcomes(approx independent) {int(round(pos))}, mean p {z[pc].mean():.3f}, slope {b:.2f} [{bci[0]:.2f},{bci[1]:.2f}], intercept {a:+.2f} [{aci[0]:+.2f},{aci[1]:+.2f}], implied at .02/.05/.10/.30/.50 = " + "/".join(f"{imp[p]:.3f}" for p in imp))
    # title buckets, preseason + last quarter pooled across checkpoints
    pc, yc = S.MARKETS["title"]
    if pc in D:
        z = D[D.week == 0].dropna(subset=[pc, yc]); bins = [0, .01, .03, .06, .12, .25, 1.0]; z = z.assign(b=pd.cut(z[pc], bins))
        g = z.groupby("b", observed=True).agg(n=(pc, "size"), mean_p=(pc, "mean"), freq=(yc, "mean"), wins=(yc, "sum"))
        print(f"  preseason title buckets (n, mean p, realised freq, wins): " + "; ".join(f"{i}: {int(r.n)}, {r.mean_p:.3f}, {r.freq:.3f}, {int(r.wins)}" for i, r in g.iterrows()))
    print()
