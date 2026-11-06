"""Scores research/NBA_FUTURES_RECENCY_RULE.md. Gates exactly as written there; nothing is tuned here.

Usage: python research/nba_futures_recency_score.py <scratch_dir> [out.json]
  <scratch_dir> holds baseA, baseB, h90A, h90B (primary) and optionally h45A, h180A (sensitivity, reported only),
  each a folder of replay CSVs nba_<season>.csv.
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

MARKETS = {"title": ("p_title", "y_title"), "finals": ("p_conf", "y_finals"), "div": ("p_div", "y_div"),
           "seed1": ("p_seed1", "y_seed1"), "playoff": ("p_playoff", "y_playoff")}
QUARTERS = {"q1": (0.001, 0.25), "q2": (0.25, 0.5), "q3": (0.5, 0.75), "q4": (0.75, 1.01)}
DRAWS, SEED, LO = 10000, 20261106, 0.002


def load(d):
    D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(d, "nba_[0-9]*.csv")))], ignore_index=True)
    return D


def loss(D, m, mask=None):
    pc, yc = MARKETS[m]
    x = D if mask is None else D[mask]
    p = x[pc].clip(LO, 1 - LO)
    l = -(x[yc] * np.log(p) + (1 - x[yc]) * np.log(1 - p))
    return l.groupby(x.season).mean()


def slope(D, m):
    pc, yc = MARKETS[m]
    p = D[pc].clip(LO, 1 - LO).to_numpy()
    y = D[yc].to_numpy(float)
    z = np.log(p / (1 - p))
    X = np.column_stack([np.ones_like(z), z])
    b = np.array([0.0, 1.0])
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu) + 1e-9
        step = np.linalg.solve(X.T @ (X * W[:, None]) + 1e-9 * np.eye(2), X.T @ (y - mu))
        b = b + step
        if np.abs(step).max() < 1e-8:
            break
    return float(b[1])


def gains(base, var):
    """Per-season primary gain, per market gain, per quarter gain (baseline loss - variant loss)."""
    out = {"markets": {}, "quarters": {}}
    per = []
    for m in MARKETS:
        g = loss(base, m) - loss(var, m)
        out["markets"][m] = g
        per.append(g)
    out["primary"] = sum(per) / len(per)
    for q, (a, b) in QUARTERS.items():
        fb, fv = (base.gp_avg / 82), (var.gp_avg / 82)
        gs = [loss(base, m, (fb >= a) & (fb < b)) - loss(var, m, (fv >= a) & (fv < b)) for m in MARKETS]
        out["quarters"][q] = sum(gs) / len(gs)
    return out


def boot_lb(g, rng):
    v = g.dropna().to_numpy()
    idx = rng.integers(0, len(v), size=(DRAWS, len(v)))
    means = v[idx].mean(axis=1)
    return float(np.quantile(means, 0.10)), float(v.mean())


def gates(G, rng):
    lb, mean = boot_lb(G["primary"], rng)
    seasons_better = int((G["primary"] > 0).sum())
    n = int(G["primary"].notna().sum())
    mk = {m: float(g.mean()) for m, g in G["markets"].items()}
    qs = {q: float(v.mean()) for q, v in G["quarters"].items()}
    g1 = bool(lb > 0 and seasons_better >= 8)
    g2 = all(v > 0 for v in mk.values())
    g3 = all(v > -0.002 for v in mk.values())
    g4 = bool(qs["q1"] > 0 and qs["q2"] > 0)
    return dict(primary_gain=mean, lower90=lb, seasons_better=seasons_better, n_seasons=n, market_gain=mk, quarter_gain=qs,
                gate1=g1, gate2=bool(g2), gate3=bool(g3), gate4=g4)


def main(d, out_path=None):
    rng = np.random.default_rng(SEED)
    A = gains(load(os.path.join(d, "baseA")), load(os.path.join(d, "h90A")))
    B = gains(load(os.path.join(d, "baseB")), load(os.path.join(d, "h90B")))
    Gavg = {"primary": (A["primary"] + B["primary"]) / 2,
            "markets": {m: (A["markets"][m] + B["markets"][m]) / 2 for m in MARKETS},
            "quarters": {q: (A["quarters"][q] + B["quarters"][q]) / 2 for q in QUARTERS}}
    res = {"set_A": gates(A, np.random.default_rng(SEED)), "set_B": gates(B, np.random.default_rng(SEED)), "average": gates(Gavg, np.random.default_rng(SEED))}
    keys = ("gate1", "gate2", "gate3", "gate4")
    res["A_B_agree"] = all(res["set_A"][k] == res["set_B"][k] for k in keys)
    avg_pass = all(res["average"][k] for k in keys)
    res["verdict"] = "inconclusive" if not res["A_B_agree"] else ("pass" if avg_pass else "fail")
    base = load(os.path.join(d, "baseA"))
    var = load(os.path.join(d, "h90A"))
    res["slope_baseline_vs_h90_seedA"] = {m: [round(slope(base, m), 3), round(slope(var, m), 3)] for m in MARKETS}
    for tag in ("h45A", "h180A"):
        p = os.path.join(d, tag)
        if os.path.isdir(p):
            G = gains(load(os.path.join(d, "baseA")), load(p))
            res[f"sensitivity_{tag}"] = {"primary_gain": float(G["primary"].mean()), "seasons_better": int((G["primary"] > 0).sum()),
                                         "market_gain": {m: float(g.mean()) for m, g in G["markets"].items()},
                                         "quarter_gain": {q: float(v.mean()) for q, v in G["quarters"].items()}}
    print(json.dumps(res, indent=1, default=float))
    if out_path:
        json.dump(res, open(out_path, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
