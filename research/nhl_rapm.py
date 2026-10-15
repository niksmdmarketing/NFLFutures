"""NHL player ratings from stints (research): regularised adjusted plus-minus on expected goals, plus goalie ratings.

Ratings as of the start of season y use seasons y-1 (weight 1), y-2 (W2), y-3 (W3) only.
Skaters: every stint (both goalies in net) gives two rows, one per attacking team: target = attacking team's xG per 60,
weight = seconds; columns = attacking skaters (offence) and defending skaters (defence), plus unpenalised terms for the
intercept, home attack and the strength state (5v4, 4v5, 4v4, ...). Ridge pulls each player toward PRIOR_RHO x his
previous rating (0 for newcomers). off_i = xG/60 he adds for his team, def_i = xG/60 he allows (lower is better).
Goalies: goals saved above expected per unblocked shot faced, shrunk by K_G shots.
Team strength (goals per game) for a lineup = sum over skaters of (off - def) x hours per game + goalie GSAx/shot x
unblocked shots against per game.
"""
import os

import numpy as np
import pandas as pd
from scipy import sparse

DATA = os.environ.get("NHL_SHIFTS", "/home/claude/shiftbr")
LAM = float(os.environ.get("RAPM_LAM", "2000"))
W2, W3 = 0.5, 0.25
K_G = float(os.environ.get("RAPM_KG", "2500"))
SHOTS_AGAINST = 40.0     # unblocked shots against per game (league typical)
_C = {}


def load(y):
    if y in _C:
        return _C[y]
    p = os.path.join(DATA, f"stints_{y}.csv.gz")
    q = os.path.join(DATA, f"shots_xg_{y}.csv.gz")
    if not (os.path.exists(p) and os.path.exists(q)):
        _C[y] = None
        return None
    S = pd.read_csv(p)
    H = pd.read_csv(q)
    H = H[~H.empty_net & H.stint.notna()]
    S["sidx"] = S.groupby("game_id").cumcount()
    agg = H.groupby(["game_id", "stint", "home"]).agg(xg=("xg", "sum"), g=("goal", "sum")).reset_index()
    agg["stint"] = agg.stint.astype(int)
    for side, hv in (("h", 1), ("a", 0)):
        a = agg[agg.home == hv].rename(columns={"stint": "sidx", "xg": f"xg_{side}", "g": f"g_{side}"}).drop(columns="home")
        S = S.merge(a, on=["game_id", "sidx"], how="left")
    for c in ("xg_h", "xg_a", "g_h", "g_a"):
        S[c] = S[c].fillna(0.0)
    S = S[(S.dur > 0) & (S.home_g > 0) & (S.away_g > 0)]
    S["season"] = y
    _C[y] = (S, H)
    return _C[y]


def _ids(s):
    return [int(x) for x in str(s).split(";") if x and x != "nan"]


def skater_ratings(y, prior=None, lam=LAM, target="xg"):
    frames = []
    for k, w in ((1, 1.0), (2, W2), (3, W3)):
        d = load(y - k)
        if d is not None and w > 0:
            frames.append(d[0].assign(w=w))
    if not frames:
        return None
    S = pd.concat(frames, ignore_index=True)
    hs = [_ids(x) for x in S.home_sk]
    as_ = [_ids(x) for x in S.away_sk]
    ids = sorted({p for l in hs for p in l} | {p for l in as_ for p in l})
    ix = {p: i for i, p in enumerate(ids)}
    m = len(ids)
    n = len(S)
    rows, cols, vals = [], [], []
    states = {}
    fixed = []
    yv = np.empty(2 * n)
    wt = np.empty(2 * n)
    dur = S.dur.to_numpy(float)
    w = S.w.to_numpy(float)
    tg_h = (S.xg_h if target == "xg" else S.g_h).to_numpy(float)
    tg_a = (S.xg_a if target == "xg" else S.g_a).to_numpy(float)
    for j in range(n):
        for r, (off, de, tg, home) in enumerate(((hs[j], as_[j], tg_h[j], 1), (as_[j], hs[j], tg_a[j], 0))):
            row = 2 * j + r
            for p in off:
                rows.append(row); cols.append(ix[p]); vals.append(1.0)
            for p in de:
                rows.append(row); cols.append(m + ix[p]); vals.append(1.0)
            st = (min(len(off), 6), min(len(de), 6))
            if st not in states:
                states[st] = len(states)
            fixed.append((row, home, states[st]))
            yv[row] = tg / dur[j] * 3600
            wt[row] = dur[j] * w[j]
    ns = len(states)
    base = 2 * m
    for row, home, st in fixed:
        rows.append(row); cols.append(base); vals.append(float(home))
        rows.append(row); cols.append(base + 1 + st); vals.append(1.0)
    P = base + 1 + ns
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(2 * n, P))
    XtW = X.T.multiply(wt).tocsr()
    A = (XtW @ X).toarray()
    b = XtW @ yv
    pr = np.zeros(P)
    if prior is not None:
        for p, i in ix.items():
            if p in prior.index:
                pr[i] = prior.loc[p, "off"]
                pr[m + i] = prior.loc[p, "def"]
    lam_v = np.zeros(P)
    lam_v[:base] = lam
    A[np.arange(P), np.arange(P)] += lam_v
    b = b + lam_v * pr
    sol = np.linalg.solve(A, b)
    # off/def relative to the average skater: centre each by its time-weighted mean
    secs = np.zeros(m)
    for j in range(n):
        for p in hs[j] + as_[j]:
            secs[ix[p]] += dur[j] * w[j]
    off = sol[:m] - np.average(sol[:m], weights=secs.clip(1))
    de = sol[m:base] - np.average(sol[m:base], weights=secs.clip(1))
    return pd.DataFrame({"off": off, "def": de, "secs": secs}, index=pd.Index(ids, name="player_id"))


def goalie_ratings(y, k=K_G):
    parts = []
    for kk, w in ((1, 1.0), (2, W2), (3, W3)):
        d = load(y - kk)
        if d is not None and w > 0:
            H = d[1]
            H = H[H.goalie.notna()]
            g = H.groupby("goalie").agg(n=("xg", "size"), sx=("xg", "sum"), sg=("goal", "sum"))
            parts.append(g * w)
    if not parts:
        return None
    G = pd.concat(parts).groupby(level=0).sum()
    G["gsax_shot"] = (G.sx - G.sg) / (G.n + k)
    G.index = G.index.astype(int)
    G.index.name = "player_id"
    return G


def box_prior(y):
    """player_id -> points per 60 vs position average (two previous seasons, shrunk), from pipeline/nhl_absence.values."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
    import nhl_absence as A
    val = A.values(y)
    rows = []
    for k in (1, 2):
        p = os.path.join(DATA, f"players_{y - k}.csv.gz")
        if os.path.exists(p):
            rows.append(pd.read_csv(p))
    if not rows:
        return pd.Series(dtype=float)
    P = pd.concat(rows).drop_duplicates("player_id")
    P = P[P.pos != "G"]
    key = P.name.str.strip().str.lower() + "|" + np.where(P.pos == "D", "D", "F")
    return pd.Series(key.map(val).fillna(0.0).to_numpy(), index=P.player_id.astype(int).to_numpy())


def ratings(y):
    """Point-in-time ratings at the start of season y, with last season's ratings (from y-1) as the ridge prior."""
    key = ("r", y)
    if key in _C:
        return _C[key]
    prior = None
    rho = float(os.environ.get("RAPM_RHO", "0"))
    if rho > 0 and load(y - 2) is not None:
        pr = ratings(y - 1)[0]
        prior = pr[["off", "def"]] * rho if pr is not None else None
    kbox = float(os.environ.get("RAPM_KBOX", "0"))
    if kbox > 0:
        bp = box_prior(y) * kbox
        if prior is None:
            prior = pd.DataFrame({"off": bp, "def": 0.0})
        else:
            prior = prior.reindex(prior.index.union(bp.index)).fillna(0.0)
            prior["off"] = prior["off"].add(bp.reindex(prior.index).fillna(0.0) * (1 - rho if rho < 1 else 0.0), fill_value=0.0)
    sk = skater_ratings(y, prior)
    gk = goalie_ratings(y)
    _C[key] = (sk, gk)
    return sk, gk


def lineup_strength(sk, gk, skaters, hours, goalie_shares, shots_against=SHOTS_AGAINST):
    """Goals per game vs average: skaters = list of player ids, hours = matching hours per game, goalie_shares = {id: share}."""
    v = 0.0
    if sk is not None:
        for p, h in zip(skaters, hours):
            if p in sk.index:
                v += (sk.at[p, "off"] - sk.at[p, "def"]) * h
    if gk is not None:
        for p, s in goalie_shares.items():
            if p in gk.index:
                v += s * gk.at[p, "gsax_shot"] * shots_against
    return v
