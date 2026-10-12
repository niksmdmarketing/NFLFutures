"""Round-by-round point-in-time replay of the AFL futures model (research / archive builder).

For each past season (2013 onward) and each checkpoint (before round 1, then after every round) the rating is
afl_site.srs(games played so far, prior=PRIOR_REG * previous season's rating, k=K_PRIOR), the real home-and-away fixture is
replayed with later results hidden and afl_site.simulate gives the probabilities the Futures page uses. Seasons up to 2025
use the final-eight finals format (finals8=True), 2026 on the top-10 wildcard format (read from the number of finalists). No injuries/list changes.
Outputs model/replay/afl_<season>.csv: season, week (round after which the checkpoint is taken), date, gp_avg, team,
p_playoff (= make finals: top 8 to 2025, top 10 from 2026), p_top8, p_div (= top 4, double chance), p_seed1 (minor premier),
p_pf (prelim final), p_conf (grand final), p_title (premiers) and 0/1 outcomes y_*.
Usage: python research/replay_afl.py [first] [last]    (env BT_SIMS, default 1500)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import afl_site as A  # noqa: E402

SIMS = int(os.environ.get("BT_SIMS", "1500"))
HL = float(os.environ.get("BT_HL", "0"))      # recency half-life in rounds for the in-season rating (0 = off, the live model)


def srs_w(g, prior, k, hl, ck):
    """A.srs with exponentially down-weighted older games (weight 0.5 ** (rounds ago / hl))."""
    teams = sorted(set(g.team) | set(prior or {}))
    ix = {t: i for i, t in enumerate(teams)}
    x = g[g.ha == "H"]
    n = len(teams)
    A_ = np.zeros((len(x) + n, n))
    b = np.zeros(len(x) + n)
    w = 0.5 ** ((ck - x.r.values) / hl)
    for r, (t, o, m, wt) in enumerate(zip(x.team, x.opp, x.margin, w)):
        sw = np.sqrt(wt)
        A_[r, ix[t]], A_[r, ix[o]] = sw, -sw
        b[r] = (m - A.HGA) * sw
    lam = np.sqrt(k / 2)
    for t, i in ix.items():
        A_[len(x) + i, i] = lam
        b[len(x) + i] = lam * (prior or {}).get(t, 0.0)
    sol = np.linalg.lstsq(A_, b, rcond=None)[0]
    sol -= sol.mean()
    return dict(zip(teams, sol))
OUT = os.environ.get("BT_OUTDIR") or os.path.join(ROOT, "model", "replay")
A.TAU0 = float(os.environ.get("BT_TAU0", A.TAU0))
A.TAU_FADE = float(os.environ.get("BT_TAU_FADE", A.TAU_FADE))


def season_frames():
    out = {}
    for y in range(A.FIRST, 2030):
        d = A.load_season(y)
        if d is None:
            continue
        g = A.team_games(d, y)
        if g is not None and not g.empty:
            out[y] = g
    return out


def ladder(reg):
    t = reg.groupby("team").agg(w=("win", lambda s: (s == 1).sum()), d=("win", lambda s: (s == .5).sum()), pf=("points_for", "sum"), pa=("points_against", "sum"))
    t["pts"] = 4 * t.w + 2 * t.d
    t["key"] = t.pts + t.pf / t.pa.clip(lower=1) * 1e-3
    return t.sort_values("key", ascending=False)


def run_season(G, y):
    g = G[y]
    reg = g[g.season_type == "REG"].copy()
    fin = g[g.season_type == "FIN"]
    if reg.empty or fin.empty or (y - 1) not in G:
        return None
    reg["r"] = pd.to_numeric(reg.rnd, errors="coerce")
    reg = reg.dropna(subset=["r"])
    prev = G[y - 1][G[y - 1].season_type == "REG"]
    prior = {t: A.PRIOR_REG * v for t, v in A.srs(prev).items()}
    lad = ladder(reg)
    teams = sorted(A.NAMES)
    pos = {t: i for i, t in enumerate(lad.index)}
    finalists = set(fin.team)
    top_finals = len(finalists)      # 8 until 2025; the top-10 wildcard format began in 2026
    gf = fin[fin["round"].astype(str).str.upper().isin(["GF", "GRANDFINAL", "GRAND FINAL"])]
    champ = gf[gf.win == 1].team.iloc[0] if len(gf[gf.win == 1]) else None
    gf_teams = set(gf.team)
    pf_teams = set(fin[fin["round"].astype(str).str.upper().isin(["PF", "PRELIMINARYFINAL", "PRELIMINARY FINAL"])].team)
    # one row per match from the home side (or the first listed side for neutral venues)
    ms = reg.sort_values("date").drop_duplicates("match_id")
    ms = ms.assign(h=np.where(ms.ha == "A", ms.opp, ms.team), a=np.where(ms.ha == "A", ms.team, ms.opp))
    rounds = sorted(reg.r.unique())
    rows = []
    for ck in [0] + list(rounds):
        played = reg[reg.r <= ck]
        remaining = [(h, a) for h, a in zip(ms[ms.r > ck].h, ms[ms.r > ck].a)]
        if len(played):
            rating = srs_w(played, prior, A.K_PRIOR, HL, ck) if HL else A.srs(played, prior=prior, k=A.K_PRIOR)
            T = played.groupby("team").agg(w=("win", lambda s: (s == 1).sum()), d=("win", lambda s: (s == .5).sum()), pf=("points_for", "sum"), pa=("points_against", "sum"))
            table = {t: {"w": T.w[t], "d": T.d[t], "pf": T.pf[t], "pa": T.pa[t]} for t in T.index}
            n_played = int(played.groupby("team").size().mean())
        else:
            rating, table, n_played = dict(prior), {}, 0
        for t in teams:
            rating.setdefault(t, 0.0)
        tau = A.TAU0 * (1 - min(n_played, 23) / A.TAU_FADE)
        sim = A.simulate(teams, table, remaining, rating, tau, n=SIMS, seed=7, finals8=top_finals == 8)
        date = str(played.date.max()) if len(played) else str(reg.date.min())
        for t in teams:
            if t not in pos:
                continue
            r = sim[t]
            rows.append(dict(season=y, week=int(ck), date=date, gp_avg=float(n_played), team=t,
                             p_playoff=r["p8"] if top_finals == 8 else r["p10"], p_top8=r["p8"], p_div=r["p4"], p_seed1=r["p1"], p_pf=r["pf"], p_conf=r["gf"], p_title=r["flag"],
                             y_playoff=int(t in finalists), y_top8=int(pos[t] < 8), y_div=int(pos[t] < 4), y_seed1=int(pos[t] == 0), y_pf=int(t in pf_teams),
                             y_finals=int(t in gf_teams), y_title=int(t == champ)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    G = season_frames()
    first = int(sys.argv[1]) if len(sys.argv) > 1 else A.FIRST + 1
    last = int(sys.argv[2]) if len(sys.argv) > 2 else max(y for y in G if not G[y][G[y].season_type == "FIN"].empty)
    os.makedirs(OUT, exist_ok=True)
    for y in range(first, last + 1):
        D = run_season(G, y)
        if D is None:
            print("skip", y)
            continue
        D.to_csv(os.path.join(OUT, f"afl_{y}.csv"), index=False)
        print("season", y, "checkpoints", D.week.nunique(), flush=True)
