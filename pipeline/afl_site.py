"""AFL section in the NHL/NFL style: ladder, futures, awards (Brownlow, Coleman), team stats, players, game logs.

Data: the fitzRoy archive collected by afl.py (AFL Tables + Footywire), 2012 onward (18-team era). Fixture for
the season ahead from the Squiggle API when available. Seasons are calendar years.
"""
import gzip
import json
import os
import urllib.request

import numpy as np
import pandas as pd

import award_model as AM
import sportsite as S
from sportsite import C

ROOT = S.ROOT
SRC = os.path.join(ROOT, "build", "afl")
OUT = os.path.join(ROOT, "build", "afl_site")
SITE = os.path.join(S.SITE, "afl")
DATA = os.path.join(ROOT, "data", "afl")
FIRST = 2012
CODES = {"Adelaide": "ADE", "Brisbane Lions": "BRI", "Carlton": "CAR", "Collingwood": "COL", "Essendon": "ESS", "Fremantle": "FRE",
         "Geelong": "GEE", "Gold Coast": "GCS", "Greater Western Sydney": "GWS", "Hawthorn": "HAW", "Melbourne": "MEL",
         "North Melbourne": "NTH", "Port Adelaide": "PTA", "Richmond": "RIC", "St Kilda": "STK", "Sydney": "SYD",
         "West Coast": "WCE", "Western Bulldogs": "WBD"}
NAMES = {v: k for k, v in CODES.items()}
SQUIGGLE_NAMES = {"Brisbane": "BRI", "GWS": "GWS", "Greater Western Sydney": "GWS", "Gold Coast": "GCS", "West Coast": "WCE",
                  "Western Bulldogs": "WBD", "Footscray": "WBD", "North Melbourne": "NTH", "Port Adelaide": "PTA", "St Kilda": "STK"}
HGA = 7.0          # points
GAME_SD = 32.0     # spread of a single game's margin around the expected margin (was 36; tuned on match outcomes 2012-2026, Oct 2026)
K_PRIOR = 12.0     # games of weight on the preseason prior (was 8)
PRIOR_REG = 0.65   # share of last season's rating carried into the new season (was 0.55)
STATS = ["disposals", "kicks", "handballs", "marks", "tackles", "clearances", "centre_clearances", "stoppage_clearances",
         "inside_50s", "rebound_50s", "contested_possessions", "uncontested_possessions", "contested_marks", "marks_inside_50",
         "intercepts", "turnovers", "metres_gained", "score_involvements", "hitouts", "clangers", "free_kicks_for",
         "free_kicks_against", "effective_disposals", "tackles_inside_50", "goal_assists", "one_percenters", "goals", "behinds"]


def code(name):
    return CODES.get(name) or SQUIGGLE_NAMES.get(name) or name


def load_season(y):
    p = os.path.join(SRC, f"season_{y}.json.gz")
    if not os.path.exists(p):
        return None
    return json.load(gzip.open(p))


# ------------------------------------------------------------------ team games

def team_games(d, y):
    tg = pd.DataFrame(d.get("team_games") or [])
    if tg.empty:
        return tg
    tg = tg[tg.season_type.isin(["REG", "FIN"])].copy()
    tg["team"] = tg.team.map(code)
    tg["opp"] = tg.opponent.map(code)
    for c in STATS + ["points_for", "points_against", "q1_for", "q1_against", "q2_for", "q2_against", "q3_for", "q3_against", "q4_for", "q4_against"]:
        tg[c] = pd.to_numeric(tg[c], errors="coerce") if c in tg else np.nan
    o = tg[["match_id", "team"] + STATS].rename(columns={c: "o_" + c for c in STATS}).rename(columns={"team": "opp"})
    tg = tg.merge(o, on=["match_id", "opp"], how="left")
    tg["margin"] = tg.points_for - tg.points_against
    tg["win"] = np.where(tg.margin > 0, 1.0, np.where(tg.margin == 0, .5, 0.0))
    tg["res"] = np.where(tg.margin > 0, "W", np.where(tg.margin == 0, "D", "L"))
    tg["ha"] = tg.home_away.astype(str).str[0].str.upper().map({"H": "H", "A": "A"}).fillna("N")
    tg["season"] = y
    tg["date"] = tg.date.astype(str).str[:10]
    tg["rnd"] = tg["round"].astype(str)
    return tg.sort_values(["team", "date"]).reset_index(drop=True)


def team_season(g):
    s = g.groupby("team")
    a = pd.DataFrame({"gp": s.size(), "w": s.apply(lambda x: (x.margin > 0).sum()), "d": s.apply(lambda x: (x.margin == 0).sum())})
    a["l"] = a.gp - a.w - a.d
    a["pts"] = 4 * a.w + 2 * a.d
    a["pf"], a["pa"] = s.points_for.sum(), s.points_against.sum()
    a["pct"] = 100 * a.pf / a.pa
    a["wp"] = (a.w + .5 * a.d) / a.gp
    a["pf_g"], a["pa_g"] = a.pf / a.gp, a.pa / a.gp
    a["margin_g"] = a.pf_g - a.pa_g
    a["pyth"] = 1 / (1 + (a.pa / a.pf) ** 3.9)
    a["pyth_w"] = a.pyth * a.gp
    a["luck"] = (a.w + .5 * a.d) - a.pyth_w
    for q in (1, 2, 3, 4):
        a[f"q{q}_m"] = (s[f"q{q}_for"].sum() - s[f"q{q}_against"].sum()) / a.gp
    for st in STATS:
        a[st + "_g"] = s[st].sum() / a.gp
        a["o_" + st + "_g"] = s["o_" + st].sum() / a.gp
    for st in ("inside_50s", "clearances", "contested_possessions", "tackles", "marks_inside_50", "intercepts", "metres_gained",
               "uncontested_possessions", "score_involvements", "hitouts", "rebound_50s"):
        a[st + "_diff"] = a[st + "_g"] - a["o_" + st + "_g"]
    a["acc"] = s.goals.sum() / (s.goals.sum() + s.behinds.sum())
    a["o_acc"] = s.o_goals.sum() / (s.o_goals.sum() + s.o_behinds.sum())
    a["shots_g"] = (s.goals.sum() + s.behinds.sum()) / a.gp
    a["o_shots_g"] = (s.o_goals.sum() + s.o_behinds.sum()) / a.gp
    a["pts_per_i50"] = a.pf / s.inside_50s.sum()
    a["o_pts_per_i50"] = a.pa / s.o_inside_50s.sum()
    a["de"] = s.effective_disposals.sum() / s.disposals.sum()
    for name, m in (("home", g.ha == "H"), ("away", g.ha == "A"), ("close", g.margin.abs() <= 12), ("big", g.margin.abs() >= 40)):
        x = g[m].groupby("team").win
        a[name + "_wp"] = x.mean()
        a[name + "_n"] = x.size()
    wp = a.wp.to_dict()
    gv = g.assign(owp=g.opp.map(wp))
    a["vs_top8_wp"] = gv[gv.opp.map(a.wp.rank(ascending=False)) <= 8].groupby("team").win.mean()
    mg = a.margin_g.to_dict()
    a["sos"] = g.assign(om=g.opp.map(mg)).groupby("team").om.mean()
    last = g.groupby("team").tail(5).groupby("team")
    a["l5_w"] = last.win.sum()
    a["l5_m"] = last.margin.mean()
    a = a.reset_index()
    a["name"] = a.team.map(NAMES)
    a = a.sort_values(["pts", "pct"], ascending=False).reset_index(drop=True)
    a["ladder"] = np.arange(1, len(a) + 1)
    return a


TEAM_COLS = [
    C("ladder", "Ladder", "Ladder", "int", lo=True), C("gp", "P", "Ladder", "int"), C("w", "W", "Ladder", "int"), C("l", "L", "Ladder", "int", lo=True),
    C("d", "D", "Ladder", "int"), C("pts", "Pts", "Ladder", "int"), C("pct", "%", "Ladder", "num1", t="Percentage: points for ÷ points against × 100"),
    C("wp", "Win %", "Ladder", "pct"), C("l5_w", "Last 5 W", "Ladder", "num1"),
    C("pf_g", "Score/G", "Scoring", "num1"), C("pa_g", "Conceded/G", "Scoring", "num1", lo=True), C("margin_g", "Margin/G", "Scoring", "pm1"),
    C("pyth_w", "Expected W", "Scoring", "num1", t="Wins that the scores for and against usually earn"),
    C("luck", "Luck", "Scoring", "pm1", t="Actual wins minus expected wins; big positive numbers tend to fade"),
    C("sos", "Opp. margin/G", "Scoring", "pm1", t="Average margin per game of the opponents played (strength of schedule)"),
    C("l5_m", "Last 5 margin", "Scoring", "pm1"),
    C("shots_g", "Scoring shots/G", "Scoring", "num1"), C("o_shots_g", "Opp scoring shots/G", "Scoring", "num1", lo=True),
    C("acc", "Accuracy", "Scoring", "pct", t="Goals ÷ scoring shots"), C("o_acc", "Opp accuracy", "Scoring", "pct", lo=True),
    C("pts_per_i50", "Pts per inside 50", "Scoring", "num2"), C("o_pts_per_i50", "Opp pts per inside 50", "Scoring", "num2", lo=True),
    C("q1_m", "1st qtr margin", "Quarters", "pm1"), C("q2_m", "2nd qtr margin", "Quarters", "pm1"), C("q3_m", "3rd qtr margin", "Quarters", "pm1"),
    C("q4_m", "4th qtr margin", "Quarters", "pm1"),
    C("inside_50s_diff", "Inside 50 diff", "Differentials", "pm1"), C("clearances_diff", "Clearance diff", "Differentials", "pm1"),
    C("contested_possessions_diff", "Contested poss diff", "Differentials", "pm1"), C("uncontested_possessions_diff", "Uncontested poss diff", "Differentials", "pm1"),
    C("tackles_diff", "Tackle diff", "Differentials", "pm1"), C("marks_inside_50_diff", "Marks inside 50 diff", "Differentials", "pm1"),
    C("intercepts_diff", "Intercept diff", "Differentials", "pm1"), C("metres_gained_diff", "Metres gained diff", "Differentials", "pm"),
    C("score_involvements_diff", "Score involvement diff", "Differentials", "pm1"), C("hitouts_diff", "Hitout diff", "Differentials", "pm1"),
    C("rebound_50s_diff", "Rebound 50 diff", "Differentials", "pm1"),
    C("disposals_g", "Disposals", "Possession", "num1"), C("kicks_g", "Kicks", "Possession", "num1"), C("handballs_g", "Handballs", "Possession", "num1"),
    C("de", "Disposal eff.", "Possession", "pct"), C("contested_possessions_g", "Contested poss", "Possession", "num1"),
    C("uncontested_possessions_g", "Uncontested poss", "Possession", "num1"), C("marks_g", "Marks", "Possession", "num1"),
    C("contested_marks_g", "Contested marks", "Possession", "num1"), C("turnovers_g", "Turnovers", "Possession", "num1", lo=True),
    C("clangers_g", "Clangers", "Possession", "num1", lo=True), C("metres_gained_g", "Metres gained", "Possession", "num0"),
    C("clearances_g", "Clearances", "Stoppages & pressure", "num1"), C("centre_clearances_g", "Centre clearances", "Stoppages & pressure", "num1"),
    C("stoppage_clearances_g", "Stoppage clearances", "Stoppages & pressure", "num1"), C("hitouts_g", "Hitouts", "Stoppages & pressure", "num1"),
    C("tackles_g", "Tackles", "Stoppages & pressure", "num1"), C("tackles_inside_50_g", "Tackles inside 50", "Stoppages & pressure", "num1"),
    C("intercepts_g", "Intercepts", "Stoppages & pressure", "num1"), C("one_percenters_g", "One percenters", "Stoppages & pressure", "num1"),
    C("inside_50s_g", "Inside 50s", "Territory", "num1"), C("o_inside_50s_g", "Opp inside 50s", "Territory", "num1", lo=True),
    C("marks_inside_50_g", "Marks inside 50", "Territory", "num1"), C("rebound_50s_g", "Rebound 50s", "Territory", "num1"),
    C("score_involvements_g", "Score involvements", "Territory", "num1"),
    C("free_kicks_for_g", "Frees for", "Discipline", "num1"), C("free_kicks_against_g", "Frees against", "Discipline", "num1", lo=True),
    C("home_wp", "Home W%", "Splits", "pct"), C("away_wp", "Away W%", "Splits", "pct"), C("vs_top8_wp", "W% vs top 8", "Splits", "pct"),
    C("close_wp", "Close-game W%", "Splits", "pct", t="Games decided by 12 points (two goals) or fewer"), C("close_n", "Close games", "Splits", "int"),
    C("big_wp", "W% in 40+ pt games", "Splits", "pct"),
]


GAME_COLS = [
    C("points_for", "Score", "Result", "int"), C("points_against", "Opp", "Result", "int", lo=True), C("margin", "Margin", "Result", "pm"),
    C("q1_m", "Q1", "Result", "pm"), C("q2_m", "Q2", "Result", "pm"), C("q3_m", "Q3", "Result", "pm"), C("q4_m", "Q4", "Result", "pm"),
    C("goals", "Goals", "Result", "int"), C("behinds", "Behinds", "Result", "int"),
    C("inside_50s", "Inside 50s", "Territory", "int"), C("o_inside_50s", "Opp I50", "Territory", "int", lo=True),
    C("marks_inside_50", "Marks I50", "Territory", "int"), C("rebound_50s", "Rebound 50s", "Territory", "int"),
    C("clearances", "Clearances", "Contest", "int"), C("o_clearances", "Opp clearances", "Contest", "int", lo=True),
    C("contested_possessions", "Contested poss", "Contest", "int"), C("o_contested_possessions", "Opp contested", "Contest", "int", lo=True),
    C("tackles", "Tackles", "Contest", "int"), C("intercepts", "Intercepts", "Contest", "int"), C("hitouts", "Hitouts", "Contest", "int"),
    C("disposals", "Disposals", "Possession", "int"), C("de", "Disposal eff.", "Possession", "pct"), C("metres_gained", "Metres gained", "Possession", "int"),
    C("turnovers", "Turnovers", "Possession", "int", lo=True), C("score_involvements", "Score involvements", "Possession", "int"),
]


PLAYER_COLS = [
    C("games", "GP", "Per game", "int"), C("disposals_pg", "Disposals", "Per game", "num1"), C("kicks_pg", "Kicks", "Per game", "num1"),
    C("handballs_pg", "Handballs", "Per game", "num1"), C("marks_pg", "Marks", "Per game", "num1"), C("goals_pg", "Goals", "Per game", "num2"),
    C("behinds_pg", "Behinds", "Per game", "num2"), C("tackles_pg", "Tackles", "Per game", "num1"), C("clearances_pg", "Clearances", "Per game", "num1"),
    C("inside_50s_pg", "Inside 50s", "Per game", "num1"), C("hitouts_pg", "Hitouts", "Per game", "num1"),
    C("contested_possessions_pg", "Contested poss", "Advanced", "num1"), C("uncontested_possessions_pg", "Uncontested poss", "Advanced", "num1"),
    C("disposal_efficiency_pct", "Disposal eff.", "Advanced", "num1", t="Per cent of disposals that are effective"),
    C("metres_gained_pg", "Metres gained", "Advanced", "num0"), C("score_involvements_pg", "Score involvements", "Advanced", "num1"),
    C("intercepts_pg", "Intercepts", "Advanced", "num1"), C("centre_clearances_pg", "Centre clearances", "Advanced", "num1"),
    C("stoppage_clearances_pg", "Stoppage clearances", "Advanced", "num1"), C("contested_marks_pg", "Contested marks", "Advanced", "num1"),
    C("marks_inside_50_pg", "Marks inside 50", "Advanced", "num1"), C("goal_assists_pg", "Goal assists", "Advanced", "num1"),
    C("tackles_inside_50_pg", "Tackles inside 50", "Advanced", "num1"), C("turnovers_pg", "Turnovers", "Advanced", "num1", lo=True),
    C("time_on_ground_pct", "Time on ground %", "Advanced", "num1"),
    C("afl_fantasy_points_pg", "AFL Fantasy", "Fantasy", "num1"), C("supercoach_points_pg", "SuperCoach", "Fantasy", "num1"),
    C("goals", "Goals", "Totals", "int"), C("behinds", "Behinds", "Totals", "int"), C("disposals", "Disposals", "Totals", "int"),
    C("tackles", "Tackles", "Totals", "int"), C("clearances", "Clearances", "Totals", "int"), C("brownlow_votes", "Brownlow votes", "Totals", "int"),
    C("scoring_accuracy_pct", "Goal accuracy %", "Totals", "num1"),
    C("age", "Age", "Bio", "num1"), C("career_games", "Career games", "Bio", "int"),
]


PSTATS = ["kicks", "marks", "handballs", "disposals", "goals", "behinds", "hitouts", "tackles", "rebound_50s", "inside_50s",
          "clearances", "clangers", "free_kicks_for", "free_kicks_against", "brownlow_votes", "contested_possessions",
          "uncontested_possessions", "contested_marks", "marks_inside_50", "one_percenters", "bounces", "goal_assists"]
ASTATS = ["effective_disposals", "afl_fantasy_points", "supercoach_points", "centre_clearances", "stoppage_clearances",
          "score_involvements", "metres_gained", "turnovers", "intercepts", "tackles_inside_50"]


def _pkey(n):
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode().lower()
    parts = re.sub(r"[^a-z ]", "", n.replace("-", "")).split()
    return (parts[-1] + "_" + parts[0][:1]) if parts else n


def player_table(d, st):
    """Player seasons rebuilt from the game logs, one row per player per club (the archive's own season table merges
    different players who share a name when the source has no player id)."""
    G = pd.DataFrame(d.get("player_games") or [])
    if G.empty:
        return G
    G = G[G.season_type == st].copy()
    for c in PSTATS + ["time_on_ground", "age", "career_games"]:
        G[c] = pd.to_numeric(G[c], errors="coerce") if c in G else np.nan
    g = G.groupby(["player", "team"])
    P = g[PSTATS].sum(min_count=1)
    P["games"] = g.size()
    P["time_on_ground_pct"] = g.time_on_ground.mean()
    P["age"] = g.age.max()
    P["career_games"] = g.career_games.max()
    A = pd.DataFrame(d.get("advanced_player_games") or [])
    if len(A):
        # AFL Tables and Footywire spell names differently (Nat/Nathan, Ollie/Oliver): match each game on date, club,
        # surname and first initial, then credit the Footywire numbers to the AFL Tables player
        A = A[A.season_type == st].copy()
        for c in ASTATS + ["disposals"]:
            A[c] = pd.to_numeric(A[c], errors="coerce") if c in A else np.nan
        A["k"] = A.date.astype(str).str[:10] + "|" + A.team.astype(str) + "|" + A.player.map(_pkey)
        A = A.drop_duplicates("k", keep=False)
        G["k"] = G.date.astype(str).str[:10] + "|" + G.team.astype(str) + "|" + G.player.map(_pkey)
        M = G[["player", "team", "k"]].merge(A[["k", "disposals"] + ASTATS], on="k", how="inner")
        ag = M.groupby(["player", "team"])
        X = ag[ASTATS].sum(min_count=1)
        X["adv_games"] = ag.size()
        X["adv_disposals"] = ag.disposals.sum(min_count=1)
        P = P.join(X, how="left")
        P["disposal_efficiency_pct"] = 100 * P.effective_disposals / P.adv_disposals
        for c in ASTATS:
            P[c + "_pg"] = P[c] / P.adv_games
    for c in PSTATS:
        P[c + "_pg"] = P[c] / P.games
    P["scoring_accuracy_pct"] = 100 * P.goals / (P.goals + P.behinds).replace(0, np.nan)
    P = P.reset_index()
    P["name"] = P.player
    P["team"] = P.team.map(code)
    return P.sort_values("disposals", ascending=False)


# ------------------------------------------------------------------ ratings, fixture, simulation

def srs(g, prior=None, k=8.0):
    """Opponent-adjusted margin per game (least squares with home advantage), shrunk to a prior with weight k games."""
    teams = sorted(set(g.team) | set(prior or {}))
    ix = {t: i for i, t in enumerate(teams)}
    x = g[g.ha == "H"]
    n = len(teams)
    A = np.zeros((len(x) + n, n))
    b = np.zeros(len(x) + n)
    for r, (t, o, m) in enumerate(zip(x.team, x.opp, x.margin)):
        A[r, ix[t]], A[r, ix[o]] = 1, -1
        b[r] = m - HGA
    lam = np.sqrt(k / 2)
    for t, i in ix.items():
        A[len(x) + i, i] = lam
        b[len(x) + i] = lam * (prior or {}).get(t, 0.0)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    sol -= sol.mean()
    return dict(zip(teams, sol))


def fetch_fixture(y):
    """Squiggle fixture for season y (list of dicts) or None."""
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, f"squiggle_games_{y}.json")
    try:
        req = urllib.request.Request(f"https://api.squiggle.com.au/?q=games;year={y}",
                                     headers={"User-Agent": "SportsFutures stats site (private, non-commercial)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        json.dump(body, open(path, "w"))
    except Exception as e:  # noqa: BLE001
        S.log("AFL fixture unavailable", y, e)
        if not os.path.exists(path):
            return None
        body = json.load(open(path))
    games = body.get("games") or []
    out = []
    for g in games:
        if g.get("is_final"):
            continue
        h, a = code(g.get("hteam")), code(g.get("ateam"))
        if h not in NAMES or a not in NAMES:
            continue
        out.append({"round": g.get("round"), "date": str(g.get("date") or "")[:10], "home": h, "away": a,
                    "complete": int(g.get("complete") or 0) == 100, "hscore": g.get("hscore"), "ascore": g.get("ascore")})
    return out or None


def balanced_fixture(teams, rng, n_extra=6):
    """Each pair once plus n_extra extra rounds of random pairings (every team plays exactly 17 + n_extra games).
    Used when the real fixture is not out yet."""
    games = []
    for i, a in enumerate(teams):
        for b in teams[i + 1:]:
            games.append((a, b) if rng.random() < .5 else (b, a))
    for _ in range(n_extra):
        order = list(rng.permutation(teams))
        games += [(order[i], order[i + 1]) for i in range(0, len(order) - 1, 2)]
    return games


def simulate(teams, table, remaining, rating, tau, n=20000, seed=7):
    """table: current wins/draws/pf/pa by team. remaining: list of (home, away). Returns per-team probabilities."""
    rng = np.random.default_rng(seed)
    T = len(teams)
    ix = {t: i for i, t in enumerate(teams)}
    R = np.array([rating[t] for t in teams])
    w0 = np.array([table.get(t, {}).get("w", 0) for t in teams], float)
    d0 = np.array([table.get(t, {}).get("d", 0) for t in teams], float)
    pf0 = np.array([table.get(t, {}).get("pf", 0) for t in teams], float)
    pa0 = np.array([table.get(t, {}).get("pa", 0) for t in teams], float)
    out = {k: np.zeros(T) for k in ("p1", "p4", "p8", "p10", "pf", "gf", "flag")}
    wins_hist = np.zeros((T, 40))
    ladder_pos = np.zeros((T, T))
    H = np.array([ix[h] for h, a in remaining], int)
    A = np.array([ix[a] for h, a in remaining], int)
    for start in range(0, n, 2000):
        m = min(2000, n - start)
        Rs = R[None, :] + rng.normal(0, tau, (m, T))
        mu = Rs[:, H] - Rs[:, A] + HGA
        marg = mu + rng.normal(0, GAME_SD, mu.shape)
        hw = (marg > 0).astype(float)
        W = np.repeat(w0[None, :], m, 0)
        PF = np.repeat(pf0[None, :], m, 0)
        PA = np.repeat(pa0[None, :], m, 0)
        avg = 85.0
        for j in range(len(H)):
            W[:, H[j]] += hw[:, j]
            W[:, A[j]] += 1 - hw[:, j]
            PF[:, H[j]] += avg + marg[:, j] / 2
            PA[:, H[j]] += avg - marg[:, j] / 2
            PF[:, A[j]] += avg - marg[:, j] / 2
            PA[:, A[j]] += avg + marg[:, j] / 2
        pts = 4 * W + 2 * d0[None, :]
        key = pts + PF / np.maximum(PA, 1) * 1e-3
        order = np.argsort(-key, axis=1)
        pos = np.empty_like(order)
        rows = np.arange(m)[:, None]
        pos[rows, order] = np.arange(T)[None, :]
        for k_, cut in (("p1", 1), ("p4", 4), ("p8", 8), ("p10", 10)):
            out[k_] += (pos < cut).sum(0)
        np.add.at(ladder_pos, (np.tile(np.arange(T), m), pos.ravel()), 1)
        wi = np.clip(W.round().astype(int), 0, 39)
        np.add.at(wins_hist, (np.tile(np.arange(T), m), wi.ravel()), 1)
        # finals: wildcard (7v10, 8v9), then the McIntyre final eight; higher seed at home
        for s in range(m):
            seed_ = order[s]
            r = Rs[s]

            def play(a, b):
                p = 1 - _ncdf(-(r[a] - r[b] + 3.0) / GAME_SD)
                return (a, b) if rng.random() < p else (b, a)
            s7, _ = play(seed_[6], seed_[9])
            s8, _ = play(seed_[7], seed_[8])
            q1w, q1l = play(seed_[0], seed_[3])
            q2w, q2l = play(seed_[1], seed_[2])
            e1w, _ = play(seed_[4], s8)
            e2w, _ = play(seed_[5], s7)
            s1w, _ = play(q1l, e1w)
            s2w, _ = play(q2l, e2w)
            p1w, p1l = play(q1w, s2w)
            p2w, p2l = play(q2w, s1w)
            for t in (q1w, q2w, s1w, s2w):
                out["pf"][t] += 1
            out["gf"][p1w] += 1
            out["gf"][p2w] += 1
            gw, _ = play(p1w, p2w)
            out["flag"][gw] += 1
    res = {}
    for t, i in ix.items():
        wh = wins_hist[i] / n
        cdf = np.cumsum(wh)
        res[t] = {**{k: float(v[i] / n) for k, v in out.items()}, "w_mean": float((wh * np.arange(40)).sum()),
                  "w_p10": int(np.searchsorted(cdf, .1)), "w_p90": int(np.searchsorted(cdf, .9)),
                  "over": (1 - np.concatenate([[0], cdf[:-1]])).tolist(), "pos": (ladder_pos[i] / n).tolist()}
    return res


def _ncdf(x):
    from math import erf, sqrt
    return 0.5 * (1 + erf(x / sqrt(2)))


# ------------------------------------------------------------------ build

def build_data():
    os.makedirs(OUT, exist_ok=True)
    seasons, po_seasons, hist_games, tables = [], [], {}, {}
    player_hist = []
    years = sorted(int(f[7:11]) for f in os.listdir(SRC) if f.startswith("season_") and f[7:11].isdigit()) if os.path.isdir(SRC) else []
    years = [y for y in years if y >= FIRST]
    for y in years:
        d = load_season(y)
        g = team_games(d, y)
        if g is None or g.empty:
            continue
        for st, suf in (("REG", ""), ("FIN", "p")):
            x = g[g.season_type == st]
            if x.empty:
                continue
            T = team_season(x)
            cols = TEAM_COLS if st == "REG" else [c for c in TEAM_COLS if c["k"] not in ("ladder", "pts", "l5_w", "l5_m", "vs_top8_wp")]
            S.write_json(OUT, f"team_{y}{suf}.json", S.columnar(T, y, ["team", "name"], cols))
            G = x.copy()
            for q in (1, 2, 3, 4):
                G[f"q{q}_m"] = G[f"q{q}_for"] - G[f"q{q}_against"]
            G["de"] = G.effective_disposals / G.disposals
            S.write_json(OUT, f"games_{y}{suf}.json", S.columnar(G, y, ["date", "rnd", "team", "opp", "ha", "res"], GAME_COLS))
            P = player_table(d, st)
            if len(P):
                S.write_json(OUT, f"players_{y}{suf}.json", S.columnar(P, y, ["name", "team"], PLAYER_COLS))
            if st == "REG":
                seasons.append(y)
                hist_games[y] = x
                tables[y] = T
                if len(P):
                    player_hist.append(P.assign(season=y))
            else:
                po_seasons.append(y)
    seasons.sort(reverse=True)
    po_seasons.sort(reverse=True)
    last = seasons[0] if seasons else None
    fin_done = last in po_seasons and _gf_played(last)
    cur = last + 1 if fin_done else last
    fut = futures(cur, hist_games, tables)
    S.write_json(OUT, "futures.json", fut)
    S.write_json(OUT, "awards.json", awards(cur, player_hist, tables))
    meta = {"season": last, "in_progress": not fin_done, "seasons": seasons, "po_seasons": po_seasons,
            "updated_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M+00:00"), "teams": NAMES,
            "groupings": [{"name": "Ladder"}], "cfg": CFG}
    S.write_json(OUT, "meta.json", meta)
    S.log("AFL site data", len(seasons), "seasons; futures for", cur)


def _gf_played(y):
    d = load_season(y)
    return any(m.get("round") == "GF" for m in (d.get("matches") or []))


def futures(cur, hist_games, tables):
    last = max(hist_games)
    # rating: previous season's opponent-adjusted margin regressed halfway, then this season's games (if any)
    prev = cur - 1 if cur - 1 in hist_games else last
    base = srs(hist_games[prev]) if prev in hist_games else {}
    prior = {t: PRIOR_REG * v for t, v in base.items()}
    played = hist_games.get(cur)
    rating = srs(played, prior=prior, k=K_PRIOR) if played is not None and len(played) else prior
    teams = sorted(NAMES)
    for t in teams:
        rating.setdefault(t, 0.0)
    fx = fetch_fixture(cur)
    table, remaining, status = {}, [], ""
    if played is not None and len(played):
        T = tables[cur].set_index("team")
        table = {t: {"w": T.w[t], "d": T.d[t], "pf": T.pf[t], "pa": T.pa[t]} for t in T.index}
    if fx:
        remaining = [(g["home"], g["away"]) for g in fx if not g["complete"]]
        status = f"{cur} season — real fixture, {len(remaining)} home-and-away games left"
    else:
        rng = np.random.default_rng(cur)
        remaining = balanced_fixture(teams, rng)
        status = f"{cur} season — fixture not released yet; using a balanced 23-round draw (every pair once plus six repeats)"
    n_played = int(np.mean([v["w"] + v["d"] for v in table.values()])) if table else 0
    tau = 14.0 * (1 - min(n_played, 23) / 30)
    res = simulate(teams, table, remaining, rating, tau)
    ctx = {t: {"left": 0, "road_left": 0, "opp": []} for t in teams}
    if fx:
        for h, a in remaining:
            for t, o, road in ((h, a, 0), (a, h, 1)):
                ctx[t]["left"] += 1
                ctx[t]["road_left"] += road
                ctx[t]["opp"].append(rating.get(o, 0.0))
    rows = []
    for t in teams:
        r = res[t]
        tb = table.get(t, {})
        rows.append({"team": t, "name": NAMES[t], "group": "", "gp": int(tb.get("w", 0) + tb.get("d", 0) + (tables[cur].set_index("team").l.get(t, 0) if cur in tables else 0)),
                     "record": f"{int(tb.get('w', 0))}-{int((tables[cur].set_index('team').l.get(t, 0)) if cur in tables else 0)}", "rating": rating[t],
                     "w_mean": r["w_mean"], "w_p10": r["w_p10"], "w_p90": r["w_p90"], "over": r["over"],
                     "left": ctx[t]["left"] if fx else None, "road_left": ctx[t]["road_left"] if fx else None,
                     "sos_left": float(np.mean(ctx[t]["opp"])) if fx and ctx[t]["opp"] else None,
                     "p10": r["p10"], "p8": r["p8"], "p4": r["p4"], "p1": r["p1"], "pf": r["pf"], "gf": r["gf"], "flag": r["flag"]})
    bt = backtest(hist_games)
    return {"season": cur, "status": status, "sims": 20000, "main": "flag", "group_label": "",
            "intro": "Ladder and finals chances from simulating the home-and-away season and the top-10 finals series (wildcard round, then the final eight).",
            "proj": {"k": "w_mean", "l": "Proj. wins", "lo": "w_p10", "hi": "w_p90", "f": "num1"},
            "rating_note": "Points per game better (+) or worse (−) than an average team on a neutral ground",
            "extra": [{"k": "left", "l": "Games left", "f": "int"}, {"k": "road_left", "l": "Away left", "f": "int"},
                      {"k": "sos_left", "l": "Remaining SOS", "f": "pm1", "t": "Average rating of the opponents still to play (+ = harder)"}] if fx else [],
            "cols": [{"k": "p10", "l": "Finals (top 10)"}, {"k": "p8", "l": "Top 8", "t": "Skip the wildcard round"},
                     {"k": "p4", "l": "Top 4", "t": "Double chance"}, {"k": "p1", "l": "Minor premiers"},
                     {"k": "pf", "l": "Prelim final"}, {"k": "gf", "l": "Grand Final"}, {"k": "flag", "l": "Premiers"}],
            "line": {"label": "Win total", "unit": "wins", "min": 0}, "backtest_html": bt,
            "about": ["Rating is opponent-adjusted margin per game: last season's, pulled 45% back to average, then blended with this season's games (last season counts as 8 games).",
                      f"Each simulation shifts every team's rating by a random amount (typical size {tau:.1f} points) before playing the games, so long-range chances are not over-confident; single games vary by about {GAME_SD:.0f} points.",
                      "It does not know about injuries, list changes, trades or coaching changes — the main reasons to disagree with it in the pre-season.",
                      "Draws are not simulated; ties on the ladder are split by percentage."],
            "teams": rows}


def backtest(hist_games):
    """Pre-season wins forecast for each past season vs a naive 'last season's wins, pulled halfway to 11.5'."""
    ys = sorted(hist_games)
    errs_m, errs_n = [], []
    for y in ys[1:]:
        prev, now = hist_games[y - 1] if y - 1 in hist_games else None, hist_games[y]
        if prev is None:
            continue
        rating = {t: .55 * v for t, v in srs(prev).items()}
        s = now.groupby("team").agg(w=("win", "sum"), gp=("win", "size"))
        pw = prev.groupby("team").win.mean()
        x = now[now.ha == "H"]
        exp = {t: 0.0 for t in s.index}
        for h, a in zip(x.team, x.opp):
            p = 1 - _ncdf(-(rating.get(h, 0) - rating.get(a, 0) + HGA) / (GAME_SD * 1.15))
            exp[h] += p
            exp[a] += 1 - p
        for t in s.index:
            errs_m.append(abs(exp[t] - s.w[t]))
            errs_n.append(abs((.5 * pw.get(t, .5) + .25) * s.gp[t] - s.w[t]))
    if not errs_m:
        return ""
    return (f'<p class="note">Pre-season test on every season from {ys[1]} to {ys[-1]} (each forecast uses only the previous season): '
            f"the rating's win forecast was off by {np.mean(errs_m):.2f} wins per team on average, versus {np.mean(errs_n):.2f} for "
            "'last season's win rate, pulled halfway to average'. Against closing bookmaker odds (2012-2026, about 2,900 matches) the market has been more accurate than these ratings at every stage of the season; see the Shiv page.</p>")


def awards(cur, player_hist, tables):
    P = pd.concat(player_hist, ignore_index=True) if player_hist else pd.DataFrame()
    if P.empty:
        return {"awards": {}}
    tw = pd.concat([t.assign(season=y)[["season", "team", "wp", "ladder"]] for y, t in tables.items()])
    P = P.merge(tw, on=["season", "team"], how="left")
    for c in ("disposals_pg", "contested_possessions_pg", "clearances_pg", "goals_pg", "score_involvements_pg", "metres_gained_pg",
              "inside_50s_pg", "tackles_pg", "brownlow_votes", "games", "goals", "afl_fantasy_points_pg", "supercoach_points_pg"):
        if c not in P:
            P[c] = np.nan
        P[c] = pd.to_numeric(P[c], errors="coerce")
    P["L"] = P.groupby("season").games.transform("max")
    P["gshare"] = P.games / P.L
    out = {}
    # Brownlow: winner = most votes (as polled); model on the season's per-game numbers
    pool = P[P.gshare >= .5].copy()
    pool["sc"] = pool.supercoach_points_pg.fillna(pool.afl_fantasy_points_pg)
    pool = pool.sort_values("sc", ascending=False).groupby("season").head(30).copy()
    mx = P.groupby("season").brownlow_votes.transform("max")
    P["bw"] = (P.brownlow_votes == mx) & (mx > 0)
    winners = P[P.bw].groupby("season").name.first().to_dict()
    pool["win"] = [np.nan if s == cur else float(winners.get(s) == n) for s, n in zip(pool.season, pool.name)]
    feats = ["sc", "disposals_pg", "contested_possessions_pg", "clearances_pg", "goals_pg", "wp", "gshare"]
    pool[feats] = pool[feats].fillna(pool[feats].median())
    hist = pool[pool.season != cur]
    bt = AM.loso(hist, feats, leader_col="disposals_pg")
    if bt:
        bt["leader_label"] = "disposals-per-game leader"
    beta = AM.fit(hist, feats)
    now = pool[pool.season == cur].copy()
    show = [C("games", "GP", "", "int"), C("disposals_pg", "Disposals", "", "num1"), C("contested_possessions_pg", "Contested", "", "num1"),
            C("clearances_pg", "Clearances", "", "num1"), C("goals_pg", "Goals", "", "num2"), C("sc", "SuperCoach", "", "num1"),
            C("wp", "Team W%", "", "pct")]
    cur_rows = []
    if len(now):
        now["prob"] = AM.predict(now, feats, beta)
        cur_rows = now.sort_values("prob", ascending=False).head(15)[["name", "team", "prob"] + [c["k"] for c in show]].to_dict("records")
    past = []
    for y in sorted(winners, reverse=True):
        r = P[(P.season == y) & P.bw].iloc[0]
        past.append({"season": int(y), "name": r["name"], "team": r.team, "brownlow_votes": r.brownlow_votes,
                     **{c["k"]: (r[c["k"]] if c["k"] in r else None) for c in show if c["k"] != "sc"},
                     "sc": r.supercoach_points_pg if r.supercoach_points_pg == r.supercoach_points_pg else r.afl_fantasy_points_pg})
    out["Brownlow"] = {"title": "Brownlow Medal", "short": "Brownlow", "backtest": bt, "cols": show, "current": cur_rows, "past": past,
                       "past_cols": [C("brownlow_votes", "Votes", "", "int")] + show,
                       "note": "Chances from a model fitted on every count since 2012, using the season's per-game numbers, SuperCoach score and team win rate. Umpires' votes are only revealed at the count, so this is the closest public guide during the season.",
                       "empty": "The new season has not started; chances appear after the first rounds."}
    # Coleman: most goals (home and away)
    gl = P.loc[P.groupby("season").goals.idxmax()]
    cp = [C("games", "GP", "", "int"), C("goals", "Goals", "", "int"), C("goals_pg", "Goals/G", "", "num2"), C("behinds", "Behinds", "", "int")]
    past_c = [{"season": int(r.season), "name": r["name"], "team": r.team, **{c["k"]: r[c["k"]] for c in cp}} for _, r in gl.sort_values("season", ascending=False).iterrows()]
    cur_c = []
    if cur in P.season.values:
        x = P[P.season == cur].sort_values("goals", ascending=False).head(15)
        rem = max(0, 23 - x.games.max())
        x = x.assign(proj=x.goals + x.goals_pg * rem)
        cur_c = x[["name", "team"] + [c["k"] for c in cp] + ["proj"]].to_dict("records")
    out["Coleman"] = {"title": "Coleman Medal (most goals, home and away)", "short": "Coleman", "cols": cp + [C("proj", "Projected", "", "num1")],
                      "current": cur_c, "has_prob": False, "past": past_c, "past_cols": cp,
                      "note": "Projected goals = goals so far plus the current rate over the remaining rounds.", "empty": "The new season has not started."}
    return {"order": ["Brownlow", "Coleman"], "awards": out}


CFG = {
    "sport": "AFL", "season_style": "calendar", "po_label": "Finals", "reg_label": "Home and away",
    "ids": {"team": ["team", "name"], "players": ["name", "team"], "games": ["date", "rnd", "team", "opp", "ha", "res"]},
    "pinned": ["gp"], "team_sort": "pts", "noshade": ["gp", "ladder", "close_n", "d"],
    "key": {"teams": ["gp", "w", "pct", "margin_g", "luck", "inside_50s_diff", "clearances_diff", "contested_possessions_diff",
                      "marks_inside_50_diff", "tackles_diff", "intercepts_diff", "pts_per_i50", "o_pts_per_i50", "acc", "de", "q4_m", "close_wp"],
            "players": ["games", "disposals_pg", "contested_possessions_pg", "clearances_pg", "inside_50s_pg", "goals_pg", "tackles_pg",
                        "score_involvements_pg", "metres_gained_pg", "supercoach_points_pg", "brownlow_votes"]},
    "standings": {"sort": "pts", "order": [["pts", 1], ["pct", 1]],
                  "cols": ["gp", "w", "l", "d", "pts", "pct", "pf_g", "pa_g", "margin_g", "pyth_w", "luck", "home_wp", "away_wp", "l5_w",
                           "inside_50s_diff", "clearances_diff", "close_wp"],
                  "alias": {"pf_g": "For/G", "pa_g": "Agst/G", "margin_g": "Margin/G", "pyth_w": "Exp W", "home_wp": "Home", "away_wp": "Away",
                            "l5_w": "L5", "inside_50s_diff": "I50 diff", "clearances_diff": "Clr diff", "close_wp": "Close W%"},
                  "note": "Four points for a win, two for a draw; ties split by percentage. From 2026 the top 10 make the finals (wildcard round 7v10 and 8v9). Exp W is what the scores usually earn; Luck is wins minus that and tends to fade. I50 and Clr diff are inside-50 and clearance differentials per game, two of the best predictors of future results."},
    "players": {"sort": "disposals", "gp_key": "games", "min_default": 5,
                "note": "AFL Tables and Footywire stats via the fitzRoy archive. Brownlow votes appear after the count."},
    "games": {"results": [["W", "Wins"], ["L", "Losses"], ["D", "Draws"]], "pinned": ["points_for", "points_against"],
              "note": "Click a heading to sort — for example by inside 50s or clearance count to find a team's most dominant games."},
    "team_note": "Differentials are per game (team minus opponent). Pts per inside 50 measures forward efficiency.",
}

PAGES = [("index", "Ladder", "AFL ladder", "Ladder with percentage, expected wins, luck, home/away, inside-50 and clearance differentials. Every season since 2012."),
         ("futures", "Futures", "AFL futures", "Premiership, Grand Final, top 4, top 8, finals and minor premiership chances, plus a win-total over/under tool."),
         ("awards", "Awards", "AFL awards", "Brownlow Medal chances from a model tested on every count since 2012, and the Coleman Medal race, with past winners."),
         ("teams", "Team stats", "AFL team stats", "Scoring, quarters, differentials, possession, stoppages, territory and splits. Season table or year by year."),
         ("players", "Players", "AFL player stats", "Per game, advanced (contested possessions, metres gained, score involvements), fantasy and totals for every player since 2012."),
         ("games", "Games", "AFL game logs", "Every team game since 2012 with quarter margins, territory and contest stats.")]


def build_site():
    S.build_pages(SITE, "AFL", "Futures", PAGES, data_src=OUT)
    # the season files and index from afl.py are no longer used by these pages
    dd = os.path.join(SITE, "data")
    for fn in os.listdir(dd):
        if fn.startswith("season_") or fn == "stats_index.json":
            os.remove(os.path.join(dd, fn))
    for fn in ("stats.js",):
        p = os.path.join(SITE, fn)
        if os.path.exists(p):
            os.remove(p)
    S.log("AFL site pages written")


if __name__ == "__main__":
    build_data()
    build_site()
