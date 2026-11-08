"""Numbers DeepSeek asked for (relay 014): within-live contrasts with season-cluster weighted bootstrap (10,000 draws, seed 20261108, exponential
cluster weights = Bayesian bootstrap; Rademacher weights are invalid for a likelihood), per-season slopes, sd of logit p, decile tables, dropped p=0/1 rows."""
import sys, glob, numpy as np, pandas as pd
sys.path.insert(0, "research")
import replay_score as S
def load(sp):
    D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"model/replay/{sp}_[0-9]*.csv"))], ignore_index=True)
    D["frac"] = D.groupby("season").week.transform(lambda w: w / max(w.max(), 1)); return D
def stage(D, name):
    lo, hi = {"preseason": (None, None), "first quarter": (0.001, .25), "third quarter": (.5, .75), "last quarter": (.75, 1.01)}[name]
    return D[D.week == 0] if name == "preseason" else D[(D.frac >= lo) & (D.frac < hi)]
def logit(p): p = np.clip(p, 1e-6, 1 - 1e-6); return np.log(p / (1 - p))
def wfit(x, y, w, it=25):
    X = np.column_stack([np.ones_like(x), x]); b = np.array([0.0, 1.0])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); g = X.T @ (w * (y - p)); H = (X * (w * p * (1 - p))[:, None]).T @ X + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g); b = b + step
        if np.abs(step).max() < 1e-8: break
    return b
def get(sp, st, m):
    D = load(sp); x = stage(D, st); pc, yc = S.MARKETS[m]; z = x.dropna(subset=[pc, yc]); n0 = len(z)
    zz = z[(z[pc] > 0) & (z[pc] < 1)]
    return zz, n0 - len(zz), n0
rng = np.random.default_rng(20261108)
def slope_boot(z, seas, W):
    xs = logit(z.p.values); ys = z.y.values; idx = z.season.map({s: i for i, s in enumerate(seas)}).values
    return np.array([wfit(xs, ys, W[d][idx])[1] for d in range(len(W))])
def contrast(spA, stA, mA, spB, stB, mB, tag, B=10000):
    out = []
    for sp, st, m in ((spA, stA, mA), (spB, stB, mB)):
        z, dropped, n0 = get(sp, st, m); pc, yc = S.MARKETS[m]; out.append((z.rename(columns={pc: "p", yc: "y"}), dropped, n0, sp, st, m))
    seas = sorted(set(out[0][0].season) | set(out[1][0].season)); W = rng.exponential(1.0, (B, len(seas)))
    bs = [slope_boot(o[0], seas, W) for o in out]; d = bs[0] - bs[1]
    for o, b in zip(out, bs):
        z = o[0]; a, s = wfit(logit(z.p.values), z.y.values, np.ones(len(z)))
        per = {int(se): round(float(wfit(logit(g.p.values), g.y.values, np.ones(len(g)))[1]), 2) for se, g in z.groupby("season") if g.y.sum() > 0 and g.y.sum() < len(g)}
        print(f"- {o[3]} | {o[4]} | {o[5]}: slope {s:.2f} [{np.percentile(b,5):.2f},{np.percentile(b,95):.2f}] int {a:+.2f}; sd logit p {logit(z.p.values).std():.2f}; dropped at p=0/1: {o[1]} of {o[2]}; per-season slopes {per}")
    print(f"  CONTRAST {tag}: {np.mean(d):+.2f} (point {wfit(logit(out[0][0].p.values), out[0][0].y.values, np.ones(len(out[0][0])))[1]-wfit(logit(out[1][0].p.values), out[1][0].y.values, np.ones(len(out[1][0])))[1]:+.2f}) 90% [{np.percentile(d,5):+.2f},{np.percentile(d,95):+.2f}], share of draws with contrast>0 {np.mean(d>0):.2f}")
def deciles(sp, st, m):
    z, dropped, n0 = get(sp, st, m); pc, yc = S.MARKETS[m]; z = z.assign(b=pd.qcut(z[pc], 10, duplicates="drop"))
    g = z.groupby("b", observed=True).agg(n=(pc, "size"), p=(pc, "mean"), f=(yc, "mean"))
    print(f"- {sp} | {st} | {m} deciles (n, mean p, realised): " + "; ".join(f"{int(r.n)}, {r.p:.3f}, {r.f:.3f}" for _, r in g.iterrows()))
print("# Numbers for DeepSeek (relay 014 ask 1-4)\n")
contrast("nhl", "preseason", "r3", "nhl", "preseason", "r2", "NHL preseason r3 - r2")
contrast("afl", "third quarter", "playoff", "afl", "first quarter", "playoff", "AFL Q3 playoff - Q1 playoff")
contrast("nba", "third quarter", "playoff", "nba", "preseason", "playoff", "NBA Q3 playoff - preseason playoff")
print()
for a in (("nba", "preseason", "playoff"), ("afl", "third quarter", "playoff"), ("nhl", "preseason", "r2"), ("nhl", "preseason", "r3")): deciles(*a)
print("\nRows dropped at p = 0 or 1, preseason title: ", end="")
for sp in ("nba", "nhl", "afl", "nbl", "nfl"):
    z, d, n0 = get(sp, "preseason", "title"); print(f"{sp} {d} of {n0}; ", end="")
print()
