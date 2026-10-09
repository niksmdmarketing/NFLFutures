"""Award-winner trends: what MVPs, top goalies, defencemen, rookies and sixth men had in common compared with the
other leading candidates in the same season. Same noise filter as the team markets (trends_engine.evaluate); the
'at the same production' test controls for the candidate's main production number instead of the team record.
"""
import os
import re
import unicodedata

import numpy as np
import pandas as pd

import trends_engine as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


ALIASES = {"alexanderovechkin": "alexovechkin", "ronartest": "mettaworldpeace", "jrsmith": "jrsmith",
           "dariusleonard": "shaquilleleonard", "saucegardner": "ahmadgardner", "patricksurtain": "patsurtain"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s+(jr|sr|ii|iii|iv)\.?$", "", s.strip())
    s = re.sub(r"[^a-z]", "", s)
    return ALIASES.get(s, s)


def rank(df, c, asc=False, by="season"):
    return df.groupby(by)[c].rank(ascending=asc, method="min")


def section(key, title, P, feats, base, base_word, pool_desc, label_fn, cur, cur_ok, note=None):
    """P: one row per candidate (season, name, team, win, base column). feats: (key, label, timing, values)."""
    P = P.copy()
    P["display"] = P.name + " (" + P.team.astype(str) + ")"
    done = P[P.season != cur].groupby("season").win.sum()
    bad = sorted(done[done != 1].index)
    P = P[~P.season.isin(bad) | (P.season == cur)]
    T = P.rename(columns={"team": "club"}).rename(columns={"display": "team"})
    T["complete"] = T.season != cur
    T["award"] = np.where(T.complete, T.win, np.nan)
    F = []
    for fk, label, timing, v in feats:
        v = pd.Series(v, index=P.index).astype(float) if not isinstance(v, pd.Series) else v.reindex(P.index).astype(float)
        F.append(dict(key=fk, label=label, timing=timing, sections=[key], v=v, base=base, market=False, base_word=base_word))
    sec = dict(key=key, outcome="award", pool=lambda T: T.team.notna(), groups=["season"])
    rows, winners = E.evaluate(T, F, sec, label_fn, cur, cur_ok)
    if not rows:
        return None
    order = {"edge": 0, "fade": 1, "priced": 2, "weak": 3, "noise": 4}
    rows.sort(key=lambda r: (order[r["verdict"]], r["p"]))
    C = T[T.complete]
    skipped = [label_fn(s) for s in bad]
    desc = note or ""
    if skipped:
        desc = (desc + " " if desc else "") + "Seasons where the winner fell outside this pool are left out: " + ", ".join(skipped) + "."
    return dict(key=key, kind="award", title=title, pool_desc=pool_desc, note=desc,
                seasons=[label_fn(min(C.season)), label_fn(max(C.season))], n_seasons=int(C.season.nunique()),
                pool=int(len(C)), winners_n=int(C.award.sum()), base_rate=float(C.award.mean()), winners=winners, trends=rows)


def _won_prev(P, winners):
    prev = {y + 1: norm(n) for y, n in winners.items()}
    return pd.Series([float(prev.get(s) == norm(n)) if (s - 1) in winners else np.nan for s, n in zip(P.season, P.name)],
                     index=P.index)


def _flag_winner(P, winners, cur):
    w = {y: norm(n) for y, n in winners.items()}
    P["win"] = [np.nan if s == cur else float(w.get(s) == norm(n)) for s, n in zip(P.season, P.name)]
    return P


# ------------------------------------------------------------------ NHL

def nhl(cur_label, cur, cur_ok):
    import nhl_awards as A
    rows = {k: [] for k in ("Hart", "Vezina", "Norris", "Calder")}
    years = sorted(A.WINNERS["Hart"])
    for y in range(min(years), cur + 1):
        t = A.season_tables(y)
        if t is None:
            continue
        sk, gl, tm = t
        L = float(A.col(tm, "gamesPlayed").max() or 82)
        trank = A.col(tm, "pointPct").rank(ascending=False, method="min")
        gf = A.col(tm, "goalsFor")
        sk = sk.copy()
        sk["season"], sk["L"] = y, L
        sk["team_rank"] = sk.team.map(trank)
        sk["team_gf"] = sk.team.map(gf)
        sk["pts_rank"] = sk.pts.rank(ascending=False, method="min")
        sk["g_rank"] = sk.goals.rank(ascending=False, method="min")
        d = sk[sk.pos == "D"]
        sk["d_pts_rank"] = d.pts.rank(ascending=False, method="min")
        sk["d_g_rank"] = d.goals.rank(ascending=False, method="min")
        sk["d_toi_rank"] = d[d.gp >= .5 * L].toi.rank(ascending=False, method="min")
        r = sk[sk.rookie == 1]
        sk["r_pts_rank"] = r.pts.rank(ascending=False, method="min")
        sk["r_g_rank"] = r.goals.rank(ascending=False, method="min")
        sk["r_toi_rank"] = r[r.gp >= .3 * L].toi.rank(ascending=False, method="min")
        rows["Hart"].append(sk.sort_values("pts", ascending=False).head(25))
        rows["Norris"].append(sk[sk.pos == "D"].sort_values("pts", ascending=False).head(12))
        rows["Calder"].append(sk[sk.rookie == 1].sort_values("pts", ascending=False).head(12))
        if len(gl):
            g = gl.copy()
            g["season"], g["L"] = y, L
            g["team_rank"] = g.team.map(trank)
            g["wins_rank"] = g.wins.rank(ascending=False, method="min")
            g = g[g.gp >= .4 * g.gp.max()]
            g = g.sort_values("saa", ascending=False).head(10)
            g["sv_rank"] = g.savePct.rank(ascending=False, method="min")
            g["gaa_rank"] = g.gaa.rank(ascending=True, method="min")
            rows["Vezina"].append(g)
    out = []
    lab = lambda s: f"{int(s)}-{str(int(s) + 1)[2:]}"

    H = _flag_winner(pd.concat(rows["Hart"], ignore_index=True), A.WINNERS["Hart"], cur)
    H["base"] = H.pts / H.groupby("season").pts.transform("max")
    out.append(section("hart", "Hart Trophy (MVP)", H, [
        ("led_pts", "Led the league in points", "end", H.pts_rank == 1),
        ("top3_pts", "Top-3 in points", "end", H.pts_rank <= 3),
        ("led_goals", "Led the league in goals", "end", H.g_rank == 1),
        ("team_top3", "His team finished top-3 in the standings", "end", H.team_rank <= 3),
        ("team_top8", "His team finished top-8 in the standings", "end", H.team_rank <= 8),
        ("team_out", "His team finished outside the top 16", "end", H.team_rank > 16),
        ("share40", "Had a point on 40%+ of his team's goals", "end", H.pts / H.team_gf >= .4),
        ("durable", "Missed no more than about 5% of games", "end", H.gp / H.L >= .94),
        ("centre", "Plays centre", "end", H.pos == "C"),
        ("won_prev", "Won the Hart the season before", "prior", _won_prev(H, A.WINNERS["Hart"])),
    ], "base", "points totals", "top-25 scorers", lab, cur, cur_ok,
        note="Skaters only: goalies are judged in the Vezina pool."))

    V = _flag_winner(pd.concat(rows["Vezina"], ignore_index=True), A.WINNERS["Vezina"], cur)
    V["base"] = V.saa / V.gp.replace(0, np.nan)
    out.append(section("vezina", "Vezina Trophy (top goalie)", V, [
        ("led_wins", "Led the league in wins", "end", V.wins_rank == 1),
        ("top3_wins", "Top-3 in wins", "end", V.wins_rank <= 3),
        ("best_sv", "Best save percentage among the leading goalies", "end", V.sv_rank == 1),
        ("best_gaa", "Lowest goals-against average among the leading goalies", "end", V.gaa_rank == 1),
        ("team_top3", "His team finished top-3 in the standings", "end", V.team_rank <= 3),
        ("team_top8", "His team finished top-8 in the standings", "end", V.team_rank <= 8),
        ("workload", "Played two-thirds or more of his team's games", "end", V.gp / V.L >= .67),
        ("won_prev", "Won the Vezina the season before", "prior", _won_prev(V, A.WINNERS["Vezina"])),
    ], "base", "saves above average", "top-10 goalies by saves above average", lab, cur, cur_ok))

    N = _flag_winner(pd.concat(rows["Norris"], ignore_index=True), A.WINNERS["Norris"], cur)
    N["base"] = N.pts / N.groupby("season").pts.transform("max")
    out.append(section("norris", "Norris Trophy (top defenceman)", N, [
        ("led_d_pts", "Led all defencemen in points", "end", N.d_pts_rank == 1),
        ("top3_d_pts", "Top-3 defenceman in points", "end", N.d_pts_rank <= 3),
        ("led_d_goals", "Led all defencemen in goals", "end", N.d_g_rank == 1),
        ("top3_toi", "Top-3 defenceman in ice time per game", "end", N.d_toi_rank <= 3),
        ("team_top8", "His team finished top-8 in the standings", "end", N.team_rank <= 8),
        ("team_out", "His team finished outside the top 16", "end", N.team_rank > 16),
        ("durable", "Missed no more than about 5% of games", "end", N.gp / N.L >= .94),
        ("won_prev", "Won the Norris the season before", "prior", _won_prev(N, A.WINNERS["Norris"])),
    ], "base", "points totals", "top-12 scoring defencemen", lab, cur, cur_ok))

    Cd = _flag_winner(pd.concat(rows["Calder"], ignore_index=True), A.WINNERS["Calder"], cur)
    Cd["base"] = Cd.pts / Cd.groupby("season").pts.transform("max")
    out.append(section("calder", "Calder Trophy (top rookie)", Cd, [
        ("led_r_pts", "Led all rookies in points", "end", Cd.r_pts_rank == 1),
        ("top3_r_pts", "Top-3 rookie in points", "end", Cd.r_pts_rank <= 3),
        ("led_r_goals", "Led all rookies in goals", "end", Cd.r_g_rank == 1),
        ("top3_r_toi", "Top-3 rookie in ice time per game", "end", Cd.r_toi_rank <= 3),
        ("defence", "Is a defenceman", "end", Cd.pos == "D"),
        ("team_top16", "His team finished in the top 16", "end", Cd.team_rank <= 16),
        ("durable", "Played 85%+ of games", "end", Cd.gp / Cd.L >= .85),
    ], "base", "points totals", "top-12 scoring rookies", lab, cur, cur_ok,
        note="Skaters only: no goalie has won since this history starts."))
    return [s for s in out if s]


# ------------------------------------------------------------------ NBA

NBA_AW = {
    "MVP": {2003: "Tim Duncan", 2004: "Kevin Garnett", 2005: "Steve Nash", 2006: "Steve Nash", 2007: "Dirk Nowitzki",
            2008: "Kobe Bryant", 2009: "LeBron James", 2010: "LeBron James", 2011: "Derrick Rose", 2012: "LeBron James",
            2013: "LeBron James", 2014: "Kevin Durant", 2015: "Stephen Curry", 2016: "Stephen Curry", 2017: "Russell Westbrook",
            2018: "James Harden", 2019: "Giannis Antetokounmpo", 2020: "Giannis Antetokounmpo", 2021: "Nikola Jokic",
            2022: "Nikola Jokic", 2023: "Joel Embiid", 2024: "Nikola Jokic", 2025: "Shai Gilgeous-Alexander",
            2026: "Shai Gilgeous-Alexander"},
    "DPOY": {2003: "Ben Wallace", 2004: "Ron Artest", 2005: "Ben Wallace", 2006: "Ben Wallace", 2007: "Marcus Camby",
             2008: "Kevin Garnett", 2009: "Dwight Howard", 2010: "Dwight Howard", 2011: "Dwight Howard", 2012: "Tyson Chandler",
             2013: "Marc Gasol", 2014: "Joakim Noah", 2015: "Kawhi Leonard", 2016: "Kawhi Leonard", 2017: "Draymond Green",
             2018: "Rudy Gobert", 2019: "Rudy Gobert", 2020: "Giannis Antetokounmpo", 2021: "Rudy Gobert", 2022: "Marcus Smart",
             2023: "Jaren Jackson Jr.", 2024: "Rudy Gobert", 2025: "Evan Mobley", 2026: "Victor Wembanyama"},
    "ROY": {2004: "LeBron James", 2005: "Emeka Okafor", 2006: "Chris Paul", 2007: "Brandon Roy", 2008: "Kevin Durant",
            2009: "Derrick Rose", 2010: "Tyreke Evans", 2011: "Blake Griffin", 2012: "Kyrie Irving", 2013: "Damian Lillard",
            2014: "Michael Carter-Williams", 2015: "Andrew Wiggins", 2016: "Karl-Anthony Towns", 2017: "Malcolm Brogdon",
            2018: "Ben Simmons", 2019: "Luka Doncic", 2020: "Ja Morant", 2021: "LaMelo Ball", 2022: "Scottie Barnes",
            2023: "Paolo Banchero", 2024: "Victor Wembanyama", 2025: "Stephon Castle", 2026: "Cooper Flagg"},
    "6MOY": {2003: "Bobby Jackson", 2004: "Antawn Jamison", 2005: "Ben Gordon", 2006: "Mike Miller", 2007: "Leandro Barbosa",
             2008: "Manu Ginobili", 2009: "Jason Terry", 2010: "Jamal Crawford", 2011: "Lamar Odom", 2012: "James Harden",
             2013: "J.R. Smith", 2014: "Jamal Crawford", 2015: "Lou Williams", 2016: "Jamal Crawford", 2017: "Eric Gordon",
             2018: "Lou Williams", 2019: "Lou Williams", 2020: "Montrezl Harrell", 2021: "Jordan Clarkson", 2022: "Tyler Herro",
             2023: "Malcolm Brogdon", 2024: "Naz Reid", 2025: "Payton Pritchard", 2026: "Keldon Johnson"},
}
NBA_ALIAS = {"metta world peace": "ron artest", "jjredick": "jjredick"}


def _nba_agg(y, cur):
    """Per-player regular-season totals for one season, cached as a small file once the season is over."""
    import nba as N
    from trends import NBA_CANON
    path = os.path.join(N.NBA_DATA, f"player_agg_{y}.csv")
    if y < cur and os.path.exists(path):
        return pd.read_csv(path)
    p = N._download("espn_nba_player_boxscores", f"player_box_{y}.csv", 2 if y >= cur - 1 else 24 * 365, required=False)
    if not p or not os.path.exists(p):
        return None
    b = pd.read_csv(p, low_memory=False)
    b = b[(b.season_type == 2)]
    if "did_not_play" in b:
        b = b[~b.did_not_play.astype(str).str.lower().eq("true")]
    b = b[pd.to_numeric(b.minutes, errors="coerce").fillna(0) > 0]
    b["team_abbreviation"] = b.team_abbreviation.replace(NBA_CANON)
    for c in ("points", "rebounds", "assists", "steals", "blocks", "turnovers", "minutes", "plus_minus", "defensive_rebounds"):
        b[c] = pd.to_numeric(b[c], errors="coerce").fillna(0)
    b["start"] = b.starter.astype(str).str.lower().eq("true").astype(float)
    b = b.sort_values("game_date")
    a = b.groupby("athlete_id").agg(name=("athlete_display_name", "last"), team=("team_abbreviation", "last"),
                                    pos=("athlete_position_abbreviation", "last"), gp=("game_id", "nunique"),
                                    starts=("start", "sum"), mins=("minutes", "sum"), pts=("points", "sum"),
                                    reb=("rebounds", "sum"), ast=("assists", "sum"), stl=("steals", "sum"),
                                    blk=("blocks", "sum"), tov=("turnovers", "sum"), pm=("plus_minus", "sum"),
                                    dreb=("defensive_rebounds", "sum")).reset_index()
    a["season"] = y
    if y < cur:
        a.to_csv(path, index=False)
    return a


def nba(cur_label, cur, cur_ok):
    from trends import NBA_DIVS, NBA_EAST
    frames, seen = [], set()
    for y in range(2003, cur + 1):
        a = _nba_agg(y, cur)
        if a is None or a.empty:
            continue
        a["rookie"] = (~a.athlete_id.isin(seen)).astype(float) if y > 2003 else np.nan
        seen |= set(a.athlete_id)
        frames.append(a)
    A = pd.concat(frames, ignore_index=True)
    tg = A.groupby("season").gp.transform("max")
    A["L"] = tg
    pg = lambda c: A[c] / A.gp.replace(0, np.nan)
    for c in ("pts", "reb", "ast", "stl", "blk", "tov", "mins", "dreb"):
        A[c + "_pg"] = pg(c)
    A["eff_pg"] = A.pts_pg + A.reb_pg + A.ast_pg + A.stl_pg + A.blk_pg - A.tov_pg
    A["def_pg"] = A.stl_pg + A.blk_pg + .3 * A.dreb_pg
    q = A.gp >= .7 * A.L
    for c in ("pts_pg", "blk_pg", "stl_pg", "eff_pg", "pm"):
        A[c + "_rank"] = A[q].groupby("season")[c].rank(ascending=False, method="min")
    # team standings from the same box scores
    tw = []
    import nba as N
    for y in sorted(A.season.unique()):
        p = os.path.join(N.NBA_DATA, f"team_box_{y}.csv")
        if not os.path.exists(p):
            continue
        t = pd.read_csv(p, low_memory=False, usecols=["season", "season_type", "team_abbreviation", "team_winner",
                                                      "opponent_team_score"])
        t = t[t.season_type == 2]
        from trends import NBA_CANON
        t["team"] = t.team_abbreviation.replace(NBA_CANON)
        t["w"] = t.team_winner.astype(str).str.lower().eq("true").astype(float)
        g = t.groupby("team").agg(wp=("w", "mean"), pa=("opponent_team_score", "mean")).reset_index()
        g["season"] = y
        tw.append(g)
    TW = pd.concat(tw, ignore_index=True)
    conf = {t: ("East" if d in NBA_EAST else "West") for d, ts in NBA_DIVS.items() for t in ts}
    TW["conf"] = TW.team.map(conf)
    TW["team_rank"] = TW.groupby("season").wp.rank(ascending=False, method="min")
    TW["conf_rank"] = TW.groupby(["season", "conf"]).wp.rank(ascending=False, method="min")
    TW["def_rank"] = TW.groupby("season").pa.rank(ascending=True, method="min")
    A = A.merge(TW[["season", "team", "team_rank", "conf_rank", "def_rank"]], on=["season", "team"], how="left")
    lab = lambda s: f"{int(s) - 1}-{str(int(s))[2:]}"
    out = []

    M = A[A.gp >= .6 * A.L].sort_values("eff_pg", ascending=False).groupby("season").head(32).reset_index(drop=True)
    M = _flag_winner(M, NBA_AW["MVP"], cur)
    M["base"] = M.eff_pg / M.groupby("season").eff_pg.transform("max")
    out.append(section("mvp", "Most Valuable Player", M, [
        ("led_ppg", "Led the league in points per game", "end", M.pts_pg_rank == 1),
        ("top3_ppg", "Top-3 in points per game", "end", M.pts_pg_rank <= 3),
        ("led_eff", "Led the league in box-score production per game", "end", M.eff_pg_rank == 1),
        ("team_best", "His team had the best record in the league", "end", M.team_rank == 1),
        ("team_top3", "His team had a top-3 record", "end", M.team_rank <= 3),
        ("conf_top", "His team was the No. 1 seed in its conference", "end", M.conf_rank == 1),
        ("team_out8", "His team was outside the top 8 in its conference", "end", M.conf_rank > 8),
        ("pm_top3", "Top-3 in total plus-minus", "end", M.pm_rank <= 3),
        ("durable", "Played 85%+ of games", "end", M.gp / M.L >= .85),
        ("won_prev", "Won the MVP the season before", "prior", _won_prev(M, NBA_AW["MVP"])),
    ], "base", "box-score production", "top-32 players by box-score production", lab, cur, cur_ok))

    D = A[A.gp >= .6 * A.L].sort_values("def_pg", ascending=False).groupby("season").head(15).reset_index(drop=True)
    D = _flag_winner(D, NBA_AW["DPOY"], cur)
    D["base"] = D.def_pg / D.groupby("season").def_pg.transform("max")
    out.append(section("dpoy", "Defensive Player of the Year", D, [
        ("led_blk", "Led the league in blocks per game", "end", D.blk_pg_rank == 1),
        ("top3_blk", "Top-3 in blocks per game", "end", D.blk_pg_rank <= 3),
        ("top3_stl", "Top-3 in steals per game", "end", D.stl_pg_rank <= 3),
        ("team_def5", "His team allowed the fewest points per game, or close (top 5)", "end", D.def_rank <= 5),
        ("team_top3", "His team had a top-3 record", "end", D.team_rank <= 3),
        ("big", "Listed at centre or power forward", "end", D.pos.astype(str).str.contains("C|PF")),
        ("durable", "Played 85%+ of games", "end", D.gp / D.L >= .85),
        ("won_prev", "Won DPOY the season before", "prior", _won_prev(D, NBA_AW["DPOY"])),
    ], "base", "steals, blocks and defensive rebounds", "top-15 by steals, blocks and defensive rebounds", lab, cur, cur_ok,
        note="Box scores capture only part of defence, so this pool misses some winners."))

    R = A[(A.rookie == 1) & (A.gp >= .4 * A.L)].sort_values("eff_pg", ascending=False).groupby("season").head(12).reset_index(drop=True)
    R = _flag_winner(R, NBA_AW["ROY"], cur)
    R["base"] = R.eff_pg / R.groupby("season").eff_pg.transform("max")
    R["r_ppg_rank"] = rank(R, "pts_pg")
    R["r_min_rank"] = rank(R, "mins_pg")
    out.append(section("roy", "Rookie of the Year", R, [
        ("led_r_ppg", "Led all rookies in points per game", "end", R.r_ppg_rank == 1),
        ("top3_r_ppg", "Top-3 rookie in points per game", "end", R.r_ppg_rank <= 3),
        ("led_r_min", "Led all rookies in minutes per game", "end", R.r_min_rank == 1),
        ("starter", "Started most of his games", "end", R.starts / R.gp >= .5),
        ("team_top8", "His team finished top-8 in its conference", "end", R.conf_rank <= 8),
        ("durable", "Played 85%+ of games", "end", R.gp / R.L >= .85),
    ], "base", "box-score production", "top-12 rookies by box-score production", lab, cur, cur_ok))

    S = A[(A.starts / A.gp.replace(0, np.nan) < .5) & (A.gp >= .5 * A.L)]
    S = S.sort_values("pts_pg", ascending=False).groupby("season").head(15).reset_index(drop=True)
    S = _flag_winner(S, NBA_AW["6MOY"], cur)
    S["base"] = S.pts_pg / S.groupby("season").pts_pg.transform("max")
    S["b_ppg_rank"] = rank(S, "pts_pg")
    out.append(section("6moy", "Sixth Man of the Year", S, [
        ("led_b_ppg", "Led bench players in points per game", "end", S.b_ppg_rank == 1),
        ("top3_b_ppg", "Top-3 bench scorer", "end", S.b_ppg_rank <= 3),
        ("team_top8", "His team finished top-8 in its conference", "end", S.conf_rank <= 8),
        ("team_top3", "His team had a top-3 record", "end", S.team_rank <= 3),
        ("guard", "Is a guard", "end", S.pos.astype(str).str.contains("G")),
        ("minutes", "Played 25+ minutes a game", "end", S.mins_pg >= 25),
        ("won_prev", "Won Sixth Man the season before", "prior", _won_prev(S, NBA_AW["6MOY"])),
    ], "base", "scoring", "top-15 bench scorers (started fewer than half their games)", lab, cur, cur_ok))
    return [s for s in out if s]


# ------------------------------------------------------------------ NFL

NFL_AW = {
    "MVP": {2010: "Tom Brady", 2011: "Aaron Rodgers", 2012: "Adrian Peterson", 2013: "Peyton Manning", 2014: "Aaron Rodgers",
            2015: "Cam Newton", 2016: "Matt Ryan", 2017: "Tom Brady"},
    "DPOY": {2010: "Troy Polamalu", 2011: "Terrell Suggs", 2012: "J.J. Watt", 2013: "Luke Kuechly", 2014: "J.J. Watt",
             2015: "J.J. Watt", 2016: "Khalil Mack", 2017: "Aaron Donald"},
}


def nfl(cur_label, cur, cur_ok):
    import awards
    from award_race import WINNERS, ALIAS
    from common import FIX
    W = {k: {**NFL_AW[k], **WINNERS[k]} for k in ("MVP", "DPOY")}
    g = pd.read_csv(os.path.join(DATA, "games.csv"), low_memory=False)
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    st = pd.read_csv(os.path.join(DATA, "nfl_standings.csv"))
    st["team"] = st.team.replace(FIX)
    rows = []
    for y in range(2010, cur + 1):
        try:
            a = awards.season_stats(y)
        except Exception:
            continue
        x = g[(g.season == y) & (g.game_type == "REG") & g.result.notna()]
        rec = {}
        for h, aw, r in zip(x.home_team, x.away_team, x.result):
            for t, s in ((h, r), (aw, -r)):
                w, n = rec.get(t, (0.0, 0))
                rec[t] = (w + (1 if s > 0 else .5 if s == 0 else 0), n + 1)
        wp = {t: w / n for t, (w, n) in rec.items() if n}
        pa = x.groupby("home_team").away_score.sum().add(x.groupby("away_team").home_score.sum(), fill_value=0)
        a = a.copy()
        a["season"] = y
        a["team_wp"] = a.team.map(wp)
        a["L"] = max(n for _, n in rec.values()) if rec else 17
        a["team_rank"] = a.team_wp.map(lambda v: sum(1 for z in wp.values() if z > v) + 1 if v == v else np.nan)
        a["def_rank"] = a.team.map(pa.rank(method="min"))
        seed = st[st.season == y].set_index("team").seed
        a["seed"] = a.team.map(seed)
        for c in ("passing_tds", "passing_yards", "def_sacks", "def_interceptions"):
            a[c + "_rank"] = a[c].rank(ascending=False, method="min")
        rows.append(a)
    A = pd.concat(rows, ignore_index=True)
    lab = lambda s: str(int(s))
    out = []

    def wins(dict_):
        return {y: ALIAS.get(n.lower(), n) for y, n in dict_.items()}

    Q = A[A.is_qb == 1].sort_values("epa", ascending=False).groupby("season").head(12).reset_index(drop=True)
    Q = _flag_winner(Q, wins(W["MVP"]), cur)
    Q["base"] = Q.epa / Q.groupby("season").epa.transform("max")
    Q["epa_rank"] = rank(Q, "epa")
    out.append(section("mvp", "Most Valuable Player", Q, [
        ("led_td", "Led the league in passing touchdowns", "end", Q.passing_tds_rank == 1),
        ("led_yds", "Led the league in passing yards", "end", Q.passing_yards_rank == 1),
        ("top3_epa", "Top-3 quarterback in expected points added", "end", Q.epa_rank <= 3),
        ("seed1", "His team was the No. 1 seed", "end", Q.seed == 1),
        ("seed2", "His team was a top-2 seed", "end", Q.seed <= 2),
        ("team_top3", "His team had a top-3 record in the league", "end", Q.team_rank <= 3),
        ("rusher", "Ran for 400+ yards", "end", Q.rushing_yards >= 400),
        ("durable", "Played every game but one or fewer", "end", Q.games >= Q.L - 1),
        ("won_prev", "Won the MVP the season before", "prior", _won_prev(Q, wins(W["MVP"]))),
    ], "base", "expected points added", "top-12 quarterbacks by expected points added", lab, cur, cur_ok,
        note="Quarterbacks only (non-quarterback MVPs are rare)."))

    Dd = A[A.is_def == 1].copy()
    Dd["dscore"] = (Dd.def_sacks + 1.5 * Dd.def_interceptions + .4 * Dd.def_pass_defended + .25 * Dd.def_tackles_for_loss +
                    Dd.def_fumbles_forced + .1 * Dd.def_qb_hits + .03 * Dd.tackles)
    Dd = Dd.sort_values("dscore", ascending=False).groupby("season").head(25).reset_index(drop=True)
    Dd = _flag_winner(Dd, wins(W["DPOY"]), cur)
    Dd["base"] = Dd.dscore / Dd.groupby("season").dscore.transform("max")
    out.append(section("dpoy", "Defensive Player of the Year", Dd, [
        ("led_sacks", "Led the league in sacks", "end", Dd.def_sacks_rank == 1),
        ("top3_sacks", "Top-3 in sacks", "end", Dd.def_sacks_rank <= 3),
        ("led_int", "Led the league in interceptions", "end", Dd.def_interceptions_rank == 1),
        ("rusher", "Pass rusher (8+ sacks)", "end", Dd.def_sacks >= 8),
        ("team_def5", "His team allowed the fewest points, or close (top 5)", "end", Dd.def_rank <= 5),
        ("playoff", "His team made the playoffs", "end", Dd.seed.notna()),
        ("won_prev", "Won DPOY the season before", "prior", _won_prev(Dd, wins(W["DPOY"]))),
    ], "base", "defensive production", "top-25 defenders by sacks, takeaways, pass break-ups and tackles", lab, cur, cur_ok))
    return [s for s in out if s]


# ------------------------------------------------------------------ NBL

NBL_MVP = {2012: "Cedric Jackson", 2013: "Rotnei Clarke", 2014: "Brian Conklin", 2015: "Kevin Lisch", 2016: "Jerome Randle",
           2017: "Bryce Cotton", 2018: "Andrew Bogut", 2019: "Bryce Cotton", 2020: "Bryce Cotton", 2021: "Jaylen Adams",
           2022: "Xavier Cooks", 2023: "Bryce Cotton", 2024: "Bryce Cotton", 2025: "Bryce Cotton"}


def nbl(cur_label, cur, cur_ok):
    import json
    from trends import SITE
    D = json.load(open(os.path.join(SITE, "nbl", "data", "stats_index.json")))
    canon = {"WOL": "ILL"}
    rows = []
    for k, S in D["seasons"].items():
        y = int(k)
        st = [r for r in (S.get("standings") or []) if str(r.get("phase", "Regular")).lower() == "regular"]
        pos = {canon.get(r["team"]["team_code"], r["team"]["team_code"]): int(r["position"]) for r in st}
        L = max((int(r["won"]) + int(r["lost"]) for r in st), default=0)
        for p in S.get("leaders") or []:
            if str(p.get("phase", "Regular")).lower() != "regular":
                continue
            pl, tm = p.get("player") or {}, p.get("team") or {}
            code = canon.get(tm.get("team_code"), tm.get("team_code"))
            rows.append(dict(season=y, name=f"{pl.get('first_name', '')} {pl.get('last_name', '')}".strip(), team=code,
                             gp=p.get("games") or 0, ppg=p.get("points_average") or 0, eff=p.get("efficiency_average") or 0,
                             rpg=p.get("rebounds_average") or 0, apg=p.get("assists_average") or 0, L=L,
                             team_pos=pos.get(code)))
    A = pd.DataFrame(rows)
    A = A[A.gp > 0]
    q = A.gp >= .6 * A.L
    A["ppg_rank"] = A[q].groupby("season").ppg.rank(ascending=False, method="min")
    A["eff_rank"] = A[q].groupby("season").eff.rank(ascending=False, method="min")
    P = A[q].sort_values("eff", ascending=False).groupby("season").head(12).reset_index(drop=True)
    P = _flag_winner(P, NBL_MVP, cur)
    P["base"] = P.eff / P.groupby("season").eff.transform("max")
    lab = lambda s: f"{int(s)}-{str(int(s) + 1)[2:]}"
    s = section("mvp", "NBL MVP", P, [
        ("led_ppg", "Led the league in points per game", "end", P.ppg_rank == 1),
        ("top3_ppg", "Top-3 in points per game", "end", P.ppg_rank <= 3),
        ("led_eff", "Led the league in efficiency rating", "end", P.eff_rank == 1),
        ("team_top2", "His team finished top-2 on the ladder", "end", P.team_pos <= 2),
        ("team_top4", "His team finished top-4 on the ladder", "end", P.team_pos <= 4),
        ("durable", "Played 90%+ of games", "end", P.gp / P.L >= .9),
        ("won_prev", "Won the MVP the season before", "prior", _won_prev(P, NBL_MVP)),
    ], "base", "efficiency ratings", "top-12 players by efficiency rating", lab, cur, cur_ok)
    return [s] if s else []


def afl(cur_label, cur, cur_ok):
    import afl_site as A
    rows = []
    for y in range(A.FIRST, cur + 1):
        d = A.load_season(y)
        if d is None:
            continue
        P = A.player_table(d, "REG")
        g = A.team_games(d, y)
        if P.empty or g is None or g.empty:
            continue
        T = A.team_season(g[g.season_type == "REG"])
        P = P.merge(T[["team", "ladder"]], on="team", how="left")
        P["season"] = y
        P["L"] = P.games.max()
        for c in ("disposals_pg", "clearances_pg", "goals_pg", "contested_possessions_pg"):
            P[c + "_rank"] = P[P.games >= .5 * P.L][c].rank(ascending=False, method="min")
        rows.append(P)
    A_ = pd.concat(rows, ignore_index=True)
    A_["sc"] = A_.supercoach_points_pg.fillna(A_.afl_fantasy_points_pg) if "supercoach_points_pg" in A_ else np.nan
    pool = A_[A_.games >= .5 * A_.L].sort_values("sc", ascending=False).groupby("season").head(30).copy()
    mx = A_.groupby("season").brownlow_votes.transform("max")
    win = A_[(A_.brownlow_votes == mx) & (mx > 0)].groupby("season").name.first().to_dict()
    pool["win"] = [np.nan if s == cur else float(win.get(s) == n) for s, n in zip(pool.season, pool.name)]
    pool["base"] = pool.sc / pool.groupby("season").sc.transform("max")
    prev = {y: n for y, n in win.items()}
    lab = lambda s: str(int(s))
    s_ = section("brownlow", "Brownlow Medal", pool, [
        ("led_disp", "Led the league in disposals per game", "end", pool.disposals_pg_rank == 1),
        ("top3_disp", "Top-3 in disposals per game", "end", pool.disposals_pg_rank <= 3),
        ("top5_clr", "Top-5 in clearances per game", "end", pool.clearances_pg_rank <= 5),
        ("top5_cp", "Top-5 in contested possessions per game", "end", pool.contested_possessions_pg_rank <= 5),
        ("goals1", "Kicked a goal a game or more", "end", pool.goals_pg >= 1),
        ("team_top4", "His team finished top 4", "end", pool.ladder <= 4),
        ("team_out8", "His team finished outside the top 8", "end", pool.ladder > 8),
        ("durable", "Played every game but one or fewer", "end", pool.games >= pool.L - 1),
        ("won_prev", "Polled the most votes the season before", "prior", _won_prev(pool, prev)),
    ], "base", "SuperCoach scores", "top-30 by SuperCoach points per game", lab, cur, cur_ok,
        note="Winner = most votes as polled (2012's Jobe Watson count included).")
    return [s_] if s_ else []


RUN = {"nfl": nfl, "nba": nba, "nhl": nhl, "nbl": nbl, "afl": afl}
