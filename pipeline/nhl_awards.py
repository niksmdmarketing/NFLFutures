"""NHL award futures: chance of winning each award, shown as probabilities.

Voted awards (Hart, Vezina, Norris, Calder) use a conditional-logit model fitted on every winner since 2010-11 and scored
leave-one-season-out. The model sees a candidate's end-of-season stats relative to the other candidates (points share,
goalie saves above average, ice time, team strength). In-season, each candidate's season is simulated forward from his
current numbers (shrunk toward last season's rate) and the model's chances are averaged over the simulations, so early-season
chances are properly wide. Art Ross (points) and Rocket Richard (goals) are straight simulations of who finishes first.
Reads the season files nhl.py has just written, so it refreshes with them.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import unicodedata

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import nhl
from common import log

WINNERS = {
    "Hart": {2010: "Corey Perry", 2011: "Evgeni Malkin", 2012: "Alexander Ovechkin", 2013: "Sidney Crosby", 2014: "Carey Price",
             2015: "Patrick Kane", 2016: "Connor McDavid", 2017: "Taylor Hall", 2018: "Nikita Kucherov", 2019: "Leon Draisaitl",
             2020: "Connor McDavid", 2021: "Auston Matthews", 2022: "Connor McDavid", 2023: "Nathan MacKinnon",
             2024: "Connor Hellebuyck", 2025: "Nikita Kucherov"},
    "Vezina": {2010: "Tim Thomas", 2011: "Henrik Lundqvist", 2012: "Sergei Bobrovsky", 2013: "Tuukka Rask", 2014: "Carey Price",
               2015: "Braden Holtby", 2016: "Sergei Bobrovsky", 2017: "Pekka Rinne", 2018: "Andrei Vasilevskiy",
               2019: "Connor Hellebuyck", 2020: "Marc-Andre Fleury", 2021: "Igor Shesterkin", 2022: "Linus Ullmark",
               2023: "Connor Hellebuyck", 2024: "Connor Hellebuyck", 2025: "Andrei Vasilevskiy"},
    "Norris": {2010: "Nicklas Lidstrom", 2011: "Erik Karlsson", 2012: "P.K. Subban", 2013: "Duncan Keith", 2014: "Erik Karlsson",
               2015: "Drew Doughty", 2016: "Brent Burns", 2017: "Victor Hedman", 2018: "Mark Giordano", 2019: "Roman Josi",
               2020: "Adam Fox", 2021: "Cale Makar", 2022: "Erik Karlsson", 2023: "Quinn Hughes", 2024: "Cale Makar",
               2025: "Zach Werenski"},
    "Calder": {2010: "Jeff Skinner", 2011: "Gabriel Landeskog", 2012: "Jonathan Huberdeau", 2013: "Nathan MacKinnon",
               2014: "Aaron Ekblad", 2015: "Artemi Panarin", 2016: "Auston Matthews", 2017: "Mathew Barzal", 2018: "Elias Pettersson",
               2019: "Cale Makar", 2020: "Kirill Kaprizov", 2021: "Moritz Seider", 2022: "Matty Beniers", 2023: "Connor Bedard",
               2024: "Lane Hutson", 2025: "Matthew Schaefer"},
}
TITLES = {"Hart": "Hart Trophy (MVP)", "Vezina": "Vezina Trophy (top goalie)", "Norris": "Norris Trophy (top defenceman)",
          "Calder": "Calder Trophy (top rookie)", "ArtRoss": "Art Ross Trophy (most points)", "Richard": "Maurice Richard Trophy (most goals)"}
NAME_FIX = {"alexanderovechkin": "alexovechkin", "pksubban": "pksubban", "nicklaslidstrom": "nicklaslidstrom"}
SEASON_GAMES = 82
LAMBDAS = (0.01, 0.05, 0.3, 1.0)


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", ""))
    return NAME_FIX.get(s.replace(" ", ""), s.replace(" ", ""))


def last_first(s: str):
    p = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace("-", "").replace(".", " ").split()
    return (p[-1], p[0][:1]) if p else ("", "")


def read(kind: str, y: int):
    path = os.path.join(nhl.NHL_OUT, f"{kind}_{y}.json")
    if not os.path.exists(path):
        return pd.DataFrame()
    d = json.load(open(path))
    ids = {"team": ["team", "name"], "skaters": ["name", "team", "pos"], "goalies": ["name", "team", "pos"]}[kind]
    cols = ids + [c["k"] for c in d["cols"]]
    return pd.DataFrame(d["rows"], columns=cols)


def col(d, c, default=0.0):
    return pd.to_numeric(d[c], errors="coerce").fillna(default) if c in d else pd.Series(default, index=d.index)


# ---------------------------------------------------------------- candidate pools (one row per candidate)

def season_tables(y: int):
    sk, gl, tm = read("skaters", y), read("goalies", y), read("team", y)
    if sk.empty or tm.empty:
        return None
    tm = tm.set_index("team")
    tm_pp = col(tm, "pointPct")
    tm_gp = col(tm, "gamesPlayed")
    tm_pts = col(tm, "points")
    first = lambda t: str(t).split(",")[-1] if t else ""        # traded players: the team he finished with
    sk = sk.assign(t1=sk.team.map(first)); gl = gl.assign(t1=gl.team.map(first)) if not gl.empty else gl
    sid = nhl.sid(y)
    # NHL rookie rule, roughly: first season, or first full season after fewer than 25 games the year before
    prev_gp = {}
    for kind in ("skaters", "goalies"):
        pv = read(kind, y - 1)
        if not pv.empty:
            for n_, g_ in zip(pv.name, col(pv, "gamesPlayed")):
                prev_gp[n_] = max(prev_gp.get(n_, 0), g_)
    prev_sid = nhl.sid(y - 1)

    def is_rookie(d):
        f = col(d, "firstSeasonForGameType")
        return ((f == sid) | ((f == prev_sid) & (d.name.map(lambda n_: prev_gp.get(n_, 0)) <= 25))).astype(float)
    base_sk = pd.DataFrame({"name": sk.name, "team": sk.t1, "pos": sk.pos, "isG": 0.0, "gp": col(sk, "gamesPlayed"), "pts": col(sk, "points"),
                            "goals": col(sk, "goals"), "toi": col(sk, "timeOnIcePerGame"), "saa": 0.0,
                            "rookie": is_rookie(sk)})
    base_gl = pd.DataFrame()
    if not gl.empty:
        base_gl = pd.DataFrame({"name": gl.name, "team": gl.t1, "pos": "G", "isG": 1.0, "gp": col(gl, "gamesPlayed"), "pts": col(gl, "points"),
                                "goals": 0.0, "toi": col(gl, "timeOnIce") / col(gl, "gamesPlayed").replace(0, np.nan), "saa": col(gl, "savesAboveAvg"),
                                "rookie": is_rookie(gl),
                                "savePct": col(gl, "savePct"), "gaa": col(gl, "goalsAgainstAverage"), "wins": col(gl, "wins"),
                                "gsax": col(gl, "mp_gsax")})
    for d in (base_sk, base_gl):
        if len(d):
            d["tm_pp"] = d.team.map(tm_pp).fillna(0.5)
            d["tm_gp"] = d.team.map(tm_gp).fillna(tm_gp.max())
            d["tm_pts"] = d.team.map(tm_pts).fillna(0.0)
    return base_sk, base_gl, tm


def pool(award: str, sk: pd.DataFrame, gl: pd.DataFrame, game_scale: float = 1.0) -> pd.DataFrame:
    """Candidates for an award, from one season's skaters/goalies (same columns whether actual or simulated)."""
    mg = sk.gp.max() if len(sk) else 0
    if award == "Hart":
        a = sk.sort_values("pts", ascending=False).head(20)
        b = gl[gl.gp >= 20 * game_scale].sort_values("saa", ascending=False).head(6) if len(gl) else gl
        return pd.concat([a, b])
    if award == "Vezina":
        g = gl[gl.gp >= 0.4 * (gl.gp.max() if len(gl) else 0)] if len(gl) else gl
        return g.sort_values("saa", ascending=False).head(10)
    if award == "Norris":
        return sk[sk.pos == "D"].sort_values("pts", ascending=False).head(12)
    if award == "Calder":
        a = sk[sk.rookie == 1].sort_values("pts", ascending=False).head(12)
        b = gl[(gl.rookie == 1) & (gl.gp >= 8 * game_scale)].sort_values("saa", ascending=False).head(4) if len(gl) else gl
        return pd.concat([a, b])
    raise KeyError(award)


# ---------------------------------------------------------------- features (arrays shaped [S, n])

def _share(x, mask):
    m = np.where(mask, x, -1e9).max(axis=-1, keepdims=True)
    return np.where(mask, x / np.maximum(m, 1e-9), 0.0), m


def feats(award: str, A: dict) -> np.ndarray:
    pts, goals, toi, saa, tm, isG, gp = (A[k] for k in ("pts", "goals", "toi", "saa", "tm", "isG", "gp"))
    sk = isG == 0
    one = lambda m, x: (np.where(m, x, -1e9) == np.where(m, x, -1e9).max(axis=-1, keepdims=True)) & m
    if award == "Hart":
        ps, _ = _share(pts, sk)
        sa, _ = _share(np.clip(saa, 0, None), isG == 1)
        f = [ps, ps ** 2, tm - 0.5, isG, sa, one(sk, pts).astype(float)]
    elif award == "Vezina":
        sa, _ = _share(np.clip(saa, 0, None), np.ones_like(saa, dtype=bool))
        gs, _ = _share(gp, np.ones_like(gp, dtype=bool))
        f = [sa, tm - 0.5, gs, one(np.ones_like(saa, dtype=bool), saa).astype(float)]
    elif award == "Norris":
        ps, _ = _share(pts, sk)
        ts, _ = _share(toi, sk)
        gsh, _ = _share(goals, sk)
        f = [ps, ts, tm - 0.5, gsh, one(sk, pts).astype(float)]
    else:  # Calder
        ps, _ = _share(pts, sk)
        sa, _ = _share(np.clip(saa, 0, None), isG == 1)
        f = [ps, isG, sa, one(sk, pts).astype(float)]
    return np.stack(f, axis=-1)


def fit(Xs, ws, lam):
    p = Xs[0].shape[1]

    def obj(b):
        loss, g = lam * (b @ b), 2 * lam * b
        for X, w in zip(Xs, ws):
            z = X @ b
            m = z.max()
            e = np.exp(z - m)
            sm = e / e.sum()
            loss += np.log(e.sum()) + m - z[w]
            g = g + X.T @ sm - X[w]
        return loss, g
    r = minimize(obj, np.zeros(p), jac=True, method="L-BFGS-B")
    return r.x


def softmax(z):
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def arrays(df: pd.DataFrame, tm_final=None):
    d = {k: df[k].to_numpy(float)[None, :] for k in ("pts", "goals", "toi", "saa", "isG", "gp")}
    d["tm"] = (df.tm_pp.to_numpy(float) if tm_final is None else tm_final)[None, :]
    return d


# ---------------------------------------------------------------- training on history

def find_winner(cands: pd.DataFrame, name: str):
    n = norm(name)
    hit = cands[cands.name.map(norm) == n]
    if hit.empty:
        l, f = last_first(name)
        hit = cands[cands.name.map(last_first).map(lambda t: t == (l, f))]
    return None if hit.empty else cands.index.get_loc(hit.sort_values("pts", ascending=False).index[0])


def train(award: str, seasons: list[int], T: dict):
    data = []
    for y in seasons:
        if y not in T or y not in WINNERS[award]:
            continue
        sk, gl, _ = T[y]
        c = pool(award, sk, gl).reset_index(drop=True)
        w = find_winner(c, WINNERS[award][y])
        if w is None:
            log("nhl awards:", award, y, "winner not in pool:", WINNERS[award][y])
            continue
        data.append((y, c, feats(award, arrays(c))[0], w))
    return data


def loso(data, lam):
    ll, top1, top3, pw = [], 0, 0, []
    for i, (y, c, X, w) in enumerate(data):
        rest = [d for j, d in enumerate(data) if j != i]
        b = fit([d[2] for d in rest], [d[3] for d in rest], lam)
        p = softmax(X @ b)
        ll.append(-np.log(max(p[w], 1e-9)))
        top1 += int(p.argmax() == w)
        top3 += int(w in np.argsort(-p)[:3])
        pw.append(float(p[w]))
    return {"logloss": float(np.mean(ll)), "top1": top1, "top3": top3, "n": len(data), "avg_p": float(np.mean(pw))}


# ---------------------------------------------------------------- current-season simulation

def simulate_current(cur: int, T: dict, S: int = 400, seed: int = 11):
    rng = np.random.default_rng(seed)
    sk, gl, tm = T[cur]
    prev = T.get(cur - 1)
    uniq = lambda d: d.sort_values("gp", ascending=False).drop_duplicates("name").set_index("name")
    prev_sk = uniq(prev[0]) if prev else None
    prev_gl = uniq(prev[1]) if prev and len(prev[1]) else None
    prev_tm = prev[2] if prev else None
    tgp = col(tm, "gamesPlayed")
    tpts = col(tm, "points")
    R = (SEASON_GAMES - tgp).clip(lower=0)
    # team final point % (talent shrunk toward last season, plus binomial noise on the remaining games)
    prior = 0.5 + 0.4 * (col(prev_tm, "pointPct").reindex(tm.index).fillna(0.5) - 0.5) if prev_tm is not None else pd.Series(0.5, index=tm.index)
    p_now = (tpts / (2 * tgp.replace(0, np.nan))).fillna(0.5)
    k = 30
    p_team = ((p_now * tgp + prior * k) / (tgp + k)).clip(0.25, 0.8)
    T_pts = np.zeros((S, len(tm)))
    for j, t in enumerate(tm.index):
        pp = np.clip(rng.normal(p_team[t], 0.05, S), 0.2, 0.85)
        T_pts[:, j] = tpts[t] + 2 * rng.binomial(int(R[t]), pp)
    tm_index = {t: j for j, t in enumerate(tm.index)}

    def team_final(df):
        return np.stack([T_pts[:, tm_index[t]] / (2 * SEASON_GAMES) if t in tm_index else np.full(S, 0.5) for t in df.team], axis=1)

    out = {}
    # ---- skater totals: Poisson on remaining games, rate shrunk to last season, gamma talent noise
    def sim_sk(df):
        n = len(df)
        Rt = np.array([R.get(t, 0) for t in df.team], float)
        grem = rng.binomial(Rt.astype(int)[None, :].repeat(S, 0), 0.92)
        res = {}
        for key, k_prior, repl in (("pts", 18, 0.30), ("goals", 22, 0.10)):
            prior_rate = np.array([(prev_sk.loc[nm, key] / prev_sk.loc[nm, "gp"]) if prev_sk is not None and nm in prev_sk.index and prev_sk.loc[nm, "gp"] >= 25 else repl
                                   for nm in df.name], float)
            rate = (df[key].to_numpy(float) + k_prior * prior_rate) / (df.gp.to_numpy(float) + k_prior)
            mult = rng.gamma(20, 1 / 20, (S, n))
            res[key] = df[key].to_numpy(float)[None, :] + rng.poisson(np.maximum(rate[None, :] * mult * grem, 0))
        res["gp"] = df.gp.to_numpy(float)[None, :] + grem
        prior_toi = np.array([prev_sk.loc[nm, "toi"] if prev_sk is not None and nm in prev_sk.index else df.toi.mean() for nm in df.name], float)
        res["toi"] = ((df.toi.to_numpy(float) * df.gp.to_numpy(float) + 10 * prior_toi) / (df.gp.to_numpy(float) + 10))[None, :].repeat(S, 0)
        return res

    def sim_gl(df):
        n = len(df)
        Rt = np.array([R.get(t, 0) for t in df.team], float)
        tg = np.array([max(tgp.get(t, 0), 1) for t in df.team], float)
        prior_share = np.array([min(prev_gl.loc[nm, "gp"] / SEASON_GAMES, 0.75) if prev_gl is not None and nm in prev_gl.index else 0.35 for nm in df.name], float)
        share = (df.gp.to_numpy(float) + 16 * prior_share) / (tg + 16)
        grem = rng.binomial(Rt.astype(int)[None, :].repeat(S, 0), np.clip(share * 0.97, 0, 0.95)[None, :].repeat(S, 0))
        prior_rate = np.array([0.5 * prev_gl.loc[nm, "saa"] / max(prev_gl.loc[nm, "gp"], 1) if prev_gl is not None and nm in prev_gl.index and prev_gl.loc[nm, "gp"] >= 20 else 0.0
                               for nm in df.name], float)
        rate = (df.saa.to_numpy(float) + 25 * prior_rate) / (df.gp.to_numpy(float) + 25)
        rate = rate[None, :] + rng.normal(0, 0.12, (S, n))
        saa = df.saa.to_numpy(float)[None, :] + grem * rate + rng.normal(0, 1.6, (S, n)) * np.sqrt(grem)
        return {"saa": saa, "gp": df.gp.to_numpy(float)[None, :] + grem}

    return sk, gl, tm, sim_sk, sim_gl, team_final, rng, S


def sim_pool(award, cur, T, models, S=400):
    sk, gl, tm, sim_sk, sim_gl, team_final, rng, S = simulate_current(cur, T, S)
    sks = sim_sk(sk) if len(sk) else {}
    gls = sim_gl(gl) if len(gl) else {}
    # pool = leaders by mean simulated totals
    sk2 = sk.assign(pts=sks["pts"].mean(0), goals=sks["goals"].mean(0), gp=sks["gp"].mean(0)) if len(sk) else sk
    gl2 = gl.assign(saa=gls["saa"].mean(0), gp=gls["gp"].mean(0)) if len(gl) else gl
    cands = pool(award, sk2, gl2, game_scale=1.0).copy()
    return cands, sk, gl, sks, gls, team_final, S, rng


def current_chances(award, cur, T, beta):
    cands, sk, gl, sks, gls, team_final, S, rng = sim_pool(award, cur, T, None)
    if cands.empty:
        return []
    arr = {k: np.zeros((S, len(cands))) for k in ("pts", "goals", "toi", "saa", "gp")}
    for j, (lab, r) in enumerate(cands.iterrows()):
        if r.isG == 1:
            i = lab
            arr["saa"][:, j] = gls["saa"][:, i]; arr["gp"][:, j] = gls["gp"][:, i]
            arr["pts"][:, j] = r.pts
        else:
            i = lab
            for k in ("pts", "goals", "toi", "gp"):
                arr[k][:, j] = sks[k][:, i]
    arr["isG"] = np.repeat(cands.isG.to_numpy(float)[None, :], S, 0)
    arr["tm"] = team_final(cands)
    P = softmax(feats(award, arr) @ beta)
    out = []
    for j, (lab, r0) in enumerate(cands.iterrows()):
        r = (gl if r0.isG == 1 else sk).loc[lab]          # report the actual numbers to date, not the projected ones
        d = {"name": r["name"], "team": r.team, "pos": r.pos, "gp": int(r.gp), "pts": int(r.pts),
             "goals": int(r.goals), "prob": float(P[:, j].mean()), "proj_pts": float(arr["pts"][:, j].mean()), "proj_goals": float(arr["goals"][:, j].mean()),
             "tm_pp": float(r.tm_pp)}
        if r.isG == 1:
            d.update(saa=float(r.saa), proj_saa=float(arr["saa"][:, j].mean()), save_pct=float(r.get("savePct", np.nan)), gaa=float(r.get("gaa", np.nan)),
                     wins=int(r.get("wins", 0)), gsax=float(r.get("gsax", 0.0)))
        out.append(d)
    out.sort(key=lambda d: -d["prob"])
    return out


def leaders_race(key, cur, T, S=4000):
    """Chance of finishing first in points (Art Ross) or goals (Richard): simulate the remaining season."""
    sk, gl, tm, sim_sk, sim_gl, team_final, rng, S = simulate_current(cur, T, S)
    if sk.empty:
        return []
    sks = sim_sk(sk)
    tot = sks[key]
    mx = tot.max(axis=1, keepdims=True)
    win = (tot == mx).astype(float)
    win /= win.sum(axis=1, keepdims=True)           # ties split
    prob = win.mean(0)
    order = np.argsort(-prob)[:15]
    out = []
    for i in order:
        r = sk.iloc[i]
        out.append({"name": r["name"], "team": r.team, "pos": r.pos, "gp": int(r.gp), "pts": int(r.pts), "goals": int(r.goals), "prob": float(prob[i]),
                    "proj_pts": float(sks["pts"][:, i].mean()), "proj_goals": float(sks["goals"][:, i].mean()),
                    "lo": float(np.percentile(tot[:, i], 10)), "hi": float(np.percentile(tot[:, i], 90))})
    return out


# ---------------------------------------------------------------- history tables

def winner_rows(award, seasons, T):
    rows = []
    for y in seasons:
        if y not in T or y not in WINNERS.get(award, {}):
            continue
        sk, gl, tm = T[y]
        c = pool(award, sk, gl).reset_index(drop=True)
        w = find_winner(c, WINNERS[award][y])
        if w is None:
            continue
        r = c.iloc[w]
        allsk = sk[sk.isG == 0]
        pts_rank = int((allsk.pts > r.pts).sum() + 1) if r.isG == 0 else None
        d = {"season": y, "name": r["name"], "team": r.team, "pos": r.pos, "gp": int(r.gp), "pts": int(r.pts), "goals": int(r.goals), "tm_pp": float(r.tm_pp),
             "pts_rank": pts_rank}
        if award == "Norris":
            dsk = sk[sk.pos == "D"]
            d["pts_rank"] = int((dsk.pts > r.pts).sum() + 1)
        if award == "Calder" and r.isG == 0:
            d["pts_rank"] = int((sk[sk.rookie == 1].pts > r.pts).sum() + 1)
        if r.isG == 1:
            d.update(saa=float(r.saa), save_pct=float(r.get("savePct", np.nan)), gaa=float(r.get("gaa", np.nan)), wins=int(r.get("wins", 0)),
                     saa_rank=int((gl.saa > r.saa).sum() + 1) if len(gl) else None)
        rows.append(d)
    return rows[::-1]


def leader_rows(key, seasons, T):
    rows = []
    for y in seasons:
        if y not in T:
            continue
        sk = T[y][0]
        sk = sk[sk.isG == 0]
        top = sk.sort_values(key, ascending=False).head(2)
        if top.empty:
            continue
        r = top.iloc[0]
        rows.append({"season": y, "name": r["name"], "team": r.team, "pos": r.pos, "gp": int(r.gp), "pts": int(r.pts), "goals": int(r.goals),
                     "tm_pp": float(r.tm_pp), "margin": float(top.iloc[0][key] - top.iloc[1][key]) if len(top) > 1 else None})
    return rows[::-1]


def build():
    cur = nhl.start_year()
    T = {}
    for y in range(nhl.FIRST, cur + 1):
        t = season_tables(y)
        if t:
            T[y] = t
    if not T:
        return
    done = [y for y in T if y < cur]
    out = {"season": cur, "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "games_played": int(col(T[cur][2], "gamesPlayed").max()) if cur in T else 0, "awards": {}}
    for award in ("Hart", "Vezina", "Norris", "Calder"):
        data = train(award, done, T)
        if len(data) < 6:
            log("nhl awards: not enough history for", award)
            continue
        scores = {lam: loso(data, lam) for lam in LAMBDAS}
        lam = min(scores, key=lambda l: scores[l]["logloss"])
        beta = fit([d[2] for d in data], [d[3] for d in data], lam)
        bt = scores[lam]
        # baseline: the stat leader (most points / most saves above average) takes the vote
        base = 0
        for y, c, X, w in data:
            lead = c.saa.idxmax() if award == "Vezina" else (c[c.isG == 0].pts.idxmax() if (c.isG == 0).any() else c.index[0])
            base += int(lead == w)
        entry = {"title": TITLES[award], "backtest": {**bt, "lambda": lam, "leader_hits": base},
                 "current": current_chances(award, cur, T, beta) if cur in T else [],
                 "past": winner_rows(award, sorted(done, reverse=True), T), "kind": award}
        out["awards"][award] = entry
        log("nhl awards", award, "LOSO top1", bt["top1"], "/", bt["n"], "logloss", round(bt["logloss"], 3), "leader baseline", base)
    if cur in T:
        out["awards"]["ArtRoss"] = {"title": TITLES["ArtRoss"], "kind": "ArtRoss", "current": leaders_race("pts", cur, T), "past": leader_rows("pts", sorted(done, reverse=True), T)}
        out["awards"]["Richard"] = {"title": TITLES["Richard"], "kind": "Richard", "current": leaders_race("goals", cur, T), "past": leader_rows("goals", sorted(done, reverse=True), T)}
    nhl.write("awards.json", out)
