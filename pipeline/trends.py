"""Winner trends for each league: what past champions, finalists, top seeds, division winners and playoff teams
had in common, filtered for noise (see trends_engine). Writes <sport>/data/trends.json and a Trends page per sport.
"""
import datetime as dt
import json
import os
import re
import shutil
import urllib.request

import numpy as np
import pandas as pd

import trends_engine as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(ROOT, "data")
SRC = os.path.join(ROOT, "site_src", "trends")


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), "trends", *a, flush=True)


def _http(url, path, max_age_h):
    if os.path.exists(path) and (dt.datetime.now().timestamp() - os.path.getmtime(path)) < max_age_h * 3600:
        return path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        with open(path, "wb") as f:
            f.write(body)
    except Exception as e:  # keep a stale copy if there is one
        log("download failed", url, e)
    return path if os.path.exists(path) else None


def _rows(G, season, date, team, opp, home, pf, pa, pts, maxpts, gid):
    return pd.DataFrame(dict(season=season, date=date, team=team, opp=opp, home=home, pf=pf, pa=pa, pts=pts,
                             maxpts=maxpts, gid=gid))


def _two_sided(df, s, d, h, a, hs, as_, gid, pts_fn, maxpts=1):
    """Home/away game rows -> one row per team per game."""
    H = _rows(None, df[s], df[d], df[h], df[a], True, df[hs], df[as_], pts_fn(df[hs], df[as_]), maxpts, df[gid])
    A = _rows(None, df[s], df[d], df[a], df[h], False, df[as_], df[hs], pts_fn(df[as_], df[hs]), maxpts, df[gid])
    out = pd.concat([H, A], ignore_index=True)
    out["win"] = out.pf > out.pa
    return out


def wl_pts(f, a):
    return np.where(f > a, 1.0, np.where(f == a, 0.5, 0.0))


# ------------------------------------------------------------------ NFL

def nfl():
    from common import FIX, NAMES
    g = pd.read_csv(os.path.join(DATA, "games.csv"), low_memory=False)
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    g = g[g.season >= 2002]
    played = g[g.result.notna()]
    G = _two_sided(played[played.game_type == "REG"], "season", "gameday", "home_team", "away_team", "home_score",
                   "away_score", "game_id", wl_pts)
    P = _two_sided(played[played.game_type != "REG"], "season", "gameday", "home_team", "away_team", "home_score",
                   "away_score", "game_id", wl_pts)
    st_path = _http("https://raw.githubusercontent.com/nflverse/nfldata/master/data/standings.csv",
                    os.path.join(DATA, "nfl_standings.csv"), 6)
    st = pd.read_csv(st_path)
    st["team"] = st.team.replace(FIX)
    M = st.rename(columns={"division": "div"})[["season", "team", "conf", "div", "seed", "div_rank"]]
    M["name"] = M.team.map(NAMES)
    # seeds from the source (official tie-breaks); non-playoff teams sit below the seeds
    M["final_dv_rank"] = M.div_rank
    M = M.drop(columns=["div_rank"])
    cur = int(g.season.max())
    M["final_playoffs"] = np.where(M.season < cur, M.seed.notna().astype(float), np.nan)
    M["spots"] = np.where(M.season >= 2020, 7, 6)

    # market strength from the first four weeks of point spreads (home margin = r_home - r_away + hfa)
    mk = []
    for s, x in g[(g.game_type == "REG") & (g.week <= 4) & g.spread_line.notna()].groupby("season"):
        teams = sorted(set(x.home_team) | set(x.away_team))
        ix = {t: i for i, t in enumerate(teams)}
        X = np.zeros((len(x), len(teams) + 1))
        for r, (h, a, neutral) in enumerate(zip(x.home_team, x.away_team, x.location == "Neutral")):
            X[r, ix[h]], X[r, ix[a]] = 1, -1
            X[r, -1] = 0 if neutral else 1
        y = x.spread_line.values
        lam = np.eye(X.shape[1]) * 0.5
        lam[-1, -1] = 0
        beta = np.linalg.solve(X.T @ X + lam, X.T @ y)
        mk += [dict(season=s, team=t, mkt=beta[ix[t]]) for t in teams]
    M = M.merge(pd.DataFrame(mk), on=["season", "team"], how="left")

    def post(T):
        T["mkt_lg"] = T.groupby("season").mkt.rank(ascending=False, method="min")
        T["mkt_cf"] = T.groupby(["season", "conf"]).mkt.rank(ascending=False, method="min")
        T["mkt_dv"] = T.groupby(["season", "div"]).mkt.rank(ascending=False, method="min")
        # a seed is official only for playoff teams; everyone else ranks below them
        T["cf_rank"] = np.where(T.seed.notna(), T.seed, 8 + T.cf_rank)
        return T

    has_mkt = lambda T: T.mkt.notna()
    cfg = dict(sport="nfl", name="NFL", close=8, close_word="8 points or fewer", pyth=2.37, pd_word="point differential",
               pf_word="points", conf=True, div=True, conf_word="conference", deep_rounds=2,
               label=lambda s: str(int(s)), min_games=1, post=post,
               extra_pre=[
                   ("mkt_top5", "Top-5 in the betting market's team ratings (weeks 1-4 point spreads)",
                    ["champ", "finalist", "top_seed", "playoffs"], lambda T: T.mkt_lg <= 5, has_mkt),
                   ("mkt_conf_top", "Market's highest-rated team in its conference (weeks 1-4 spreads)",
                    ["top_seed", "finalist"], lambda T: T.mkt_cf == 1, has_mkt),
                   ("mkt_div_top", "Market's highest-rated team in its division (weeks 1-4 spreads)",
                    ["div_win"], lambda T: T.mkt_dv == 1, has_mkt),
                   ("mkt_bottom_half", "Bottom half of the market's ratings (weeks 1-4 spreads)",
                    ["playoffs"], lambda T: T.mkt_lg > 16, has_mkt),
               ])
    return G, P, M, cfg


# ------------------------------------------------------------------ NBA

NBA_CANON = {"NJ": "BKN", "SEA": "OKC", "NOH": "NO", "NOK": "NO", "GSW": "GS", "SAS": "SA", "NYK": "NY", "UTA": "UTAH",
             "WAS": "WSH", "PHO": "PHX", "NOP": "NO", "BRK": "BKN", "CHO": "CHA"}
NBA_DIVS = {"Atlantic": ["BOS", "BKN", "NY", "PHI", "TOR"], "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
            "Southeast": ["ATL", "CHA", "MIA", "ORL", "WSH"], "Northwest": ["DEN", "MIN", "OKC", "POR", "UTAH"],
            "Pacific": ["GS", "LAC", "LAL", "PHX", "SAC"], "Southwest": ["DAL", "HOU", "MEM", "NO", "SA"]}
NBA_EAST = {"Atlantic", "Central", "Southeast"}


def nba():
    import nba as N
    first, cur = 2003, N.season_end_year()
    frames = []
    for y in range(first, cur + 1):
        p = N._download("espn_nba_team_boxscores", f"team_box_{y}.csv", 2 if y >= cur - 1 else 24 * 365,
                        required=y < cur)
        if p and os.path.exists(p):
            t = pd.read_csv(p, low_memory=False)
            if len(t):
                frames.append(t)
    t = pd.concat(frames, ignore_index=True)
    for c in ("team_abbreviation", "opponent_team_abbreviation"):
        t[c] = t[c].replace(NBA_CANON)
    teams = {x for v in NBA_DIVS.values() for x in v}
    t = t[t.team_abbreviation.isin(teams) & t.opponent_team_abbreviation.isin(teams)]
    t = t.drop_duplicates(["game_id", "team_abbreviation"])
    t["pts_"] = t.team_winner.astype(str).str.lower().eq("true").astype(float)

    def rows(x):
        out = pd.DataFrame(dict(season=x.season, date=x.game_date, team=x.team_abbreviation, opp=x.opponent_team_abbreviation,
                                home=x.team_home_away.eq("home"), pf=x.team_score, pa=x.opponent_team_score,
                                pts=x.pts_, maxpts=1.0, gid=x.game_id))
        out["win"] = out.pts == 1
        return out.reset_index(drop=True)

    G = rows(t[t.season_type == 2])
    P = rows(t[t.season_type == 3])
    # 3-point profile per team-season (shooting and share of shots that are threes)
    reg = t[t.season_type == 2]
    agg = reg.groupby(["season", "team_abbreviation"]).agg(f3m=("three_point_field_goals_made", "sum"),
                                                          f3a=("three_point_field_goals_attempted", "sum"),
                                                          fga=("field_goals_attempted", "sum"),
                                                          tov=("total_turnovers", "sum"))
    opp = reg.groupby(["season", "opponent_team_abbreviation"]).agg(o3m=("three_point_field_goals_made", "sum"),
                                                                    o3a=("three_point_field_goals_attempted", "sum"),
                                                                    otov=("total_turnovers", "sum"))
    opp.index.names = agg.index.names
    X = agg.join(opp).reset_index().rename(columns={"team_abbreviation": "team"})
    X["fg3_pct"], X["fg3_rate"], X["opp_fg3_pct"] = X.f3m / X.f3a, X.f3a / X.fga, X.o3m / X.o3a
    X["tov_margin"] = X.otov - X.tov
    names = t.drop_duplicates("team_abbreviation").set_index("team_abbreviation").team_display_name.to_dict()
    names.update(N.NAMES)
    M = []
    for s in sorted(set(G.season) | {cur}):
        for d, ts in NBA_DIVS.items():
            for tm in ts:
                if tm == "CHA" and s < 2005:
                    continue
                conf = "East" if d in NBA_EAST or (tm == "NO" and s <= 2004) else "West"
                M.append(dict(season=s, team=tm, name=names.get(tm, tm), conf=conf, div=d if s >= 2005 else None, spots=8))
    M = pd.DataFrame(M).merge(X[["season", "team", "fg3_pct", "fg3_rate", "opp_fg3_pct", "tov_margin"]],
                              on=["season", "team"], how="left")
    for c in ("fg3_pct", "fg3_rate", "tov_margin"):
        M[f"{c}_lg"] = M.groupby("season")[c].rank(ascending=False, method="min")
    M["opp_fg3_pct_lg"] = M.groupby("season").opp_fg3_pct.rank(ascending=True, method="min")
    k = lambda T: E.topk(T, 5)
    has = lambda c: (lambda T: T[c].notna())
    cfg = dict(sport="nba", name="NBA", close=5, close_word="5 points or fewer", pyth=14, pd_word="point differential",
               pf_word="points", conf=True, div=True, conf_word="conference", deep_rounds=2,
               label=lambda s: f"{int(s) - 1}-{str(int(s))[2:]}", min_games=4,
               extra_end=[
                   ("fg3_top", "Top-5 three-point percentage", lambda T: T.fg3_pct_lg <= k(T), has("fg3_pct")),
                   ("fg3_rate_top", "Top-5 for share of shots taken from three", lambda T: T.fg3_rate_lg <= k(T), has("fg3_rate")),
                   ("opp_fg3_top", "Top-5 at holding opponents' three-point percentage down",
                    lambda T: T.opp_fg3_pct_lg <= k(T), has("opp_fg3_pct")),
                   ("tov_top", "Top-5 turnover margin", lambda T: T.tov_margin_lg <= k(T), has("tov_margin")),
               ])
    return G, P, M, cfg


# ------------------------------------------------------------------ NHL

NHL_CANON = {"ATL": "WPG", "PHX": "ARI"}
NHL_OLD = {"Atlantic": ["NJD", "NYI", "NYR", "PHI", "PIT"], "Northeast": ["BOS", "BUF", "MTL", "OTT", "TOR"],
           "Southeast": ["WPG", "CAR", "FLA", "TBL", "WSH"], "Central": ["CHI", "CBJ", "DET", "NSH", "STL"],
           "Northwest": ["CGY", "COL", "EDM", "MIN", "VAN"], "Pacific": ["ANA", "DAL", "LAK", "ARI", "SJS"]}
NHL_OLD_EAST = {"Atlantic", "Northeast", "Southeast"}
NHL_MID = {"Atlantic": ["BOS", "BUF", "DET", "FLA", "MTL", "OTT", "TBL", "TOR"],
           "Metropolitan": ["CAR", "CBJ", "NJD", "NYI", "NYR", "PHI", "PIT", "WSH"],
           "Central": ["CHI", "COL", "DAL", "MIN", "NSH", "STL", "WPG"],
           "Pacific": ["ANA", "ARI", "CGY", "EDM", "LAK", "SJS", "VAN", "VGK"]}
NHL_2020 = {"North": ["CGY", "EDM", "MTL", "OTT", "TOR", "VAN", "WPG"],
            "East": ["BOS", "BUF", "NJD", "NYI", "NYR", "PHI", "PIT", "WSH"],
            "Central": ["CAR", "CBJ", "CHI", "DAL", "DET", "FLA", "NSH", "TBL"],
            "West": ["ANA", "ARI", "COL", "LAK", "MIN", "SJS", "STL", "VGK"]}
NHL_NOW = {"Atlantic": ["BOS", "BUF", "DET", "FLA", "MTL", "OTT", "TBL", "TOR"],
           "Metropolitan": ["CAR", "CBJ", "NJD", "NYI", "NYR", "PHI", "PIT", "WSH"],
           "Central": ["ARI", "CHI", "COL", "DAL", "MIN", "NSH", "STL", "UTA", "WPG"],
           "Pacific": ["ANA", "CGY", "EDM", "LAK", "SEA", "SJS", "VAN", "VGK"]}


def nhl_align(s, t):
    if s <= 2012:
        for d, ts in NHL_OLD.items():
            if t in ts:
                return ("East" if d in NHL_OLD_EAST else "West"), d
    elif s <= 2019:
        for d, ts in NHL_MID.items():
            if t in ts:
                return ("East" if d in ("Atlantic", "Metropolitan") else "West"), d
    elif s == 2020:
        for d, ts in NHL_2020.items():
            if t in ts:
                return None, d
    else:
        for d, ts in NHL_NOW.items():
            if t in ts:
                return ("East" if d in ("Atlantic", "Metropolitan") else "West"), d
    return None, None


def _cols(path, nid):
    d = json.load(open(path))
    keys = [c["k"] for c in d["cols"]]
    return pd.DataFrame([dict(zip(["_id%d" % i for i in range(nid)] + keys, r)) for r in d["rows"]])


def _nhl_games_published(y, po):
    p = os.path.join(SITE, "nhl", "data", f"games_{y}{'p' if po else ''}.json")
    if not os.path.exists(p):
        return None
    d = _cols(p, 5)
    if d.empty:
        return None
    res = d._id4
    out = pd.DataFrame(dict(season=y, date=d._id0, team=d._id1, opp=d._id2, home=d._id3.eq("H"), pf=d.goalsFor,
                            pa=d.goalsAgainst, pts=np.select([res.eq("W"), res.isin(["OTL", "T"])], [2.0, 1.0], 0.0),
                            maxpts=2.0))
    # same game appears twice (once per team): build an id from date + sorted pair
    out["gid"] = out.date + "|" + [("-".join(sorted(p))) for p in zip(out.team, out.opp)]
    out["win"] = res.eq("W")
    return out


def _nhl_games_api(y, po):
    import nhl as H
    rows = H._fetch("team", "summary", y, True, False, 3 if po else 2)
    if not rows:
        return None, {}
    by = {}
    for r in rows:
        by.setdefault(r["gameId"], []).append(r)
    tid = {}
    for v in by.values():
        if len(v) == 2:
            tid[v[0]["teamId"]] = v[1].get("opponentTeamAbbrev")
            tid[v[1]["teamId"]] = v[0].get("opponentTeamAbbrev")
    d = pd.DataFrame(rows)
    d["team"] = d.teamId.map(tid)
    d = d[d.team.notna()]
    for c in ("wins", "otLosses", "ties"):
        if c not in d:
            d[c] = 0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    out = pd.DataFrame(dict(season=y, date=d.gameDate.astype(str).str[:10], team=d.team, opp=d.opponentTeamAbbrev,
                            home=d.homeRoad.eq("H"), pf=d.goalsFor, pa=d.goalsAgainst,
                            pts=2.0 * d.wins + d.otLosses + d.ties, maxpts=2.0, gid=d.gameId.astype(str)))
    out["win"] = d.wins.values > 0
    return out.reset_index(drop=True), tid


def nhl():
    import nhl as H
    cur = H.start_year()
    Gs, Ps, X = [], [], []
    for y in range(2000, cur + 1):
        if y == 2004:
            continue                                            # lockout
        g = _nhl_games_published(y, False)
        p = _nhl_games_published(y, True)
        if g is not None:
            tp = os.path.join(SITE, "nhl", "data", f"team_{y}.json")
            if os.path.exists(tp):
                t = _cols(tp, 2)
                t["team"], t["season"] = t._id0, y
                X.append(t[[c for c in ("season", "team", "powerPlayPct", "penaltyKillPct", "satPct", "savePct5v5",
                                        "shotsForPerGame", "shotsAgainstPerGame") if c in t]])
        elif y < H.FIRST and os.environ.get("TRENDS_NHL_OLD", "1") != "0":
            try:
                g, tid = _nhl_games_api(y, False)
                p, _ = _nhl_games_api(y, True)
                s = H._fetch("team", "summary", y, False, False, 2) or []
                if s:
                    t = pd.DataFrame(s)
                    t["team"], t["season"] = t.teamId.map(tid), y
                    X.append(t[[c for c in ("season", "team", "powerPlayPct", "penaltyKillPct", "shotsForPerGame",
                                            "shotsAgainstPerGame") if c in t]])
            except Exception as e:
                log("nhl old season failed", y, e)
                g = p = None
        if g is not None:
            Gs.append(g)
        if p is not None:
            Ps.append(p)
    G, P = pd.concat(Gs, ignore_index=True), pd.concat(Ps, ignore_index=True)
    for D in (G, P):
        for c in ("team", "opp"):
            D[c] = D[c].replace(NHL_CANON)
    X = pd.concat(X, ignore_index=True) if X else pd.DataFrame(columns=["season", "team"])
    X["team"] = X.team.replace(NHL_CANON)
    names = json.load(open(os.path.join(SITE, "nhl", "data", "meta.json"))).get("teams", {}) if os.path.exists(
        os.path.join(SITE, "nhl", "data", "meta.json")) else {}
    if isinstance(names, str):
        names = {}
    names.update({"WPG": "Winnipeg Jets / Atlanta Thrashers", "ARI": "Arizona / Phoenix Coyotes"})
    M = []
    for s in sorted(set(G.season)):
        for tm in sorted(set(G[G.season == s].team)):
            c, d = nhl_align(s, tm)
            M.append(dict(season=s, team=tm, name=names.get(tm, tm), conf=c, div=d, spots=4 if s == 2020 else 8))
    M = pd.DataFrame(M).merge(X, on=["season", "team"], how="left")
    for c, asc in (("powerPlayPct", False), ("penaltyKillPct", False), ("satPct", False), ("savePct5v5", False),
                   ("shotsForPerGame", False), ("shotsAgainstPerGame", True)):
        if c in M:
            M[f"{c}_lg"] = M.groupby("season")[c].rank(ascending=asc, method="min")
        else:
            M[c] = M[f"{c}_lg"] = np.nan
    k = lambda T: E.topk(T, 5)
    has = lambda c: (lambda T: T[c].notna())
    cfg = dict(sport="nhl", name="NHL", close=1, close_word="one goal (including overtime and shootouts)", pyth=2.0,
               pd_word="goal differential", pf_word="goals", conf=True, div=True, conf_word="conference", deep_rounds=2,
               label=lambda s: f"{int(s)}-{str(int(s) + 1)[2:]}", min_games=3, after={2019: "2020-08-11"},
               extra_end=[
                   ("pp_top", "Top-5 power play", lambda T: T.powerPlayPct_lg <= k(T), has("powerPlayPct")),
                   ("pk_top", "Top-5 penalty kill", lambda T: T.penaltyKillPct_lg <= k(T), has("penaltyKillPct")),
                   ("corsi_top", "Top-5 shot-attempt share at 5-on-5 (Corsi)", lambda T: T.satPct_lg <= k(T), has("satPct")),
                   ("sv5_top", "Top-5 save percentage at 5-on-5", lambda T: T.savePct5v5_lg <= k(T), has("savePct5v5")),
                   ("shots_top", "Top-5 shots on goal per game", lambda T: T.shotsForPerGame_lg <= k(T), has("shotsForPerGame")),
                   ("shots_ag_top", "Top-5 at limiting shots against", lambda T: T.shotsAgainstPerGame_lg <= k(T),
                    has("shotsAgainstPerGame")),
               ])
    return G, P, M, cfg


# ------------------------------------------------------------------ NBL

# Grand Final winner and runner-up by season start year (checked against NBL records; the feed is missing scores
# for some finals games, e.g. Game 5 in 2018)
NBL_FINALS = {2012: ("NZL", "PER"), 2013: ("PER", "ADL"), 2014: ("NZL", "CNS"), 2015: ("PER", "NZL"), 2016: ("PER", "ILL"),
              2017: ("MEL", "ADL"), 2018: ("PER", "MEL"), 2019: ("PER", "SYD"), 2020: ("MEL", "PER"), 2021: ("SYD", "TAS"),
              2022: ("SYD", "NZL"), 2023: ("TAS", "MEL"), 2024: ("ILL", "MEL"), 2025: ("SYD", "ADL")}


def _nbl_src():
    """The raw NBL feed export (build copy; the published site no longer carries it)."""
    for p in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "nbl_stats_index.json"),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site", "nbl", "data", "stats_index.json")):
        if os.path.exists(p):
            return p
    return p


def nbl():
    path = _nbl_src()
    canon = {"WOL": "ILL"}
    D = json.load(open(path))
    Gs, Ps, Ms = [], [], []
    for key, S in D["seasons"].items():
        y = int(key)
        # the feed may hold regular-season and finals rows together (tagged by "phase"); the ladder is regular only
        st = [r for r in (S.get("standings") or []) if str(r.get("phase", "Regular")).lower() == "regular"]
        if not st:
            continue
        code = lambda c: canon.get(c, c)
        reg_n = {code(r["team"]["team_code"]): int(r["won"]) + int(r["lost"]) for r in st}
        pos = {code(r["team"]["team_code"]): int(r["position"]) for r in st}
        names = {code(r["team"]["team_code"]): r["team"]["name"] for r in st}
        rows, seen_ids = [], set()
        for g in S.get("games") or []:
            if g.get("id") in seen_ids:
                continue
            seen_ids.add(g.get("id"))
            if g.get("match_status") != "complete" or "CUP" in str(g.get("round", "")).upper():
                continue
            h, a = code((g.get("home_team") or {}).get("team_code")), code((g.get("away_team") or {}).get("team_code"))
            if h not in reg_n or a not in reg_n:
                continue
            try:
                hs, as_ = float(g["home_score"]), float(g["away_score"])
            except (TypeError, ValueError):
                continue
            rows.append(dict(date=str(g.get("start_time") or "")[:10], h=h, a=a, hs=hs, as_=as_, gid=g["id"]))
        if not rows:
            continue
        x = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        seen = {t: 0 for t in reg_n}
        fin = []
        for i, r in x.iterrows():
            is_fin = seen[r.h] >= reg_n[r.h] and seen[r.a] >= reg_n[r.a]
            fin.append(is_fin)
            if not is_fin:
                seen[r.h] += 1
                seen[r.a] += 1
        x["fin"] = fin
        x["season"] = y
        both = _two_sided(x, "season", "date", "h", "a", "hs", "as_", "gid", wl_pts)
        isfin = both.gid.map(dict(zip(x.gid, x.fin)))
        Gs.append(both[~isfin])
        Ps.append(both[isfin])
        for t in reg_n:
            Ms.append(dict(season=y, team=t, name=names[t], conf="NBL", div=None, spots=4,
                           final_lg_rank=pos[t], final_cf_rank=pos[t]))
    G, P, M = pd.concat(Gs, ignore_index=True), pd.concat(Ps, ignore_index=True), pd.DataFrame(Ms)
    cfg = dict(sport="nbl", name="NBL", close=5, close_word="5 points or fewer", pyth=14, pd_word="point differential",
               pf_word="points", conf=False, div=False, conf_word="league", deep_rounds=1,
               label=lambda s: f"{int(s)}-{str(int(s) + 1)[2:]}", min_games=2, known=NBL_FINALS)
    return G, P, M, cfg


# ------------------------------------------------------------------ AFL

def afl():
    import afl_site as A
    Gs, Ps, Ms, known = [], [], [], {}
    for y in range(A.FIRST, 2100):
        d = A.load_season(y)
        if d is None:
            if y > A.FIRST + 1:
                break
            continue
        g = A.team_games(d, y)
        if g is None or g.empty:
            continue
        g["pts"] = g.win
        g["maxpts"] = 1.0
        g["home"] = g.ha.eq("H")
        g = g.rename(columns={"points_for": "pf", "points_against": "pa", "match_id": "gid"})
        cols = ["season", "date", "team", "opp", "home", "pf", "pa", "pts", "maxpts", "gid", "win"]
        Gs.append(g[g.season_type == "REG"][cols])
        Ps.append(g[g.season_type == "FIN"][cols].assign(win=lambda x: x.win == 1))
        for t in sorted(set(g.team)):
            Ms.append(dict(season=y, team=t, name=A.NAMES.get(t, t), conf="AFL", div=None, spots=10 if y >= 2026 else 8))
        gf = [m for m in d.get("matches") or [] if m.get("round") == "GF"]
        if gf:
            m = gf[-1]
            h, a = A.code(m["home_team"]), A.code(m["away_team"])
            known[y] = (h, a) if m["home_score"] > m["away_score"] else (a, h)
    G, P, M = pd.concat(Gs, ignore_index=True), pd.concat(Ps, ignore_index=True), pd.DataFrame(Ms)
    cfg = dict(sport="afl", name="AFL", close=12, close_word="12 points (two goals) or fewer", pyth=3.9, pd_word="points margin",
               pf_word="points", conf=False, div=False, conf_word="league", deep_rounds=2, label=lambda s: str(int(s)), min_games=1,
               known=known)
    return G, P, M, cfg


# ------------------------------------------------------------------ build

SECTIONS = {
    "nfl": [("champ", "Super Bowl winner", "playoff teams"), ("finalist", "Conference champion (reach the Super Bowl)", "playoff teams"),
            ("top_seed", "No. 1 seed in the conference", "teams"), ("div_win", "Division winner", "teams"),
            ("playoffs", "Make the playoffs", "teams")],
    "nba": [("champ", "NBA champion", "playoff teams"), ("finalist", "Conference champion (reach the Finals)", "playoff teams"),
            ("top_seed", "No. 1 seed in the conference", "teams"), ("div_win", "Division winner", "teams"),
            ("playoffs", "Make the playoffs (first round)", "teams")],
    "nhl": [("champ", "Stanley Cup winner", "playoff teams"), ("finalist", "Conference champion (reach the Cup Final)", "playoff teams"),
            ("top_seed", "Top of the conference", "teams"), ("div_win", "Division winner", "teams"),
            ("playoffs", "Make the playoffs", "teams")],
    "afl": [("champ", "Premiers", "finals teams"), ("finalist", "Reach the Grand Final", "finals teams"),
            ("top_seed", "Minor premiership (top of the ladder)", "all teams"), ("playoffs", "Make the finals", "all teams")],
    "nbl": [("champ", "NBL champion", "semi-finalists"), ("finalist", "Reach the Grand Final", "semi-finalists"),
            ("top_seed", "Minor premiership (top of the ladder)", "teams"),
            ("playoffs", "Make the semi-finals", "teams")],
}
# Plausibility review (TypeSafe, Oct 2026) of findings that beat or fell short of the record: probability the
# pattern is a real, persistent effect rather than a small-sample streak. Below 0.5 -> downgraded to "Unproven".
REVIEW = {
    "nfl:top_seed:playoffs_prev": 0.61, "nfl:top_seed:unlucky_prev": 0.65, "nfl:top_seed:lost_final_prev": 0.39,
    "nfl:div_win:playoffs_prev": 0.60, "nfl:div_win:div_pd_not_lead_h": 0.62, "nfl:playoffs:out_spot_good_pd_h": 0.63,
    "nfl:playoffs:unlucky_prev": 0.61, "nfl:playoffs:lucky_h": 0.60, "nfl:playoffs:lucky_q": 0.60,
    "nfl:playoffs:lucky_prev": 0.64, "nfl:playoffs:out_spot_good_pd_q": 0.69, "nba:playoffs:spot_h": 0.60,
    "nba:playoffs:spot_q": 0.60,
    "nhl:finalist:corsi_top": 0.70, "nhl:finalist:shots_top": 0.74, "nhl:finalist:shots_ag_top": 0.71,
    "nhl:playoffs:unlucky_prev": 0.70,
    "afl:finalist:pd_top3": 0.88, "afl:finalist:unlucky": 0.88,
    # awards
    "afl:brownlow:top5_cp": 0.89, "afl:brownlow:top5_clr": 0.89,
    "nba:mvp:team_top3": 0.92, "nba:mvp:conf_top": 0.93, "nba:mvp:pm_top3": 0.93, "nba:mvp:durable": 0.93,
    "nba:mvp:team_out8": 0.93, "nba:dpoy:team_def5": 0.93, "nba:dpoy:team_top3": 0.93, "nba:6moy:team_top8": 0.92,
    "nhl:vezina:top3_wins": 0.93, "nhl:vezina:team_top3": 0.93, "nhl:vezina:workload": 0.93, "nbl:mvp:led_ppg": 0.93,
    "nbl:mvp:team_top4": 0.93, "nfl:mvp:seed1": 0.93, "nba:playoffs:lucky_q": 0.70, "nba:playoffs:lucky_h": 0.69,
}
MECHANISM = [
    ("lucky", "Winning close games is mostly luck and does not carry over, so records that run ahead of scoring tend to fall back."),
    ("unlucky", "Scoring margin predicts future results better than the win-loss record, so unlucky teams tend to bounce back."),
    ("out_spot_good_pd", "Scoring margin is a better guide to true strength than the record, so these teams tend to climb."),
    ("div_pd_not_lead", "Scoring margin is a better guide to true strength than the record, so these teams tend to climb."),
    ("pd_beats_record", "Scoring margin is a better guide to true strength than the record."),
    ("underrated_prev", "Scoring margin is a better guide to true strength than the record."),
    ("playoffs_prev", "Playoff teams usually keep their core (quarterback, coach, stars), which last season's record alone understates."),
    ("spot_", "Conference position captures conference strength and schedule that the league-wide record misses."),
    ("corsi", "Controlling shot attempts predicts playoff success better than the record, which leans on goaltending and luck."),
    ("shots", "Controlling shot volume predicts playoff success better than the record, which leans on goaltending and luck."),
    ("lost_final_prev", "Beaten finalists have tended to slip back the following season."),
    ("top5_cp", "Umpires' votes favour inside midfielders who win the contested ball."),
    ("top5_clr", "Umpires' votes favour inside midfielders who win the clearances."),
    ("pd_top", "Scoring margin is a better guide to true strength than the record."),
    ("team_def", "Voters credit defenders on the best defensive teams."),
    ("team_", "Voters reward players on winning teams; individual numbers alone underrate them."),
    ("conf_top", "Voters reward players on winning teams; individual numbers alone underrate them."),
    ("seed", "Voters reward the quarterback of the best team."),
    ("pm_top", "Plus-minus tracks team success, which voters weigh heavily."),
    ("durable", "Voters mark down players who miss games."),
    ("workload", "Voters (the general managers) favour goalies who carry the workload."),
    ("top3_wins", "Vezina voters weigh goalie wins heavily, beyond save quality."),
    ("led_wins", "Vezina voters weigh goalie wins heavily, beyond save quality."),
    ("led_ppg", "A scoring title carries weight with voters beyond overall efficiency."),
]


def review(sport, sec, r):
    if r["verdict"] not in ("edge", "fade"):
        return
    p = REVIEW.get(f"{sport}:{sec}:{r['key']}")
    why = next((m for k, m in MECHANISM if r["key"].startswith(k)), None)
    if p is not None and p < 0.5:
        r["verdict"] = "weak"
        r["why"] = "Passed the statistical tests, but the plausibility review rates it more likely a small-sample streak"
        return
    bits = []
    if why:
        bits.append(why)
    if p is not None:
        bits.append(f"TypeSafe rates it a real effect ({round(p * 100)}%).")
    r["review"] = " ".join(bits) or None


OUTPUT = {"afl": os.path.join(SITE, "afl", "data"), "nfl": os.path.join(SITE, "data"), "nba": os.path.join(SITE, "nba", "data"),
          "nhl": os.path.join(SITE, "nhl", "data"), "nbl": os.path.join(SITE, "nbl", "data")}
LOADERS = {"nfl": nfl, "nba": nba, "nhl": nhl, "nbl": nbl, "afl": afl}


def analyse(sport):
    G, P, M, cfg = LOADERS[sport]()
    T = E.team_table(G, M, cfg)
    # every team in the current season gets a row even before it has played
    missing = M.merge(T[["season", "team"]], on=["season", "team"], how="left", indicator=True)
    missing = missing[missing._merge == "left_only"].drop(columns="_merge")
    if len(missing):
        T = pd.concat([T, missing], ignore_index=True)
        T["nteams"] = T.groupby("season").team.transform("size")
    if cfg.get("post"):
        T = cfg["post"](T)
    S = E.series(P, cfg.get("min_games", 1), cfg.get("after"))
    T = E.outcomes(T, S, cfg)
    T = E.add_prior(T, ["wp", "champ", "finalist", "rounds_won", "playoffs", "pd_lg", "luck_lg", "lg_rank", "last_wp_lg",
                        "div_win", "pd_dv", "top_seed"])
    F = E.features(T, cfg)
    done = sorted(T[T.complete].season.unique())
    cur = int(T.season.max()) if T.season.max() not in done else None
    gp_now = T[T.season == cur].gp.median() if cur is not None else 0
    L = T[T.season == done[-1]].gp.median()
    gp_now = 0 if gp_now != gp_now else gp_now

    def cur_ok(timing):
        if cur is None:
            return False
        if timing in ("prior", "pre"):
            return True
        if timing == "q":
            return gp_now >= round(L * .25)
        if timing == "h":
            return gp_now >= round(L * .5)
        return gp_now >= round(L * .25)

    out = []
    for key, title, pool_desc in SECTIONS[sport]:
        groups = ["season"]
        if key in ("finalist", "top_seed") and cfg["conf"]:
            groups = ["season", "conf"]
        if key == "div_win":
            groups = ["season", "div"]
        if key in ("champ", "finalist"):
            pool = lambda T: T.playoffs == 1
        elif key == "top_seed":
            pool = lambda T: T.conf.notna()
        elif key == "div_win":
            pool = lambda T: T["div"].notna()
        else:
            pool = lambda T: T.team.notna()
        sec = dict(key=key, outcome=key, pool=pool, groups=groups)
        rows, winners = E.evaluate(T, F, sec, cfg["label"], cur, cur_ok)
        if not rows:
            continue
        for r in rows:
            review(sport, key, r)
        order = {"edge": 0, "fade": 1, "priced": 2, "weak": 3, "noise": 4}
        rows.sort(key=lambda r: (order[r["verdict"]], r["p"]))
        C = T[T.complete & pool(T) & T[key].notna()]
        out.append(dict(key=key, kind="team", title=title, pool_desc=pool_desc, seasons=[cfg["label"](min(C.season)), cfg["label"](max(C.season))],
                        n_seasons=int(C.season.nunique()), pool=int(len(C)), winners_n=int(C[key].sum()),
                        base_rate=float(C[key].mean()), winners=winners, trends=rows))
        log(sport, key, "seasons", C.season.nunique(), "trends", len(rows),
            {v: sum(r["verdict"] == v for r in rows) for v in order})
    try:
        import trends_awards
        acur = cur if cur is not None else int(T.season.max()) + 1
        aw = trends_awards.RUN[sport](cfg["label"](acur), acur, cur_ok)
        for sec in aw:
            for r in sec["trends"]:
                review(sport, sec["key"], r)
            sec["trends"].sort(key=lambda r: ({"edge": 0, "fade": 1, "priced": 2, "weak": 3, "noise": 4}[r["verdict"]], r["p"]))
            log(sport, sec["key"], "seasons", sec["n_seasons"], {v: sum(r["verdict"] == v for r in sec["trends"]) for v in
                                                                  ("edge", "fade", "priced", "weak", "noise")})
        out += aw
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        log(sport, "award trends failed", e)
    cur_label = cfg["label"](cur) if cur is not None else None
    return dict(sport=sport, league=cfg["name"], updated_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"),
                current=cur_label, current_gp=float(gp_now), season_games=float(L),
                fdr=E.FDR, min_pool=E.MIN_POOL_WITH, sections=out)


def build_data(sports=("nfl", "nba", "nhl", "nbl", "afl")):
    for s in sports:
        try:
            res = analyse(s)
        except Exception as e:
            import traceback
            traceback.print_exc()
            log(s, "failed", e)
            continue
        os.makedirs(OUTPUT[s], exist_ok=True)
        with open(os.path.join(OUTPUT[s], "trends.json"), "w") as f:
            json.dump(E.clean(res), f, separators=(",", ":"), allow_nan=False)


# ------------------------------------------------------------------ pages

PAGE_DIR = {"nfl": SITE, "nba": os.path.join(SITE, "nba"), "nhl": os.path.join(SITE, "nhl"), "nbl": os.path.join(SITE, "nbl"),
            "afl": os.path.join(SITE, "afl")}
INTRO = ("What past winners of each futures market had in common, tested against every other team in the same pool. "
         "Only patterns that pass a strict noise filter are shown as signals; the rest are listed as noise so you can ignore them.")


def _nav_link(html_text, active):
    """Adds a Trends link to the page's section nav (once)."""
    if 'href="trends.html"' in html_text:
        return html_text
    cur = ' aria-current="page"' if active else ""
    link = f'<a href="trends.html"{cur}>Trends</a>'
    grp = re.search(r'(<nav class="nav[^"]*"[^>]*>\s*<div class="navgrp">.*?)(</div>)', html_text, flags=re.S)
    if grp:  # grouped nav (NFL): join the first group (Model)
        return html_text[:grp.end(1)] + link + html_text[grp.end(1):]
    return re.sub(r"(<nav class=\"nav[^\"]*\"[^>]*>.*?)(</nav>)", lambda m: m.group(1) + f'<a href="trends.html"{cur}>Trends</a>' + m.group(2),
                  html_text, count=1, flags=re.S)


def build_site():
    for sport, d in PAGE_DIR.items():
        idx = os.path.join(d, "index.html")
        if not os.path.exists(idx) or not os.path.exists(os.path.join(OUTPUT[sport], "trends.json")):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".html") and fn != "trends.html":
                p = os.path.join(d, fn)
                s = open(p, encoding="utf-8").read()
                s2 = _nav_link(s, False)
                if s2 != s:
                    open(p, "w", encoding="utf-8").write(s2)
        src = open(idx, encoding="utf-8").read()
        head_end = src.find("</header>")
        if head_end < 0:
            continue
        top = src[:head_end + len("</header>")]
        top = re.sub(r'\saria-current=("page"|page|\'page\')', "", top)
        top = re.sub(r'(<div class="sportbar">.*?<a href="(?:\./|\.\./)?"?)', lambda m: m.group(1), top, flags=re.S)
        # keep the sport itself marked as current in the sport bar
        sport_label = {"nfl": "NFL", "nba": "NBA", "nhl": "NHL", "nbl": "NBL", "afl": "AFL"}[sport]
        top = re.sub(rf'(<div class="sportbar">.*?)(<a href="[^"]*">{sport_label}</a>)',
                     lambda m: m.group(1) + m.group(2).replace("<a ", '<a aria-current="page" '), top, count=1, flags=re.S)
        top = top.replace('href="trends.html">Trends', 'href="trends.html" aria-current="page">Trends')
        top = re.sub(r"<title>.*?</title>", f"<title>{sport_label} winner trends</title>", top, count=1, flags=re.S)
        top = re.sub(r'(<meta name="description" content=")[^"]*', rf"\1{sport_label} futures: what past winners had in common, with the noise filtered out.", top, count=1)
        data_path = "data/trends.json"
        body = f"""
<main class="page" id="main">
  <div class="page-head"><h1>{sport_label} winner trends</h1><p>{INTRO}</p></div>
  <div id="trends" data-src="{data_path}"><p class="note">Loading…</p></div>
</main>
<footer class="stamp">Trends recalculated on every refresh from the same public data as the rest of the site. Probabilities and history only, not betting advice.</footer>
</div>
<link rel="stylesheet" href="trends.css">
<script src="trends.js"></script>
</body></html>"""
        if "<div class=\"wrap\">" not in top:
            body = body.replace("</div>\n<link", "<link", 1)
        open(os.path.join(d, "trends.html"), "w", encoding="utf-8").write(top + body)
        for f in ("trends.js", "trends.css"):
            shutil.copy(os.path.join(SRC, f), os.path.join(d, f))
    log("pages written")


if __name__ == "__main__":
    import sys
    build_data(tuple(sys.argv[1:]) or ("nfl", "nba", "nhl", "nbl", "afl"))
