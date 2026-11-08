"""M2 evaluation (research/FUTURES_BAKEOFF_RULE.md Amendment 1). Usage: python m2_eval.py <live_dir> <arm_dir> [first last] [drop_year]
Paired season-cluster Bayesian (exponential-weight) bootstrap, 10,000 draws, seed 20261108, clip 0.001/0.999, L2 lambda LAM on (a, b-1)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "research")
import replay_score as S
LIVE, ARM = sys.argv[1], sys.argv[2]
FIRST, LAST = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (2019, 2026)
DROP = int(sys.argv[5]) if len(sys.argv) > 5 else 2020
LAM = 1.0; B = 10000
def load(d):
    D = pd.concat([pd.read_csv(f"{d}/afl_{y}.csv") for y in range(FIRST, LAST + 1) if y != DROP], ignore_index=True)
    D["frac"] = D.groupby("season").week.transform(lambda w: w / max(w.max(), 1)); return D
def stage(D, name):
    lo, hi = [(a, b) for a, b, n in S.STAGES if n == name][0]
    return D[D.week == 0] if name == "preseason" else D[(D.frac >= lo) & (D.frac < hi)]
def wfit(z, y, w):
    th = np.array([0.0, 1.0])
    for _ in range(25):
        eta = th[0] + th[1] * z; q = 1 / (1 + np.exp(-eta)); g = np.array([(w * (y - q)).sum(), (w * (y - q) * z).sum()]) - LAM * (th - [0, 1])
        h = np.array([[(w * q * (1 - q)).sum(), (w * q * (1 - q) * z).sum()], [(w * q * (1 - q) * z).sum(), (w * q * (1 - q) * z * z).sum()]]) + LAM * np.eye(2)
        st = np.linalg.solve(h, g); th = th + np.clip(st, -3, 3)
        if np.abs(st).max() < 1e-8: break
    return th
def prep(x, pc, yc):
    p = x[pc].clip(0.001, 0.999).values; return np.log(p / (1 - p)), x[yc].values.astype(float), p
rng = np.random.default_rng(20261108)
L, A = load(LIVE), load(ARM); seas = sorted(L.season.unique()); W = rng.exponential(1.0, (B, len(seas))); W /= W.mean(1, keepdims=True)
print(f"live {LIVE}\narm {ARM}\neval seasons {seas}, draws {B}, lambda {LAM}, clip 0.001/0.999")
for mk, (pc, yc) in {"playoff": ("p_playoff", "y_playoff"), "top4": ("p_div", "y_div"), "finals": ("p_conf", "y_finals")}.items():
    for st in ("preseason", "first quarter", "third quarter", "last quarter") if mk == "playoff" else ("third quarter",):
        xl, xa = stage(L, st), stage(A, st); zl, yl, pl = prep(xl, pc, yc); za, ya, pa = prep(xa, pc, yc)
        sl, sa = xl.season.values, xa.season.values
        bl, ba = wfit(zl, yl, np.ones(len(zl)))[1], wfit(za, ya, np.ones(len(za)))[1]
        idl = np.searchsorted(seas, sl); ida = np.searchsorted(seas, sa); c = []; bad = 0
        for i in range(B):
            l_, a_ = wfit(zl, yl, W[i][idl])[1], wfit(za, ya, W[i][ida])[1]
            bad += (abs(l_) > 5) or (abs(a_) > 5); c.append(a_ - l_)
        c = np.array(c); pc10, pc50, pc90 = np.percentile(c, [10, 50, 90])
        ll = lambda p, y: -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
        print(f"{mk:8s} {st:14s} n {len(zl):4d} live slope {bl:.2f} arm slope {ba:.2f} contrast {ba - bl:+.3f} [10% {pc10:+.3f}, 50% {pc50:+.3f}, 90% {pc90:+.3f}] half-width {(pc90 - pc10) / 2:.3f} |slope|>5 {bad / B:.1%}  LL live {ll(pl, yl):.4f} arm {ll(pa, ya):.4f} diff {ll(pa, ya) - ll(pl, yl):+.4f}")
