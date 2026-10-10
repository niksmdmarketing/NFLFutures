"""NHL team futures: chances for the Stanley Cup, conference, division, the playoffs, the best record, and season point totals.

How it works
  1. Rating = goal difference per game vs league average. The pre-season rating is a regression on last season's goal
     difference, last season's expected-goals difference (MoneyPuck) and the season before, fitted on every season since 2010-11.
  2. In season, the rating is (games x current rate + k x prior) / (games + k), with k fitted on how well the first 20 and 41
     games predict the rest of the season (2012-2025). Current rate blends goals with xG (xG share is a judgment call, not fitted).
  3. The rest of the schedule is simulated thousands of times. Each simulation first perturbs every rating by the amount the
     back-test says ratings are typically off by, so futures are not over-confident.
  4. Playoffs follow the real format (3 per division + 2 wild cards, division brackets, best-of-7 with 2-2-1-1-1 home ice).
Back-test: the same model is run from the start of 2021-22 .. 2025-26 and after 20 games, and scored against simple baselines.
Not in the model: roster changes, injuries, goalie moves, trade-deadline additions.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd
from scipy.special import ndtr

import nhl
from common import log

ALIGN = {t: d for d, ts in nhl.DIVS.items() for t in ts}
ALIGN["ARI"] = "Central"                      # Utah took Arizona's slot
CONF_OF = nhl.CONF
GAME_SD = 2.4                                  # sd of one game's goal margin
SEASON_GAMES = 82
SIMS = int(os.environ.get("NHL_SIMS", 20000))
CHUNK = 2000


# ---------------------------------------------------------------- data

def read_team(y):
    p = os.path.join(nhl.NHL_OUT, f"team_{y}.json")
    if not os.path.exists(p):
        return pd.DataFrame()
    d = json.load(open(p))
    return pd.DataFrame(d["rows"], columns=["team", "name"] + [c["k"] for c in d["cols"]]).set_index("team")


def read_games(y):
    p = os.path.join(nhl.NHL_OUT, f"games_{y}.json")
    if not os.path.exists(p):
        return pd.DataFrame()
    d = json.load(open(p))
    return pd.DataFrame(d["rows"], columns=["date", "team", "opp", "ha", "res"] + [c["k"] for c in d["cols"]])


def numcol(d, c, default=0.0):
    return pd.to_numeric(d[c], errors="coerce").fillna(default) if c in d else pd.Series(default, index=d.index)


def season_rates(T):
    """Per-team goal-difference and xG-difference per game for one season table."""
    gp = numcol(T, "gamesPlayed").replace(0, np.nan)
    gd = (numcol(T, "goalsFor") - numcol(T, "goalsAgainst")) / gp
    if "mp_xGoalsFor" in T:
        xgd = (numcol(T, "mp_xGoalsFor") - numcol(T, "mp_xGoalsAgainst")) / gp
        xgd = xgd.where(numcol(T, "mp_xGoalsFor") > 0, gd)
    else:
        xgd = gd.copy()
    return gd - gd.mean(), xgd - xgd.mean()


# ---------------------------------------------------------------- fitting on history

ROSTER = os.environ.get("NHL_ROSTER", "none")   # none | rel | abs | mix: roster-based preseason terms (nhl_roster.py)


def prior_features(y, TT):
    """(gd1, xgd1, gd2[, rsk, rg]) per team for season y from the two previous seasons (+ roster value when enabled)."""
    teams = TT[y].index if y in TT else []
    out = pd.DataFrame(0.0, index=teams, columns=["gd1", "xgd1", "gd2"])
    if y - 1 in TT:
        g1, x1 = season_rates(TT[y - 1])
        out["gd1"] = g1.reindex(teams).values
        out["xgd1"] = x1.reindex(teams).values
        out["gd2"] = out["gd1"]
    if y - 2 in TT:
        g2, _ = season_rates(TT[y - 2])
        out["gd2"] = g2.reindex(teams).fillna(out["gd1"]).values
    if ROSTER != "none":
        import nhl_roster
        out = out.join(nhl_roster.roster_features(y, teams, current=nhl.start_year(), mode=ROSTER))
    return out.fillna(0.0)


def fit_prior(TT, years):
    X, Y, W = [], [], []
    for y in years:
        if y - 1 not in TT or y not in TT:
            continue
        f = prior_features(y, TT)
        g, _ = season_rates(TT[y])
        X.append(f.values); Y.append(g.reindex(f.index).values); W.append(numcol(TT[y], "gamesPlayed").reindex(f.index).values)
    X, Y, W = np.vstack(X), np.concatenate(Y), np.concatenate(W)
    ok = np.isfinite(Y) & np.isfinite(X).all(1)
    X, Y, W = X[ok], Y[ok], W[ok]
    sw = np.sqrt(W)[:, None]
    beta, *_ = np.linalg.lstsq(X * sw, Y * sw[:, 0], rcond=None)
    pred = X @ beta
    r2 = 1 - ((Y - pred) ** 2).sum() / (Y ** 2).sum()
    return beta, float(r2), float(np.sqrt(((Y - pred) ** 2).mean()))


def tune_shrinkage(TT, GG, betas_by_year, years):
    """k and rating uncertainty (tau) from predicting the rest of each season with the first N games."""
    res = {}
    for N in (0, 20, 41):
        rows = []
        for y in years:
            if y not in GG or y - 1 not in TT:
                continue
            g = GG[y].copy()
            g["gd"] = numcol(g, "goalsFor") - numcol(g, "goalsAgainst")
            g["n"] = g.groupby("team").cumcount() + 1
            prior = (prior_features(y, TT).values @ betas_by_year[y])
            prior = pd.Series(prior, index=prior_features(y, TT).index)
            first = g[g.n <= N].groupby("team").gd.mean() if N else pd.Series(0.0, index=prior.index)
            rest = g[g.n > N].groupby("team").gd.agg(["mean", "count"])
            for t in prior.index:
                if t in rest.index:
                    rows.append((prior[t], first.get(t, 0.0) - 0.0, rest.loc[t, "mean"], rest.loc[t, "count"]))
        a = np.array(rows)
        res[N] = a
    # one k shared by N=20 and N=41; league-mean the current rates inside each season is already implicit (sum of GD ~ 0)
    best_k, best = None, 1e9
    for k in (5, 10, 15, 20, 25, 30, 40, 55, 70, 90):
        mse = 0
        for N in (20, 41):
            p, c, r, n = res[N].T
            pred = (N * c + k * p) / (N + k)
            mse += np.mean((pred - r) ** 2)
        if mse < best:
            best, best_k = mse, k
    tau = {}
    for N in (0, 20, 41):
        p, c, r, n = res[N].T
        pred = p if N == 0 else (N * c + best_k * p) / (N + best_k)
        mse = np.mean((pred - r) ** 2)
        samp = np.mean(GAME_SD ** 2 / n)
        tau[N] = float(np.sqrt(max(mse - samp, 0.0016)))
    return int(best_k), tau


# Extra preseason rating uncertainty, fading out by game 20. Point-in-time back-test 2021-2025: F=1.5 cut preseason
# playoff log-loss 0.572 -> 0.560 and division 1.751 -> 1.719 (better in 4 of 5 seasons); chosen with TypeSafe (96%).
TAU_PRE = 1.5


def tau_at(tau, n):
    widen = 1 + (TAU_PRE - 1) * max(0.0, 1 - n / 20)
    if n <= 0:
        return tau[0] * widen
    if n <= 20:
        return (tau[0] + (tau[20] - tau[0]) * n / 20) * widen
    if n <= 41:
        return tau[20] + (tau[41] - tau[20]) * (n - 20) / 21
    return tau[41] * float(np.sqrt(41 / n))


def league_scoring(GG, years):
    h = a = n = 0
    for y in years:
        g = GG.get(y)
        if g is None or g.empty:
            continue
        hh = g[g.ha == "H"]
        h += numcol(hh, "goalsFor").sum(); a += numcol(hh, "goalsAgainst").sum(); n += len(hh)
    return float((h + a) / n), float((h - a) / n)


# ---------------------------------------------------------------- simulation

def simulate(teams, state, games, ratings, tau, total, hfa, n_sims, seed=7, div_map=ALIGN):
    """state: DataFrame by team (points, rw, row, gd). games: list of (home, away) still to play. Returns dict of arrays."""
    rng = np.random.default_rng(seed)
    T = len(teams)
    idx = {t: i for i, t in enumerate(teams)}
    h = np.array([idx[g[0]] for g in games], int)
    a = np.array([idx[g[1]] for g in games], int)
    G = len(games)
    Hm = np.zeros((G, T), np.float32); Am = np.zeros((G, T), np.float32)
    Hm[np.arange(G), h] = 1; Am[np.arange(G), a] = 1
    div_of = [div_map[t] for t in teams]
    divs = sorted(set(div_of))
    div_idx = {d: np.array([i for i, x in enumerate(div_of) if x == d]) for d in divs}
    conf_idx = {c: np.array([i for i, x in enumerate(div_of) if CONF_OF[x] == c]) for c in ("East", "West")}
    base = {k: state[k].reindex(teams).to_numpy(float) for k in ("points", "rw", "row", "gd")}
    out = {k: np.zeros(T) for k in ("playoffs", "div", "pres", "r2", "r3", "final", "cup")}
    pts_hist = np.zeros((T, 161))
    pts_sum = np.zeros(T); pts_sq = np.zeros(T)
    r0 = np.array([ratings[t] for t in teams], float)
    done = 0
    while done < n_sims:
        S = min(CHUNK, n_sims - done)
        R = r0[None, :] + rng.normal(0, tau, (S, T))
        m = R[:, h] + 0.0 - R[:, a] + hfa
        lam_h = np.clip((total + m) / 2, 0.4, None); lam_a = np.clip((total - m) / 2, 0.4, None)
        gh = rng.poisson(lam_h); ga = rng.poisson(lam_a)
        tie = gh == ga
        p_ot_h = ndtr(m / GAME_SD)
        ot_home = rng.random((S, G)) < p_ot_h
        ot_ends = rng.random((S, G)) < 0.62                       # OT decides it; otherwise shootout
        home_win = np.where(tie, ot_home, gh > ga)
        reg = ~tie
        pts_h = np.where(home_win, 2, np.where(tie, 1, 0)).astype(np.float32)
        pts_a = np.where(~home_win, 2, np.where(tie, 1, 0)).astype(np.float32)
        rw_h = (reg & home_win).astype(np.float32); rw_a = (reg & ~home_win).astype(np.float32)
        row_h = (rw_h + (tie & home_win & ot_ends)).astype(np.float32); row_a = (rw_a + (tie & ~home_win & ot_ends)).astype(np.float32)
        gdh = (gh - ga).astype(np.float32)
        pts = base["points"][None, :] + pts_h @ Hm + pts_a @ Am
        rw = base["rw"][None, :] + rw_h @ Hm + rw_a @ Am
        rowc = base["row"][None, :] + row_h @ Hm + row_a @ Am
        gd = base["gd"][None, :] + gdh @ Hm - gdh @ Am
        comp = pts * 1e8 + rw * 1e6 + rowc * 1e4 + gd * 10 + rng.random((S, T))
        # ---- playoff field
        in_po = np.zeros((S, T), bool); div_win = np.zeros((S, T), bool)
        top3 = {}
        for d, ix in div_idx.items():
            o = np.argsort(-comp[:, ix], axis=1)
            t3 = ix[o[:, :3]]
            top3[d] = t3
            div_win[np.arange(S), t3[:, 0]] = True
            for j in range(3):
                in_po[np.arange(S), t3[:, j]] = True
        conf_series = {}
        for c, cix in conf_idx.items():
            cdivs = [d for d in divs if CONF_OF[d] == c]
            masked = comp[:, cix].copy()
            for d in cdivs:
                for j in range(3):
                    col = np.searchsorted(cix, top3[d][:, j])
                    masked[np.arange(S), col] = -1
            wo = np.argsort(-masked, axis=1)[:, :2]
            wc = cix[wo]                                          # [S,2] best first
            for j in range(2):
                in_po[np.arange(S), wc[:, j]] = True
            conf_series[c] = (cdivs, wc)
        # ---- playoff rounds
        def series(x, y):
            """x has home ice. Returns winners."""
            rx, ry = R[np.arange(S), x], R[np.arange(S), y]
            ph = ndtr((rx - ry + hfa) / GAME_SD); pa = ndtr((rx - ry - hfa) / GAME_SD)
            wins = np.zeros(S, int)
            for g in range(7):
                p = ph if g in (0, 1, 4, 6) else pa
                wins += rng.random(S) < p
            return np.where(wins >= 4, x, y)

        def better(x, y):
            return np.where(comp[np.arange(S), x] >= comp[np.arange(S), y], x, y), np.where(comp[np.arange(S), x] >= comp[np.arange(S), y], y, x)

        conf_winner = {}
        for c, (cdivs, wc) in conf_series.items():
            d1, d2 = cdivs
            w1, w2 = top3[d1][:, 0], top3[d2][:, 0]
            dw1, dw2 = better(w1, w2)                              # dw1 = division winner with the better record
            wc1, wc2 = wc[:, 0], wc[:, 1]
            sA = series(dw1, wc2)                                  # best division winner vs worse wild card
            sB = series(dw2, wc1)
            adv = {}
            for d, w in ((d1, w1), (d2, w2)):
                t = top3[d]
                s23 = series(*better(t[:, 1], t[:, 2]))
                main_w = np.where(w == dw1, sA, sB)                # this division's winner (plus the wild card he meets)
                for t_ in (s23, main_w):
                    out["r2"] += np.bincount(t_, minlength=T)
                adv[d] = series(*better(main_w, s23))
            for t_ in adv.values():
                out["r3"] += np.bincount(t_, minlength=T)
            conf_winner[c] = series(*better(adv[d1], adv[d2]))
        ew, ww = conf_winner["East"], conf_winner["West"]
        for t_ in (ew, ww):
            out["final"] += np.bincount(t_, minlength=T)
        fx, fy = better(ew, ww)
        cup = series(fx, fy)
        out["cup"] += np.bincount(cup, minlength=T)
        out["playoffs"] += in_po.sum(0); out["div"] += div_win.sum(0)
        out["pres"] += np.bincount(np.argmax(comp, axis=1), minlength=T)
        pts_sum += pts.sum(0); pts_sq += (pts ** 2).sum(0)
        for t in range(T):
            pts_hist[t] += np.bincount(np.clip(pts[:, t].astype(int), 0, 160), minlength=161)
        done += S
    n = float(n_sims)
    res = {k: v / n for k, v in out.items()}
    res["pts_mean"] = pts_sum / n
    res["pts_sd"] = np.sqrt(np.maximum(pts_sq / n - (pts_sum / n) ** 2, 0))
    res["pts_hist"] = pts_hist / n
    return res


# ---------------------------------------------------------------- schedule

API = "https://api-web.nhle.com/v1/club-schedule-season"


def fetch_schedule(teams, y):
    """Remaining regular-season games [(home, away)] from the NHL schedule feed, cached for two hours."""
    os.makedirs(nhl.NHL_DATA, exist_ok=True)
    games, failed = {}, 0
    for t in teams:
        path = os.path.join(nhl.NHL_DATA, f"sched_{t}_{y}.json")
        data = None
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < 2 * 3600:
            data = json.load(open(path))
        else:
            for attempt in range(3):
                try:
                    req = urllib.request.Request(f"{API}/{t}/{nhl.sid(y)}", headers={"User-Agent": "SportsFutures/1.0"})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        data = json.load(r)
                    json.dump(data, open(path, "w"))
                    break
                except Exception:
                    time.sleep(2 * (attempt + 1))
            if data is None and os.path.exists(path):
                data = json.load(open(path))
        if data is None:
            failed += 1
            continue
        for g in data.get("games", []):
            if g.get("gameType") == 2 and g.get("gameState") not in ("FINAL", "OFF"):
                games[g["id"]] = (g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"])
    return list(games.values()), failed


# ---------------------------------------------------------------- back-test

def params_before(TT, GG, fit_years, done, y):
    """Every model setting re-estimated from seasons before y only, so a back-test of season y uses no later information."""
    past = [z for z in fit_years if z < y]
    betas = {z: fit_prior(TT, [w for w in past if w != z])[0] for z in past}
    beta = fit_prior(TT, past)[0]
    k, tau = tune_shrinkage(TT, GG, betas, [z for z in past if z >= nhl.FIRST + 2])
    total, hfa = league_scoring(GG, [z for z in done if z < y][-5:])
    return beta, k, tau, total, hfa


def backtest(TT, GG, fit_years, done, years, return_rows=False):
    rows = []
    for y in years:
        if y not in GG or y not in TT or y - 1 not in TT:
            continue
        beta_y, k, tau, total, hfa = params_before(TT, GG, fit_years, done, y)
        T = TT[y]
        teams = sorted(T.index)
        if len(teams) != 32 or any(t not in ALIGN for t in teams):
            continue
        g = GG[y].copy()
        g["gd"] = numcol(g, "goalsFor") - numcol(g, "goalsAgainst")
        g["pts"] = g.res.map({"W": 2, "OTL": 1, "L": 0}).fillna(0)
        g["n"] = g.groupby("team").cumcount() + 1
        g = g.sort_values(["date", "team"])
        if g.groupby("team").size().min() < 70:
            continue
        # actual outcomes
        fin = g.groupby("team").agg(pts=("pts", "sum"), wins=("res", lambda r: (r == "W").sum()), gd=("gd", "sum"))
        comp = fin.pts * 1e6 + fin.wins * 1e3 + fin.gd
        po = set()
        for d in set(ALIGN[t] for t in teams):
            dt_ = [t for t in teams if ALIGN[t] == d]
            po |= set(sorted(dt_, key=lambda t: -comp[t])[:3])
        for c in ("East", "West"):
            rest = [t for t in teams if CONF_OF[ALIGN[t]] == c and t not in po]
            po |= set(sorted(rest, key=lambda t: -comp[t])[:2])
        divwin = {d: max([t for t in teams if ALIGN[t] == d], key=lambda t: comp[t]) for d in set(ALIGN[t] for t in teams)}
        prior_f = prior_features(y, TT).reindex(teams).fillna(0)
        prior = pd.Series(prior_f.values @ beta_y, index=teams)
        prev_pts = (numcol(TT[y - 1], "points") / numcol(TT[y - 1], "gamesPlayed") * SEASON_GAMES).reindex(teams).fillna(91)
        for N in (0, 20):
            gp = g[g.n <= N].groupby("team").size().reindex(teams).fillna(0)
            played = g[g.n <= N]
            cur = (played.groupby("team").gd.mean().reindex(teams).fillna(0) if N else pd.Series(0.0, index=teams))
            cur = cur - cur.mean()
            rating = (gp * cur + k * prior) / (gp + k)
            rating = rating - rating.mean()
            state = pd.DataFrame({"points": played.groupby("team").pts.sum().reindex(teams).fillna(0),
                                  "rw": played.assign(w=(played.res == "W").astype(float)).groupby("team").w.sum().reindex(teams).fillna(0),
                                  "gd": played.groupby("team").gd.sum().reindex(teams).fillna(0)}, index=teams)
            state["row"] = state.rw
            rem = g[(g.n > N) & (g.ha == "H")]
            games = list(zip(rem.team, rem.opp))
            sim = simulate(teams, state, games, rating.to_dict(), tau_at(tau, N), total, hfa, 3000, seed=3)
            for i, t in enumerate(teams):
                rows.append({"season": y, "N": N, "team": t, "pts_pred": sim["pts_mean"][i], "pts": fin.pts[t], "p_po": sim["playoffs"][i], "po": int(t in po),
                             "p_div": sim["div"][i], "is_div": int(divwin[ALIGN[t]] == t), "p_cup": sim["cup"][i], "p_final": sim["final"][i], "date": str(g[g.n <= N].date.max()) if N else None, "naive": 91 + 0.5 * (prev_pts[t] - 91)})
    if not rows:
        return None
    d = pd.DataFrame(rows)
    if return_rows:
        return d
    out = {}
    for N, x in d.groupby("N"):
        p = x.p_po.clip(0.005, 0.995)
        pd_ = x.p_div.clip(0.003, 0.997)
        out[str(N)] = {"seasons": int(x.season.nunique()), "mae_model": float((x.pts_pred - x.pts).abs().mean()), "mae_naive": float((x.naive - x.pts).abs().mean()),
                       "logloss_playoffs": float(-(x.po * np.log(p) + (1 - x.po) * np.log(1 - p)).mean()), "logloss_playoffs_base": float(np.log(2)),
                       "logloss_division": float(-(x.is_div * np.log(pd_) + (1 - x.is_div) * np.log(1 - pd_)).mean()),
                       "logloss_division_base": float(-(0.125 * np.log(0.125) + 0.875 * np.log(0.875)))}
    # reliability: predicted playoff chance vs how often it happened
    x = d[d.N == 20]
    bins = pd.cut(x.p_po, [0, .1, .3, .5, .7, .9, 1.0], include_lowest=True)
    out["method"] = "point-in-time: every setting re-estimated from earlier seasons only"
    out["calibration_20"] = [{"bin": str(b), "pred": float(v.p_po.mean()), "actual": float(v.po.mean()), "n": int(len(v))} for b, v in x.groupby(bins, observed=True)]
    return out


# ---------------------------------------------------------------- build

def build():
    cur = nhl.start_year()
    TT, GG = {}, {}
    for y in range(nhl.FIRST, cur + 1):
        t = read_team(y)
        if not t.empty:
            TT[y] = t
        g = read_games(y)
        if not g.empty:
            GG[y] = g
    done = [y for y in TT if y < cur and y in GG and GG[y].groupby("team").size().min() >= 40]
    if cur not in TT or len(done) < 6:
        log("nhl model: not enough data")
        return
    fit_years = [y for y in done if y - 1 in TT]
    betas_by_year = {y: fit_prior(TT, [z for z in fit_years if z != y])[0] for y in fit_years}
    beta, r2, rmse = fit_prior(TT, fit_years)
    k, tau = tune_shrinkage(TT, GG, betas_by_year, [y for y in fit_years if y >= nhl.FIRST + 2])
    total, hfa = league_scoring(GG, done[-5:])
    log("nhl model: prior beta", np.round(beta, 3).tolist(), "r2", round(r2, 3), "k", k, "tau", {a: round(b, 3) for a, b in tau.items()}, "total", round(total, 2), "hfa", round(hfa, 3))

    # ---- current season
    Tc = TT[cur]
    teams = sorted(Tc.index)
    games, failed = fetch_schedule(teams, cur)
    if failed > 3 or not games:
        log("nhl model: schedule unavailable (", failed, "teams failed )")
        return
    gp = numcol(Tc, "gamesPlayed").reindex(teams)
    pf = prior_features(cur, TT).reindex(teams).fillna(0)
    prior = pd.Series(pf.values @ beta, index=teams)
    gdr, xgr = season_rates(Tc)
    cur_rate = (0.6 * gdr + 0.4 * xgr).reindex(teams).fillna(0)
    cur_rate = cur_rate - cur_rate.mean()
    rating = ((gp * cur_rate + k * prior) / (gp + k))
    rating = rating - rating.mean()
    state = pd.DataFrame({"points": numcol(Tc, "points"), "rw": numcol(Tc, "winsInRegulation"), "row": numcol(Tc, "regulationAndOtWins"),
                          "gd": numcol(Tc, "goalDiff")}, index=Tc.index).reindex(teams).fillna(0)
    n_avg = float(gp.mean())
    tau_now = tau_at(tau, n_avg)
    remaining_ct = pd.Series(0, index=teams)
    for h_, a_ in games:
        for t_ in (h_, a_):
            if t_ in remaining_ct.index:
                remaining_ct[t_] += 1
    log("nhl model: remaining games", len(games), "remaining per team min/max", int(remaining_ct.min()), int(remaining_ct.max()), "tau", round(tau_now, 3))
    sim = simulate(teams, state, games, rating.to_dict(), tau_now, total, hfa, SIMS)
    cdf = np.cumsum(sim["pts_hist"][:, ::-1], axis=1)[:, ::-1]                      # P(points >= x)
    names = Tc.name.to_dict()
    rows = []
    for i, t in enumerate(teams):
        hist = sim["pts_hist"][i]
        c = np.cumsum(hist)
        q = lambda p: int(np.searchsorted(c, p))
        rows.append({"team": t, "name": names.get(t, t), "div": ALIGN.get(t), "gp": int(gp[t]), "points": int(state.points[t]),
                     "record": f"{int(numcol(Tc, 'wins')[t])}-{int(numcol(Tc, 'losses')[t])}-{int(numcol(Tc, 'otLosses')[t])}",
                     "rating": float(rating[t]), "prior": float(prior[t]), "cur_rate": float(cur_rate[t]),
                     "pts_mean": float(sim["pts_mean"][i]), "pts_p10": q(0.10), "pts_p50": q(0.50), "pts_p90": q(0.90),
                     "p_playoffs": float(sim["playoffs"][i]), "p_div": float(sim["div"][i]), "p_pres": float(sim["pres"][i]),
                     "p_r2": float(sim["r2"][i]), "p_r3": float(sim["r3"][i]), "p_final": float(sim["final"][i]), "p_cup": float(sim["cup"][i]),
                     "over": [round(float(v), 4) for v in cdf[i][30:141]]})
    cache = os.path.join(nhl.NHL_DATA, "model_backtest.json")
    key = f"v3-point-in-time-{done[-1]}-{TAU_PRE}-{SIMS > 0}"
    bt = None
    if os.path.exists(cache):
        c0 = json.load(open(cache))
        if c0.get("key") == key:
            bt = c0["bt"]
    if bt is None:
        bt = backtest(TT, GG, fit_years, done, [y for y in done if y >= 2021])
        json.dump({"key": key, "bt": bt}, open(cache, "w"))
    out = {"season": cur, "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "games_played": n_avg, "sims": SIMS,
           "params": {"k": k, "tau_now": tau_now, "tau": tau, "total_goals": total, "hfa": hfa, "beta": [float(b) for b in beta], "prior_r2": r2, "prior_rmse": rmse},
           "backtest": bt, "teams": rows, "pts_axis": [30, 140]}
    nhl.write("futures.json", out)
    log("nhl model done: top cup", sorted(((r["p_cup"], r["team"]) for r in rows), reverse=True)[:4])
