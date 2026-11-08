"""Round 3 of research/TOP10_BACKTEST_EDGES_RULE.md: apply Amendment 3 penalties (leave-season-out) at game level, score, relist the top 10, redo the mirrored tail.
Usage: python research/top10_round3.py <out dir>   (reads edges_fix_round2.csv, seedfixed_stage1_rows.csv)"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import match_vs_market as M
import ratings
S = ratings.S


def ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main():
    out = sys.argv[1]
    D = pd.read_csv(os.path.join(out, "edges_fix_round2.csv")); R = pd.read_csv(os.path.join(out, "seedfixed_stage1_rows.csv"))
    sigma = (S["sim"]["sigma"] ** 2 + 2 * S["sim"]["tau"] ** 2) ** 0.5
    D["fnl"] = np.where(D.lockd == 0, D.fixd, 0)
    def loso(group, y):
        X = R[(R.group == group) & (R.season != y)]; return -float(X.side.mean())
    D["Ps"] = [loso("strict", y) for y in D.season]; D["Pf"] = [loso("fixed_not_locked", y) for y in D.season]
    D["margin3"] = D.margin0 - D.Ps * D.lockd - D.Pf * D.fnl
    D["p3"] = M.phi(D.margin3 / sigma)
    D["l0"] = ll(M.phi(D.margin0 / sigma), D.y.values); D["l3"] = ll(D.p3, D.y.values)
    gain = (D.l0 - D.l3).groupby(D.season).mean(); ev = gain[gain.index >= 2020]
    rng = np.random.default_rng(0); bs = [rng.choice(ev.values, len(ev)).mean() for _ in range(4000)]
    print(f"games moved: strict {int((D.lockd!=0).sum())}, fixed-not-locked {int((D.fnl!=0).sum())}")
    print(f"eval 2020-25 gain per game {ev.mean():+.5f} 90% [{np.percentile(bs,5):+.5f},{np.percentile(bs,95):+.5f}] seasons worse {(ev<0).sum()}/6; disc gain {gain[gain.index<=2019].mean():+.5f}; all-games LL {D.l0.mean():.4f} -> {D.l3.mean():.4f}")
    fw = D[D.week == D.groupby('season').week.transform('max')]
    print("final-week games LL", round(fw.l0.mean(), 4), "->", round(fw.l3.mean(), 4))
    D["gap3"] = D.p3 - D.p_market; D["edge3"] = D.gap3.abs()
    top = D[D.season <= 2019].sort_values("edge3", ascending=False).head(10)
    print(top[["season", "week", "home", "away", "gap3", "fixd", "lockd"]].round(3).to_string(index=False))
    for name, X in (("all", D), ("disc", D[D.season <= 2019]), ("eval", D[D.season >= 2020])):
        k = int(round(len(X) * 0.05))
        A = X.sort_values("edge3", ascending=False).head(k); B = X.assign(g2=-X.gap3).sort_values("g2", ascending=False).head(k)
        d = lambda Z: ll(Z.p3, Z.y.values) - ll(Z.p_market, Z.y.values)
        seas = sorted(X.season.unique()); b = []
        for _ in range(2000):
            pick = rng.choice(seas, len(seas)); a = np.concatenate([d(A[A.season == s]) for s in pick]); c = np.concatenate([d(B[B.season == s]) for s in pick])
            if len(a) and len(c): b.append(a.mean() - c.mean())
        print(name, "mirrored D", round(d(A).mean() - d(B).mean(), 4), np.percentile(b, [5, 95]).round(3), "wk>=17 share top5%", round((A.week >= D.groupby('season').week.transform('max').loc[A.index]).mean(), 3))
    D.to_csv(os.path.join(out, "edges_round3.csv"), index=False)


if __name__ == "__main__":
    main()
