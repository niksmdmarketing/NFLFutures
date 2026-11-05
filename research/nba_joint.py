"""Joint team-and-player estimate for NBA futures (research/NBA_JOINT_TEAM_PLAYER_RULE.md and Amendment 1).

One ridge fit on lineup stints estimates every player's rating (beta) and every team-season's remaining effect (tau):
    y_s = eta + sum(beta, home five) - sum(beta, away five) + tau[home, k] - tau[away, k]
y_s = 100 x margin / possessions, weight = possessions x w_k (w_K = w_c, w_(K-1) = 1, w_(K-2) = 0.5).
Penalties: LAM_BETA x (beta - mu)^2, mu = K_BOX x box-score value from seasons K-1 and K-2 only; lambda_tau x tau^2 for the two
earlier seasons; lambda_tau x (tau_K - rho x tau_(K-1))^2 for the current one. Team rating at a checkpoint:
    scale x [ sum over the 12-man rotation of (beta + development) x minutes / 48 + tau_K ], centred.
Everything here is point in time: stints dated on or before the checkpoint, box scores of K-1 and K-2 only.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import sparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "pipeline"), os.path.join(ROOT, "research")):   # append only: pipeline/nba_rapm.py must stay ahead of research/nba_rapm.py
    if _p not in sys.path:
        sys.path.append(_p)
import nba as N  # noqa: E402
N.OVERRIDES_PATH = ""   # owner judgement overrides apply to the live season only, never to replays (as research/replay_nba.py)
N.OVERRIDES_ON = False

STINTS = os.environ.get("NBA_STINTS", "/home/claude/nbapbp/jstints")
LAM_BETA, W_K1, W_K2, K_BOX, ROOKIE = 3000.0, 1.0, 0.5, 2.5, -1.0
DEV_YOUNG, DEV_YEARS = 1.0, 4
BLEND_G = 10.0                 # games of projected minutes in the minutes blend (fixed, not tuned)
PRIOR_GAMES = 10               # pre-season roster: first team within that team's first 10 games
UNKNOWN_MIN = 180.0            # roster-step convention for a current-roster player with no prior minutes
MIN_USABLE = 0.60
PO_K, PO_GAMMA, PO_CAP = 1.0, 1.5, 42 / 240
GRID = [(wc, lt, rho) for wc in (2.0, 4.0, 8.0) for lt in (1000.0, 4000.0, 16000.0) for rho in (0.0, 0.5)]


def _id(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- raw data
_PBOX, _RAWBOX, _FIRST, _STINTS, _META = {}, {}, {}, {}, None


def raw_box(y):
    if y not in _RAWBOX:
        _RAWBOX[y] = pd.read_csv(os.path.join(N.NBA_DATA, f"player_box_{y}.csv"), low_memory=False)
    return _RAWBOX[y]


def pbox(y):
    """Regular-season player games with minutes: athlete_id (int), team_abbreviation, team_id, minutes, date."""
    if y not in _PBOX:
        d = pd.read_csv(os.path.join(N.NBA_DATA, f"player_box_{y}.csv"), low_memory=False,
                        usecols=["athlete_id", "team_abbreviation", "team_id", "minutes", "season_type", "game_date"])
        d = d[(pd.to_numeric(d.season_type, errors="coerce") == 2) & (pd.to_numeric(d.minutes, errors="coerce") > 0)].copy()
        d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
        d = d.dropna(subset=["athlete_id"])
        d["athlete_id"] = d.athlete_id.astype("int64")
        d["team_id"] = pd.to_numeric(d.team_id, errors="coerce").astype("int64")
        d["minutes"] = pd.to_numeric(d.minutes, errors="coerce")
        d["date"] = pd.to_datetime(d.game_date.astype(str).str[:10])
        _PBOX[y] = d[["athlete_id", "team_abbreviation", "team_id", "minutes", "date"]].reset_index(drop=True)
    return _PBOX[y]


def first_seasons(upto):
    """athlete_id -> first season (2002 onward) with regular-season minutes, using seasons <= upto only."""
    if upto not in _FIRST:
        fs = {}
        for y in range(2002, upto + 1):
            for a in pbox(y).athlete_id.unique():
                fs.setdefault(int(a), y)
        _FIRST[upto] = fs
    return _FIRST[upto]


def stints(y):
    if y not in _STINTS:
        p = os.path.join(STINTS, f"stints_{y}.parquet")
        global _META
        if _META is None:
            mp = os.path.join(STINTS, "meta.json")
            _META = json.load(open(mp)) if os.path.exists(mp) else {}
        if not os.path.exists(p) or _META.get(str(y), {}).get("usable_share", 1.0) < MIN_USABLE:
            _STINTS[y] = None
        else:
            S = pd.read_parquet(p, columns=["game_id", "date", "htid", "atid", "home5", "away5", "hpts", "apts", "poss"])
            # ESPN ids 1-30 are the NBA teams; larger ids are All-Star / exhibition sides filed as regular season
            S = S[(S.poss > 0.5) & S.htid.between(1, 30) & S.atid.between(1, 30)].reset_index(drop=True)
            S["date"] = pd.to_datetime(S.date)
            S["y"] = 100.0 * (S.hpts.to_numpy(float) - S.apts.to_numpy(float)) / S.poss.to_numpy(float)
            S["h"] = list(np.array([s.split(",") for s in S.home5], dtype=float).astype(np.int64))
            S["a"] = list(np.array([s.split(",") for s in S.away5], dtype=float).astype(np.int64))
            _STINTS[y] = S
    return _STINTS[y]


def box_prior(K):
    """mu_p = K_BOX x roster-step impact built from box scores of K-1 and K-2 only (the live prior)."""
    v = N._roster_values(N._player_values(raw_box(K - 1)), N._player_values(raw_box(K - 2)))
    return {int(float(a)): K_BOX * float(i) for a, i in zip(v.athlete_id, v.impact)}


# ---------------------------------------------------------------- the fit
class Fit:
    """All stints for a fit in season K (K, K-1, K-2) in one sparse design; normal equations by checkpoint."""

    def __init__(self, K):
        self.K = K
        self.seasons = [s for s in (K - 2, K - 1, K) if stints(s) is not None]
        self.has_cur = K in self.seasons
        pl = set()
        self.tix = {}
        for s in self.seasons:
            S = stints(s)
            pl |= set(np.concatenate(list(S.h)).tolist()) | set(np.concatenate(list(S.a)).tolist())
            for t in sorted(set(S.htid) | set(S.atid)):
                self.tix[(s, int(t))] = len(self.tix)
        self.ids = sorted(pl)
        self.pix = {a: i for i, a in enumerate(self.ids)}
        self.m, self.T = len(self.ids), len(self.tix)
        self.ncol = self.m + self.T + 1
        self.X, self.y, self.poss, self.date = {}, {}, {}, {}
        for s in self.seasons:
            S = stints(s)
            n = len(S)
            H = np.vectorize(self.pix.get)(np.vstack(S.h.to_list()))
            A = np.vectorize(self.pix.get)(np.vstack(S.a.to_list()))
            th = np.array([self.m + self.tix[(s, int(t))] for t in S.htid])
            ta = np.array([self.m + self.tix[(s, int(t))] for t in S.atid])
            cols = np.column_stack([H, A, th, ta, np.full(n, self.m + self.T)])
            vals = np.tile(np.r_[np.ones(5), -np.ones(5), 1.0, -1.0, 1.0], (n, 1))
            rows = np.repeat(np.arange(n), 13)
            self.X[s] = sparse.csr_matrix((vals.ravel(), (rows, cols.ravel())), shape=(n, self.ncol))
            self.y[s] = S.y.to_numpy(float)
            self.poss[s] = S.poss.to_numpy(float)
            self.date[s] = S.date.to_numpy()
        self.A0 = np.zeros((self.ncol, self.ncol))
        self.b0 = np.zeros(self.ncol)
        for s, w in ((K - 1, W_K1), (K - 2, W_K2)):
            if s in self.X:
                Aw, bw = self._normal(s, None, w)
                self.A0 += Aw
                self.b0 += bw
        self._cur = {}

    def _normal(self, s, cutoff, w):
        X, y, p = self.X[s], self.y[s], self.poss[s]
        if cutoff is not None:
            k = self.date[s] <= np.datetime64(cutoff)
            X, y, p = X[k], y[k], p[k]
        if X.shape[0] == 0:
            return np.zeros((self.ncol, self.ncol)), np.zeros(self.ncol)
        XtW = X.T.multiply(p * w).tocsr()
        return (XtW @ X).toarray(), np.asarray(XtW @ y).ravel()

    def current(self, cutoff):
        """Normal equations of the current season's stints dated on or before cutoff (weight 1; scaled by w_c later)."""
        key = pd.Timestamp(cutoff)
        if key not in self._cur:
            self._cur[key] = self._normal(self.K, key, 1.0) if self.has_cur else (np.zeros((self.ncol, self.ncol)), np.zeros(self.ncol))
        return self._cur[key]

    def last_date_used(self, cutoff):
        if not self.has_cur:
            return None
        d = self.date[self.K]
        d = d[d <= np.datetime64(pd.Timestamp(cutoff))]
        return None if len(d) == 0 else pd.Timestamp(d.max())

    def solve(self, cutoff, wc, lam_tau, rho, mu):
        Ac, bc = self.current(cutoff)
        A = self.A0 + wc * Ac
        b = self.b0 + wc * bc
        d = np.arange(self.m)
        A[d, d] += LAM_BETA
        b[:self.m] += LAM_BETA * np.array([mu.get(a, 0.0) for a in self.ids])
        K, tix, m = self.K, self.tix, self.m
        for (s, t), j in tix.items():
            c = m + j
            A[c, c] += lam_tau
            if s == K and (K - 1, t) in tix and rho != 0.0:
                c1 = m + tix[(K - 1, t)]
                A[c1, c1] += lam_tau * rho * rho
                A[c, c1] -= lam_tau * rho
                A[c1, c] -= lam_tau * rho
        A[-1, -1] += 1e-6
        sol = np.linalg.solve(A, b)
        beta = dict(zip(self.ids, sol[:m]))
        tauK = {t: sol[m + j] for (s, t), j in tix.items() if s == K}
        return beta, tauK, float(sol[-1])


# ---------------------------------------------------------------- rosters (Amendment 1, item 2)
def roster_v2(K, cutoff, season_games, noleak=False):
    """Pre-season: first team a player appears for within that team's first 10 games. At a checkpoint: the team he last played
    for on or before the cutoff, otherwise his pre-season team. noleak: players absent all season stay on last season's team."""
    pb = pbox(K).sort_values("date")
    tg = pb.groupby("team_abbreviation").date.apply(lambda s: {d: i + 1 for i, d in enumerate(sorted(s.unique()))})
    rank = np.array([tg[t][d] for t, d in zip(pb.team_abbreviation, pb.date)])
    early = pb[rank <= PRIOR_GAMES]
    pre = early.groupby("athlete_id").team_abbreviation.first()
    now = pb[pb.date <= pd.Timestamp(cutoff)].groupby("athlete_id").team_abbreviation.last()
    ros = pd.concat([pre[~pre.index.isin(now.index)], now])   # played by the cutoff: last team; otherwise pre-season team
    if noleak:
        prior = pbox(K - 1).sort_values("date").groupby("athlete_id").team_abbreviation.last()
        gone = prior[~prior.index.isin(pb.athlete_id.unique())]
        ros = pd.concat([ros, gone])
    out = ros.reset_index()
    out.columns = ["athlete_id", "team_abbreviation"]
    out["athlete_id"] = out.athlete_id.astype("int64").astype(str)
    return out


# ---------------------------------------------------------------- team strength from a fit
def minutes_table(K, cutoff, roster, rv):
    """Per team, up to 12 players with blended minutes scaled to 240.
    m_raw = (minutes with the team so far + 10 x projected per game) / (games so far + 10), projected = roster-step minutes / 82."""
    proj = {int(float(a)): min(float(mn), 2600.0) / 82 for a, mn in zip(rv.athlete_id, rv.minutes)}
    pb = pbox(K)
    pb = pb[pb.date <= pd.Timestamp(cutoff)]
    so_far = pb.groupby(["team_abbreviation", "athlete_id"]).minutes.sum().to_dict()
    G = pb.groupby("team_abbreviation").date.nunique().to_dict()
    rows = []
    for a, t in zip(roster.athlete_id, roster.team_abbreviation):
        a = int(a)
        p = proj.get(a, UNKNOWN_MIN / 82)
        rows.append((t, a, (so_far.get((t, a), 0.0) + BLEND_G * p) / (G.get(t, 0) + BLEND_G)))
    d = pd.DataFrame(rows, columns=["team", "athlete_id", "m_raw"]).drop_duplicates(["team", "athlete_id"])
    d = d[d.team.isin(N.TEAMS)].sort_values(["team", "m_raw"], ascending=[True, False]).groupby("team").head(12).copy()
    d["m"] = d.m_raw * 240.0 / d.groupby("team").m_raw.transform("sum")
    return d


def player_values(K, beta):
    """beta + development, once. Players with no prior-season minutes get no bonus; players with no rating get ROOKIE."""
    fs = first_seasons(K - 1)
    def one(a):
        if a not in beta:
            return ROOKIE
        return beta[a] + (DEV_YOUNG * max(0, DEV_YEARS - (K - fs[a])) if a in fs else 0.0)
    return one


def team_strength(mt, val):
    """mt: minutes_table; val: athlete_id -> beta + development. Returns S_t (points per 100, uncentred) and per-player r."""
    mt = mt.assign(r=[val(a) for a in mt.athlete_id])
    S = mt.groupby("team").apply(lambda g: float(np.sum(g.r.to_numpy() * g.m.to_numpy()) / 48.0), include_groups=False)
    return S, mt


def po_ratio(K):
    """Last season's playoff / regular-season minutes per game (the live ratio), athlete_id (int) -> ratio."""
    d = raw_box(K - 1)[["athlete_id", "minutes", "season_type"]].copy()
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce")
    d["st"] = pd.to_numeric(d.season_type, errors="coerce")
    d = d[d.minutes > 0]
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    po = d[d.st == 3].groupby("athlete_id").minutes.agg(["mean", "size"])
    rs = d[d.st == 2].groupby("athlete_id").minutes.agg(["mean", "size"])
    j = po.join(rs, lsuffix="_po", rsuffix="_rs", how="inner")
    j = j[(j.size_po >= 4) & (j.size_rs >= 20)]
    return {int(a): v for a, v in (j.mean_po / j.mean_rs).clip(0.5, 1.5).items()}


def playoff_delta(mt_r, ratio, scale):
    """Per-team scale x PO_K x (playoff-rotation strength - regular strength), same 12 players, same minutes m, same units.
    mt_r: minutes_table with column r. Returns a Series by team (centred)."""
    out = {}
    for t, g in mt_r.groupby("team"):
        m, r = g.m.to_numpy(float), g.r.to_numpy(float)
        reg = 5 * float(np.sum(m / m.sum() * r))
        mp = m * np.array([ratio.get(int(a), 1.0) for a in g.athlete_id])
        o = np.argsort(-mp, kind="stable")
        mp, rp = mp[o], r[o]
        sh = mp / mp.sum()
        top = sh[:8] ** PO_GAMMA
        top = top / top.sum()
        for _ in range(5):
            top = np.minimum(top, PO_CAP)
            top = top / top.sum()
        out[t] = scale * PO_K * (5 * float(np.sum(top * rp[:8])) - reg)
    s = pd.Series(out).reindex(N.TEAMS).fillna(0.0)
    return s - s.mean()


_FITS = {}


def get_fit(K):
    if K not in _FITS:
        _FITS[K] = Fit(K)
    return _FITS[K]


def season_context(K):
    """Season-level inputs that do not depend on the checkpoint."""
    v1, v2 = N._player_values(raw_box(K - 1)), N._player_values(raw_box(K - 2))
    rv = N._roster_values(v1, v2)
    pbk = pbox(K)
    tid2abbr = pbk.drop_duplicates("team_id").set_index("team_id").team_abbreviation.to_dict()
    return dict(rv=rv, mu=box_prior(K), tid2abbr=tid2abbr)


def rating_at(K, cutoff, roster, hp, ctx, scale=1.0, return_parts=False):
    """Team ratings (centred, points per 100) and playoff delta at a checkpoint for hyperparameters hp = (wc, lam_tau, rho)."""
    f = get_fit(K)
    beta, tauK, _ = f.solve(cutoff, *hp, ctx["mu"])
    mt = minutes_table(K, cutoff, roster, ctx["rv"])
    val = player_values(K, beta)
    S, mt_r = team_strength(mt, val)
    tau = pd.Series({ctx["tid2abbr"].get(t): v for t, v in tauK.items()}).reindex(N.TEAMS).fillna(0.0)
    S = S.reindex(N.TEAMS).fillna(0.0)
    parts = dict(players=S - S.mean(), tau=tau - tau.mean())
    rating = scale * (S + tau)
    rating = rating - rating.mean()
    if return_parts:
        return rating, mt_r, parts
    return rating, mt_r
