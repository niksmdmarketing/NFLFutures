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
CUT_GAMES = {}          # (season, cutoff) -> game ids played before the cutoff (set by the caller)


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
    S = S.drop(columns=[c for c in ("home", "away", "start", "end", "period") if c in S])
    H = H[["game_id", "stint", "home", "shooter", "goalie", "goal", "xg"]]
    loaded = [k for k in _C if isinstance(k, int) and _C[k] is not None]
    for k in sorted(loaded, key=lambda k: abs(k - y), reverse=True)[:max(0, len(loaded) - 4)]:
        del _C[k]
    _C[y] = (S, H)
    return _C[y]


def _ids(s):
    return [int(x) for x in str(s).split(";") if x and x != "nan"]


def skater_ratings(y, prior=None, lam=LAM, target="xg", cutoff=None, wcur=1.0):
    frames = []
    for k, w in ((1, 1.0), (2, W2), (3, W3)):
        d = load(y - k)
        if d is not None and w > 0:
            frames.append(d[0].assign(w=w))
    if cutoff is not None:
        d = load(y)
        if d is not None:
            ids = d[0].game_id
            cur = d[0][ids.isin(CUT_GAMES.get((y, str(cutoff)), set()))]
            if len(cur):
                frames.append(cur.assign(w=wcur))
    if not frames:
        return None
    S = pd.concat(frames, ignore_index=True)
    n = len(S)

    def explode(col):
        e = S[col].fillna("").astype(str).str.split(";").explode().dropna()
        e = e[(e != "") & (e != "nan")]
        return e.index.to_numpy(), e.astype(float).astype(np.int64).to_numpy()

    hj, hp = explode("home_sk")
    aj, ap = explode("away_sk")
    ids, inv = np.unique(np.concatenate([hp, ap]), return_inverse=True)
    hi, ai = inv[:len(hp)], inv[len(hp):]
    m = len(ids)
    nh = np.bincount(hj, minlength=n).clip(max=6)
    na = np.bincount(aj, minlength=n).clip(max=6)
    # rows 2j (home attacking) and 2j+1 (away attacking)
    r_off = np.concatenate([2 * hj, 2 * aj + 1])
    c_off = np.concatenate([hi, ai])
    r_def = np.concatenate([2 * aj, 2 * hj + 1])
    c_def = m + np.concatenate([ai, hi])
    off_n = np.empty(2 * n, int); def_n = np.empty(2 * n, int)
    off_n[0::2], off_n[1::2] = nh, na
    def_n[0::2], def_n[1::2] = na, nh
    st_code = off_n * 7 + def_n
    st_vals, st_id = np.unique(st_code, return_inverse=True)
    base = 2 * m
    allrows = np.arange(2 * n)
    home_flag = np.zeros(2 * n); home_flag[0::2] = 1.0
    rows = np.concatenate([r_off, r_def, allrows, allrows])
    cols = np.concatenate([c_off, c_def, np.full(2 * n, base), base + 1 + st_id])
    vals = np.concatenate([np.ones(len(r_off) + len(r_def)), home_flag, np.ones(2 * n)])
    P = base + 1 + len(st_vals)
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(2 * n, P))
    dur = S.dur.to_numpy(float)
    w = S.w.to_numpy(float)
    tg_h = (S.xg_h if target == "xg" else S.g_h).to_numpy(float)
    tg_a = (S.xg_a if target == "xg" else S.g_a).to_numpy(float)
    yv = np.empty(2 * n); yv[0::2] = tg_h / dur * 3600; yv[1::2] = tg_a / dur * 3600
    wt = np.repeat(dur * w, 2)
    XtW = X.T.multiply(wt).tocsr()
    A = (XtW @ X).toarray()
    b = XtW @ yv
    pr = np.zeros(P)
    if prior is not None:
        pi = pd.Index(ids)
        pp = prior.reindex(pi)
        pr[:m] = pp["off"].fillna(0.0).to_numpy()
        pr[m:base] = pp["def"].fillna(0.0).to_numpy()
    lam_v = np.zeros(P)
    lam_v[:base] = lam
    A[np.arange(P), np.arange(P)] += lam_v
    b = b + lam_v * pr
    sol = np.linalg.solve(A, b)
    sw = dur * w
    secs = np.bincount(hi, weights=sw[hj], minlength=m) + np.bincount(ai, weights=sw[aj], minlength=m)
    off = sol[:m] - np.average(sol[:m], weights=secs.clip(1))
    de = sol[m:base] - np.average(sol[m:base], weights=secs.clip(1))
    ids = ids.tolist()
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


def build_prior(y):
    rho = float(os.environ.get("RAPM_RHO", "0"))
    prior = None
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
    return prior


def ratings_at(y, cutoff, game_ids, wcur=1.0):
    """Ratings during season y: earlier seasons plus this season's games before `cutoff` (weight wcur)."""
    CUT_GAMES[(y, str(cutoff))] = set(game_ids)
    sk = skater_ratings(y, build_prior(y), cutoff=cutoff, wcur=wcur)
    return adjust(y, sk.copy()) if sk is not None else None


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
    cache = os.environ.get("RAPM_CACHE", "/tmp/claude-0/-home-claude/05818a0d-0d82-5af8-8a3a-91e344d8290f/scratchpad/rapm_cache")
    tag = f"{y}_{LAM:g}_{kbox:g}_{rho:g}"
    cp = os.path.join(cache, f"sk_{tag}.csv")
    if os.path.exists(cp):
        sk = pd.read_csv(cp, index_col=0)
    else:
        sk = skater_ratings(y, prior)
        if sk is not None:
            os.makedirs(cache, exist_ok=True)
            sk.to_csv(cp)
    gk = goalie_ratings(y)
    if sk is not None:
        sk = adjust(y, sk.copy())
    _C[key] = (sk, gk)
    return sk, gk


FIN = float(os.environ.get("RAPM_FIN", "0"))      # weight on shooting talent (goals - xG per shot, shrunk)
K_F = float(os.environ.get("RAPM_KF", "300"))     # shots at which a shooter's finishing counts half


def finishing(y):
    """player_id -> (goals - xG) per shot, shrunk, and shots per 60 (seasons y-1.. weighted like the ratings)."""
    parts = []
    for kk, w in ((1, 1.0), (2, W2), (3, W3)):
        d = load(y - kk)
        if d is not None and w > 0:
            H = d[1][d[1].shooter.notna()]
            g = H.groupby("shooter").agg(n=("xg", "size"), sx=("xg", "sum"), sg=("goal", "sum"))
            parts.append(g * w)
    if not parts:
        return None
    F = pd.concat(parts).groupby(level=0).sum()
    F.index = F.index.astype(int)
    F["fin"] = (F.sg - F.sx) / (F.n + K_F)
    return F


def adjust(y, sk):
    """Post-fit refinements on the skater ratings: shooting talent (RAPM_FIN) and age (RAPM_AGE)."""
    if FIN > 0:
        F = finishing(y)
        if F is not None:
            f = F.reindex(sk.index)
            shots_per_60 = (f.n / (sk.secs / 3600).clip(lower=1)).fillna(0.0)
            sk["off"] = sk["off"] + FIN * f.fin.fillna(0.0) * shots_per_60
    age_c = os.environ.get("RAPM_AGE")
    if age_c:
        sk["off"] = sk["off"] + age_term(y, sk.index, age_c)
    return sk


def age_term(y, ids, spec):
    """Per-60 change expected over the coming season by age on 1 October of season y. spec 'a,b': +a per year under 26,
    -b per year over 29 (linear)."""
    a, b = (float(x) for x in spec.split(","))
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "research", "nhl_bios.csv")
    if not os.path.exists(p):
        return 0.0
    B = pd.read_csv(p).set_index("player_id")
    bd = pd.to_datetime(B.birth_date, errors="coerce")
    age = ((pd.Timestamp(y, 10, 1) - bd).dt.days / 365.25).reindex(ids)
    t = np.where(age < 26, a * (26 - age), np.where(age > 29, -b * (age - 29), 0.0))
    return pd.Series(np.nan_to_num(t), index=ids)


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
