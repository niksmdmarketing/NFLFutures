"""NBA section in the NHL/NFL style: standings, futures, awards, team stats, players, game logs.

Data: SportsDataverse ESPN box scores (2002-03 onward, regular season and playoffs) for everything computed
here, plus the NBA Stats-derived advanced tables GPT's collector writes (2016-17 onward) and the season
simulation in nba.py (futures). Season keys are end years (2026 = 2025-26).
"""
import json
import os

import numpy as np
import pandas as pd

import award_model as AM
import sportsite as S
from sportsite import C

ROOT = S.ROOT
OUT = os.path.join(ROOT, "build", "nba_site")
SITE = os.path.join(S.SITE, "nba")
FIRST = 2003

DIVS = {"Atlantic": ["BOS", "BKN", "NY", "PHI", "TOR"], "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
        "Southeast": ["ATL", "CHA", "MIA", "ORL", "WSH"], "Northwest": ["DEN", "MIN", "OKC", "POR", "UTAH"],
        "Pacific": ["GS", "LAC", "LAL", "PHX", "SAC"], "Southwest": ["DAL", "HOU", "MEM", "NO", "SA"]}
OLD_DIVS = {"Atlantic": ["BOS", "BKN", "NY", "ORL", "PHI", "WSH", "MIA"], "Central": ["ATL", "CHI", "CLE", "DET", "IND", "MIL", "NO", "TOR"],
            "Midwest": ["DAL", "DEN", "HOU", "MEM", "MIN", "SA", "UTAH"], "Pacific": ["GS", "LAC", "LAL", "PHX", "POR", "SAC", "OKC"]}
EAST = {"Atlantic", "Central", "Southeast"}
CANON = {"NJ": "BKN", "SEA": "OKC", "NOH": "NO", "NOK": "NO", "GSW": "GS", "SAS": "SA", "NYK": "NY", "UTA": "UTAH",
         "WAS": "WSH", "PHO": "PHX", "NOP": "NO", "BRK": "BKN", "CHO": "CHA"}
TEAMS = {t for v in DIVS.values() for t in v}
CUP = {}          # season -> NBA Cup final game ids (excluded from regular-season stats)


def conf_of(team, y):
    if y <= 2004:
        return "East" if team in OLD_DIVS["Atlantic"] + OLD_DIVS["Central"] else "West"
    return next(("East" if d in EAST else "West") for d, ts in DIVS.items() if team in ts)


def div_of(team, y):
    D = OLD_DIVS if y <= 2004 else DIVS
    return next((d for d, ts in D.items() if team in ts), None)


def _num(df, c):
    return pd.to_numeric(df[c], errors="coerce").fillna(0.0) if c in df else pd.Series(0.0, index=df.index)


# ------------------------------------------------------------------ team box -> team-game rows

def cup_finals(t):
    """Game ids of NBA Cup finals: listed as regular-season games but not counted in the standings.
    Found as the one game between two teams that each played one more 'regular' game than everyone else."""
    r = t[t.season_type == 2]
    n = r.groupby("team_abbreviation").game_id.nunique()
    if n.empty:
        return set()
    usual = int(n.mode().iloc[0])
    extra = set(n[n == usual + 1].index)
    if len(extra) < 2:
        return set()
    x = r[r.team_abbreviation.isin(extra)]
    both = x.groupby("game_id").team_abbreviation.nunique()
    ids = set(both[both == 2].index)
    # the final is the only game played that day
    per_day = r.groupby(r.game_date.astype(str).str[:10]).game_id.nunique()
    day = x.drop_duplicates("game_id").set_index("game_id").game_date.astype(str).str[:10]
    return {i for i in ids if per_day.get(day.get(i), 0) == 1}


def team_games(y):
    import nba as N
    p = os.path.join(N.NBA_DATA, f"team_box_{y}.csv")
    if not os.path.exists(p):
        p = N._download("espn_nba_team_boxscores", f"team_box_{y}.csv", 2, required=False)
    if not p or not os.path.exists(p):
        return None
    t = pd.read_csv(p, low_memory=False)
    t = t[t.season_type.isin([2, 3])].copy()
    for c in ("team_abbreviation", "opponent_team_abbreviation"):
        t[c] = t[c].replace(CANON)
    t = t[t.team_abbreviation.isin(TEAMS) & t.opponent_team_abbreviation.isin(TEAMS)].drop_duplicates(["game_id", "team_abbreviation"])
    CUP[y] = cup_finals(t)
    t = t[~t.game_id.isin(CUP[y])]
    g = pd.DataFrame({"gid": t.game_id.values, "st": t.season_type.values, "date": t.game_date.astype(str).str[:10].values,
                      "team": t.team_abbreviation.values, "opp": t.opponent_team_abbreviation.values,
                      "ha": np.where(t.team_home_away.eq("home"), "H", "A")})
    tov = _num(t, "total_turnovers") if "total_turnovers" in t else _num(t, "turnovers")
    for k, c in (("pts", "team_score"), ("fgm", "field_goals_made"), ("fga", "field_goals_attempted"),
                 ("fg3m", "three_point_field_goals_made"), ("fg3a", "three_point_field_goals_attempted"),
                 ("ftm", "free_throws_made"), ("fta", "free_throws_attempted"), ("oreb", "offensive_rebounds"),
                 ("dreb", "defensive_rebounds"), ("reb", "total_rebounds"), ("ast", "assists"), ("stl", "steals"),
                 ("blk", "blocks"), ("pf", "fouls"), ("fb", "fast_break_points"), ("paint", "points_in_paint"),
                 ("pot", "turnover_points"), ("lead", "largest_lead")):
        g[k] = _num(t, c).values
    g["tov"] = tov.values
    o = g.drop(columns=["st", "date", "opp", "ha"]).rename(columns=lambda c: c if c in ("gid", "team") else "o_" + c)
    g = g.merge(o.rename(columns={"team": "opp"}), on=["gid", "opp"], how="left")
    g = g[g.o_pts.notna()].copy()
    g["win"] = (g.pts > g.o_pts).astype(float)
    g["poss"] = 0.5 * ((g.fga - g.oreb + g.tov + .44 * g.fta) + (g.o_fga - g.o_oreb + g.o_tov + .44 * g.o_fta))
    g["season"] = y
    g = g.sort_values(["team", "date"])
    d = pd.to_datetime(g.date)
    g["rest"] = (d - d.groupby(g.team).shift(1)).dt.days.sub(1).clip(upper=7)
    return g.reset_index(drop=True)


def team_season(g, y):
    """Aggregate team-game rows (one season type) into the team stats table."""
    s = g.groupby("team")
    a = s[["pts", "o_pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf",
           "fb", "paint", "pot", "o_fgm", "o_fga", "o_fg3m", "o_fg3a", "o_ftm", "o_fta", "o_oreb", "o_dreb", "o_reb", "o_ast",
           "o_tov", "o_fb", "o_paint", "o_pot", "poss", "win", "lead", "o_lead"]].sum()
    a["gp"] = s.size()
    a["w"] = a.win
    a["l"] = a.gp - a.w
    a["wp"] = a.w / a.gp
    G = a.gp
    a["ppg"], a["oppg"] = a.pts / G, a.o_pts / G
    a["net"] = a.ppg - a.oppg
    a["pace"] = a.poss / G
    a["ortg"], a["drtg"] = 100 * a.pts / a.poss, 100 * a.o_pts / a.poss
    a["netrtg"] = a.ortg - a.drtg
    a["efg"] = (a.fgm + .5 * a.fg3m) / a.fga
    a["o_efg"] = (a.o_fgm + .5 * a.o_fg3m) / a.o_fga
    a["ts"] = a.pts / (2 * (a.fga + .44 * a.fta))
    a["tov_pct"] = a.tov / (a.fga + .44 * a.fta + a.tov)
    a["o_tov_pct"] = a.o_tov / (a.o_fga + .44 * a.o_fta + a.o_tov)
    a["orb_pct"] = a.oreb / (a.oreb + a.o_dreb)
    a["drb_pct"] = a.dreb / (a.dreb + a.o_oreb)
    a["ftr"], a["o_ftr"] = a.ftm / a.fga, a.o_ftm / a.o_fga
    a["fg_pct"], a["fg3_pct"], a["ft_pct"] = a.fgm / a.fga, a.fg3m / a.fg3a, a.ftm / a.fta.replace(0, np.nan)
    a["o_fg3_pct"] = a.o_fg3m / a.o_fg3a
    a["fg3a_rate"], a["o_fg3a_rate"] = a.fg3a / a.fga, a.o_fg3a / a.o_fga
    a["fg3m_g"] = a.fg3m / G
    a["ast_pct"] = a.ast / a.fgm
    for k in ("reb", "ast", "stl", "blk", "tov", "pf", "fb", "paint", "pot", "o_fb", "o_paint", "o_pot", "oreb", "lead"):
        a[k + "_g"] = a[k] / G
    a["pyth"] = 1 / (1 + (a.o_pts / a.pts) ** 14)
    a["pyth_w"] = a.pyth * G
    a["luck"] = a.w - a.pyth_w
    for name, m in (("home", g.ha == "H"), ("road", g.ha == "A"), ("close", (g.pts - g.o_pts).abs() <= 5),
                    ("blowout", (g.pts - g.o_pts).abs() >= 15), ("b2b", g.rest == 0), ("rested", g.rest >= 1)):
        x = g[m].groupby("team").win
        a[name + "_wp"] = x.mean()
        a[name + "_n"] = x.size()
    wp = a.wp.to_dict()
    gv = g.assign(owp=g.opp.map(wp))
    a["vs_win_wp"] = gv[gv.owp >= .5].groupby("team").win.mean()
    a["vs_lose_wp"] = gv[gv.owp < .5].groupby("team").win.mean()
    net = a.netrtg.to_dict()
    a["sos"] = g.assign(on=g.opp.map(net)).groupby("team").on.mean()
    a["adj_net"] = a.netrtg + a.sos
    last = g.groupby("team").tail(10).groupby("team")
    a["l10_w"] = last.win.sum()
    a["l10_net"] = (last.pts.sum() - last.o_pts.sum()) / last.size()

    def streak(x):
        v = x.win.values[::-1]
        if not len(v):
            return 0
        n = 1
        while n < len(v) and v[n] == v[0]:
            n += 1
        return n if v[0] == 1 else -n
    a["streak"] = g.groupby("team")[["win"]].apply(streak)
    a = a.reset_index()
    a["conf"] = a.team.map(lambda t: conf_of(t, y))
    a["div"] = a.team.map(lambda t: div_of(t, y))
    a["conf_rank"] = a.groupby("conf").wp.rank(ascending=False, method="min")
    lead = a.loc[a.groupby("conf").wp.idxmax(), ["conf", "w", "l"]].rename(columns={"w": "lw", "l": "ll"})
    a = a.merge(lead, on="conf", how="left")
    a["gb"] = ((a.lw - a.w) + (a.l - a.ll)) / 2
    return a


TEAM_COLS = [
    C("gp", "GP", "Record", "int"), C("w", "W", "Record", "int"), C("l", "L", "Record", "int", lo=True), C("wp", "Win %", "Record", "pct"),
    C("gb", "GB", "Record", "num1", lo=True, t="Games behind the conference leader"),
    C("conf_rank", "Conf. rank", "Record", "int", lo=True), C("l10_w", "Last 10 W", "Record", "int"),
    C("streak", "Streak", "Record", "pm", t="Current run: positive = wins, negative = losses"),
    C("ppg", "PTS/G", "Scoring", "num1"), C("oppg", "Opp PTS/G", "Scoring", "num1", lo=True), C("net", "Point diff/G", "Scoring", "pm1"),
    C("pyth_w", "Expected W", "Scoring", "num1", t="Wins a team with this points for and against usually gets (Pythagorean, exponent 14)"),
    C("luck", "Luck", "Scoring", "pm1", t="Actual wins minus expected wins; big positive numbers tend to regress"),
    C("ortg", "Off. rating", "Ratings", "num1", t="Points scored per 100 possessions"),
    C("drtg", "Def. rating", "Ratings", "num1", lo=True, t="Points allowed per 100 possessions"),
    C("netrtg", "Net rating", "Ratings", "pm1", t="Points per 100 possessions, scored minus allowed"),
    C("sos", "Opp. net rating", "Ratings", "pm1", t="Average net rating of the opponents played (strength of schedule)"),
    C("adj_net", "Adj. net rating", "Ratings", "pm1", t="Net rating plus strength of schedule"),
    C("pace", "Pace", "Ratings", "num1", t="Possessions per game"),
    C("l10_net", "Last 10 point diff", "Ratings", "pm1"),
    C("efg", "eFG%", "Four factors", "pct", t="Effective field-goal %: threes count 1.5 times"),
    C("tov_pct", "TOV%", "Four factors", "pct", lo=True, t="Turnovers per 100 plays"),
    C("orb_pct", "ORB%", "Four factors", "pct", t="Share of own misses rebounded"),
    C("ftr", "FT rate", "Four factors", "num2", t="Free throws made per field-goal attempt"),
    C("o_efg", "Opp eFG%", "Four factors", "pct", lo=True), C("o_tov_pct", "Forced TOV%", "Four factors", "pct"),
    C("drb_pct", "DRB%", "Four factors", "pct", t="Share of opponent misses rebounded"),
    C("o_ftr", "Opp FT rate", "Four factors", "num2", lo=True),
    C("fg_pct", "FG%", "Shooting", "pct"), C("fg3_pct", "3P%", "Shooting", "pct"), C("ft_pct", "FT%", "Shooting", "pct"),
    C("ts", "TS%", "Shooting", "pct", t="True shooting: points per shooting possession"),
    C("fg3m_g", "3PM/G", "Shooting", "num1"), C("fg3a_rate", "3PA rate", "Shooting", "pct", t="Share of shots taken from three"),
    C("o_fg3_pct", "Opp 3P%", "Shooting", "pct", lo=True), C("o_fg3a_rate", "Opp 3PA rate", "Shooting", "pct", lo=True),
    C("reb_g", "REB/G", "Box score", "num1"), C("oreb_g", "OREB/G", "Box score", "num1"), C("ast_g", "AST/G", "Box score", "num1"),
    C("ast_pct", "AST%", "Box score", "pct", t="Share of made baskets assisted"), C("stl_g", "STL/G", "Box score", "num1"),
    C("blk_g", "BLK/G", "Box score", "num1"), C("tov_g", "TOV/G", "Box score", "num1", lo=True), C("pf_g", "Fouls/G", "Box score", "num1", lo=True),
    C("fb_g", "Fast-break PTS/G", "Box score", "num1"), C("paint_g", "Paint PTS/G", "Box score", "num1"),
    C("pot_g", "PTS off TOV/G", "Box score", "num1"), C("o_fb_g", "Opp fast-break PTS/G", "Box score", "num1", lo=True),
    C("o_paint_g", "Opp paint PTS/G", "Box score", "num1", lo=True), C("lead_g", "Avg largest lead", "Box score", "num1"),
    C("home_wp", "Home W%", "Splits", "pct"), C("road_wp", "Road W%", "Splits", "pct"),
    C("vs_win_wp", "W% vs .500+", "Splits", "pct", t="Win % against teams with a winning record"),
    C("vs_lose_wp", "W% vs sub-.500", "Splits", "pct"),
    C("close_wp", "Close-game W%", "Splits", "pct", t="Games decided by 5 points or fewer"), C("close_n", "Close games", "Splits", "int"),
    C("blowout_wp", "W% in 15+ pt games", "Splits", "pct"),
    C("b2b_wp", "Back-to-back W%", "Splits", "pct", t="Second night of a back-to-back"), C("b2b_n", "Back-to-backs", "Splits", "int"),
    C("rested_wp", "W% with 1+ days rest", "Splits", "pct"),
]
ADV_TEAM = [C("pie", "PIE", "NBA advanced", "pct", t="Player Impact Estimate (team share of game events), NBA Stats"),
            C("second_chance_points", "2nd-chance PTS/G", "NBA advanced", "num1"),
            C("opponent_second_chance_points", "Opp 2nd-chance PTS/G", "NBA advanced", "num1", lo=True),
            C("assist_to_turnover", "AST/TOV", "NBA advanced", "num2")]
ZONES = [("At rim (0–4 ft)", "rim"), ("Short paint (5–10 ft)", "paint"), ("Mid-range (11–16 ft)", "mid"),
         ("Long mid-range (17–22 ft)", "long"), ("Corner 3", "c3"), ("Above-break 3", "ab3")]


def shot_zone_cols():
    out = []
    for z, k in ZONES:
        out += [C(f"z_{k}_share", f"{z} share", "Shot profile", "pct", t=f"Share of all shots taken from: {z}"),
                C(f"z_{k}_fg", f"{z} FG%", "Shot profile", "pct")]
    return out


def _adv_team():
    p = os.path.join(ROOT, "build", "nba_advanced_team_stats.json")
    z = os.path.join(ROOT, "build", "nba_shot_zones.json")
    A = pd.DataFrame(json.load(open(p))["rows"]) if os.path.exists(p) else pd.DataFrame()
    Z = pd.DataFrame(json.load(open(z))["rows"]) if os.path.exists(z) else pd.DataFrame()
    if len(A):
        A["team"] = A.team.replace(CANON)
    if len(Z):
        Z["team"] = Z.team.replace(CANON)
        tot = Z.groupby(["season", "season_type", "team"]).attempts.transform("sum")
        Z["share"] = Z.attempts / tot
        rows = []
        for (s, st, t), x in Z.groupby(["season", "season_type", "team"]):
            r = {"season": s, "season_type": st, "team": t}
            for z_, k in ZONES:
                q = x[x.zone == z_]
                if len(q):
                    r[f"z_{k}_share"] = float(q.share.iloc[0])
                    r[f"z_{k}_fg"] = float(q.fg_pct.iloc[0]) if q.fg_pct.iloc[0] == q.fg_pct.iloc[0] else None
            rows.append(r)
        Z = pd.DataFrame(rows)
    return A, Z


# ------------------------------------------------------------------ players

def player_box(y, cur):
    """Per player, per season type: totals from ESPN player box scores (cached once a season is over)."""
    import nba as N
    path = os.path.join(N.NBA_DATA, f"player_site2_{y}.csv")
    if y < cur and os.path.exists(path):
        return pd.read_csv(path)
    p = N._download("espn_nba_player_boxscores", f"player_box_{y}.csv", 2 if y >= cur - 1 else 24 * 365, required=False)
    if not p or not os.path.exists(p):
        return None
    b = pd.read_csv(p, low_memory=False)
    b = b[b.season_type.isin([2, 3]) & ~b.game_id.isin(CUP.get(y, set()))]
    if "did_not_play" in b:
        b = b[~b.did_not_play.astype(str).str.lower().eq("true")]
    b = b.copy()
    b["mins"] = pd.to_numeric(b.minutes, errors="coerce").fillna(0)
    b = b[b.mins > 0]
    b["team_abbreviation"] = b.team_abbreviation.replace(CANON)
    cols = {"points": "pts", "rebounds": "reb", "offensive_rebounds": "oreb", "defensive_rebounds": "dreb", "assists": "ast",
            "steals": "stl", "blocks": "blk", "turnovers": "tov", "fouls": "pf", "plus_minus": "pm", "field_goals_made": "fgm",
            "field_goals_attempted": "fga", "three_point_field_goals_made": "fg3m", "three_point_field_goals_attempted": "fg3a",
            "free_throws_made": "ftm", "free_throws_attempted": "fta"}
    for c, k in cols.items():
        b[k] = pd.to_numeric(b[c], errors="coerce").fillna(0) if c in b else 0.0
    b["start"] = b.starter.astype(str).str.lower().eq("true").astype(float)
    b["dd"] = ((b[["pts", "reb", "ast", "stl", "blk"]] >= 10).sum(axis=1) >= 2).astype(float)
    b["td"] = ((b[["pts", "reb", "ast", "stl", "blk"]] >= 10).sum(axis=1) >= 3).astype(float)
    b["g30"] = (b.pts >= 30).astype(float)
    b["win"] = b.team_winner.astype(str).str.lower().eq("true").astype(float)
    b = b.sort_values("game_date")
    agg = {k: (k, "sum") for k in list(cols.values()) + ["mins", "start", "dd", "td", "g30", "win"]}
    a = b.groupby(["season_type", "athlete_id"]).agg(name=("athlete_display_name", "last"), team=("team_abbreviation", "last"),
                                                    pos=("athlete_position_abbreviation", "last"), gp=("game_id", "nunique"), **agg).reset_index()
    a["season"] = y
    if y < cur:
        a.to_csv(path, index=False)
    return a


PLAYER_COLS = [
    C("gp", "GP", "Per game", "int"), C("gs", "GS", "Per game", "int"), C("mpg", "MIN", "Per game", "num1"),
    C("ppg", "PTS", "Per game", "num1"), C("rpg", "REB", "Per game", "num1"), C("apg", "AST", "Per game", "num1"),
    C("spg", "STL", "Per game", "num1"), C("bpg", "BLK", "Per game", "num1"), C("tpg", "TOV", "Per game", "num1", lo=True),
    C("fg3m_g", "3PM", "Per game", "num1"), C("pm_g", "+/-", "Per game", "pm1", t="Plus-minus per game"),
    C("fg_pct", "FG%", "Shooting", "pct"), C("fg3_pct", "3P%", "Shooting", "pct"), C("ft_pct", "FT%", "Shooting", "pct"),
    C("efg", "eFG%", "Shooting", "pct"), C("ts", "TS%", "Shooting", "pct"), C("fga_g", "FGA", "Shooting", "num1"),
    C("fg3a_g", "3PA", "Shooting", "num1"), C("fta_g", "FTA", "Shooting", "num1"), C("fg3a_rate", "3PA rate", "Shooting", "pct"),
    C("pts36", "PTS/36", "Per 36", "num1"), C("reb36", "REB/36", "Per 36", "num1"), C("ast36", "AST/36", "Per 36", "num1"),
    C("stocks36", "STL+BLK/36", "Per 36", "num1"), C("ast_tov", "AST/TOV", "Per 36", "num2"),
    C("pts", "PTS", "Totals", "int"), C("reb", "REB", "Totals", "int"), C("ast", "AST", "Totals", "int"), C("stl", "STL", "Totals", "int"),
    C("blk", "BLK", "Totals", "int"), C("fg3m", "3PM", "Totals", "int"), C("mins", "MIN", "Totals", "int"), C("pm", "+/-", "Totals", "pm"),
    C("dd", "Double-doubles", "Totals", "int"), C("td", "Triple-doubles", "Totals", "int"), C("g30", "30-pt games", "Totals", "int"),
    C("team_wp", "Team W% in his games", "Totals", "pct"),
    C("usage_pct", "USG%", "NBA advanced", "pct", t="Share of team plays used while on court (NBA Stats)"),
    C("off_rating", "Off. rating", "NBA advanced", "num1"), C("def_rating", "Def. rating", "NBA advanced", "num1", lo=True),
    C("net_rating", "Net rating", "NBA advanced", "pm1"), C("pie", "PIE", "NBA advanced", "pct", t="Player Impact Estimate (NBA Stats)"),
    C("assist_pct", "AST%", "NBA advanced", "pct"), C("rebound_pct", "REB%", "NBA advanced", "pct"),
]


def player_table(a):
    a = a.copy()
    G = a.gp.replace(0, np.nan)
    a["gs"] = a.start
    a["mpg"] = a.mins / G
    for k, c in (("ppg", "pts"), ("rpg", "reb"), ("apg", "ast"), ("spg", "stl"), ("bpg", "blk"), ("tpg", "tov"),
                 ("fg3m_g", "fg3m"), ("pm_g", "pm"), ("fga_g", "fga"), ("fg3a_g", "fg3a"), ("fta_g", "fta")):
        a[k] = a[c] / G
    a["fg_pct"] = S.pct(a.fgm, a.fga)
    a["fg3_pct"] = S.pct(a.fg3m, a.fg3a)
    a["ft_pct"] = S.pct(a.ftm, a.fta)
    a["efg"] = S.pct(a.fgm + .5 * a.fg3m, a.fga)
    a["ts"] = S.pct(a.pts, 2 * (a.fga + .44 * a.fta))
    a["fg3a_rate"] = S.pct(a.fg3a, a.fga)
    M = a.mins.replace(0, np.nan)
    a["pts36"], a["reb36"], a["ast36"] = 36 * a.pts / M, 36 * a.reb / M, 36 * a.ast / M
    a["stocks36"] = 36 * (a.stl + a.blk) / M
    a["ast_tov"] = S.pct(a.ast, a.tov)
    a["team_wp"] = a.win / G
    return a


def _adv_players():
    p = os.path.join(ROOT, "build", "nba_advanced_player_stats.json")
    if not os.path.exists(p):
        return pd.DataFrame()
    A = pd.DataFrame(json.load(open(p))["rows"])
    A["key"] = A.player.map(_norm)
    return A


def _norm(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


GAME_COLS = [
    C("pts", "PTS", "Result", "int"), C("o_pts", "Opp", "Result", "int", lo=True), C("margin", "Margin", "Result", "pm"),
    C("rest", "Rest days", "Result", "int", t="Days off before this game (0 = back-to-back)"),
    C("poss", "Poss.", "Efficiency", "num1"), C("ortg", "Off. rtg", "Efficiency", "num1"), C("drtg", "Def. rtg", "Efficiency", "num1", lo=True),
    C("efg", "eFG%", "Efficiency", "pct"), C("o_efg", "Opp eFG%", "Efficiency", "pct", lo=True), C("tov_pct", "TOV%", "Efficiency", "pct", lo=True),
    C("orb_pct", "ORB%", "Efficiency", "pct"), C("ftr", "FT rate", "Efficiency", "num2"),
    C("fg3m", "3PM", "Box score", "int"), C("fg3a", "3PA", "Box score", "int"), C("fg3_pct", "3P%", "Box score", "pct"),
    C("reb", "REB", "Box score", "int"), C("ast", "AST", "Box score", "int"), C("tov", "TOV", "Box score", "int", lo=True),
    C("stl", "STL", "Box score", "int"), C("blk", "BLK", "Box score", "int"), C("fb", "Fast-break PTS", "Box score", "int"),
    C("paint", "Paint PTS", "Box score", "int"), C("lead", "Largest lead", "Box score", "int"),
]


def game_table(g):
    g = g.copy()
    g["margin"] = g.pts - g.o_pts
    g["ortg"], g["drtg"] = 100 * g.pts / g.poss, 100 * g.o_pts / g.poss
    g["efg"] = S.pct(g.fgm + .5 * g.fg3m, g.fga)
    g["o_efg"] = S.pct(g.o_fgm + .5 * g.o_fg3m, g.o_fga)
    g["tov_pct"] = S.pct(g.tov, g.fga + .44 * g.fta + g.tov)
    g["orb_pct"] = S.pct(g.oreb, g.oreb + g.o_dreb)
    g["ftr"] = S.pct(g.ftm, g.fga)
    g["fg3_pct"] = S.pct(g.fg3m, g.fg3a)
    g["res"] = np.where(g.win == 1, "W", "L")
    return g


# ------------------------------------------------------------------ build

def build_data():
    import nba as N
    cur = N.season_end_year()
    os.makedirs(OUT, exist_ok=True)
    advT, zones = _adv_team()
    advP = _adv_players()
    seasons, po_seasons, finals = [], [], {}
    names = dict(N.NAMES)
    team_hist, player_hist = {}, []
    for y in range(FIRST, cur + 1):
        g = team_games(y)
        if g is None or g.empty:
            continue
        pb = player_box(y, cur)
        for st, suf in ((2, ""), (3, "p")):
            x = g[g.st == st]
            if x.empty:
                continue
            T = team_season(x, y)
            T["name"] = T.team.map(names)
            if len(advT):
                A = advT[(advT.season == y) & (advT.season_type == st)]
                if len(A):
                    T = T.merge(A[["team"] + [c["k"] for c in ADV_TEAM if c["k"] in A]], on="team", how="left")
            if len(zones):
                Z = zones[(zones.season == y) & (zones.season_type == st)]
                if len(Z):
                    T = T.merge(Z.drop(columns=["season", "season_type"]), on="team", how="left")
            cols = TEAM_COLS + ADV_TEAM + shot_zone_cols()
            if st == 3:
                cols = [c for c in cols if c["k"] not in ("gb", "conf_rank", "streak", "l10_w", "l10_net")]
            S.write_json(OUT, f"team_{y}{suf}.json", S.columnar(T, y, ["team", "name"], cols))
            GT = game_table(x)
            S.write_json(OUT, f"games_{y}{suf}.json", S.columnar(GT, y, ["date", "team", "opp", "ha", "res"], GAME_COLS))
            if st == 2:
                seasons.append(y)
                team_hist[y] = T
            else:
                po_seasons.append(y)
            if pb is not None:
                P = player_table(pb[pb.season_type == st])
                P["pos"] = P.pos.fillna("")
                if len(advP):
                    A = advP[(advP.season == y) & (advP.season_type == st)].drop_duplicates("key")
                    P["key"] = P.name.map(_norm)
                    P = P.merge(A[["key", "usage_pct", "off_rating", "def_rating", "net_rating", "pie", "assist_pct", "rebound_pct"]],
                                on="key", how="left")
                P = P.sort_values("pts", ascending=False)
                S.write_json(OUT, f"players_{y}{suf}.json", S.columnar(P, y, ["name", "team", "pos"], PLAYER_COLS))
                if st == 2:
                    player_hist.append(P.assign(season=y))
    seasons.sort(reverse=True)
    po_seasons.sort(reverse=True)
    in_progress = cur in seasons
    S.write_json(OUT, "futures.json", futures(cur))
    S.write_json(OUT, "awards.json", awards(cur, player_hist, team_hist))
    groupings = [
        {"name": "Division", "groups": DIVS, "by_season": {str(y): OLD_DIVS for y in seasons if y <= 2004}},
        {"name": "Conference", "groups": {"Eastern Conference": [t for d in EAST for t in DIVS[d]],
                                          "Western Conference": [t for d in DIVS if d not in EAST for t in DIVS[d]]},
         "by_season": {str(y): {"Eastern Conference": OLD_DIVS["Atlantic"] + OLD_DIVS["Central"],
                                "Western Conference": OLD_DIVS["Midwest"] + OLD_DIVS["Pacific"]} for y in seasons if y <= 2004}},
        {"name": "League"}]
    meta = {"season": cur if in_progress else seasons[0], "in_progress": in_progress, "seasons": seasons, "po_seasons": po_seasons,
            "updated_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M+00:00"), "teams": names, "groupings": groupings,
            "cfg": CFG}
    S.write_json(OUT, "meta.json", meta)
    S.log("NBA site data", len(seasons), "seasons", len(po_seasons), "playoff seasons")


CFG = {
    "sport": "NBA", "season_style": "split_end", "po_label": "Playoffs",
    "ids": {"team": ["team", "name"], "players": ["name", "team", "pos"], "games": ["date", "team", "opp", "ha", "res"]},
    "pinned": ["gp"], "team_sort": "wp", "noshade": ["gp", "gs", "close_n", "b2b_n"],
    "key": {"teams": ["gp", "w", "wp", "netrtg", "adj_net", "ortg", "drtg", "pace", "efg", "tov_pct", "orb_pct", "ftr", "o_efg",
                      "fg3_pct", "fg3a_rate", "luck", "close_wp", "vs_win_wp", "b2b_wp", "l10_net"],
            "players": ["gp", "mpg", "ppg", "rpg", "apg", "spg", "bpg", "fg3m_g", "ts", "usage_pct", "net_rating", "pie", "pm_g", "dd"]},
    "standings": {"sort": "wp", "order": [["wp", 1], ["netrtg", 1]],
                  "cols": ["gp", "w", "l", "wp", "gb", "home_wp", "road_wp", "l10_w", "streak", "ppg", "oppg", "net", "netrtg", "adj_net",
                           "pyth_w", "luck", "close_wp", "vs_win_wp"],
                  "alias": {"gp": "GP", "wp": "W%", "netrtg": "Net rtg", "adj_net": "Adj. net", "pyth_w": "Exp W", "close_wp": "Close W%",
                            "vs_win_wp": "vs .500+", "home_wp": "Home", "road_wp": "Road", "l10_w": "L10"},
                  "note": "Ties are ordered by net rating (official tie-breaks are not applied). Exp W is what the points scored and allowed usually earn; Luck is actual wins minus that, and big positive luck tends to fade. Adj. net adds strength of schedule."},
    "players": {"sort": "pts", "gp_key": "gp", "min_default": 10,
                "positions": [["", "All"], ["G", "Guards"], ["F", "Forwards"], ["C", "Centres"]],
                "pos_groups": {"G": ["G", "PG", "SG"], "F": ["F", "SF", "PF"], "C": ["C"]},
                "note": "Box-score stats from ESPN; USG%, ratings, PIE and AST%/REB% come from NBA Stats (2016-17 onward)."},
    "games": {"results": [["W", "Wins"], ["L", "Losses"]], "pinned": ["pts", "o_pts"],
              "note": "Click a heading to sort — for example a team's games by margin, or by rest days to see back-to-backs."},
    "team_note": "Ratings are per 100 possessions. Shot profile and NBA advanced columns start in 2016-17.",
}


def futures(cur):
    p = os.path.join(ROOT, "build", "nba_futures.json")
    if not os.path.exists(p):
        return {"teams": [], "cols": [], "proj": {"k": "w_mean", "l": "Proj. wins"}, "intro": "Futures are not available yet."}
    F = json.load(open(p))
    import nba as N
    rows = []
    rec = {}
    tp = os.path.join(OUT, f"team_{cur}.json")
    if os.path.exists(tp):
        d = json.load(open(tp))
        ks = [c["k"] for c in d["cols"]]
        for r in d["rows"]:
            o = dict(zip(["team", "name"] + ks, r))
            rec[o["team"]] = o
    for t, v in F["teams"].items():
        dist = np.array(v.get("win_dist") or [])
        cdf = np.cumsum(dist)
        over = (1 - np.concatenate([[0], cdf[:-1]])).tolist() if len(dist) else None
        q = lambda p_: int(np.searchsorted(cdf, p_)) if len(cdf) else None
        r0 = rec.get(t, {})
        rows.append({"team": t, "name": N.NAMES.get(t, t), "group": div_of(t, cur), "gp": r0.get("gp", 0),
                     "record": f"{int(r0.get('w', 0))}-{int(r0.get('l', 0))}", "rating": v.get("rating"),
                     "w_mean": v.get("mean_wins"), "w_p10": q(.1), "w_p90": q(.9), "over": over,
                     **{k: v.get(k) for k in ("p_playoff", "p_top6", "p_playin", "p_div", "p_seed1", "p_conf", "p_title")}})
    sched = schedule_context(cur, {r["team"]: r["rating"] for r in rows})
    for r in rows:
        r.update(sched.get(r["team"], {}))
    gp = np.mean([r["gp"] for r in rows]) if rows else 0
    return {"season": cur, "group_label": "Division", "sims": 100000, "main": "p_title",
            "status": f"{cur - 1}-{str(cur)[2:]} season" + (" — before opening night" if gp == 0 else f" — through about {gp:.0f} games per team"),
            "intro": "Projected wins and chances from the season simulation (opponent-adjusted offence and defence, weighted heavily to last season and this season's games, plus a cautious roster adjustment, then every remaining game, the play-in and the playoffs).",
            "backtest_html": _backtest_html(),
            "avail_html": _avail_html(F.get("availability") or {}),
            "proj": {"k": "w_mean", "l": "Proj. wins", "lo": "w_p10", "hi": "w_p90", "f": "num1"},
            "rating_note": "Points per 100 possessions better (+) or worse (−) than an average team",
            "extra": [{"k": "left", "l": "Games left", "f": "int"}, {"k": "road_left", "l": "Road left", "f": "int"},
                      {"k": "b2b_left", "l": "B2Bs left", "f": "int", "t": "Back-to-backs left (second game on consecutive days)"},
                      {"k": "sos_left", "l": "Remaining SOS", "f": "pm1", "t": "Average rating of the opponents still to play (+ = harder)"}],
            "cols": [{"k": "p_playoff", "l": "Playoffs", "t": "Reach the first round (top six or through the play-in)"},
                     {"k": "p_top6", "l": "Top 6", "t": "Avoid the play-in"}, {"k": "p_playin", "l": "Play-in"},
                     {"k": "p_div", "l": "Division"}, {"k": "p_seed1", "l": "No. 1 seed"}, {"k": "p_conf", "l": "Conference"},
                     {"k": "p_title", "l": "Title"}],
            "line": {"label": "Win total", "unit": "wins", "min": 0},
            "about": ["The model does not use bookmaker prices, so it is independent of the market, not proof of value.",
                      "Known absences are included (see Who is out): each player's cost is measured against what the team rating already assumes about his availability. Return dates are ESPN's estimates, drawn with uncertainty in each simulation.",
                      "Rookies and coaching changes are only partly reflected; they matter most before the season.",
                      "The roster adjustment cannot be back-tested (no historical rosters), so it is kept small.",
                      "Against prediction-market prices (Polymarket, 2024-25 and 2025-26) at the same dates: before the season the market was much more accurate; from about 40% of the season the model was more accurate on the title, but not on conference winners. Two seasons only; prices are never used by the model."],
            "teams": rows}


def _avail_html(a):
    from html import escape as e
    stale = ""
    if a.get("stale") and a.get("age_hours") is not None:
        stale = (f'<p class="note"><b>The injury report could not be refreshed; using the last one ({a["age_hours"]:.0f} hours old).</b> '
                 "Only confirmed long-term absences are kept from it; short-term statuses have been dropped.</p>")
    if not a.get("available"):
        return stale + '<p class="note">No injury report could be read, so nobody is listed out; every player is assumed to miss games at his usual rate.</p>'
    rows = [r for r in a.get("rows", []) if r["points"] >= 0.5 and r.get("games", 1) > 0]
    intro = ('<p class="note">Each player has a points value: how much worse his team is per game without him, from his box-score production '
             "per minute over three seasons against a replacement-level rotation player, times his minutes when he plays. "
             "<b>Already in rating</b> is how often he was missing in the games the team rating is built on; only the difference costs "
             "points, so an absence the rating already reflects costs little and a return is an uplift. Players not listed are assumed to miss "
             "games at their usual rate. Return dates are ESPN's estimates; each simulation draws its own return date around them "
             "(two weeks with a wide spread if none is given, longer for surgeries), and anyone still out at the end of the regular season "
             "weakens his team in the playoffs. Listed: players whose absence costs at least half a point and who will miss a regular-season game."
             + (f" Report time {e(str(a.get('feed_time'))[:16].replace('T', ' '))} UTC." if a.get("feed_time") else "") + "</p>")
    if not rows:
        return stale + intro + '<p class="note">No listed absences reach a regular-season game yet.</p>'
    body = "".join(f"<tr><td>{e(r['team'])}</td><td>{e(r['player'])}</td><td>{e(r['status'])}</td><td>{e(r['injury'] or '')}</td>"
                   f"<td>{e(r['est_return'] or 'not given')}</td><td>{r.get('value', 0):.1f}</td><td>{100 * r.get('baseline', 0):.0f}%</td>"
                   f"<td>{r.get('games', '')}</td><td><b>−{r['points']:.1f}</b></td></tr>" for r in rows)
    return (stale + intro + '<div class="scroll"><table class="stbl"><thead><tr><th>Team</th><th>Player</th><th>Status</th><th>Injury</th>'
            '<th>Est. return</th><th title="Points per game his team is worse without him">Value</th>'
            '<th title="Share of the rating\'s games he was already missing">Already in rating</th>'
            '<th title="Remaining regular-season games before the estimated return">Games</th>'
            '<th title="Points per game the team is worse than its rating while he is out">Cost (pts/game)</th></tr></thead><tbody>'
            + body + "</tbody></table></div>" + _avail_record_html(a.get("record")))


def _avail_record_html(rec):
    if not rec or not rec.get("games"):
        return ('<p class="note">Live record: every refresh stores the next games\' probabilities with and without these adjustments; '
                "they are scored here once games are played.</p>")
    return (f'<p class="note"><b>Live record</b> ({rec["games"]} games since {rec["since"]}): log-loss {rec["with"]:.4f} with the '
            f"adjustments vs {rec['without']:.4f} without (lower is better). "
            f"Games where the adjustment moved the probability by 5+ points: {rec['big_games']} ({rec['big_with']:.4f} vs {rec['big_without']:.4f}).</p>")


def _backtest_html():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba_backtest_summary.json")
    if not os.path.exists(p):
        return ""
    b = json.load(open(p))
    lab = {0.0: "Before the season", 0.2: "20% of games played", 0.4: "40%", 0.6: "60%", 0.8: "80%"}
    rows = "".join(f"<tr><td>{lab.get(c, c)}</td><td><b>{b['mae']['current'][i]:.1f}</b></td><td>{b['mae']['last year'][i]:.1f}</td>"
                   f"<td>{b['mae']['record so far'][i]:.1f}</td><td>{b['mae']['previous'][i]:.1f}</td></tr>"
                   for i, c in enumerate(b["checkpoints"]))
    return ('<p class="note">Point-in-time test on ' + str(b["n_seasons"]) + " past seasons (" + b["seasons"] + "): at each checkpoint the model "
            "only sees games already played, projects the rest of that season, and is scored on final wins. Average miss per team, in wins (lower is better). "
            "The roster adjustment is not included because historical rosters are not available.</p>"
            '<div class="scroll"><table class="stbl"><thead><tr><th>When</th><th>This model</th><th>Last season, regressed</th>'
            '<th>Record so far</th><th>Previous version</th></tr></thead><tbody>' + rows + "</tbody></table></div>")


def schedule_context(cur, rating):
    """Games left, road games left, back-to-backs left and average opponent rating still to play."""
    import nba as N
    p = os.path.join(N.NBA_DATA, f"nba_schedule_{cur}.csv")
    if not os.path.exists(p):
        return {}
    s = pd.read_csv(p, low_memory=False)
    s = s[s.season_type == 2].copy()
    for c in ("home_abbreviation", "away_abbreviation"):
        s[c] = s[c].replace(CANON)
    done = s.status_type_completed.astype(str).str.lower().eq("true") if "status_type_completed" in s else False
    day = pd.to_datetime(s.game_date if "game_date" in s else s.date.astype(str).str[:10])
    H = pd.DataFrame({"team": s.home_abbreviation, "opp": s.away_abbreviation, "road": 0, "day": day, "done": done})
    A = pd.DataFrame({"team": s.away_abbreviation, "opp": s.home_abbreviation, "road": 1, "day": day, "done": done})
    g = pd.concat([H, A]).sort_values(["team", "day"])
    g["b2b"] = (g.day - g.groupby("team").day.shift(1)).dt.days.eq(1).astype(int)
    left = g[~g.done.astype(bool)]
    out = {}
    for t, x in left.groupby("team"):
        out[t] = {"left": len(x), "road_left": int(x.road.sum()), "b2b_left": int(x.b2b.sum()),
                  "sos_left": float(x.opp.map(rating).mean()) if len(x) else None}
    return out


# ------------------------------------------------------------------ awards

def awards(cur, player_hist, team_hist):
    from trends_awards import NBA_AW
    P = pd.concat(player_hist, ignore_index=True) if player_hist else pd.DataFrame()
    if P.empty:
        return {"awards": {}}
    tw = pd.concat([t.assign(season=y)[["season", "team", "wp", "conf_rank", "drtg"]] for y, t in team_hist.items()])
    tw["team_rank"] = tw.groupby("season").wp.rank(ascending=False, method="min")
    tw["def_rank"] = tw.groupby("season").drtg.rank(ascending=True, method="min")
    P = P.merge(tw, on=["season", "team"], how="left")
    P["L"] = P.groupby("season").gp.transform("max")
    P["gshare"] = P.gp / P.L
    P["eff_g"] = P.ppg + P.rpg + P.apg + P.spg + P.bpg - P.tpg
    P["def_g"] = P.spg + P.bpg + .3 * P.dreb / P.gp
    seen, rook = set(), []
    for y in sorted(P.season.unique()):
        ids = set(P[P.season == y].athlete_id)
        rook += [(y, i) for i in ids - seen] if y > FIRST else []
        seen |= ids
    rk = set(rook)
    P["rookie"] = [((s, i) in rk) for s, i in zip(P.season, P.athlete_id)]
    P["bench"] = (P.start / P.gp) < .5
    out = {}
    specs = [
        ("MVP", "Most Valuable Player", "MVP", lambda D: D[D.gshare >= .5], "eff_g", 25,
         ["eff_g", "ppg", "pm_g", "wp", "gshare", "ts"], "points-per-game leader"),
        ("DPOY", "Defensive Player of the Year", "DPOY", lambda D: D[D.gshare >= .5], "def_g", 20,
         ["def_g", "bpg", "spg", "rpg", "wp", "gshare"], "blocks + steals leader"),
        ("ROY", "Rookie of the Year", "ROY", lambda D: D[D.rookie & (D.gshare >= .3)], "eff_g", 15,
         ["eff_g", "ppg", "mpg", "gshare", "wp"], "rookie scoring leader"),
        ("6MOY", "Sixth Man of the Year", "Sixth Man", lambda D: D[D.bench & (D.gshare >= .5)], "ppg", 15,
         ["ppg", "mpg", "pm_g", "wp", "gshare"], "bench scoring leader"),
    ]
    show = [C("gp", "GP", "", "int"), C("mpg", "MIN", "", "num1"), C("ppg", "PTS", "", "num1"), C("rpg", "REB", "", "num1"),
            C("apg", "AST", "", "num1"), C("spg", "STL", "", "num1"), C("bpg", "BLK", "", "num1"), C("ts", "TS%", "", "pct"),
            C("pm_g", "+/-", "", "pm1"), C("wp", "Team W%", "", "pct")]
    for key, title, short, poolf, rankcol, n, feats, leader in specs:
        pools = []
        for y, D in P.groupby("season"):
            D = poolf(D).sort_values(rankcol, ascending=False).head(n).copy()
            winners = {y_: AM_norm(n_) for y_, n_ in NBA_AW[key].items()}
            D["win"] = [float(AM_norm(nm) == winners.get(y)) if y != cur else np.nan for nm in D.name]
            pools.append(D)
        Pool = pd.concat(pools, ignore_index=True)
        Pool[feats] = Pool[feats].fillna(Pool[feats].median())
        hist = Pool[Pool.season != cur]
        lead_col = "ppg" if key in ("MVP", "ROY", "6MOY") else "def_g"
        bt = AM.loso(hist, feats, leader_col=lead_col)
        if bt:
            bt["leader_label"] = leader
        beta = AM.fit(hist, feats)
        now = Pool[Pool.season == cur].copy()
        cur_rows = []
        if len(now):
            now["prob"] = AM.predict(now, feats, beta)
            now = now.sort_values("prob", ascending=False).head(15)
            cur_rows = now[["name", "team", "prob"] + [c["k"] for c in show]].to_dict("records")
        past = []
        for y, nm in sorted(NBA_AW[key].items(), reverse=True):
            x = Pool[(Pool.season == y) & (Pool.win == 1)]
            if len(x):
                r = x.iloc[0]
                past.append({"season": int(y), "name": r["name"], "team": r.team, **{c["k"]: r[c["k"]] for c in show}})
            else:
                past.append({"season": int(y), "name": nm, "team": ""})
        out[key] = {"title": title, "short": short, "backtest": bt, "cols": show, "current": cur_rows, "past": past,
                    "past_note": "Each winner's final per-game numbers and his team's record.",
                    "note": f"Chances come from a model fitted on every winner since {FIRST - 1}-{str(FIRST)[2:]}, using the candidate's numbers to date, his team's record and games played. Pool: top {n} by {('box-score production' if rankcol == 'eff_g' else 'steals, blocks and rebounds' if rankcol == 'def_g' else 'scoring')}.",
                    "empty": "The season has not started; chances appear after the first games."}
    return {"order": ["MVP", "DPOY", "ROY", "6MOY"], "awards": out,
            "intro": "Award chances from a model trained on past voting, tested one season at a time. The winning-team pull and availability rules (65 games) matter as much as raw numbers — see the Trends tab."}


def AM_norm(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s+(jr|sr|ii|iii|iv)\.?$", "", s.strip())
    return re.sub(r"[^a-z]", "", s)


PAGES = [("index", "Standings", "NBA standings", "Records, ratings, luck and splits by division, conference or league. Any season since 2002-03."),
         ("futures", "Futures", "NBA season futures", "Projected wins and chances for the playoffs, play-in, division, No. 1 seed, conference and title, plus a win-total over/under tool."),
         ("awards", "Awards", "NBA award chances", "MVP, Defensive Player, Rookie and Sixth Man chances from a model tested on every season since 2002-03, with past winners."),
         ("teams", "Team stats", "NBA team stats", "Ratings, four factors, shooting, shot profile, splits (home/road, back-to-backs, close games, vs winning teams) and box score. Season table or year by year."),
         ("players", "Players", "NBA player stats", "Per game, shooting, per 36, totals and NBA advanced (usage, ratings, PIE) for every player since 2002-03, regular season and playoffs."),
         ("games", "Games", "NBA game logs", "Every team game since 2002-03 with efficiency, four factors and rest days.")]


def build_site():
    S.build_pages(SITE, "NBA", "Futures", PAGES, data_src=OUT)
    S.log("NBA site pages written")


if __name__ == "__main__":
    build_data()
    build_site()
