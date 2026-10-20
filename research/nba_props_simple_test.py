"""NBA simple prop challenger per research/NBA_PROPS_SIMPLE_RULE.md (with amendments 1 and 2).
  python research/nba_props_simple_test.py build   -> <W>/props_rows.parquet (features for stage-one candidate player-games 2017-2026)
  python research/nba_props_simple_test.py score   -> research/nba_props_simple_results.json
W = GENV_DIR scratch (derived from ESPN data; private). Stage-one projected minutes come from <W>/proj_minutes.csv.gz
(research/nba_game_env_test.py minutes: frozen stage one for 2022-2026).
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.optimize import minimize_scalar

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba_minutes_test as M  # noqa: E402

W = os.environ.get("GENV_DIR", "/tmp/claude-0/-home-claude/05818a0d-0d82-5af8-8a3a-91e344d8290f/scratchpad/genv")
STATS = ["pts", "reb", "ast"]
SUP_CLIP = {"pts": 60, "reb": 25, "ast": 20}
SUP_FULL = {"pts": 100, "reb": 45, "ast": 35}
TEST = [2022, 2023, 2024, 2025, 2026]
HALF = 15.0
LAST_W = 0.5
M0_GRID = [0, 25, 50, 100, 200, 400, 800]
ROT_MIN = 12.0


# ---------------------------------------------------------------- build
def player_box():
    frames = []
    for y in range(2015, 2027):
        d = pd.read_csv(os.path.join(ROOT, "data", "nba", f"player_box_{y}.csv"), low_memory=False,
                        usecols=["game_id", "season", "season_type", "game_date_time", "athlete_id", "team_abbreviation", "opponent_team_abbreviation",
                                 "minutes", "points", "rebounds", "assists", "athlete_position_abbreviation"])
        frames.append(d[pd.to_numeric(d.season_type, errors="coerce") == 2])
    d = pd.concat(frames, ignore_index=True)
    for c in ("minutes", "points", "rebounds", "assists"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["athlete_id"] = pd.to_numeric(d.athlete_id, errors="coerce")
    d = d.dropna(subset=["athlete_id"])
    d["aid"] = d.athlete_id.astype(int)
    d["game_id"] = pd.to_numeric(d.game_id, errors="coerce").astype(int)
    d["season"] = pd.to_numeric(d.season, errors="coerce").astype(int)
    d["tip"] = pd.to_datetime(d.game_date_time, utc=True, errors="coerce", format="ISO8601")
    d = d.rename(columns={"points": "pts", "rebounds": "reb", "assists": "ast", "team_abbreviation": "team", "opponent_team_abbreviation": "opp"})
    d["grp"] = d.athlete_position_abbreviation.map(M.GROUP).fillna("W")
    return d


def game_poss():
    import nba as N
    import nba_backtest as B
    reg = N._regular_boxes(B.load_boxes(2026))
    return reg.groupby(reg.game_id.astype(int)).poss.first()


def build():
    pb = player_box()
    poss = game_poss()
    pb["poss"] = pb.game_id.map(poss)
    D = pd.read_csv(M.ROWS, low_memory=False)
    D["fallback"] = D.fallback.fillna(0)
    D = D[(D.aid != -1) & (D.season >= 2017)].copy()
    D["aid"] = D.aid.astype(int)
    D["tip"] = pd.to_datetime(D.tip, utc=True, format="ISO8601")
    for c in ("st1", "st6"):
        D[c] = D[c].fillna("")
    D["ewm"] = D["ewm"].fillna(0.0)
    # actual stats (0 if not appearing)
    act = pb.set_index(["game_id", "aid"])[["pts", "reb", "ast", "grp"]]
    act = act[~act.index.duplicated()]
    J = act.reindex(pd.MultiIndex.from_arrays([D.game_id, D.aid]))
    for s in STATS:
        D[s] = J[s].fillna(0.0).to_numpy()
    grp_last = pb.sort_values("tip").groupby("aid").grp.last()
    D["grp"] = D["grp"].where(D["grp"].notna(), D.aid.map(grp_last)).fillna("W") if "grp" in D else D.aid.map(grp_last).fillna("W")
    # projected minutes (stage one) at 1h and 6h
    P = pd.read_csv(os.path.join(W, "proj_minutes.csv.gz"), dtype={"tag": str})
    for tag in ("1", "6"):
        Q = P[P.tag == tag].drop_duplicates(["game_id", "team", "aid"]).set_index(["game_id", "team", "aid"])[["pa", "mu", "sd", "emin_app"]]
        Jq = Q.reindex(pd.MultiIndex.from_arrays([D.game_id, D.team, D.aid]))
        for c in ("pa", "mu", "sd", "emin_app"):
            D[f"{c}{tag}"] = Jq[c].to_numpy()
    D = D.dropna(subset=["pa1", "pa6"]).reset_index(drop=True)
    # opponent and expected pace from the stage-two game table
    G = pd.read_csv(os.path.join(W, "games.csv.gz")).drop_duplicates("gid")
    G["pace"] = (G.pace_h + G.pace_a) / 2
    gh = dict(zip(G.gid, G.home))
    ga = dict(zip(G.gid, G.away))
    D["opp"] = [ga[g] if gh.get(g) == t else gh.get(g) for g, t in zip(D.game_id, D.team)]
    D["pace_exp"] = D.game_id.map(dict(zip(G.gid, G.pace)))
    D = D.dropna(subset=["opp", "pace_exp"]).reset_index(drop=True)

    # ---- unshrunk recency-weighted per-minute rates (for teammate shares) and team-game missing shares
    hist = history(pb)
    D = D.merge(hist, on=["game_id", "aid"], how="left")
    dup = D.columns[D.columns.duplicated()].tolist()
    if dup:
        print("duplicate columns", dup)
        D = D.loc[:, ~D.columns.duplicated()]
    grp_rate = {s: pb[pb.minutes > 0].groupby("grp")[s].sum() / pb[pb.minutes > 0].groupby("grp").minutes.sum() for s in STATS}
    for s in STATS:
        raw = np.where(D.h_M > 0, D[f"h_{s}"] / D.h_M.where(D.h_M > 0, 1), D.grp.map(grp_rate[s]))
        D[f"share_{s}"] = np.where(D["ewm"] >= ROT_MIN, raw * D["ewm"], 0.0)
    tg = D.groupby(["game_id", "team"])
    for s in STATS:
        tot = tg[f"share_{s}"].transform("sum").replace(0, np.nan)
        app = (D.minutes > 0).astype(float)
        D[f"miss_act_{s}"] = (tg[f"share_{s}"].transform(lambda x: x) * 0)  # placeholder
        miss = (D[f"share_{s}"] * (1 - app)).groupby([D.game_id, D.team]).transform("sum")
        D[f"miss_act_{s}"] = (miss / tot).fillna(0.0)
        for tag in ("1", "6"):
            expmiss = (D[f"share_{s}"] * (1 - D[f"pa{tag}"])).groupby([D.game_id, D.team]).transform("sum")
            own = D[f"share_{s}"] * (1 - D[f"pa{tag}"])
            D[f"V_now{tag}_{s}"] = ((expmiss - own) / tot).fillna(0.0)
    # reflected missing share: weighted over the player's history games (computed in a second pass using team-game actual shares)
    tgm = D.groupby(["game_id", "team"])[[f"miss_act_{s}" for s in STATS]].first()
    pb2 = pb.join(tgm, on=["game_id", "team"])
    for s in STATS:
        pb2[f"miss_act_{s}"] = pb2[f"miss_act_{s}"].fillna(0.0)
    hist2 = history(pb2, extra=[f"miss_act_{s}" for s in STATS])
    D = D.merge(hist2[["game_id", "aid"] + [f"h_miss_act_{s}" for s in STATS]], on=["game_id", "aid"], how="left")
    for s in STATS:
        D[f"V_ref_{s}"] = np.where(D.h_M > 0, D[f"h_miss_act_{s}"] / D.h_M.where(D.h_M > 0, 1), 0.0)
    # opponent factor per stat (season-to-date allowed per 100 possessions vs league; shrunk with last season, prior 10 games)
    D = D.merge(opponent_factors(pb), on=["game_id", "opp"], how="left")
    for s in STATS:
        D[f"opp_{s}"] = D[f"opp_{s}"].fillna(1.0)
    D.to_parquet(os.path.join(W, "props_rows.parquet"), index=False)
    print("rows", len(D), D.groupby("season").size().to_dict())


def history(pb, extra=()):
    """for each (game, player) in the box (and as of any later target), weighted sums over his prior appearances this season (w 1) and
    last season (w 0.5), half-life 15 games played. Returns rows keyed by the TARGET (game_id, aid) for every game of the player's teams'
    schedule he could be a candidate in: computed for each game in which the player appears in the box (played or not) and joined later."""
    pb = pb.sort_values(["aid", "tip"])
    cols = ["minutes", "pts", "reb", "ast", "pm_pace"] + list(extra)
    pb = pb.assign(pm_pace=pb.minutes * pb.poss.fillna(100.0))
    for c in extra:
        pb[c] = pb[c] * pb.minutes          # minutes-weighted, like the rates
    # targets: every candidate (game, aid) from stage-one rows
    D = pd.read_csv(M.ROWS, low_memory=False, usecols=["game_id", "aid", "season", "tip"])
    D = D[(D.aid != -1) & (D.season >= 2017)].copy()
    D["aid"] = D.aid.astype(int)
    D["tip"] = pd.to_datetime(D.tip, utc=True, format="ISO8601")
    out = []
    played = pb[pb.minutes > 0]
    groups = {a: g for a, g in played.groupby("aid")}
    for a, T in D.sort_values("tip").groupby("aid"):
        g = groups.get(a)
        if g is None:
            out.append(pd.DataFrame({"game_id": T.game_id.to_numpy(), "aid": a, "h_minutes": 0.0}))
            continue
        tips = g.tip.to_numpy()
        seas = g.season.to_numpy()
        V = g[cols].to_numpy(float)
        res = np.zeros((len(T), len(cols) + 7))
        # this-season-only aggregates for B1/B2/B3: count, sum minutes, sums of stats; last-10 sums
        for i, (tt, sy) in enumerate(zip(T.tip.to_numpy(), T.season.to_numpy())):
            j = np.searchsorted(tips, tt)
            if j == 0:
                continue
            lo = np.searchsorted(seas[:j], sy - 1)            # seasons are sorted with time
            idx = np.arange(lo, j)
            idx = idx[seas[idx] >= sy - 1]
            if not len(idx):
                continue
            age = (j - 1 - idx).astype(float)
            w = 0.5 ** (age / HALF) * np.where(seas[idx] == sy, 1.0, LAST_W)
            res[i, :len(cols)] = (w[:, None] * V[idx]).sum(0)
            cur = idx[seas[idx] == sy]
            prv = idx[seas[idx] == sy - 1]
            res[i, len(cols)] = len(cur)
            res[i, len(cols) + 1] = V[cur, 0].sum() if len(cur) else 0.0
            for k, c in enumerate(("pts", "reb", "ast")):
                ci = cols.index(c)
                res[i, len(cols) + 2 + k] = V[cur, ci].sum() if len(cur) else 0.0
            res[i, len(cols) + 5] = len(prv)
            res[i, len(cols) + 6] = V[prv, 0].sum() if len(prv) else 0.0
        f = pd.DataFrame(res, columns=[f"h_{c}" for c in cols] + ["n_cur", "min_cur", "pts_cur", "reb_cur", "ast_cur", "n_prv", "min_prv"])
        f["game_id"] = T.game_id.to_numpy()
        f["aid"] = a
        # last-season stat sums and last-10 (this season) sums
        l10 = np.zeros((len(T), 4))
        prev_sums = np.zeros((len(T), 3))
        for i, (tt, sy) in enumerate(zip(T.tip.to_numpy(), T.season.to_numpy())):
            j = np.searchsorted(tips, tt)
            cur = np.nonzero((seas[:j] == sy))[0][-10:]
            if len(cur):
                l10[i] = [len(cur), V[cur, 1].sum(), V[cur, 2].sum(), V[cur, 3].sum()]
            prv = np.nonzero(seas[:j] == sy - 1)[0]
            if len(prv):
                prev_sums[i] = V[prv, 1:4].sum(0)
        f[["n_l10", "pts_l10", "reb_l10", "ast_l10"]] = l10
        f[["pts_prv", "reb_prv", "ast_prv"]] = prev_sums
        out.append(f)
    H = pd.concat(out, ignore_index=True).fillna(0.0)
    H = H.rename(columns={"h_minutes": "h_M"}).drop_duplicates(["game_id", "aid"])
    return H


def opponent_factors(pb):
    tg = pb.groupby(["game_id", "season", "team", "opp"]).agg(pts=("pts", "sum"), reb=("reb", "sum"), ast=("ast", "sum"),
                                                                 poss=("poss", "first"), tip=("tip", "min")).reset_index().dropna(subset=["poss"])
    tg = tg.sort_values("tip")
    rows = []
    full = {}
    for y, S in tg.groupby("season"):
        lg = {s: S[s].sum() / S.poss.sum() for s in STATS}
        for t, X in S.groupby("opp"):   # X: what team t allowed (opponents' production against t)
            full[(y, t)] = {s: (X[s].sum() / X.poss.sum()) / lg[s] for s in STATS}
    for y, S in tg.groupby("season"):
        S = S.sort_values("tip")
        cum_lg = {s: S[s].cumsum().shift().to_numpy() for s in STATS}
        cum_lp = S.poss.cumsum().shift().to_numpy()
        lg_prev = {s: tg[tg.season == y - 1][s].sum() / max(1, tg[tg.season == y - 1].poss.sum()) for s in STATS}
        by_def = {}
        for k, (gid, team, opp) in enumerate(zip(S.game_id, S.team, S.opp)):
            # the defending team is opp; the factor for players of `team` facing `opp`
            st = by_def.setdefault(opp, {"n": 0, "poss": 0.0, **{s: 0.0 for s in STATS}})
            r = {"game_id": gid, "opp": opp}
            for s in STATS:
                lg = (cum_lg[s][k] / cum_lp[k]) if k > 0 and cum_lp[k] > 0 else lg_prev[s]
                raw = (st[s] / st["poss"]) / lg if st["poss"] > 0 and lg > 0 else 1.0
                last = full.get((y - 1, opp), {}).get(s, 1.0)
                n = st["n"]
                r[f"opp_{s}"] = (n * raw + 10 * last) / (n + 10)
            rows.append(r)
        # update after computing all rows of a game date would be stricter; rows are processed in tip order, so a game's own
        # totals are added only after its own row has been computed
            st["n"] += 1
            st["poss"] += S.poss.iloc[k]
            for s in STATS:
                st[s] += S[s].iloc[k]
    return pd.DataFrame(rows).drop_duplicates(["game_id", "opp"])


# ---------------------------------------------------------------- distributions
def nb_logpmf(k, mu, r):
    mu = np.maximum(mu, 1e-6)
    return gammaln(k + r) - gammaln(r) - gammaln(k + 1) + r * np.log(r / (r + mu)) + k * np.log(mu / (r + mu))


def fit_r(y, mu):
    f = lambda lr: -nb_logpmf(y, mu, np.exp(lr)).sum()
    o = minimize_scalar(f, bounds=(-3, 8), method="bounded")
    return float(np.exp(o.x)), -float(o.fun)


def q_minutes(mu, sd):
    return M.disc_normal(np.asarray(mu, float), np.asarray(sd, float))


def mixture_pmf(rate, q, r, K):
    """P(k | appear) = sum_m q(m) NB(k; rate m, r), k = 0..K (last bin collects the tail)."""
    m = np.arange(1, M.MAXM + 1, dtype=float)
    k = np.arange(K + 1, dtype=float)
    mu = rate[:, None] * m[None, :]                                                     # n x 53
    lp = nb_logpmf(k[None, None, :], mu[:, :, None], r)                                 # n x 53 x K+1
    P = np.einsum("nm,nmk->nk", q, np.exp(lp))
    P[:, -1] += np.clip(1 - P.sum(1), 0, None)
    return P


def nb_pmf(mean, r, K):
    k = np.arange(K + 1, dtype=float)
    P = np.exp(nb_logpmf(k[None, :], mean[:, None], r))
    P[:, -1] += np.clip(1 - P.sum(1), 0, None)
    return P


def rps_rows(P, y, K):
    """mean over thresholds 0..K-1 of (F(k) - 1[y <= k])^2 (outcome clipped to K)."""
    F = np.cumsum(P[:, :K + 1], 1)[:, :K]
    yc = np.clip(y, 0, K)
    I = (yc[:, None] <= np.arange(K)[None, :]).astype(float)
    return ((F - I) ** 2).mean(1)


# ---------------------------------------------------------------- scoring
def rates(D, s, m0, grp_rate):
    g = D.grp.map(grp_rate[s]).to_numpy()
    return (D[f"h_{s}"].to_numpy() + m0 * g) / (D.h_M.to_numpy() + m0) if m0 > 0 else np.where(D.h_M > 0, D[f"h_{s}"] / D.h_M.where(D.h_M > 0, 1), g)


def base_means(D, s, grp_rate, grp_pg):
    n, mc = D.n_cur.to_numpy(), D.min_cur.to_numpy()
    prev_avg = np.where(D.n_prv > 0, D[f"{s}_prv"] / D.n_prv.where(D.n_prv > 0, 1), np.nan)
    gpg = D.grp.map(grp_pg[s]).to_numpy()
    b1 = np.where(n > 0, D[f"{s}_cur"] / np.maximum(n, 1), np.where(np.isnan(prev_avg), gpg, prev_avg))
    b2 = np.where(D.n_l10 > 0, D[f"{s}_l10"] / D.n_l10.where(D.n_l10 > 0, 1), b1)
    prev_rate = np.where(D.min_prv > 0, D[f"{s}_prv"] / D.min_prv.where(D.min_prv > 0, 1), np.nan)
    grate = D.grp.map(grp_rate[s]).to_numpy()
    r3 = np.where(mc > 0, D[f"{s}_cur"] / np.maximum(mc, 1e-9), np.where(np.isnan(prev_rate), grate, prev_rate))
    return np.maximum(b1, 0.01), np.maximum(b2, 0.01), np.maximum(r3, 1e-4)


def adjust(D, s, rate, b=0.0, c=None, tag="1"):
    out = rate.copy()
    if b:
        V = D[f"V_now{tag}_{s}"].to_numpy() - D[f"V_ref_{s}"].to_numpy()
        out = out * np.clip(1 + b * V, 0.2, 3.0)
    if c is not None:
        ph = np.where(D.h_M > 0, D.h_pm_pace / D.h_M.where(D.h_M > 0, 1), D.pace_exp)
        out = out * D[f"opp_{s}"].to_numpy() ** c * (D.pace_exp.to_numpy() / ph)
    return out


def score():
    D = pd.read_parquet(os.path.join(W, "props_rows.parquet"))
    D = D[D.fallback == 0].reset_index(drop=True)
    D["app"] = (D.minutes > 0)
    D["min_clip"] = np.clip(np.round(D.minutes), 1, M.MAXM)
    wk = (D.season.astype(str) + "_" + D.tip.dt.isocalendar().week.astype(str)).to_numpy()
    rng = np.random.default_rng(11)
    res = {"rows_by_season": D[D.season.isin(TEST)].groupby("season").size().to_dict(), "fits": {}, "stats": {}}
    scores = {}     # (tag, stat, model) -> DataFrame of per-row scores for test rows
    for s_ in TEST:
        F = D[(D.season < s_) & D.app]
        Z = D[D.season == s_]
        grp_rate = {s: F.groupby("grp")[s].sum() / F.groupby("grp").minutes.sum() for s in STATS}
        grp_pg = {s: F.groupby("grp")[s].mean() for s in STATS}
        fits = {}
        for s in STATS:
            y = F[s].to_numpy()
            mins = F.minutes.to_numpy()
            # m0 by maximum likelihood (dispersion refitted per m0)
            best = None
            for m0 in M0_GRID:
                r_, ll = fit_r(y, rates(F, s, m0, grp_rate) * mins)
                if best is None or ll > best[2]:
                    best = (m0, r_, ll)
            m0, rP, _ = best
            rateF = rates(F, s, m0, grp_rate)
            # adjustments (grids, dispersion refitted at the chosen value)
            bb = max(np.arange(0, 1.0001, 0.05), key=lambda b: nb_logpmf(y, adjust(F, s, rateF, b=b) * mins, rP).sum())
            rT, _ = fit_r(y, adjust(F, s, rateF, b=bb) * mins)
            cc = max(np.arange(0, 1.0001, 0.05), key=lambda c: nb_logpmf(y, adjust(F, s, rateF, c=c) * mins, rP).sum())
            rO, _ = fit_r(y, adjust(F, s, rateF, c=cc) * mins)
            rTO, _ = fit_r(y, adjust(F, s, rateF, b=bb, c=cc) * mins)
            b1, b2, r3 = base_means(F, s, grp_rate, grp_pg)
            r1, _ = fit_r(y, b1)
            r2, _ = fit_r(y, b2)
            r3e, _ = fit_r(y, r3 * F.emin_app1.to_numpy())
            r3m, _ = fit_r(y, r3 * mins)
            fits[s] = dict(m0=m0, r_P=rP, b=float(bb), r_T=rT, c=float(cc), r_O=rO, r_TO=rTO, r_B1=r1, r_B2=r2, r_B3=r3e, r_B3m=r3m)
            for tag in ("1", "6"):
                pa = np.clip(Z[f"pa{tag}"].to_numpy(), 1e-3, 1 - 1e-3)
                q = q_minutes(Z[f"mu{tag}"], Z[f"sd{tag}"])
                rateZ = rates(Z, s, m0, grp_rate)
                b1z, b2z, r3z = base_means(Z, s, grp_rate, grp_pg)
                K = SUP_FULL[s]
                models = {"P": ("mix", rateZ, rP), "P+T": ("mix", adjust(Z, s, rateZ, b=bb, tag=tag), rT),
                          "P+O": ("mix", adjust(Z, s, rateZ, c=cc), rO), "P+T+O": ("mix", adjust(Z, s, rateZ, b=bb, c=cc, tag=tag), rTO),
                          "B1": ("nb", b1z, r1), "B2": ("nb", b2z, r2), "B3": ("nb", r3z * Z[f"emin_app{tag}"].to_numpy(), r3e),
                          "B3m": ("mix", r3z, r3m)}
                yv = Z[s].to_numpy()
                app = Z.app.to_numpy()
                for name, (kind, par, r_) in models.items():
                    out = []
                    for b0 in range(0, len(Z), 3000):
                        sl = slice(b0, b0 + 3000)
                        cond = mixture_pmf(par[sl], q[sl], r_, K) if kind == "mix" else nb_pmf(par[sl], r_, K)
                        unc = pa[sl, None] * cond
                        unc[:, 0] += 1 - pa[sl]
                        yy = yv[sl]
                        Fc = np.cumsum(cond, 1)
                        yi = np.clip(yy, 0, K).astype(int)
                        hi = Fc[np.arange(len(yi)), yi]
                        lo = np.where(yi > 0, Fc[np.arange(len(yi)), np.maximum(yi - 1, 0)], 0.0)
                        pit = lo + rng.random(len(yi)) * (hi - lo)
                        Fu = np.cumsum(unc, 1)
                        cov = {}
                        for cl in (0.5, 0.8):
                            lo_ = (Fc < (1 - cl) / 2).sum(1)
                            hi_ = (Fc < 1 - (1 - cl) / 2).sum(1)
                            cov[cl] = (yy >= lo_) & (yy <= hi_)
                        line = np.floor(b1z[sl]) + 0.5
                        li = np.floor(line).astype(int)
                        p_over_c = 1 - Fc[np.arange(len(li)), np.clip(li, 0, K)]
                        p_short = q[sl][:, :14].sum(1)          # P(minutes < 15 | appear)
                        out.append(pd.DataFrame(dict(
                            idx=Z.index[sl], rps_u=rps_rows(unc, yy, SUP_CLIP[s]), rps_u_full=rps_rows(unc, yy, K),
                            rps_c=rps_rows(cond, yy, SUP_CLIP[s]), rps_c_full=rps_rows(cond, yy, K), pit=pit, cov50=cov[0.5], cov80=cov[0.8],
                            line=line, p_over=p_over_c, over=(yy > line), p_short=p_short)))
                    S = pd.concat(out).set_index("idx")
                    S["app"] = app
                    scores.setdefault((tag, s, name), []).append(S)
        res["fits"][int(s_)] = {s: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()} for s, f in fits.items()}
        print("season", s_, flush=True)
    T = D[D.season.isin(TEST)]
    keys = np.unique(wk[T.index])
    widx = {k: np.where(wk[T.index] == k)[0] for k in keys}
    brng = np.random.default_rng(2026)
    draws = [np.concatenate([widx[k] for k in brng.choice(keys, len(keys))]) for _ in range(2000)]
    boot = lambda v: np.array([v[d].mean() for d in draws])
    S = {k: pd.concat(v).loc[T.index] for k, v in scores.items()}
    seasons = T.season.to_numpy()
    for tag in ("1", "6"):
        for s in STATS:
            R = {}
            for name in ("P", "P+T", "P+O", "P+T+O", "B1", "B2", "B3", "B3m"):
                X = S[(tag, s, name)]
                a = X.app.to_numpy()
                dec = np.histogram(X.pit[a], bins=10, range=(0, 1))[0] / a.sum()
                R[name] = dict(rps_uncond=round(float(X.rps_u.mean()), 6), rps_uncond_unclipped=round(float(X.rps_u_full.mean()), 6),
                               rps_given_appearing=round(float(X.rps_c[a].mean()), 6), rps_given_appearing_unclipped=round(float(X.rps_c_full[a].mean()), 6),
                               pit_deciles_given_appearing=[round(float(v), 3) for v in dec],
                               coverage_50=round(float(X.cov50[a].mean()), 3), coverage_80=round(float(X.cov80[a].mean()), 3),
                               by_season={int(y): round(float(X.rps_u[seasons == y].mean()), 6) for y in TEST})
            gates = {}
            P = S[(tag, s, "P")]
            for bname in ("B1", "B2", "B3", "B3m"):
                Bx = S[(tag, s, bname)]
                gain = (Bx.rps_u - P.rps_u).to_numpy()
                bs = boot(gain)
                sb = int(sum(P.rps_u[seasons == y].mean() < Bx.rps_u[seasons == y].mean() for y in TEST))
                a = P.app.to_numpy()
                gates[bname] = dict(gain=round(float(gain.mean()), 6), lower90=round(float(np.percentile(bs, 10)), 6), g1=bool(np.percentile(bs, 10) > 0),
                                    seasons_better=sb, g2=sb >= 4, cond_gain=round(float((Bx.rps_c[a] - P.rps_c[a]).mean()), 6),
                                    g4=bool((Bx.rps_c[a] - P.rps_c[a]).mean() > 0))
            decP = R["P"]["pit_deciles_given_appearing"]
            g3 = all(0.07 <= v <= 0.13 for v in decP)
            passP = all(g["g1"] and g["g2"] and g["g4"] for g in gates.values()) and g3
            adj = {}
            for an in ("P+T", "P+O"):
                Ax = S[(tag, s, an)]
                gain = (P.rps_u - Ax.rps_u).to_numpy()
                bs = boot(gain)
                adj[an] = dict(gain=round(float(gain.mean()), 6), lower_98_33=round(float(np.percentile(bs, 100 / 60)), 6),
                               passes=bool(np.percentile(bs, 100 / 60) > 0))
            comb = S[(tag, s, "P+T+O")]
            adj["P+T+O (reported)"] = dict(gain=round(float((P.rps_u - comb.rps_u).mean()), 6))
            kept = [a for a in ("P+T", "P+O") if adj[a]["passes"]]
            if len(kept) == 2:
                kept = [max(kept, key=lambda a: adj[a]["gain"])]
            # B3m vs B3: value of the minutes distribution (reported)
            mins_value = round(float((S[(tag, s, "B3")].rps_u - S[(tag, s, "B3m")].rps_u).mean()), 6)
            # over / under calibration at formula lines (P, given appearing)
            X = P[P.app]
            ou = {}
            for side in ("over", "under"):
                p = X.p_over.to_numpy() if side == "over" else 1 - X.p_over.to_numpy()
                o = X.over.to_numpy() if side == "over" else ~X.over.to_numpy()
                bins = np.clip((p * 10).astype(int), 0, 9)
                ou[side] = [dict(decile=int(b), n=int((bins == b).sum()), mean_p=round(float(p[bins == b].mean()), 3), freq=round(float(o[bins == b].mean()), 3))
                            for b in range(10) if (bins == b).sum() >= 50]
                ou[side + "_overall"] = dict(mean_p=round(float(p.mean()), 4), freq=round(float(o.mean()), 4))
            lr = X[X.p_short >= 0.2]
            ou["over_low_minute_risk (P(min<15|appear)>=0.2)"] = dict(n=int(len(lr)), mean_p=round(float(lr.p_over.mean()), 4), freq=round(float(lr.over.mean()), 4))
            st = T.start10.to_numpy() >= 0.5 if "start10" in T else np.zeros(len(T), bool)
            split = {}
            for nm, msk in (("starters", st), ("bench", ~st)):
                split[nm] = {m: round(float(S[(tag, s, m)].rps_u[msk].mean()), 6) for m in ("P", "B1", "B2", "B3", "B3m")}
            res["stats"].setdefault(f"tag{tag}", {})[s] = dict(models=R, gates_vs_baselines=gates, g3_calibration=g3, P_passes=passP,
                                                              adjustments=adj, adjustments_kept=kept, minutes_distribution_value_B3_minus_B3m=mins_value,
                                                              over_under=ou, splits=split)
    with open(os.path.join(HERE, "nba_props_simple_results.json"), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    for s in STATS:
        r = res["stats"]["tag1"][s]
        print(s, "P passes:", r["P_passes"], {b: (g["gain"], g["lower90"], g["seasons_better"], g["g4"]) for b, g in r["gates_vs_baselines"].items()},
              "pit ok", r["g3_calibration"], "adj", r["adjustments"], "kept", r["adjustments_kept"])


if __name__ == "__main__":
    {"build": build, "score": score}[sys.argv[1]]()
