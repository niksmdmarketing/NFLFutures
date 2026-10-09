"""Generic award-chance model used by the NBA, NBL and AFL sections.

Conditional logit over each season's candidate pool (one winner per season), ridge-penalised, features
standardised within season. Validated leave-one-season-out: top-1 / top-3 hit rate and the average
probability given to the eventual winner, compared with simply picking the leader in the main stat.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

LAM = 0.5


def _z(P, feats):
    X = P[feats].astype(float).copy()
    for c in feats:
        g = X.groupby(P.season)[c]
        X[c] = ((X[c] - g.transform("mean")) / g.transform("std").replace(0, np.nan)).fillna(0.0)
    return X.values


def fit(P, feats, lam=LAM):
    """P: rows with season, win (1 for the winner, 0 otherwise). Seasons without exactly one winner are dropped."""
    s = P.groupby("season").win.transform("sum")
    D = P[s == 1]
    if D.empty:
        return np.zeros(len(feats))
    X = _z(D, feats)
    y = D.win.values
    gidx = pd.factorize(D.season)[0]
    ng = gidx.max() + 1

    def nll(b):
        eta = X @ b
        lse = np.full(ng, -np.inf)
        np.logaddexp.at(lse, gidx, eta)
        return -(eta[y == 1].sum() - lse.sum()) + lam * (b ** 2).sum()

    return minimize(nll, np.zeros(len(feats)), method="BFGS").x


def predict(P, feats, beta):
    """Probabilities within each season of P."""
    if P.empty:
        return np.array([])
    eta = _z(P, feats) @ beta
    out = np.zeros(len(P))
    for s in P.season.unique():
        m = (P.season == s).values
        e = np.exp(eta[m] - eta[m].max())
        out[m] = e / e.sum()
    return out


def loso(P, feats, leader_col=None):
    """Leave-one-season-out backtest."""
    s = P.groupby("season").win.transform("sum")
    D = P[s == 1]
    seasons = sorted(D.season.unique())
    top1 = top3 = lead = 0
    probs = []
    for y in seasons:
        b = fit(D[D.season != y], feats)
        T = D[D.season == y].copy()
        T["p"] = predict(T, feats, b)
        T = T.sort_values("p", ascending=False).reset_index(drop=True)
        w = T.index[T.win == 1][0]
        top1 += w == 0
        top3 += w < 3
        probs.append(float(T.p[w]))
        if leader_col:
            lead += int(T.loc[T[leader_col].idxmax(), "win"] == 1)
    if not seasons:
        return None
    return {"n": len(seasons), "top1": int(top1), "top3": int(top3), "avg_p": float(np.mean(probs)),
            "leader_hits": int(lead) if leader_col else None}
