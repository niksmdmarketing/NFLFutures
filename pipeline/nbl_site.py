"""NBL section in the NHL/NFL style: ladder, futures, MVP chances, team stats, players, game logs.

Data: the NBL's public stats feed (Rosetta / Genius Sports) collected by nbl.py, 2012-13 onward. The feed holds
season standings, team season totals (with quarter splits), player season stats, the full fixture with results
and, for recent seasons, player box scores. Season keys are start years (2025 = 2025-26).
"""
import json
import os

import numpy as np
import pandas as pd

import award_model as AM
import sportsite as S
from sportsite import C

ROOT = S.ROOT
SRC = os.path.join(ROOT, "build", "nbl_stats_index.json")
OUT = os.path.join(ROOT, "build", "nbl_site")
SITE = os.path.join(S.SITE, "nbl")
CANON = {"WOL": "ILL"}
HCA = 3.0
GAME_SD = 12.0


def code(c):
    return CANON.get(c, c)


def is_reg(r):
    return str(r.get("phase", "Regular")).lower() in ("regular", "regular season", "")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


# ------------------------------------------------------------------ games

def season_games(Sd):
    """All completed games of a season, flagged regular or finals; plus the remaining regular-season fixture."""
    st = [r for r in (Sd.get("standings") or []) if is_reg(r)]
    reg_n = {code(r["team"]["team_code"]): int(r["won"]) + int(r["lost"]) for r in st}
    rows, todo, seen = [], [], set()
    for g in Sd.get("games") or []:
        if g.get("id") in seen:
            continue
        seen.add(g.get("id"))
        rnd = str(g.get("round") or g.get("override_round") or "")
        if "CUP" in rnd.upper() and "FINAL" in rnd.upper():
            continue                                   # Ignite Cup final: not a ladder game
        h, a = code((g.get("home_team") or {}).get("team_code")), code((g.get("away_team") or {}).get("team_code"))
        if h not in reg_n or a not in reg_n:
            continue
        date = str(g.get("start_time") or "")[:10]
        if g.get("match_status") != "complete":
            if g.get("match_status") == "scheduled" and is_reg(g) and not any(w in rnd.upper() for w in ("PLAY", "SEMI", "CHAMP", "FINAL", "ELIM", "SEED", "QUALIF")):
                todo.append({"date": date, "home": h, "away": a})
            continue
        hs, as_ = num(g.get("home_score")), num(g.get("away_score"))
        if hs != hs or as_ != as_:
            continue
        rows.append({"gid": g.get("id"), "date": date, "rnd": rnd, "h": h, "a": a, "hs": hs, "as": as_,
                     "phase": str(g.get("phase") or "")})
    if not rows:
        return pd.DataFrame(), todo, reg_n
    x = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    if x.phase.str.lower().str.contains("final").any():
        x["fin"] = x.phase.str.lower().str.contains("final")
    else:                                              # older feed: a game is a final once both teams have played their regular count
        cnt = {t: 0 for t in reg_n}
        fin = []
        for h, a in zip(x.h, x.a):
            f_ = cnt[h] >= reg_n[h] and cnt[a] >= reg_n[a]
            fin.append(f_)
            if not f_:
                cnt[h] += 1
                cnt[a] += 1
        x["fin"] = fin
    return x, todo, reg_n


def team_rows(x):
    """One row per team per game."""
    H = pd.DataFrame({"gid": x.gid, "date": x.date, "rnd": x.rnd, "team": x.h, "opp": x.a, "ha": "H", "pf": x.hs, "pa": x["as"], "fin": x.fin})
    A = pd.DataFrame({"gid": x.gid, "date": x.date, "rnd": x.rnd, "team": x.a, "opp": x.h, "ha": "A", "pf": x["as"], "pa": x.hs, "fin": x.fin})
    g = pd.concat([H, A], ignore_index=True).sort_values(["team", "date"])
    g["margin"] = g.pf - g.pa
    g["win"] = (g.margin > 0).astype(float)
    g["res"] = np.where(g.win == 1, "W", "L")
    return g.reset_index(drop=True)


def box_by_game(Sd):
    """Team totals per game from player box scores (recent seasons only)."""
    B = Sd.get("boxscores") or []
    if not B:
        return pd.DataFrame()
    rows = []
    for r in B:
        gm = r.get("_game") or {}
        t = r.get("team") if isinstance(r.get("team"), dict) else {}
        tc = code(t.get("team_code") or r.get("team_code") or "")
        if not tc or not gm.get("id"):
            continue
        rows.append({"gid": gm.get("id"), "team": tc, **{k: num(r.get(k)) for k in (
            "points", "field_goals_made", "field_goals_attempted", "three_points_made", "three_points_attempted", "free_throws_made",
            "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "rebounds", "assists", "turnovers", "steals", "blocks")}})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).groupby(["gid", "team"]).sum(min_count=1).reset_index()


# ------------------------------------------------------------------ team table

def team_table(Sd, g):
    st = [r for r in (Sd.get("standings") or []) if is_reg(r)]
    T = pd.DataFrame([{"team": code(r["team"]["team_code"]), "name": r["team"]["name"], "pos": int(r["position"]), "w": int(r["won"]), "l": int(r["lost"]),
                       "pf": num(r.get("points_for")), "pa": num(r.get("points_against")), "home_w": num(r.get("home_wins")), "home_l": num(r.get("home_losses")),
                       "away_w": num(r.get("away_wins")), "away_l": num(r.get("away_losses")), "streak": num(r.get("streak"))} for r in st])
    if T.empty:
        return T
    T["gp"] = T.w + T.l
    T["wp"] = T.w / T.gp
    T["ppg"], T["oppg"] = T.pf / T.gp, T.pa / T.gp
    T["net"] = T.ppg - T.oppg
    T["home_wp"] = T.home_w / (T.home_w + T.home_l)
    T["away_wp"] = T.away_w / (T.away_w + T.away_l)
    T["pyth"] = 1 / (1 + (T.pa / T.pf) ** 14)
    T["pyth_w"] = T.pyth * T.gp
    T["luck"] = T.w - T.pyth_w
    lead = T.sort_values("pos").iloc[0]
    T["gb"] = ((lead.w - T.w) + (T.l - lead.l)) / 2
    # team season totals (period 0 = whole game, 1-4 = quarters)
    tot = {}
    for r in Sd.get("teams") or []:
        if not is_reg(r) or not isinstance(r.get("team"), dict):
            continue
        k = (code(r["team"]["team_code"]), str(r.get("period")))
        tot[k] = r
    for t in T.team:
        a = tot.get((t, "0"))
        if not a:
            continue
        G = num(a.get("games")) or np.nan
        for k, src in (("fgm", "field_goals_made"), ("fga", "field_goals_attempted"), ("fg3m", "three_points_made"), ("fg3a", "three_points_attempted"),
                       ("ftm", "free_throws_made"), ("fta", "free_throws_attempted"), ("oreb", "offensive_rebounds"), ("dreb", "defensive_rebounds"),
                       ("reb", "rebounds"), ("ast", "assists"), ("stl", "steals"), ("blk", "blocks"), ("tov", "turnovers"), ("pf_", "fouls"), ("pts_all", "points")):
            T.loc[T.team == t, k] = num(a.get(src))
        T.loc[T.team == t, "games_all"] = G
        for q in ("1", "2", "3", "4"):
            b = tot.get((t, q))
            if b:
                T.loc[T.team == t, f"q{q}_ppg"] = num(b.get("points")) / (num(b.get("games")) or np.nan)
    if "fga" in T:
        G = T.games_all
        T["poss_g"] = (T.fga - T.oreb + T.tov + .44 * T.fta) / G
        T["ortg"] = 100 * T.pts_all / (T.fga - T.oreb + T.tov + .44 * T.fta)
        T["efg"] = (T.fgm + .5 * T.fg3m) / T.fga
        T["ts"] = T.pts_all / (2 * (T.fga + .44 * T.fta))
        T["tov_pct"] = T.tov / (T.fga + .44 * T.fta + T.tov)
        T["ftr"] = T.ftm / T.fga
        T["fg3a_rate"] = T.fg3a / T.fga
        T["fg_pct"], T["fg3_pct"], T["ft_pct"] = T.fgm / T.fga, T.fg3m / T.fg3a, T.ftm / T.fta
        for k in ("reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf_", "fg3m"):
            T[k + "_g"] = T[k] / G
        T["ast_tov"] = T.ast / T.tov
        T["drtg"] = 100 * T.pa / (T.poss_g * T.gp)
        T["netrtg"] = T.ortg - T.drtg
    if len(g):
        r = g[~g.fin]
        for name, m in (("close", (r.margin.abs() <= 5)), ("blow", r.margin.abs() >= 15)):
            x = r[m].groupby("team").win
            T[name + "_wp"] = T.team.map(x.mean())
            T[name + "_n"] = T.team.map(x.size())
        top4 = set(T.sort_values("pos").team.head(4))
        T["vs_top4_wp"] = T.team.map(r[r.opp.isin(top4)].groupby("team").win.mean())
        mg = r.groupby("team").margin.mean()
        T["sos"] = T.team.map(r.assign(om=r.opp.map(mg)).groupby("team").om.mean())
        last = r.groupby("team").tail(5).groupby("team")
        T["l5_w"] = T.team.map(last.win.sum())
        T["l5_m"] = T.team.map(last.margin.mean())
        T["home_m"] = T.team.map(r[r.ha == "H"].groupby("team").margin.mean())
        T["away_m"] = T.team.map(r[r.ha == "A"].groupby("team").margin.mean())
    return T.sort_values("pos")


TEAM_COLS = [
    C("pos", "Ladder", "Ladder", "int", lo=True), C("gp", "GP", "Ladder", "int"), C("w", "W", "Ladder", "int"), C("l", "L", "Ladder", "int", lo=True),
    C("wp", "Win %", "Ladder", "pct"), C("gb", "GB", "Ladder", "num1", lo=True), C("streak", "Streak", "Ladder", "pm"), C("l5_w", "Last 5 W", "Ladder", "int"),
    C("ppg", "PTS/G", "Scoring", "num1"), C("oppg", "Opp PTS/G", "Scoring", "num1", lo=True), C("net", "Point diff/G", "Scoring", "pm1"),
    C("pyth_w", "Expected W", "Scoring", "num1", t="Wins the points for and against usually earn"), C("luck", "Luck", "Scoring", "pm1", t="Wins minus expected wins; tends to fade"),
    C("sos", "Opp. point diff/G", "Scoring", "pm1", t="Average point differential of opponents played"), C("l5_m", "Last 5 margin", "Scoring", "pm1"),
    C("ortg", "Off. rating", "Ratings", "num1", t="Points per 100 possessions (all games incl. finals)"), C("drtg", "Def. rating", "Ratings", "num1", lo=True),
    C("netrtg", "Net rating", "Ratings", "pm1"), C("poss_g", "Pace", "Ratings", "num1", t="Possessions per game"),
    C("efg", "eFG%", "Shooting", "pct"), C("ts", "TS%", "Shooting", "pct"), C("fg_pct", "FG%", "Shooting", "pct"), C("fg3_pct", "3P%", "Shooting", "pct"),
    C("ft_pct", "FT%", "Shooting", "pct"), C("fg3a_rate", "3PA rate", "Shooting", "pct"), C("fg3m_g", "3PM/G", "Shooting", "num1"), C("ftr", "FT rate", "Shooting", "num2"),
    C("tov_pct", "TOV%", "Box score", "pct", lo=True), C("reb_g", "REB/G", "Box score", "num1"), C("oreb_g", "OREB/G", "Box score", "num1"),
    C("ast_g", "AST/G", "Box score", "num1"), C("ast_tov", "AST/TOV", "Box score", "num2"), C("stl_g", "STL/G", "Box score", "num1"),
    C("blk_g", "BLK/G", "Box score", "num1"), C("tov_g", "TOV/G", "Box score", "num1", lo=True), C("pf__g", "Fouls/G", "Box score", "num1", lo=True),
    C("q1_ppg", "1st qtr PTS", "Quarters", "num1"), C("q2_ppg", "2nd qtr PTS", "Quarters", "num1"), C("q3_ppg", "3rd qtr PTS", "Quarters", "num1"),
    C("q4_ppg", "4th qtr PTS", "Quarters", "num1"),
    C("home_wp", "Home W%", "Splits", "pct"), C("away_wp", "Away W%", "Splits", "pct"), C("home_m", "Home margin", "Splits", "pm1"),
    C("away_m", "Away margin", "Splits", "pm1"), C("vs_top4_wp", "W% vs top 4", "Splits", "pct"),
    C("close_wp", "Close-game W%", "Splits", "pct", t="Games decided by 5 points or fewer"), C("close_n", "Close games", "Splits", "int"),
    C("blow_wp", "W% in 15+ pt games", "Splits", "pct"),
]

PLAYER_COLS = [
    C("gp", "GP", "Per game", "int"), C("gs", "GS", "Per game", "int"), C("mpg", "MIN", "Per game", "num1"), C("ppg", "PTS", "Per game", "num1"),
    C("rpg", "REB", "Per game", "num1"), C("apg", "AST", "Per game", "num1"), C("spg", "STL", "Per game", "num1"), C("bpg", "BLK", "Per game", "num1"),
    C("tpg", "TOV", "Per game", "num1", lo=True), C("fg3m_g", "3PM", "Per game", "num1"), C("pm_g", "+/-", "Per game", "pm1"),
    C("eff_g", "Efficiency", "Per game", "num1", t="NBL efficiency rating per game"),
    C("fg_pct", "FG%", "Shooting", "pct"), C("fg2_pct", "2P%", "Shooting", "pct"), C("fg3_pct", "3P%", "Shooting", "pct"), C("ft_pct", "FT%", "Shooting", "pct"),
    C("efg", "eFG%", "Shooting", "pct"), C("ts", "TS%", "Shooting", "pct"), C("fga_g", "FGA", "Shooting", "num1"), C("fg3a_g", "3PA", "Shooting", "num1"),
    C("fta_g", "FTA", "Shooting", "num1"),
    C("pts36", "PTS/36", "Per 36", "num1"), C("reb36", "REB/36", "Per 36", "num1"), C("ast36", "AST/36", "Per 36", "num1"), C("ast_tov", "AST/TOV", "Per 36", "num2"),
    C("pts", "PTS", "Totals", "int"), C("reb", "REB", "Totals", "int"), C("ast", "AST", "Totals", "int"), C("stl", "STL", "Totals", "int"),
    C("blk", "BLK", "Totals", "int"), C("fg3m", "3PM", "Totals", "int"), C("mins", "MIN", "Totals", "int"), C("pm", "+/-", "Totals", "pm"),
    C("eff", "Efficiency", "Totals", "int"),
]


def player_table(Sd):
    rows = []
    for p in Sd.get("leaders") or []:
        if not is_reg(p):
            continue
        pl, tm = p.get("player") or {}, p.get("team") or {}
        name = f"{pl.get('first_name', '')} {pl.get('last_name', '')}".strip()
        if not name:
            continue
        g = num(p.get("games"))
        rows.append({"name": name, "team": code(tm.get("team_code")), "gp": g, "gs": num(p.get("games_started")), "mins": num(p.get("minutes")),
                     "pts": num(p.get("points")), "reb": num(p.get("rebounds")), "ast": num(p.get("assists")), "stl": num(p.get("steals")),
                     "blk": num(p.get("blocks")), "tov": num(p.get("turnovers")), "fgm": num(p.get("field_goals_made")), "fga": num(p.get("field_goals_attempted")),
                     "fg2m": num(p.get("two_points_made")), "fg2a": num(p.get("two_points_attempted")), "fg3m": num(p.get("three_points_made")),
                     "fg3a": num(p.get("three_points_attempted")), "ftm": num(p.get("free_throws_made")), "fta": num(p.get("free_throws_attempted")),
                     "pm": num(p.get("plus_minus")), "eff": num(p.get("efficiency"))})
    P = pd.DataFrame(rows)
    if P.empty:
        return P
    P = P[P.gp > 0].drop_duplicates(["name", "team"])
    G = P.gp
    for k, c in (("mpg", "mins"), ("ppg", "pts"), ("rpg", "reb"), ("apg", "ast"), ("spg", "stl"), ("bpg", "blk"), ("tpg", "tov"), ("fg3m_g", "fg3m"),
                 ("pm_g", "pm"), ("eff_g", "eff"), ("fga_g", "fga"), ("fg3a_g", "fg3a"), ("fta_g", "fta")):
        P[k] = P[c] / G
    P["fg_pct"], P["fg2_pct"], P["fg3_pct"], P["ft_pct"] = S.pct(P.fgm, P.fga), S.pct(P.fg2m, P.fg2a), S.pct(P.fg3m, P.fg3a), S.pct(P.ftm, P.fta)
    P["efg"] = S.pct(P.fgm + .5 * P.fg3m, P.fga)
    P["ts"] = S.pct(P.pts, 2 * (P.fga + .44 * P.fta))
    M = P.mins.replace(0, np.nan)
    P["pts36"], P["reb36"], P["ast36"] = 36 * P.pts / M, 36 * P.reb / M, 36 * P.ast / M
    P["ast_tov"] = S.pct(P.ast, P.tov)
    return P.sort_values("pts", ascending=False)


GAME_COLS = [C("pf", "PTS", "Result", "int"), C("pa", "Opp", "Result", "int", lo=True), C("margin", "Margin", "Result", "pm"),
             C("fg_pct", "FG%", "Box score", "pct"), C("fg3m", "3PM", "Box score", "int"), C("fg3a", "3PA", "Box score", "int"),
             C("fg3_pct", "3P%", "Box score", "pct"), C("ftm", "FTM", "Box score", "int"), C("fta", "FTA", "Box score", "int"),
             C("reb", "REB", "Box score", "int"), C("oreb", "OREB", "Box score", "int"), C("ast", "AST", "Box score", "int"),
             C("tov", "TOV", "Box score", "int", lo=True), C("stl", "STL", "Box score", "int"), C("blk", "BLK", "Box score", "int")]


# ------------------------------------------------------------------ ratings and simulation

def srs(g, prior=None, k=6.0):
    teams = sorted(set(g.team) | set(prior or {}))
    ix = {t: i for i, t in enumerate(teams)}
    x = g[g.ha == "H"]
    n = len(teams)
    A = np.zeros((len(x) + n, n))
    b = np.zeros(len(x) + n)
    for r, (t, o, m) in enumerate(zip(x.team, x.opp, x.margin)):
        A[r, ix[t]], A[r, ix[o]] = 1, -1
        b[r] = m - HCA
    lam = np.sqrt(k / 2)
    for t, i in ix.items():
        A[len(x) + i, i] = lam
        b[len(x) + i] = lam * (prior or {}).get(t, 0.0)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    return dict(zip(teams, sol - sol.mean()))


def _p(d):
    from math import erf, sqrt
    return 0.5 * (1 + erf(d / (GAME_SD * sqrt(2))))


def simulate(teams, W0, L0, PD0, todo, rating, tau, n=20000, seed=11):
    rng = np.random.default_rng(seed)
    T = len(teams)
    ix = {t: i for i, t in enumerate(teams)}
    R = np.array([rating.get(t, 0.0) for t in teams])
    H = np.array([ix[g["home"]] for g in todo], int)
    A = np.array([ix[g["away"]] for g in todo], int)
    acc = {k: np.zeros(T) for k in ("p1", "p2", "p6", "semi", "gf", "champ")}
    maxw = int(max(W0.values(), default=0) + len(todo) + 2)
    wins_hist = np.zeros((T, maxw + 1))
    for start in range(0, n, 2000):
        m = min(2000, n - start)
        Rs = R[None, :] + rng.normal(0, tau, (m, T))
        W = np.repeat(np.array([W0.get(t, 0) for t in teams], float)[None, :], m, 0)
        PD = np.repeat(np.array([PD0.get(t, 0) for t in teams], float)[None, :], m, 0)
        if len(todo):
            mu = Rs[:, H] - Rs[:, A] + HCA
            mg = mu + rng.normal(0, GAME_SD, mu.shape)
            hw = (mg > 0).astype(float)
            np.add.at(W.T, H, hw.T)
            np.add.at(W.T, A, (1 - hw).T)
            np.add.at(PD.T, H, mg.T)
            np.add.at(PD.T, A, -mg.T)
        key = W + PD * 1e-4
        order = np.argsort(-key, axis=1)
        pos = np.empty_like(order)
        pos[np.arange(m)[:, None], order] = np.arange(T)[None, :]
        acc["p1"] += (pos < 1).sum(0)
        acc["p2"] += (pos < 2).sum(0)
        acc["p6"] += (pos < 6).sum(0)
        wi = np.clip(W.astype(int), 0, maxw)
        np.add.at(wins_hist, (np.tile(np.arange(T), m), wi.ravel()), 1)
        for s in range(m):
            o, r = order[s], Rs[s]

            def game(a, b, home_a=True):
                return rng.random() < _p(r[a] - r[b] + (HCA if home_a else -HCA))

            def series(a, b, need):        # a has home court (games 1, 3, 5 at a's venue)
                wa = wb = i = 0
                while wa < need and wb < need:
                    if game(a, b, home_a=(i % 2 == 0)):
                        wa += 1
                    else:
                        wb += 1
                    i += 1
                return (a, b) if wa == need else (b, a)
            # play-in: 3v4 winner is 3rd; 5v6 winner meets 3v4 loser for 4th
            s3, l34 = (o[2], o[3]) if game(o[2], o[3]) else (o[3], o[2])
            w56 = o[4] if game(o[4], o[5]) else o[5]
            s4 = l34 if game(l34, w56) else w56
            sf1, _ = series(o[0], s4, 2)
            sf2, _ = series(o[1], s3, 2)
            for t in (o[0], o[1], s3, s4):
                acc["semi"][t] += 1
            acc["gf"][sf1] += 1
            acc["gf"][sf2] += 1
            first = sf1 if key[s, sf1] >= key[s, sf2] else sf2
            other = sf2 if first == sf1 else sf1
            champ, _ = series(first, other, 3)
            acc["champ"][champ] += 1
    out = {}
    for t, i in ix.items():
        wh = wins_hist[i] / n
        cdf = np.cumsum(wh)
        out[t] = {**{k: float(v[i] / n) for k, v in acc.items()}, "w_mean": float((wh * np.arange(len(wh))).sum()),
                  "w_p10": int(np.searchsorted(cdf, .1)), "w_p90": int(np.searchsorted(cdf, .9)),
                  "over": (1 - np.concatenate([[0], cdf[:-1]])).tolist()}
    return out


# ------------------------------------------------------------------ build

def build_data():
    if not os.path.exists(SRC):
        S.log("NBL site: no source data")
        return
    D = json.load(open(SRC))
    os.makedirs(OUT, exist_ok=True)
    seasons, po_seasons, hist, tables, players = [], [], {}, {}, []
    names = {}
    cur_info = None
    for key in sorted(D.get("seasons", {}), key=int):
        y = int(key)
        Sd = D["seasons"][key]
        x, todo, reg_n = season_games(Sd)
        if not reg_n:
            continue
        g = team_rows(x) if len(x) else pd.DataFrame()
        T = team_table(Sd, g)
        if T.empty:
            continue
        names.update(dict(zip(T.team, T.name)))
        box = box_by_game(Sd)
        S.write_json(OUT, f"team_{y}.json", S.columnar(T, y, ["team", "name"], TEAM_COLS))
        seasons.append(y)
        tables[y] = T
        if len(g):
            gg = g.merge(box.rename(columns={"points": "box_pts"}), on=["gid", "team"], how="left") if len(box) else g
            ren = {"field_goals_made": "fgm", "field_goals_attempted": "fga", "three_points_made": "fg3m", "three_points_attempted": "fg3a",
                   "free_throws_made": "ftm", "free_throws_attempted": "fta", "offensive_rebounds": "oreb", "rebounds": "reb", "assists": "ast",
                   "turnovers": "tov", "steals": "stl", "blocks": "blk"}
            gg = gg.rename(columns=ren)
            if "fga" in gg:
                gg["fg_pct"], gg["fg3_pct"] = S.pct(gg.fgm, gg.fga), S.pct(gg.fg3m, gg.fg3a)
            S.write_json(OUT, f"games_{y}.json", S.columnar(gg[~gg.fin], y, ["date", "team", "opp", "ha", "res"], GAME_COLS))
            if gg.fin.any():
                S.write_json(OUT, f"games_{y}p.json", S.columnar(gg[gg.fin], y, ["date", "team", "opp", "ha", "res"], GAME_COLS))
                f = g[g.fin].groupby("team").agg(gp=("win", "size"), w=("win", "sum"), pf=("pf", "sum"), pa=("pa", "sum"))
                f["l"], f["wp"] = f.gp - f.w, f.w / f.gp
                f["ppg"], f["oppg"] = f.pf / f.gp, f.pa / f.gp
                f["net"] = f.ppg - f.oppg
                f = f.reset_index()
                f["name"] = f.team.map(dict(zip(T.team, T.name)))
                S.write_json(OUT, f"team_{y}p.json", S.columnar(f, y, ["team", "name"], [c for c in TEAM_COLS if c["k"] in ("gp", "w", "l", "wp", "ppg", "oppg", "net")]))
                po_seasons.append(y)
            hist[y] = g[~g.fin]
        P = player_table(Sd)
        if len(P):
            S.write_json(OUT, f"players_{y}.json", S.columnar(P, y, ["name", "team"], PLAYER_COLS))
            players.append(P.assign(season=y))
        cur_info = (y, x, todo, reg_n, T)
    seasons.sort(reverse=True)
    po_seasons.sort(reverse=True)
    y, x, todo, reg_n, T = cur_info
    in_progress = bool(todo) or (len(x) and not x.fin.any())
    S.write_json(OUT, "futures.json", futures(y, hist, tables, todo, T, names))
    S.write_json(OUT, "awards.json", awards(y if in_progress else y + 1, players, tables))
    meta = {"season": y, "in_progress": bool(in_progress), "seasons": seasons, "po_seasons": po_seasons, "teams": names,
            "updated_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M+00:00"), "groupings": [{"name": "Ladder"}], "cfg": CFG}
    S.write_json(OUT, "meta.json", meta)
    S.log("NBL site data", len(seasons), "seasons", len(po_seasons), "with finals")


def futures(y, hist, tables, todo, T, names):
    prev = hist.get(y - 1)
    prior = {t: .5 * v for t, v in srs(prev).items()} if prev is not None and len(prev) else {}
    g = hist.get(y, pd.DataFrame())
    rating = srs(g, prior=prior) if len(g) else prior
    teams = list(T.team)
    W0 = dict(zip(T.team, T.w))
    L0 = dict(zip(T.team, T.l))
    PD0 = dict(zip(T.team, T.pf - T.pa))
    gp = float(np.mean([W0[t] + L0[t] for t in teams]))
    total = gp + 2 * len(todo) / max(len(teams), 1)
    tau = 4.0 * max(0.15, 1 - gp / max(total, 1))
    res = simulate(teams, W0, L0, PD0, todo, rating, tau)
    left = {t: {"left": 0, "road_left": 0, "opp": []} for t in teams}
    for gm in todo:
        for t, o, road in ((gm["home"], gm["away"], 0), (gm["away"], gm["home"], 1)):
            if t in left:
                left[t]["left"] += 1
                left[t]["road_left"] += road
                left[t]["opp"].append(rating.get(o, 0.0))
    rows = [{"team": t, "name": names.get(t, t), "group": "", "left": left[t]["left"], "road_left": left[t]["road_left"],
             "sos_left": float(np.mean(left[t]["opp"])) if left[t]["opp"] else None, "gp": int(W0[t] + L0[t]), "record": f"{int(W0[t])}-{int(L0[t])}",
             "rating": rating.get(t, 0.0), **{k: res[t][k] for k in ("w_mean", "w_p10", "w_p90", "over", "p1", "p2", "p6", "semi", "gf", "champ")}}
            for t in teams]
    bt = backtest(hist)
    status = f"{y}-{str(y + 1)[2:]} season — " + (f"through about {gp:.0f} games per team, {len(todo)} regular-season games left" if todo else "regular season complete")
    return {"season": y, "status": status, "sims": 20000, "main": "champ",
            "intro": "Ladder and title chances from simulating every remaining game on the real fixture, the play-in (3v4, 5v6, then for 4th), best-of-three semi-finals and the best-of-five Grand Final series.",
            "proj": {"k": "w_mean", "l": "Proj. wins", "lo": "w_p10", "hi": "w_p90", "f": "num1"},
            "rating_note": "Points per game better (+) or worse (−) than an average team on a neutral court",
            "extra": [{"k": "left", "l": "Games left", "f": "int"}, {"k": "road_left", "l": "Road left", "f": "int"},
                      {"k": "sos_left", "l": "Remaining SOS", "f": "pm1", "t": "Average rating of the opponents still to play (+ = harder)"}],
            "cols": [{"k": "p6", "l": "Finals (top 6)"}, {"k": "p2", "l": "Top 2", "t": "Straight to the semi-finals"},
                     {"k": "p1", "l": "Minor premiers"}, {"k": "semi", "l": "Semi-finals"}, {"k": "gf", "l": "Grand Final"},
                     {"k": "champ", "l": "Champions"}],
            "line": {"label": "Win total", "unit": "wins", "min": 0}, "backtest_html": bt,
            "about": ["Rating is opponent-adjusted point differential per game: last season's, pulled halfway back to average and worth six games, blended with this season's results.",
                      f"Each simulation moves every team's rating by a random amount (typical size {tau:.1f} points) before playing, and single games vary by about {GAME_SD:.0f} points; home court is worth about {HCA:.0f}.",
                      "It does not know about imports arriving or leaving, injuries or coaching changes — the main reasons to disagree with it.",
                      "Ladder ties are split by points difference (the official tie-break uses head-to-head first)."],
            "teams": rows}


def backtest(hist):
    """Pre-season wins forecast for each past season (rating from the previous season only, actual fixture)
    versus a naive 'last season's win rate pulled halfway to .500'."""
    ys = sorted(hist)
    em, en = [], []
    for y in ys:
        prev, now = hist.get(y - 1), hist[y]
        if prev is None or not len(prev) or not len(now):
            continue
        rating = {t: .5 * v for t, v in srs(prev).items()}
        pw = prev.groupby("team").win.mean()
        x = now[now.ha == "H"]
        exp = {t: 0.0 for t in now.team.unique()}
        for h, a in zip(x.team, x.opp):
            p = _p((rating.get(h, 0) - rating.get(a, 0) + HCA) / 1.1)
            exp[h] += p
            exp[a] += 1 - p
        s = now.groupby("team").agg(w=("win", "sum"), n=("win", "size"))
        for t in s.index:
            em.append(abs(exp[t] - s.w[t]))
            en.append(abs((.5 * pw.get(t, .5) + .25) * s.n[t] - s.w[t]))
    if not em:
        return ""
    return (f'<p class="note">Pre-season test on {len(ys) - 1} past seasons (each forecast uses only the previous season and the real fixture): '
            f"off by {np.mean(em):.2f} wins per team on average, versus {np.mean(en):.2f} for 'last season's win rate, pulled halfway to .500'. "
            "In-season numbers lean more on current results as games are played. Not compared with betting markets.</p>")


def awards(cur, players, tables):
    from trends_awards import NBL_MVP, norm
    P = pd.concat(players, ignore_index=True) if players else pd.DataFrame()
    if P.empty:
        return {"awards": {}}
    tw = pd.concat([t.assign(season=y)[["season", "team", "wp", "pos"]] for y, t in tables.items()])
    P = P.merge(tw, on=["season", "team"], how="left")
    P["L"] = P.groupby("season").gp.transform("max")
    P["gshare"] = P.gp / P.L
    pool = P[P.gshare >= .5].sort_values("eff_g", ascending=False).groupby("season").head(15).copy()
    pool["win"] = [np.nan if s == cur else float(norm(NBL_MVP.get(s, "")) == norm(n)) for s, n in zip(pool.season, pool.name)]
    feats = ["eff_g", "ppg", "pm_g", "wp", "gshare"]
    pool[feats] = pool[feats].fillna(pool[feats].median())
    hist = pool[(pool.season != cur) & pool.season.isin(NBL_MVP)]
    bt = AM.loso(hist, feats, leader_col="ppg")
    if bt:
        bt["leader_label"] = "scoring leader"
    beta = AM.fit(hist, feats)
    show = [C("gp", "GP", "", "int"), C("mpg", "MIN", "", "num1"), C("ppg", "PTS", "", "num1"), C("rpg", "REB", "", "num1"), C("apg", "AST", "", "num1"),
            C("eff_g", "Eff.", "", "num1"), C("ts", "TS%", "", "pct"), C("pm_g", "+/-", "", "pm1"), C("wp", "Team W%", "", "pct")]
    now = pool[pool.season == cur].copy()
    cur_rows = []
    if len(now):
        now["prob"] = AM.predict(now, feats, beta)
        cur_rows = now.sort_values("prob", ascending=False).head(12)[["name", "team", "prob"] + [c["k"] for c in show]].to_dict("records")
    past = []
    for y, nm in sorted(NBL_MVP.items(), reverse=True):
        x = P[(P.season == y) & (P.name.map(norm) == norm(nm))]
        r = x.iloc[0] if len(x) else None
        past.append({"season": y, "name": nm, "team": r.team if r is not None else "", **({c["k"]: r[c["k"]] for c in show} if r is not None else {})})
    return {"order": ["MVP"], "awards": {"MVP": {
        "title": "NBL Most Valuable Player (Andrew Gaze Trophy)", "short": "MVP", "backtest": bt, "cols": show, "current": cur_rows, "past": past,
        "note": "Chances from a model fitted on every MVP since 2012-13 using efficiency, scoring, plus-minus, team win rate and games played (see Trends: scoring titles and top-4 teams carry extra weight with voters).",
        "empty": "No current-season numbers yet."}}}


CFG = {
    "sport": "NBL", "season_style": "split_start", "po_label": "Finals",
    "ids": {"team": ["team", "name"], "players": ["name", "team"], "games": ["date", "team", "opp", "ha", "res"]},
    "pinned": ["gp"], "team_sort": "wp", "noshade": ["gp", "pos", "close_n", "gs"], "po_kinds": ["team", "games"],
    "key": {"teams": ["gp", "w", "wp", "net", "netrtg", "ortg", "drtg", "efg", "ts", "tov_pct", "fg3_pct", "fg3a_rate", "luck", "close_wp", "home_m", "away_m", "l5_m"],
            "players": ["gp", "mpg", "ppg", "rpg", "apg", "eff_g", "ts", "fg3_pct", "pm_g", "spg", "bpg"]},
    "standings": {"sort": "wp", "order": [["wp", 1], ["net", 1]],
                  "cols": ["gp", "w", "l", "wp", "gb", "streak", "l5_w", "ppg", "oppg", "net", "pyth_w", "luck", "home_wp", "away_wp", "netrtg", "close_wp", "vs_top4_wp"],
                  "alias": {"wp": "W%", "pyth_w": "Exp W", "home_wp": "Home", "away_wp": "Away", "netrtg": "Net rtg", "close_wp": "Close W%", "vs_top4_wp": "vs top 4", "l5_w": "L5"},
                  "note": "Ordered by win % then point differential (the official ladder uses head-to-head first). Top 2 go straight to the semi-finals; 3rd to 6th play the play-in. Exp W is what the scores usually earn; Luck is wins minus that. Ratings use all games including finals."},
    "players": {"sort": "pts", "gp_key": "gp", "min_default": 5, "note": "Season stats from the NBL feed (regular season)."},
    "games": {"results": [["W", "Wins"], ["L", "Losses"]], "pinned": ["pf", "pa"],
              "note": "Box-score columns are filled for recent seasons, where the feed has match box scores."},
    "team_note": "Ratings and box-score stats come from the NBL's team totals, which include finals games.",
}

PAGES = [("index", "Ladder", "NBL ladder", "Records, ratings, luck and splits for every season since 2012-13."),
         ("futures", "Futures", "NBL futures", "Championship, Grand Final, semi-final, top-2, finals and minor premiership chances from the real fixture, plus a win-total over/under tool."),
         ("awards", "Awards", "NBL MVP", "MVP chances from a model tested on every season since 2012-13, with past winners."),
         ("teams", "Team stats", "NBL team stats", "Scoring, ratings, shooting, box score, quarter scoring and splits. Season table or year by year."),
         ("players", "Players", "NBL player stats", "Per game, shooting, per 36 and totals for every player since 2012-13."),
         ("games", "Games", "NBL game logs", "Every team game since 2012-13, regular season and finals.")]


def build_site():
    S.build_pages(SITE, "NBL", "Futures", PAGES, data_src=OUT)
    for fn in ("stats.js", os.path.join("data", "stats_index.json")):
        p = os.path.join(SITE, fn)          # the raw feed (28 MB+) is not used by these pages and is too big for Pages
        if os.path.exists(p):
            os.remove(p)
    S.log("NBL site pages written")


if __name__ == "__main__":
    build_data()
    build_site()
