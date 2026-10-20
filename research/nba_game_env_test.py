"""NBA stage two: game environment, per research/NBA_GAME_ENV_RULE.md (with amendment 1).
  python research/nba_game_env_test.py ratings   -> <W>/games.csv.gz (weekly team ratings, actuals, injury term), usual lineups
  python research/nba_game_env_test.py rapm      -> <W>/odrapm.pkl (two-sided player ratings per weekly checkpoint)
  python research/nba_game_env_test.py minutes   -> <W>/proj_minutes.csv.gz (stage-one projected minutes 2017-2026)
  python research/nba_game_env_test.py lineup    -> <W>/lineup.csv.gz (offence/defence lineup deltas per team-game)
  python research/nba_game_env_test.py sim       -> <W>/sim_<model>.npz
  python research/nba_game_env_test.py score     -> research/nba_game_env_results.json
W = GENV_DIR (scratch; derived from ESPN data, private).
"""
import collections
import json
import math
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402

W = os.environ.get("GENV_DIR", "/tmp/claude-0/-home-claude/05818a0d-0d82-5af8-8a3a-91e344d8290f/scratchpad/genv")
AVAIL = os.environ.get("GENV_AVAIL", "/tmp/claude-0/-home-claude-nflfutures/05818a0d-0d82-5af8-8a3a-91e344d8290f/scratchpad/nba_avail2_games.csv")
SEASONS = list(range(2017, 2027))
TEST = [2022, 2023, 2024, 2025, 2026]
S_EFF = math.sqrt(N.GAME_SIGMA ** 2 + 2 * N.TEAM_TAU ** 2)
AV_SCALE = 0.45


def season_weights(end_year, seasons, decay=0.2, current_weight=8.0):
    s = np.asarray(seasons)
    w = np.power(decay, np.maximum(0, (end_year - 1) - s))
    return np.where(s == end_year, current_weight, w)


# ---------------------------------------------------------------- ratings
def ratings():
    import nba_backtest as B
    boxes = B.load_boxes(2026)
    reg = N._regular_boxes(boxes)
    reg["season"] = reg.season.astype(int)
    pb = load_player_box(2013)
    games, usual = [], {}
    for y in SEASONS:
        g = B.season_games(boxes, y)
        g["wk"] = ((g.date - g.date.min()).dt.days // 7).astype(int)
        nw = g.wk.max() + 1
        prior_boxes = boxes[pd.to_numeric(boxes.season, errors="coerce") < y]
        cur_boxes = boxes[pd.to_numeric(boxes.season, errors="coerce") == y]
        for w in range(nw):
            past_ids = set(g[g.wk < w].gid)
            tr = pd.concat([prior_boxes, cur_boxes[cur_boxes.game_id.isin(past_ids)]]) if past_ids else prior_boxes
            R, fit = N._fit_ratings(tr, y)
            hca = fit["home_offense_points_per_100"] if 0 < fit["home_offense_points_per_100"] < 6 else 2.2
            r = R.set_index("team")
            wk_start = g[g.wk == w].date.min()
            for x in g[g.wk == w].itertuples():
                if x.home not in r.index or x.away not in r.index:
                    continue
                games.append(dict(season=y, gid=int(x.gid), date=x.date, wk=w, frac=w / nw, home=x.home, away=x.away, margin=x.margin,
                                  base=fit["base_ortg"], hca=hca, off_h=r.off[x.home], def_h=r["def"][x.home], pace_h=r.pace[x.home],
                                  off_a=r.off[x.away], def_a=r["def"][x.away], pace_a=r.pace[x.away], wk_start=wk_start))
            # usual lineup: minutes per weighted team game over the games the rating used
            trg = N._regular_boxes(tr)
            trg = trg[trg.season.astype(int) >= y - 4]
            wts = dict(zip(trg.game_id.astype(int), season_weights(y, trg.season.astype(int))))
            P = pb[pb.game_id.isin(wts.keys())]
            P = P.assign(w=P.game_id.map(wts))
            tg = trg.assign(w=trg.game_id.astype(int).map(wts)).groupby("team_abbreviation").w.sum()
            um = (P.assign(wm=P.w * P.minutes).groupby(["team_abbreviation", "athlete_id"]).wm.sum())
            for (t, a), v in um.items():
                if t in tg.index and tg[t] > 0:
                    usual.setdefault((y, w, t), {})[int(a)] = v / tg[t]
        print("ratings", y, len(games), flush=True)
    G = pd.DataFrame(games)
    # actual scores and possessions
    h = reg[reg.team_home_away == "home"].drop_duplicates("game_id")
    act = pd.DataFrame(dict(gid=h.game_id.astype(int), hs=h.team_score.astype(float),
                            as_=pd.to_numeric(h.opponent_team_score, errors="coerce"), poss=h.poss.astype(float)))
    G = G.merge(act, on="gid", how="left")
    # tip time
    tips = pb.groupby("game_id").tip.first()
    G["tip"] = G.gid.map(tips)
    # official-report injury term (v2_official, as in research/nba_availability2.py)
    A = pd.read_csv(AVAIL, parse_dates=["date"])[["date", "home", "away", "v2_official_h", "v2_official_a", "covered"]]
    G["date"] = pd.to_datetime(G.date).dt.normalize()
    G = G.merge(A, on=["date", "home", "away"], how="left")
    G[["v2_official_h", "v2_official_a"]] = G[["v2_official_h", "v2_official_a"]].fillna(0.0)
    G.to_csv(os.path.join(W, "games.csv.gz"), index=False, compression="gzip")
    with open(os.path.join(W, "usual.pkl"), "wb") as f:
        pickle.dump(usual, f)
    print("games", len(G))


def load_player_box(first):
    frames = []
    for y in range(first, 2027):
        d = pd.read_csv(os.path.join(ROOT, "data", "nba", f"player_box_{y}.csv"), low_memory=False,
                        usecols=["game_id", "season", "season_type", "game_date_time", "athlete_id", "team_abbreviation", "minutes"])
        d = d[pd.to_numeric(d.season_type, errors="coerce") == 2]
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["minutes"] = pd.to_numeric(d.minutes, errors="coerce").fillna(0.0)
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    d = d.dropna(subset=["athlete_id"])
    d["athlete_id"] = d.athlete_id.astype(int)
    d["game_id"] = pd.to_numeric(d.game_id, errors="coerce").astype(int)
    d["tip"] = pd.to_datetime(d.game_date_time, utc=True, errors="coerce", format="ISO8601")
    return d


# ---------------------------------------------------------------- two-sided RAPM
def _rapm_mod():
    os.environ.setdefault("NP_KBOX", "2.5")
    os.environ.setdefault("NP_DEV", "1.0")
    import importlib.util
    spec = importlib.util.spec_from_file_location("research_nba_rapm", os.path.join(HERE, "nba_rapm.py"))
    RA = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(RA)
    sys.modules["research_nba_rapm"] = RA
    import nba_player_replay as NP
    NP.RA = RA
    return RA, NP


def _design(S):
    hp = S.home5.str.split(",").to_list()
    ap = S.away5.str.split(",").to_list()
    H = np.array([[int(float(a)) for a in x] for x in hp])
    A = np.array([[int(float(a)) for a in x] for x in ap])
    return H, A


def od_fit(frames, prior, lam=3000.0):
    """frames: list of (stints with columns H(5), A(5), hpts, apts, poss, w). Returns {aid: (O, D)}."""
    H = np.vstack([f[0] for f in frames])
    A = np.vstack([f[1] for f in frames])
    S = pd.concat([f[2] for f in frames], ignore_index=True)
    ids = np.unique(np.concatenate([H.ravel(), A.ravel()]))
    ix = {a: i for i, a in enumerate(ids)}
    m = len(ids)
    from scipy import sparse
    n = len(S)
    hi = np.vectorize(ix.get)(H)
    ai = np.vectorize(ix.get)(A)
    # row block 1: home offence vs away defence; block 2: away offence vs home defence. columns: O (0..m-1), D (m..2m-1), mean, home
    r1 = np.repeat(np.arange(n), 10)
    c1 = np.concatenate([hi, ai + m], axis=1).ravel()
    v1 = np.tile(np.r_[np.ones(5), -np.ones(5)], n)
    r2 = np.repeat(np.arange(n), 10) + n
    c2 = np.concatenate([ai, hi + m], axis=1).ravel()
    X = sparse.csr_matrix((np.r_[v1, v1], (np.r_[r1, r2], np.r_[c1, c2])), shape=(2 * n, 2 * m + 2)).tolil()
    X[:, 2 * m] = 1.0
    X[:n, 2 * m + 1] = 1.0
    X = X.tocsr()
    poss = S.poss.to_numpy(float)
    yv = np.r_[100 * S.hpts.to_numpy(float) / poss, 100 * S.apts.to_numpy(float) / poss]
    wt = np.r_[poss * S.w.to_numpy(float), poss * S.w.to_numpy(float)]
    XtW = X.T.multiply(wt)
    Am = (XtW @ X).toarray()
    b = XtW @ yv
    pr = np.array([prior.get(int(a), 0.0) / 2 for a in ids]) if prior else np.zeros(m)
    Am[np.arange(2 * m), np.arange(2 * m)] += lam
    b[:m] += lam * pr
    b[m:2 * m] += lam * pr
    sol = np.linalg.solve(Am, b)
    return {int(a): (float(sol[i]), float(sol[m + i])) for i, a in enumerate(ids)}


def rapm():
    RA, NP = _rapm_mod()
    G = pd.read_csv(os.path.join(W, "games.csv.gz"), parse_dates=["wk_start"])
    cache = {}

    def stints(y):
        if y not in cache:
            S = RA.load(y)
            if S is None:
                cache[y] = None
            else:
                S = S.reset_index(drop=True)
                H, A = _design(S)
                cache[y] = (H, A, S[["date", "hpts", "apts", "poss"]].assign(date=pd.to_datetime(S.date)))
        return cache[y]
    out = {}
    for y in SEASONS:
        prior = NP.box_prior(y - 1)
        fs = NP.first_season()
        base = []
        for k, w in ((1, 1.0), (2, 0.5)):
            st = stints(y - k)
            if st is not None:
                base.append((st[0], st[1], st[2].assign(w=w)))
        cur = stints(y)
        for wk, ws in G[G.season == y].groupby("wk").wk_start.first().items():
            cutoff = ws - pd.Timedelta(days=1)
            frames = list(base)
            if cur is not None:
                msk = (cur[2].date <= cutoff).to_numpy()
                if msk.any():
                    frames.append((cur[0][msk], cur[1][msk], cur[2][msk].assign(w=1.0)))
            r = od_fit(frames, prior)
            # young-player development as live (NP.develop on the net), split equally between offence and defence
            dev = {a: NP.DEV_YOUNG * max(0, 4 - (y - fs.get(int(a), y))) - NP.DEV_OLD * max(0, (y - fs.get(int(a), y)) - 11) for a in r}
            out[(y, int(wk))] = {a: (o + dev[a] / 2, d + dev[a] / 2) for a, (o, d) in r.items()}
        print("rapm", y, flush=True)
    with open(os.path.join(W, "odrapm.pkl"), "wb") as f:
        pickle.dump(out, f)


# ---------------------------------------------------------------- stage-one projected minutes (2017-2026)
def minutes():
    import nba_minutes_test as M
    from sklearn.linear_model import LogisticRegression
    D = pd.read_csv(M.ROWS)
    if "fallback" not in D:
        D["fallback"] = 0
    D["fallback"] = D.fallback.fillna(0)
    D = D[(D.fallback == 0) & (D.aid != -1)].copy()
    D["y_app"] = (D.minutes > 0).astype(float)
    for c in ("st1", "st6"):
        D[c] = D[c].fillna("")
    D["newcomer"] = D["ewm"].isna()
    fill = {"app10": 0.5, "mpg10": 12.0, "ewm": 12.0, "season_mpg": 12.0, "season_app": 0.5}
    for c, v in fill.items():
        D[c] = D[c].fillna(v)
    D["early"] = (D.gi < 10).astype(float)
    res = []
    for tag in ("1", "6"):
        st = D["st" + tag]
        for s in SEASONS:
            lo = 2020 if s in TEST else 2016          # test seasons exactly as frozen stage one; fitting seasons 2016..s-1
            tr = ((D.season < s) & (D.season >= lo)).to_numpy()
            te = (D.season == s).to_numpy()
            T = D[tr]
            pmiss = {k: float(1 - T[T["st" + tag] == k].y_app.mean()) for k in M.PM if (T["st" + tag] == k).sum() > 50}
            pm_te = st[te].map(pmiss).fillna(0.0).to_numpy()
            ok = ~T["st" + tag].isin(["Out", "Doubtful", "Questionable"])
            Xf = lambda Z: np.column_stack([Z.app10, Z.mpg10 / 48, Z.start10, np.log1p(Z.streak), Z["vac_same" + tag] / 48, Z["vac_other" + tag] / 48, Z.early, Z["ewm"] / 48, Z.newcomer.astype(float)])
            lr = LogisticRegression(C=1.0, max_iter=500).fit(Xf(T[ok]), T[ok].y_app)
            Z = D[te]
            pa = (1 - pm_te) * lr.predict_proba(Xf(Z))[:, 1]
            P = T[T.minutes > 0]
            Xm = lambda Z: np.column_stack([np.ones(len(Z)), Z["ewm"], Z.season_mpg, Z["vac_same" + tag] * Z["ewm"] / 36, Z["vac_other" + tag] * Z["ewm"] / 36,
                                            ((Z.streak >= 2) & (Z["st" + tag] != "Out")).astype(float), Z.start10, Z.early, Z.newcomer.astype(float)])
            bm = np.linalg.lstsq(Xm(P), P.minutes.to_numpy(), rcond=None)[0]
            muP = np.clip(Xm(P) @ bm, 1, 48)
            sdM = M.sd_fit(muP, P.minutes.to_numpy())
            mu = np.clip(Xm(Z) @ bm, 1, 48)
            q = M.disc_normal(mu, sdM(mu))
            emin = q @ np.arange(1, M.MAXM + 1)
            res.append(pd.DataFrame(dict(tag=tag, season=s, game_id=Z.game_id.to_numpy(), team=Z.team.to_numpy(), aid=Z.aid.to_numpy().astype(int),
                                         pa=pa, emin_app=emin, mu=mu, sd=sdM(mu))))
        print("minutes", tag, flush=True)
    R = pd.concat(res, ignore_index=True)
    R.to_csv(os.path.join(W, "proj_minutes.csv.gz"), index=False, compression="gzip")


# ---------------------------------------------------------------- lineup deltas
UNRATED = (-0.5, -0.5)


def lineup():
    G = pd.read_csv(os.path.join(W, "games.csv.gz"))
    R = pd.read_csv(os.path.join(W, "proj_minutes.csv.gz"), dtype={"tag": str})
    with open(os.path.join(W, "odrapm.pkl"), "rb") as f:
        OD = pickle.load(f)
    with open(os.path.join(W, "usual.pkl"), "rb") as f:
        U = pickle.load(f)
    rows = []
    groups = {k: g for k, g in R.groupby(["tag", "game_id", "team"])}
    for x in G.itertuples():
        od = OD.get((x.season, x.wk))
        if od is None:
            continue
        for side, t in (("h", x.home), ("a", x.away)):
            usual = U.get((x.season, x.wk, t), {})
            if not usual:
                continue
            us = sum(usual.values())
            uo = sum(m / us * 240 / 48 * od.get(a, UNRATED)[0] for a, m in usual.items())
            ud = sum(m / us * 240 / 48 * od.get(a, UNRATED)[1] for a, m in usual.items())
            for tag in ("1", "6"):
                g = groups.get((tag, x.gid, t))
                if g is None:
                    continue
                e = (g.pa * g.emin_app).to_numpy()
                if e.sum() <= 0:
                    continue
                e = e / e.sum() * 240
                o = np.array([od.get(int(a), UNRATED)[0] for a in g.aid])
                d = np.array([od.get(int(a), UNRATED)[1] for a in g.aid])
                rows.append(dict(gid=x.gid, side=side, tag=tag, dO=float((e / 48 * o).sum() - uo), dD=float((e / 48 * d).sum() - ud),
                                 n=len(g), aids=",".join(str(int(a)) for a in g.aid), pa=",".join(f"{v:.4f}" for v in g.pa),
                                 emin=",".join(f"{v:.3f}" for v in g.emin_app), O=",".join(f"{v:.3f}" for v in o), D=",".join(f"{v:.3f}" for v in d),
                                 uo=uo, ud=ud))
    L = pd.DataFrame(rows).drop_duplicates(["gid", "side", "tag"])
    L.to_csv(os.path.join(W, "lineup.csv.gz"), index=False, compression="gzip")
    print("lineup rows", len(L))




# ================================================================ simulation and scoring
MG = np.arange(-90, 91)        # margin support (unclipped reporting range)
TT = np.arange(100, 361)       # total support
D_DRAWS = 4000


def load_games():
    G = pd.read_csv(os.path.join(W, "games.csv.gz"), parse_dates=["date"]).drop_duplicates("gid")
    G = G.dropna(subset=["hs", "as_", "poss"]).copy()
    pb = load_player_box(2017)
    tm = pb.groupby(["game_id", "team_abbreviation"]).minutes.sum().groupby("game_id").max()
    G["ot"] = G.gid.map(tm).fillna(240) >= 262
    G["total"] = G.hs + G.as_
    G["ortg_h_exp"] = G.base + G.off_h - G.def_a + G.hca
    G["ortg_a_exp"] = G.base + G.off_a - G.def_h
    G["pace"] = (G.pace_h + G.pace_a) / 2
    G["d_av"] = G.v2_official_h - G.v2_official_a
    G["m_L"] = (G.off_h + G.def_h - G.off_a - G.def_a + G.hca) * G.pace / 100 - AV_SCALE * G.d_av
    G["t_L"] = (G.ortg_h_exp + G.ortg_a_exp) * G.pace / 100
    return G.sort_values(["date", "gid"]).reset_index(drop=True)


def fit_k(G, Lu, s):
    """k_O, k_D by ridge toward (1, 1) on team-game residuals of seasons 2017..s-1 (amendment 1, item 1)."""
    T = G[(G.season < s)]
    L1 = Lu[Lu.tag == "1"].drop_duplicates(["gid", "side"])
    L = {(g, sd): (o, d) for g, sd, o, d in zip(L1.gid, L1.side, L1.dO, L1.dD)}
    rows = []
    for x in T.itertuples():
        for side, opp, act, exp in (("h", "a", x.hs / x.poss * 100, x.ortg_h_exp), ("a", "h", x.as_ / x.poss * 100, x.ortg_a_exp)):
            if (x.gid, side) in L and (x.gid, opp) in L:
                rows.append((L[(x.gid, side)][0], -L[(x.gid, opp)][1], act - exp))
    A = np.array(rows)
    X, r = A[:, :2], A[:, 2]
    lam = 1000 * (X ** 2).mean(0)
    k = np.linalg.solve(X.T @ X + np.diag(lam), X.T @ r + lam * 1.0)
    return float(k[0]), float(k[1]), len(rows)


def poss_inputs(s):
    """points pmf and duration pool from play-by-play of up to three earlier seasons with complete free-throw coverage (2020+)."""
    ys = [y for y in range(max(2020, s - 3), s)]
    d, p = [], []
    for y in ys:
        z = np.load(os.path.join(W, f"poss_{y}.npz"))
        d.append(z["dur"])
        p.append(z["pts"])
    d, p = np.concatenate(d), np.concatenate(p)
    pmf = np.bincount(p) / len(p)
    return d, pmf, ys


def tilt_table(pmf):
    k = np.arange(len(pmf))
    th = np.linspace(-1.5, 1.5, 3001)
    w = pmf[None, :] * np.exp(th[:, None] * k[None, :])
    mean = (w * k).sum(1) / w.sum(1)
    return th, mean


def tilted_cdf(pmf, th_tab, mean_tab, target):
    th = np.interp(target, mean_tab, th_tab)
    k = np.arange(len(pmf))
    w = pmf[None, :] * np.exp(th[:, None] * k[None, :])
    w /= w.sum(1, keepdims=True)
    return np.cumsum(w, 1)


def _quarter_counts(dur, scale, rng, n=20000, length=720.0):
    clock = np.full(n, length)
    cnt = np.zeros(n)
    act = np.arange(n)
    while len(act):
        clock[act] -= dur[rng.integers(len(dur), size=len(act))] * scale
        cnt[act] += 1
        act = act[clock[act] > 0]
    return cnt


def calibrate(dur, G, s, rng):
    """scale(pace) mapping and the shared pace factor's sd (fitted on earlier seasons' regulation games)."""
    scales = np.linspace(0.75, 1.3, 23)
    per_team = []   # possessions per team per 48
    var_team = []
    for c in scales:
        q = np.stack([_quarter_counts(dur, c, rng, n=8000) for _ in range(4)])   # 4 quarters
        tot = q.sum(0)
        per_team.append(tot.mean() / 2)
        var_team.append(tot.var() / 4)
    per_team, var_team = np.array(per_team), np.array(var_team)
    E = G[(G.season < s) & (G.season >= max(2020, s - 3)) & ~G.ot]
    resid = E.poss - E.pace
    inh = np.interp(E.pace.mean(), per_team[::-1], var_team[::-1])
    sig = math.sqrt(max(0.0, resid.var() - inh)) / E.pace.mean()
    return scales, per_team, sig


def simulate(G, ortg_h, ortg_a, s, seed, Gcal, lineup_draws=None, batch=60):
    """returns dict of per-game arrays: margin pmf, total pmf, p_win, p_ot and moments."""
    rng = np.random.default_rng(seed)
    dur, pmf, ys = poss_inputs(s)
    scales, per_team, sig = calibrate(dur, Gcal, s, rng)
    th_tab, mean_tab = tilt_table(pmf)
    n = len(G)
    out = {k: [] for k in ("mpmf", "tpmf", "pwin", "pot", "mh", "ma", "vh", "va", "cov", "pclose")}
    pace = G.pace.to_numpy()
    sc_g = np.interp(pace, per_team[::-1], scales[::-1])
    poss_exp = pace   # per team, regulation
    for b0 in range(0, n, batch):
        idx = np.arange(b0, min(n, b0 + batch))
        g = len(idx)
        M = g * D_DRAWS
        gi = np.repeat(np.arange(g), D_DRAWS)
        f = np.exp(sig * rng.standard_normal(M))
        scale = sc_g[idx][gi] * f
        # per-draw ratings (G1s: lineup drawn per draw)
        if lineup_draws is not None:
            oh, oa = lineup_draws(idx, rng)          # arrays (g, D) of ortg
            oh, oa = oh.ravel(), oa.ravel()
        else:
            oh, oa = ortg_h[idx][gi], ortg_a[idx][gi]
        # tilted cdfs per element
        CH = tilted_cdf(pmf, th_tab, mean_tab, oh / 100)
        CA = tilted_cdf(pmf, th_tab, mean_tab, oa / 100)
        hs = np.zeros(M)
        as_ = np.zeros(M)
        tipw = rng.random(M) < 0.5     # True: home wins the opening tip

        def period(sel, length, home_first):
            clock = np.full(len(sel), length)
            offh = home_first.copy()
            act = np.arange(len(sel))
            while len(act):
                e = sel[act]
                u = rng.random(len(act))
                C = np.where(offh[act][:, None], CH[e], CA[e])
                pts = (u[:, None] > C[:, :-1]).sum(1)
                np.add.at(hs, e[offh[act]], pts[offh[act]])
                np.add.at(as_, e[~offh[act]], pts[~offh[act]])
                clock[act] -= dur[rng.integers(len(dur), size=len(act))] * scale[e]
                offh[act] = ~offh[act]
                act = act[clock[act] > 0]
        allx = np.arange(M)
        for q in range(4):
            period(allx, 720.0, tipw if q in (0, 3) else ~tipw)
        ot = np.zeros(M, bool)
        for _ in range(10):
            tied = np.nonzero(hs == as_)[0]
            if not len(tied):
                break
            ot[tied] = True
            period(tied, 300.0, rng.random(len(tied)) < 0.5)
        mg = np.clip(hs - as_, MG[0], MG[-1]).astype(int) - MG[0]
        tt = np.clip(hs + as_, TT[0], TT[-1]).astype(int) - TT[0]
        out["mpmf"].append(np.bincount(gi * len(MG) + mg, minlength=g * len(MG)).reshape(g, len(MG)) / D_DRAWS)
        out["tpmf"].append(np.bincount(gi * len(TT) + tt, minlength=g * len(TT)).reshape(g, len(TT)) / D_DRAWS)
        H = hs.reshape(g, D_DRAWS)
        A = as_.reshape(g, D_DRAWS)
        out["pwin"].append((H > A).mean(1))
        out["pot"].append(ot.reshape(g, D_DRAWS).mean(1))
        out["mh"].append(H.mean(1))
        out["ma"].append(A.mean(1))
        out["vh"].append(H.var(1))
        out["va"].append(A.var(1))
        out["cov"].append(((H - H.mean(1, keepdims=True)) * (A - A.mean(1, keepdims=True))).mean(1))
        out["pclose"].append((np.abs(H - A) <= 3).mean(1))
    res = {k: np.concatenate(v) for k, v in out.items()}
    res["calib"] = dict(pace_factor_sd=sig, poss_seasons=ys, pmf=[round(float(x), 5) for x in pmf])
    return res


def test_games(G, Lu):
    """games of the test seasons where every model has a forecast (lineup for both teams at 1 hour before)."""
    have = set(map(tuple, Lu[Lu.tag == "1"][["gid", "side"]].to_numpy()))
    T = G[G.season.isin(TEST)].copy()
    ok = np.array([(g, "h") in have and (g, "a") in have for g in T.gid])
    return T[ok].reset_index(drop=True), int((~ok).sum())


def model_ratings(model, T, G, Lu, s):
    inj = AV_SCALE * T.d_av / 2 / (T.pace / 100)
    if model == "G0":
        return (T.ortg_h_exp - inj).to_numpy(), (T.ortg_a_exp + inj).to_numpy(), None, {}
    tag = "6" if model == "G1_6h" else "1"
    kO, kD, nfit = fit_k(G, Lu, s)
    L = Lu[Lu.tag == tag].drop_duplicates(["gid", "side"]).set_index(["gid", "side"])
    def get(side, col):
        return np.array([L.loc[(g, side), col] if (g, side) in L.index else 0.0 for g in T.gid])
    dOh, dOa, dDh, dDa = get("h", "dO"), get("a", "dO"), get("h", "dD"), get("a", "dD")
    oh = T.ortg_h_exp.to_numpy() + kO * dOh - kD * dDa
    oa = T.ortg_a_exp.to_numpy() + kO * dOa - kD * dDh
    info = dict(k_O=kO, k_D=kD, fit_rows=nfit)
    if model != "G1s":
        return oh, oa, None, info
    # G1s: appearance sampled per draw
    rec = {}
    for gid in T.gid:
        for side in ("h", "a"):
            r = L.loc[(gid, side)]
            rec[(gid, side)] = (np.array(r.pa.split(","), float), np.array(r.emin.split(","), float), np.array(r.O.split(","), float),
                                np.array(r.D.split(","), float), r.uo, r.ud)
    base_h, base_a = T.ortg_h_exp.to_numpy(), T.ortg_a_exp.to_numpy()
    gids = T.gid.to_numpy()

    def draws(idx, rng):
        oh_ = np.empty((len(idx), D_DRAWS))
        oa_ = np.empty((len(idx), D_DRAWS))
        for j, i in enumerate(idx):
            d = {}
            for side in ("h", "a"):
                pa, em, O, Dd, uo, ud = rec[(gids[i], side)]
                app = rng.random((D_DRAWS, len(pa))) < pa[None, :]
                e = app * em[None, :]
                tot = e.sum(1, keepdims=True)
                e = np.where(tot > 0, e / np.maximum(tot, 1e-9) * 240, 0.0)
                d[side] = (np.where(tot[:, 0] > 0, e @ O / 48 - uo, 0.0), np.where(tot[:, 0] > 0, e @ Dd / 48 - ud, 0.0))
            oh_[j] = base_h[i] + kO * d["h"][0] - kD * d["a"][1]
            oa_[j] = base_a[i] + kO * d["a"][0] - kD * d["h"][1]
        return oh_, oa_
    return oh, oa, draws, info


def run_sim(model, s):
    global D_DRAWS
    if model in ("G1s", "G1_6h"):
        D_DRAWS = 2000          # reported-only variants
    G = load_games()
    Lu = pd.read_csv(os.path.join(W, "lineup.csv.gz"), dtype={"tag": str})
    T, _ = test_games(G, Lu)
    T = T[T.season == s].reset_index(drop=True)
    oh, oa, draws, info = model_ratings(model, T, G, Lu, s)
    r = simulate(T, oh, oa, s, 1000 + s, G, lineup_draws=draws)
    calib = r.pop("calib")
    np.savez_compressed(os.path.join(W, f"sim_{model}_{s}.npz"), gid=T.gid.to_numpy(), **r)
    with open(os.path.join(W, f"sim_{model}_{s}.json"), "w") as f:
        json.dump(dict(calib, **info, draws=D_DRAWS, games=len(T)), f)
    print("done", model, s, len(T), flush=True)


# ---------------------------------------------------------------- scoring
from scipy.stats import norm  # noqa: E402


def normal_margin_pmf(m, sd):
    """positive k gets (k-1, k], negative k gets [k, k+1); zero has no mass; tails at the support ends."""
    edges_pos = norm.cdf((np.arange(0, MG[-1] + 1)[None, :] - m[:, None]) / sd[:, None])    # F(0..90)
    edges_neg = norm.cdf((np.arange(MG[0], 1)[None, :] - m[:, None]) / sd[:, None])         # F(-90..0)
    P = np.zeros((len(m), len(MG)))
    zero = -MG[0]
    P[:, zero + 1:] = np.diff(edges_pos, axis=1)
    P[:, zero + 1 + len(MG[zero + 1:]) - 1] += 1 - edges_pos[:, -1]
    P[:, :zero] = np.diff(edges_neg, axis=1)
    P[:, 0] += edges_neg[:, 0]
    return P


def normal_total_pmf(t, sd):
    e = norm.cdf((np.r_[TT - 0.5, TT[-1] + 0.5][None, :] - t[:, None]) / sd[:, None])
    P = np.diff(e, axis=1)
    P[:, 0] += e[:, 0]
    P[:, -1] += 1 - e[:, -1]
    return P


def rps(P, support, y, lo, hi):
    """mean over thresholds k = lo..hi-1 of (F(k) - 1[y <= k])^2, outcome clipped to [lo, hi]."""
    F = np.cumsum(P, 1)
    ks = np.arange(lo, hi)
    cols = ks - support[0]
    yc = np.clip(y, lo, hi)
    I = (yc[:, None] <= ks[None, :]).astype(float)
    return ((F[:, cols] - I) ** 2).mean(1)


def pit(P, support, y, rng):
    yi = np.clip(y, support[0], support[-1]).astype(int) - support[0]
    F = np.cumsum(P, 1)
    hi = F[np.arange(len(yi)), yi]
    lo = np.where(yi > 0, F[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
    return lo + rng.random(len(yi)) * (hi - lo)


def median_of(P, support):
    F = np.cumsum(P, 1)
    return support[(F < 0.5).sum(1)]


def b_model(G):
    """B: season-to-date offensive/defensive rating and pace (previous season blended over the first 10 games)."""
    import nba_backtest as B
    reg = N._regular_boxes(B.load_boxes(2026))
    reg["season"] = reg.season.astype(int)
    reg["date"] = pd.to_datetime(reg.game_date).dt.normalize()
    opp = reg[["game_id", "team_abbreviation", "ortg"]].rename(columns={"team_abbreviation": "opponent_team_abbreviation", "ortg": "drtg"})
    reg = reg.merge(opp, on=["game_id", "opponent_team_abbreviation"], how="left")
    full = reg.groupby(["season", "team_abbreviation"])[["ortg", "drtg", "poss"]].mean()
    out = {}
    for (y, t), X in reg.sort_values("date").groupby(["season", "team_abbreviation"]):
        prev = full.loc[(y - 1, t)] if (y - 1, t) in full.index else full.xs(y - 1, level=0).mean() if (y - 1) in full.index.get_level_values(0) else None
        c = X[["ortg", "drtg", "poss"]].expanding().mean().shift()
        n = np.arange(len(X))
        for i, (gid, d) in enumerate(zip(X.game_id, X.date)):
            cur = c.iloc[i]
            wgt = min(n[i], 10) / 10
            if prev is None:
                v = cur.to_numpy() if n[i] > 0 else np.array([110.0, 110.0, 100.0])
            else:
                v = prev.to_numpy() if n[i] == 0 else wgt * cur.to_numpy() + (1 - wgt) * prev.to_numpy()
            out[(int(gid), t)] = v
    oh = np.array([out.get((g, h), [np.nan] * 3) for g, h in zip(G.gid, G.home)])
    oa = np.array([out.get((g, a), [np.nan] * 3) for g, a in zip(G.gid, G.away)])
    pace = (oh[:, 2] + oa[:, 2]) / 2
    m_net = ((oh[:, 0] + oa[:, 1]) / 2 - (oa[:, 0] + oh[:, 1]) / 2) * pace / 100
    tot = ((oh[:, 0] + oa[:, 1]) / 2 + (oa[:, 0] + oh[:, 1]) / 2) * pace / 100
    return m_net, tot


def score():
    rng = np.random.default_rng(7)
    G = load_games()
    Lu = pd.read_csv(os.path.join(W, "lineup.csv.gz"), dtype={"tag": str})
    G["m_B0"], G["t_B"] = b_model(G)
    T, dropped = test_games(G, Lu)
    yM = (T.hs - T.as_).to_numpy()
    yT = T.total.to_numpy()
    preds = {}
    # L, L_fit and B (normal forms; sds fitted on earlier seasons 2017..s-1)
    for name in ("L", "L_fit", "B"):
        mp, tp, pw = [], [], []
        for s in TEST:
            E = G[(G.season < s)]
            Z = T[T.season == s]
            if name == "B":
                hfa = float((E.hs - E.as_).mean() - E.m_B0.mean())
                m_E, m_Z = E.m_B0 + hfa, Z.m_B0 + hfa
                t_E, t_Z = E.t_B, Z.t_B
            else:
                m_E, m_Z, t_E, t_Z = E.m_L, Z.m_L, E.t_L, Z.t_L
            sd_t = float(np.nanstd(E.total - t_E))
            sd_m = S_EFF if name == "L" else float(np.nanstd((E.hs - E.as_) - m_E))
            mz = m_Z.to_numpy(float)
            mp.append(normal_margin_pmf(mz, np.full(len(Z), sd_m)))
            tp.append(normal_total_pmf(t_Z.to_numpy(float), np.full(len(Z), sd_t)))
            pw.append(norm.cdf(mz / sd_m))
        preds[name] = dict(mpmf=np.vstack(mp), tpmf=np.vstack(tp), pwin=np.concatenate(pw))
    sims = {}
    for m in ("G0", "G1", "G1s", "G1_6h"):
        parts = []
        for s in TEST:
            p = os.path.join(W, f"sim_{m}_{s}.npz")
            if not os.path.exists(p):
                parts = None
                break
            z = dict(np.load(p))
            parts.append(z)
        if parts is None:
            continue
        z = {k: np.concatenate([p_[k] for p_ in parts]) for k in parts[0]}
        order = pd.Series(np.arange(len(z["gid"])), index=z["gid"]).reindex(T.gid).to_numpy()
        z = {k: v[order] for k, v in z.items()}
        preds[m] = dict(mpmf=z["mpmf"], tpmf=z["tpmf"], pwin=np.clip(z["pwin"], 1e-4, 1 - 1e-4))
        sims[m] = z
        sims[m]["info"] = [json.load(open(os.path.join(W, f"sim_{m}_{s}.json"))) for s in TEST]
    yW = (yM > 0).astype(float)
    S = {}
    for k, P in preds.items():
        pwin = np.clip(P["pwin"], 1e-4, 1 - 1e-4)
        S[k] = pd.DataFrame(dict(
            rps_m=rps(P["mpmf"], MG, yM, -50, 50), rps_t=rps(P["tpmf"], TT, yT, 160, 300),
            rps_m_full=rps(P["mpmf"], MG, yM, -90, 90), rps_t_full=rps(P["tpmf"], TT, yT, 100, 360),
            ll=-(yW * np.log(pwin) + (1 - yW) * np.log(1 - pwin)),
            pit_m=pit(P["mpmf"], MG, yM, rng), pit_t=pit(P["tpmf"], TT, yT, rng),
            ae_m=np.abs(median_of(P["mpmf"], MG) - yM), ae_t=np.abs(median_of(P["tpmf"], TT) - yT), pwin=pwin))
    wk = (T.season.astype(str) + "_" + T.date.dt.isocalendar().week.astype(str)).to_numpy()
    keys = np.unique(wk)
    idx = {k_: np.where(wk == k_)[0] for k_ in keys}
    brng = np.random.default_rng(2026)
    draws = [np.concatenate([idx[k_] for k_ in brng.choice(keys, len(keys))]) for _ in range(2000)]

    def boot(v):
        return np.array([v[d].mean() for d in draws])

    def summary(k):
        X = S[k]
        dec = lambda v: [round(float(x), 3) for x in np.histogram(v, bins=10, range=(0, 1))[0] / len(v)]
        lr = None
        try:
            from sklearn.linear_model import LogisticRegression
            lp = np.log(X.pwin / (1 - X.pwin)).to_numpy()[:, None]
            lr = float(LogisticRegression(C=1e6).fit(lp, yW).coef_[0, 0])
        except Exception:  # noqa: BLE001
            pass
        cov = {}
        for nm, P, y, sup in (("margin", preds[k]["mpmf"], yM, MG), ("total", preds[k]["tpmf"], yT, TT)):
            F = np.cumsum(P, 1)
            for c in (0.5, 0.8):
                lo_ = sup[(F < (1 - c) / 2).sum(1)]
                hi_ = sup[np.minimum((F < 1 - (1 - c) / 2).sum(1), len(sup) - 1)]
                cov[f"{nm}_{int(c*100)}"] = round(float(((y >= lo_) & (y <= hi_)).mean()), 3)
        return dict(rps_margin=round(float(X.rps_m.mean()), 5), rps_total=round(float(X.rps_t.mean()), 5),
                    rps_margin_unclipped=round(float(X.rps_m_full.mean()), 5), rps_total_unclipped=round(float(X.rps_t_full.mean()), 5),
                    win_logloss=round(float(X.ll.mean()), 5), win_calibration_slope=round(lr, 3) if lr else None,
                    pit_margin_deciles=dec(X.pit_m), pit_total_deciles=dec(X.pit_t), interval_coverage=cov,
                    median_abs_err_margin=round(float(X.ae_m.mean()), 2), p99_abs_err_margin=round(float(np.percentile(X.ae_m, 99)), 1),
                    median_abs_err_total=round(float(X.ae_t.mean()), 2), p99_abs_err_total=round(float(np.percentile(X.ae_t, 99)), 1),
                    by_season={int(s): dict(rps_margin=round(float(X.rps_m[(T.season == s).to_numpy()].mean()), 5),
                                            rps_total=round(float(X.rps_t[(T.season == s).to_numpy()].mean()), 5),
                                            win_logloss=round(float(X.ll[(T.season == s).to_numpy()].mean()), 5)) for s in TEST})
    res = {"test_games": int(len(T)), "dropped_no_lineup": dropped, "games_by_season": T.groupby("season").size().to_dict(),
           "outside_rps_range": {"margin_outside_-50..50": int((np.abs(yM) > 50).sum()), "total_outside_160..300": int(((yT < 160) | (yT > 300)).sum())},
           "models": {k: summary(k) for k in S}}
    # realism (gate A)
    act = dict(sd_total=float(np.std(yT)), sd_margin=float(np.std(yM)), corr=float(np.corrcoef(T.hs, T.as_)[0, 1]),
               close=float((np.abs(yM) <= 3).mean()), ot=float(T.ot.mean()))
    res["actual"] = {k: round(v, 4) for k, v in act.items()}
    gates = {}
    for m, z in sims.items():
        mh, ma, vh, va, cv = z["mh"], z["ma"], z["vh"], z["va"], z["cov"]
        sim = dict(sd_total=float(np.sqrt((vh + va + 2 * cv).mean() + np.var(mh + ma))),
                   sd_margin=float(np.sqrt((vh + va - 2 * cv).mean() + np.var(mh - ma))),
                   corr=float((cv.mean() + np.cov(mh, ma)[0, 1]) / np.sqrt((vh.mean() + np.var(mh)) * (va.mean() + np.var(ma)))),
                   close=float(z["pclose"].mean()), ot=float(z["pot"].mean()))
        pm, pt = S[m].pit_m.to_numpy(), S[m].pit_t.to_numpy()
        decm = np.histogram(pm, bins=10, range=(0, 1))[0] / len(pm)
        dect = np.histogram(pt, bins=10, range=(0, 1))[0] / len(pt)
        A = {"A1_sd_total": abs(sim["sd_total"] / act["sd_total"] - 1) <= 0.10,
             "A2_sd_margin": abs(sim["sd_margin"] / act["sd_margin"] - 1) <= 0.10,
             "A3_corr": abs(sim["corr"] - act["corr"]) <= 0.10,
             "A4_close": abs(sim["close"] - act["close"]) <= 0.02,
             "A5_ot": abs(sim["ot"] - act["ot"]) <= 0.015,
             "A6_pit": bool(((decm >= 0.08) & (decm <= 0.12)).all() and ((dect >= 0.08) & (dect <= 0.12)).all())}
        gates[m] = {"simulated": {k: round(v, 4) for k, v in sim.items()}, "A": {k: bool(v) for k, v in A.items()}, "A_pass": bool(all(A.values())),
                    "sim_info": z["info"]}
        # gate B vs L
        gt = (S["L"].rps_t - S[m].rps_t).to_numpy()
        gm = (S["L"].rps_m - S[m].rps_m).to_numpy()
        gl = (S["L"].ll - S[m].ll).to_numpy()
        bt, bm, bl = boot(gt), boot(gm), boot(gl)
        seasons_better = int(sum(S[m].rps_t[(T.season == s).to_numpy()].mean() < S["L"].rps_t[(T.season == s).to_numpy()].mean() for s in TEST))
        Bg = {"B1_total_gain": round(float(gt.mean()), 6), "B1_total_gain_90pct_lower": round(float(np.percentile(bt, 10)), 6),
              "B1": bool(np.percentile(bt, 10) > 0), "B2_seasons_total_better": seasons_better, "B2": seasons_better >= 4,
              "B3_margin_rel_change": round(float(S[m].rps_m.mean() / S["L"].rps_m.mean() - 1), 5),
              "B3": bool(S[m].rps_m.mean() / S["L"].rps_m.mean() - 1 <= 0.005),
              "B3_reported_90pct_bound_on_deterioration": round(float(-np.percentile(bm, 10) / S["L"].rps_m.mean()), 5),
              "B4_logloss_change": round(float(S[m].ll.mean() - S["L"].ll.mean()), 5), "B4": bool(S[m].ll.mean() - S["L"].ll.mean() <= 0.002),
              "B4_reported_90pct_bound_on_deterioration": round(float(-np.percentile(bl, 10)), 5)}
        gates[m]["B"] = Bg
        gates[m]["B_pass"] = bool(Bg["B1"] and Bg["B2"] and Bg["B3"] and Bg["B4"])
    if "G1" in S and "G0" in S:
        gm = (S["G0"].rps_m - S["G1"].rps_m).to_numpy()
        gt = (S["G0"].rps_t - S["G1"].rps_t).to_numpy()
        gl = (S["G0"].ll - S["G1"].ll).to_numpy()
        bm, bt, bl = boot(gm), boot(gt), boot(gl)
        C = {"margin_gain": round(float(gm.mean()), 6), "margin_gain_95pct_lower": round(float(np.percentile(bm, 5)), 6),
             "total_gain": round(float(gt.mean()), 6), "total_gain_95pct_lower": round(float(np.percentile(bt, 5)), 6),
             "C1": bool(np.percentile(bm, 5) > 0 or np.percentile(bt, 5) > 0),
             "C2": bool(gm.mean() >= 0 and gt.mean() >= 0),
             "logloss_gain": round(float(gl.mean()), 6), "C3": bool(gl.mean() >= 0),
             "reported_90pct_bounds": {"margin": round(float(np.percentile(bm, 10)), 6), "total": round(float(np.percentile(bt, 10)), 6),
                                       "logloss": round(float(np.percentile(bl, 10)), 6)},
             "by_season": {int(s): dict(margin=round(float(gm[(T.season == s).to_numpy()].mean()), 6), total=round(float(gt[(T.season == s).to_numpy()].mean()), 6)) for s in TEST}}
        C["C_pass"] = bool(C["C1"] and C["C2"] and C["C3"])
        gates["G1_vs_G0"] = C
        g1 = gates["G1"]["A_pass"] and gates["G1"]["B_pass"] and C["C_pass"]
        g0 = gates["G0"]["A_pass"] and gates["G0"]["B_pass"]
        res["decision_by_written_gates"] = "G1" if g1 else ("G0" if g0 else "neither: record and revise stage two under a new rule")
    res["gates"] = gates
    # reported splits
    D = pd.read_csv(os.path.join(ROOT, "data", "research", "nba_minutes_rows.csv.gz"), usecols=["season", "game_id", "team", "aid", "ewm", "st1", "gi", "fallback"], low_memory=False)
    D = D[D.fallback.fillna(0) == 0]
    out_rot = set(D[(D["ewm"] >= 25) & (D.st1 == "Out")].game_id)
    gi = D.groupby(["game_id", "team"]).gi.max()
    early = np.array([gi.get((g, h), 99) < 10 or gi.get((g, a), 99) < 10 for g, h, a in zip(T.gid, T.home, T.away)])
    splits = {"rotation_player_out": T.gid.isin(out_rot).to_numpy(), "team_games_1_10": early,
              "close_expected_|m|<5": (np.abs(T.m_L) < 5).to_numpy(), "lopsided_expected_|m|>=10": (np.abs(T.m_L) >= 10).to_numpy()}
    res["splits"] = {}
    for nm, msk in splits.items():
        for nm2, mm in ((nm, msk), ("not_" + nm, ~msk)):
            res["splits"][nm2] = {"games": int(mm.sum()), **{k: dict(rps_margin=round(float(S[k].rps_m[mm].mean()), 5), rps_total=round(float(S[k].rps_t[mm].mean()), 5))
                                                         for k in S if k in ("L", "G0", "G1", "G1s")}}
    # diagnostic: short-minutes tail vs final margin
    P = pd.read_csv(os.path.join(W, "proj_minutes.csv.gz"), dtype={"tag": str})
    P = P[(P.tag == "1") & P.season.isin(TEST)]
    Mr = pd.read_csv(os.path.join(ROOT, "data", "research", "nba_minutes_rows.csv.gz"), usecols=["game_id", "team", "aid", "minutes", "fallback"], low_memory=False)
    Mr = Mr[Mr.fallback.fillna(0) == 0]
    J = P.merge(Mr, left_on=["game_id", "team", "aid"], right_on=["game_id", "team", "aid"])
    J = J[(J.emin_app >= 24) & (J.minutes > 0)]
    fm = dict(zip(T.gid, np.abs(yM)))
    J["blowout"] = J.game_id.map(fm) >= 20
    J["short"] = J.minutes < J.emin_app - 12
    J = J.dropna(subset=["blowout"])
    res["diagnostic_short_minutes"] = {"definition": "appeared, expected 24+ minutes if appearing, played 12+ fewer",
                                       "rate_in_blowouts_final_margin_20plus": round(float(J[J.blowout].short.mean()), 4),
                                       "rate_other_games": round(float(J[~J.blowout].short.mean()), 4),
                                       "share_of_short_nights_in_blowouts": round(float(J[J.short].blowout.mean()), 4),
                                       "share_of_games_blowouts": round(float((np.abs(yM) >= 20).mean()), 4)}
    with open(os.path.join(HERE, "nba_game_env_results.json"), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({k: res[k] for k in ("test_games", "decision_by_written_gates") if k in res}, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "sim":
        run_sim(sys.argv[2], int(sys.argv[3]))
    else:
        {"ratings": ratings, "rapm": rapm, "minutes": minutes, "lineup": lineup, "score": lambda: score()}[sys.argv[1]]()
