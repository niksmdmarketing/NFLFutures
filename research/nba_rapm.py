"""Regularised adjusted plus-minus (RAPM) player ratings from lineup stints (research/nba_stints.py).

Rating for season Y uses stints from seasons before Y only (Y-1 at weight 1, Y-2 at weight W2, Y-3 at W3): each stint is
one row, y = 100 x (home points - away points) / possessions, home players +1, away players -1, an intercept for home court,
weighted by possessions. Ridge pulls each player toward a prior: K_BOX x his box-score value (game score + plus-minus) from
the same seasons, or 0. Output: points per 100 possessions a player adds vs an average player (on a 5-man basis).
"""
import os

import numpy as np
import pandas as pd
from scipy import sparse

STINTS = os.environ.get("NBA_STINTS", "/home/claude/nbapbp/stints")


def load(y):
    p = os.path.join(STINTS, f"stints_{y}.parquet")
    if not os.path.exists(p):
        return None
    S = pd.read_parquet(p)
    S = S[S.poss > 0.5]
    return S


def fit(y, lam=3000.0, w2=0.5, w3=0.0, prior=None, cache={}):
    """Ratings as of the start of season y. prior: dict athlete_id -> prior rating (default 0)."""
    frames = []
    for k, w in ((1, 1.0), (2, w2), (3, w3)):
        if w <= 0:
            continue
        key = y - k
        if key not in cache:
            cache[key] = load(key)
        S = cache[key]
        if S is not None:
            frames.append(S.assign(w=w))
    if not frames:
        return {}
    S = pd.concat(frames, ignore_index=True)
    hp = S.home5.str.split(",")
    ap = S.away5.str.split(",")
    ids = sorted({int(float(a)) for lst in hp for a in lst} | {int(float(a)) for lst in ap for a in lst})
    ix = {a: i for i, a in enumerate(ids)}
    n, m = len(S), len(ids)
    rows = np.repeat(np.arange(n), 10)
    cols = np.empty(n * 10, dtype=np.int64)
    vals = np.empty(n * 10)
    for j, (h, a) in enumerate(zip(hp, ap)):
        cols[j * 10:j * 10 + 5] = [ix[int(float(x))] for x in h]
        cols[j * 10 + 5:j * 10 + 10] = [ix[int(float(x))] for x in a]
        vals[j * 10:j * 10 + 5] = 1.0
        vals[j * 10 + 5:j * 10 + 10] = -1.0
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(n, m))
    yv = 100 * (S.hpts.to_numpy(float) - S.apts.to_numpy(float)) / S.poss.to_numpy(float)
    wt = S.poss.to_numpy(float) * S.w.to_numpy(float)
    # intercept (home court) solved jointly: append a column of ones without penalty
    Xa = sparse.hstack([X, sparse.csr_matrix(np.ones((n, 1)))]).tocsr()
    XtW = Xa.T.multiply(wt)
    A = (XtW @ Xa).toarray()
    b = XtW @ yv
    pr = np.zeros(m + 1)
    if prior:
        pr[:m] = [prior.get(a, 0.0) for a in ids]
    A[np.arange(m), np.arange(m)] += lam
    b[:m] += lam * pr[:m]
    sol = np.linalg.solve(A, b)
    return dict(zip(ids, sol[:m]))
