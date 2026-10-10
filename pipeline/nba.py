"""NBA ratings, season simulation and static-site output.

The live job deliberately uses compact SportsDataverse/ESPN CSV releases rather
than the full play-by-play archive.  Ten completed seasons are available for
validation, while the production rating uses the latest four seasons plus a
conservative roster-continuity adjustment.
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import os
import shutil
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from common import DATA, OUT, ROOT, log, write_json


NBA_DATA = os.path.join(DATA, "nba")
NBA_SRC = os.path.join(ROOT, "site_src", "nba")
NBA_SITE = os.path.join(ROOT, "site", "nba")

DIVS = {
    "Atlantic": ["BOS", "BKN", "NY", "PHI", "TOR"],
    "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
    "Southeast": ["ATL", "CHA", "MIA", "ORL", "WSH"],
    "Northwest": ["DEN", "MIN", "OKC", "POR", "UTAH"],
    "Pacific": ["GS", "LAC", "LAL", "PHX", "SAC"],
    "Southwest": ["DAL", "HOU", "MEM", "NO", "SA"],
}
EAST = DIVS["Atlantic"] + DIVS["Central"] + DIVS["Southeast"]
WEST = DIVS["Northwest"] + DIVS["Pacific"] + DIVS["Southwest"]
TEAMS = sorted(EAST + WEST)
TIX = {t: i for i, t in enumerate(TEAMS)}
NAMES = {
    "ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GS": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NO": "New Orleans Pelicans", "NY": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SA": "San Antonio Spurs", "SAC": "Sacramento Kings",
    "TOR": "Toronto Raptors", "UTAH": "Utah Jazz", "WSH": "Washington Wizards",
}

RELEASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
# Ratings are points per 100 possessions. A game margin is (rating gap + home edge) x game pace / 100, with the home
# edge fitted in the same per-100 units by _fit_ratings (set in build_data). Settings below were chosen on a
# point-in-time backtest of 2011-2026 (pipeline/nba_backtest.py) with TypeSafe.
HFA = 2.2            # per 100 possessions; replaced by the fitted value at build time
GAME_SIGMA = 12.2
TEAM_TAU = 2.2
PACE = np.full(30, 100.0)   # team pace (possessions per 48), replaced at build time
_OPTIONAL_DOWNLOADS_BLOCKED = False


def season_end_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year + 1 if today.month >= 7 else today.year


def _download(tag: str, name: str, max_age_h: float, required: bool = True) -> str | None:
    global _OPTIONAL_DOWNLOADS_BLOCKED
    os.makedirs(NBA_DATA, exist_ok=True)
    path = os.path.join(NBA_DATA, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        return path
    if not required and _OPTIONAL_DOWNLOADS_BLOCKED:
        return path if os.path.exists(path) else None
    url = f"{RELEASE}/{tag}/{name}"
    # A missing optional research feed must not hold the entire multi-sport
    # refresh through repeated long timeouts. Existing cached data still wins.
    attempts = 4 if required else 1
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"})
            tmp = path + ".part"
            with urllib.request.urlopen(req, timeout=120 if required else 30) as response, open(tmp, "wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            os.replace(tmp, path)
            return path
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and not required:
                return path if os.path.exists(path) else None
            if not required and exc.code in (408, 425, 429, 500, 502, 503, 504):
                _OPTIONAL_DOWNLOADS_BLOCKED = True
                log("NBA optional source temporarily unavailable; skipping remaining optional downloads", exc)
                return path if os.path.exists(path) else None
            if attempt == attempts - 1 and required:
                raise
        except Exception as exc:
            if not required:
                _OPTIONAL_DOWNLOADS_BLOCKED = True
                log("NBA optional source unreachable; using cached files and skipping remaining optional downloads", exc)
                return path if os.path.exists(path) else None
            if attempt == attempts - 1:
                if required:
                    raise
                return path if os.path.exists(path) else None
        if attempt < attempts - 1:
            time.sleep(4 * (attempt + 1))
    return path if os.path.exists(path) else None


def _csv(path: str | None) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path else pd.DataFrame()


def _load_inputs(end_year: int):
    # A decade is kept for backtesting. The live rating itself uses the latest
    # four seasons, so old team identities cannot dominate today's estimate.
    boxes = []
    for year in range(end_year - 10, end_year):
        name = f"team_box_{year}.csv"
        path = _download("espn_nba_team_boxscores", name, 24 * 365)
        frame = _csv(path)
        if len(frame):
            boxes.append(frame)
    current_box = _download("espn_nba_team_boxscores", f"team_box_{end_year}.csv", 2, required=False)
    if current_box:
        boxes.append(_csv(current_box))
    team_boxes = pd.concat(boxes, ignore_index=True)

    schedule = _csv(_download("espn_nba_schedules", f"nba_schedule_{end_year}.csv", 2))
    player_frames = []
    for year in range(end_year - 10, end_year):
        path = _download("espn_nba_player_boxscores", f"player_box_{year}.csv", 24 * 365)
        frame = _csv(path)
        if len(frame):
            player_frames.append(frame)
    # The current season's player release may not exist yet (or may be partial).
    current_players = _download("espn_nba_player_boxscores", f"player_box_{end_year}.csv", 2, required=False)
    if current_players:
        frame = _csv(current_players)
        if len(frame):
            player_frames.append(frame)
    players = pd.concat(player_frames, ignore_index=True) if player_frames else pd.DataFrame()
    prior_roster = _csv(_download("espn_nba_rosters", f"rosters_{end_year - 1}.csv", 24 * 30))
    current_roster = _csv(_download("espn_nba_rosters", f"rosters_{end_year}.csv", 12))
    return team_boxes, schedule, players, prior_roster, current_roster


def _numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column not in frame:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


def _ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def _stats_data(team_boxes: pd.DataFrame, players: pd.DataFrame) -> tuple[list[dict], list[dict], list[dict]]:
    """Build historical team/player season tables and game logs from box scores."""
    team_cols = ["season", "season_type", "team_score", "field_goals_made", "field_goals_attempted",
                 "three_point_field_goals_made", "three_point_field_goals_attempted", "free_throws_made",
                 "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "total_rebounds",
                 "assists", "steals", "blocks", "total_turnovers", "turnovers", "fouls",
                 "points_in_paint", "fast_break_points", "turnover_points"]
    d = team_boxes.copy()
    if "total_turnovers" not in d and "turnovers" in d:
        d["total_turnovers"] = d["turnovers"]
    d = _numeric(d, team_cols)
    d = d[d.team_abbreviation.isin(TEAMS) & d.opponent_team_abbreviation.isin(TEAMS)
          & d.season_type.isin([2, 3])].copy()
    d["team_turnovers"] = d.total_turnovers.where(d.total_turnovers.ne(0), d.turnovers)
    d["poss0"] = d.field_goals_attempted - d.offensive_rebounds + d.team_turnovers + .44 * d.free_throws_attempted
    game_poss = d.groupby("game_id").poss0.transform("mean").clip(60, 130)
    d["poss"] = game_poss
    d["margin"] = d.team_score - pd.to_numeric(d.opponent_team_score, errors="coerce").fillna(0)
    d["win"] = d.margin.gt(0)
    d["home"] = d.team_home_away.astype(str).str.lower().eq("home")
    d["ortg"] = d.team_score / d.poss * 100
    d["drtg"] = pd.to_numeric(d.opponent_team_score, errors="coerce") / d.poss * 100
    d["efg"] = (d.field_goals_made + .5 * d.three_point_field_goals_made) / d.field_goals_attempted.replace(0, np.nan)
    d["ts"] = d.team_score / (2 * (d.field_goals_attempted + .44 * d.free_throws_attempted)).replace(0, np.nan)
    d["three_rate"] = d.three_point_field_goals_attempted / d.field_goals_attempted.replace(0, np.nan)
    d["ft_rate"] = d.free_throws_attempted / d.field_goals_attempted.replace(0, np.nan)

    # Boxscore season profile: per-game counting stats, shooting rates and
    # possession-adjusted efficiency, with regular season and postseason separate.
    team_rows = []
    basic = ["team_score", "opponent_team_score", "field_goals_made", "field_goals_attempted",
             "three_point_field_goals_made", "three_point_field_goals_attempted", "free_throws_made",
             "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "total_rebounds",
             "assists", "steals", "blocks", "team_turnovers", "fouls", "points_in_paint",
             "fast_break_points", "turnover_points", "poss", "margin"]
    for (season, season_type, team), g in d.groupby(["season", "season_type", "team_abbreviation"]):
        gp = int(g.game_id.nunique())
        totals = g[basic].sum(numeric_only=True)
        home, road = g[g.home], g[~g.home]
        home_gp, road_gp = int(home.game_id.nunique()), int(road.game_id.nunique())
        wins = int(g.win.sum())
        row = {"season": int(season), "season_type": int(season_type), "team": team,
               "name": NAMES[team], "gp": gp, "w": wins, "l": gp - wins,
               "pct": _ratio(wins, gp), "home_w": int(home.win.sum()), "home_gp": home_gp,
               "road_w": int(road.win.sum()), "road_gp": road_gp,
               "ppg": _ratio(totals.team_score, gp), "opp_ppg": _ratio(totals.opponent_team_score, gp),
               "point_diff": _ratio(totals.margin, gp), "pace": _ratio(totals.poss, gp),
               "ortg": _ratio(totals.team_score * 100, totals.poss),
               "drtg": _ratio(totals.opponent_team_score * 100, totals.poss),
               "netrtg": _ratio((totals.team_score - totals.opponent_team_score) * 100, totals.poss)}
        per_game = {"fgm": "field_goals_made", "fga": "field_goals_attempted", "tpm": "three_point_field_goals_made",
                    "tpa": "three_point_field_goals_attempted", "ftm": "free_throws_made", "fta": "free_throws_attempted",
                    "orb": "offensive_rebounds", "drb": "defensive_rebounds", "reb": "total_rebounds",
                    "ast": "assists", "stl": "steals", "blk": "blocks", "tov": "team_turnovers", "pf": "fouls",
                    "paint": "points_in_paint", "fastbreak": "fast_break_points", "tov_pts": "turnover_points"}
        for out, source in per_game.items():
            row[out] = _ratio(totals[source], gp)
        row.update({"fg_pct": _ratio(totals.field_goals_made, totals.field_goals_attempted),
                    "tp_pct": _ratio(totals.three_point_field_goals_made, totals.three_point_field_goals_attempted),
                    "ft_pct": _ratio(totals.free_throws_made, totals.free_throws_attempted),
                    "efg_pct": _ratio((totals.field_goals_made + .5 * totals.three_point_field_goals_made), totals.field_goals_attempted),
                    "ts_pct": _ratio(totals.team_score, 2 * (totals.field_goals_attempted + .44 * totals.free_throws_attempted)),
                    "three_rate": _ratio(totals.three_point_field_goals_attempted, totals.field_goals_attempted),
                    "ft_rate": _ratio(totals.free_throws_attempted, totals.field_goals_attempted),
                    "home_ppg": _ratio(home.team_score.sum(), home_gp), "road_ppg": _ratio(road.team_score.sum(), road_gp)})
        team_rows.append(row)

    # Player seasonal totals and rates. A traded player's combined row is
    # labelled TOT, while team-split rows remain available for context.
    player_rows: list[dict] = []
    if len(players):
        pcols = ["season", "season_type", "minutes", "field_goals_made", "field_goals_attempted",
                 "three_point_field_goals_made", "three_point_field_goals_attempted", "free_throws_made",
                 "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "rebounds", "assists",
                 "steals", "blocks", "turnovers", "fouls", "points"]
        p = players.copy()
        p = _numeric(p, pcols)
        p = p[p.team_abbreviation.isin(TEAMS) & p.athlete_id.notna() & p.season_type.isin([2, 3])].copy()
        p["starter"] = p.starter.astype(str).str.lower().isin({"true", "1", "yes"}).astype(int) if "starter" in p else 0
        p["pm"] = pd.to_numeric(p.plus_minus.astype(str).str.replace("+", "", regex=False), errors="coerce").fillna(0) if "plus_minus" in p else 0
        p = p[p.minutes > 0]
        fields = pcols[2:] + ["starter", "pm"]
        for (season, season_type, athlete), all_rows in p.groupby(["season", "season_type", "athlete_id"]):
            team_groups = list(all_rows.groupby("team_abbreviation"))
            splits = [(team_groups[0][0], team_groups[0][1])] if len(team_groups) == 1 else team_groups + [("TOT", all_rows)]
            for team_key, g in splits:
                gp = int(g.game_id.nunique())
                totals = g[fields].sum(numeric_only=True)
                minutes = float(totals.minutes)
                row = {"season": int(season), "season_type": int(season_type), "team": team_key,
                       "teams": ",".join(sorted(g.team_abbreviation.unique())) if team_key == "TOT" else team_key,
                       "player": str(g.athlete_display_name.iloc[0]), "position": str(g.athlete_position_abbreviation.iloc[0]) if "athlete_position_abbreviation" in g else "",
                       "gp": gp, "gs": int(totals.starter), "min": minutes, "plus_minus": float(totals.pm)}
                count_fields = {"pts": "points", "reb": "rebounds", "orb": "offensive_rebounds", "drb": "defensive_rebounds",
                                "ast": "assists", "stl": "steals", "blk": "blocks", "tov": "turnovers", "pf": "fouls",
                                "fgm": "field_goals_made", "fga": "field_goals_attempted", "tpm": "three_point_field_goals_made",
                                "tpa": "three_point_field_goals_attempted", "ftm": "free_throws_made", "fta": "free_throws_attempted"}
                for out, source in count_fields.items():
                    row[out] = _ratio(totals[source], gp)
                    row[out + "_total"] = float(totals[source])
                row.update({"fg_pct": _ratio(totals.field_goals_made, totals.field_goals_attempted),
                            "tp_pct": _ratio(totals.three_point_field_goals_made, totals.three_point_field_goals_attempted),
                            "ft_pct": _ratio(totals.free_throws_made, totals.free_throws_attempted),
                            "efg_pct": _ratio(totals.field_goals_made + .5 * totals.three_point_field_goals_made, totals.field_goals_attempted),
                            "ts_pct": _ratio(totals.points, 2 * (totals.field_goals_attempted + .44 * totals.free_throws_attempted))})
                for out in ("pts", "reb", "ast", "stl", "blk", "tov"):
                    row[out + "36"] = _ratio(row[out + "_total"] * 36, minutes)
                row["plus_minus_pg"] = _ratio(totals.pm, gp)
                team_context = team_rows
                # Use the player's team-season context for a standard box-score usage estimate.
                ctx = [x for x in team_context if x["season"] == int(season) and x["season_type"] == int(season_type)
                       and x["team"] == team_key]
                if team_key == "TOT":
                    ctx = [x for x in team_context if x["season"] == int(season) and x["season_type"] == int(season_type)
                           and x["team"] in g.team_abbreviation.unique()]
                if ctx and minutes:
                    context_rows = [x for x in ctx if x["gp"]]
                    denominator = 0.0
                    team_minutes = 0.0
                    for x in context_rows:
                        # Convert per-game team totals back to totals for this player's team stint.
                        split_gp = int(g[g.team_abbreviation == x["team"]].game_id.nunique()) if team_key == "TOT" else gp
                        denominator += (x.get("fga", 0) * split_gp + .44 * x.get("fta", 0) * split_gp + x.get("tov", 0) * split_gp)
                        team_minutes += split_gp * 240
                    numerator = totals.field_goals_attempted + .44 * totals.free_throws_attempted + totals.turnovers
                    row["usg_pct"] = _ratio(numerator * team_minutes / 5, minutes * denominator)
                else:
                    row["usg_pct"] = None
                player_rows.append(row)

    game_rows = []
    for _, r in d.iterrows():
        game_rows.append({"season": int(r.season), "season_type": int(r.season_type), "date": str(r.game_date),
                          "game_id": str(r.game_id), "team": r.team_abbreviation,
                          "opponent": r.opponent_team_abbreviation, "venue": "H" if r.home else "A",
                          "result": "W" if r.win else "L", "score": int(r.team_score),
                          "opp_score": int(r.opponent_team_score), "margin": float(r.margin),
                          "poss": float(r.poss), "ortg": float(r.ortg), "drtg": float(r.drtg),
                          "fgm": float(r.field_goals_made), "fga": float(r.field_goals_attempted), "fg_pct": _ratio(r.field_goals_made, r.field_goals_attempted),
                          "tpm": float(r.three_point_field_goals_made), "tpa": float(r.three_point_field_goals_attempted), "tp_pct": _ratio(r.three_point_field_goals_made, r.three_point_field_goals_attempted),
                          "ftm": float(r.free_throws_made), "fta": float(r.free_throws_attempted), "ft_pct": _ratio(r.free_throws_made, r.free_throws_attempted),
                          "orb": float(r.offensive_rebounds), "drb": float(r.defensive_rebounds), "reb": float(r.total_rebounds),
                          "ast": float(r.assists), "stl": float(r.steals), "blk": float(r.blocks), "tov": float(r.team_turnovers),
                          "pf": float(r.fouls), "paint": float(r.points_in_paint), "fastbreak": float(r.fast_break_points),
                          "tov_pts": float(r.turnover_points)})
    return team_rows, player_rows, game_rows


def _read_release_csv(tag: str, name: str, max_age_h: float) -> pd.DataFrame:
    """Read a published CSV through the pipeline cache so refreshes are bounded."""
    path = _download(tag, name, max_age_h, required=False)
    if not path:
        log("NBA advanced source unavailable", f"{tag}/{name}")
        return pd.DataFrame()
    try:
        return _csv(path)
    except Exception as exc:
        log("NBA advanced CSV could not be parsed", f"{tag}/{name}", exc)
        return pd.DataFrame()


TEAM_ALIASES = {
    "atlanta": "ATL", "hawks": "ATL", "brooklyn": "BKN", "nets": "BKN",
    "boston": "BOS", "celtics": "BOS", "charlotte": "CHA", "hornets": "CHA",
    "chicago": "CHI", "bulls": "CHI", "cleveland": "CLE", "cavaliers": "CLE",
    "dallas": "DAL", "mavericks": "DAL", "denver": "DEN", "nuggets": "DEN",
    "detroit": "DET", "pistons": "DET", "goldenstate": "GS", "warriors": "GS",
    "houston": "HOU", "rockets": "HOU", "indiana": "IND", "pacers": "IND",
    "laclippers": "LAC", "losangelesclippers": "LAC", "clippers": "LAC",
    "losangeleslakers": "LAL", "lakers": "LAL", "memphis": "MEM", "grizzlies": "MEM",
    "miami": "MIA", "heat": "MIA", "milwaukee": "MIL", "bucks": "MIL",
    "minnesota": "MIN", "timberwolves": "MIN", "neworleans": "NO", "pelicans": "NO",
    "newyork": "NY", "knicks": "NY", "oklahomacity": "OKC", "thunder": "OKC",
    "orlando": "ORL", "magic": "ORL", "philadelphia": "PHI", "76ers": "PHI",
    "phoenix": "PHX", "suns": "PHX", "portland": "POR", "trailblazers": "POR",
    "sanantonio": "SA", "spurs": "SA", "sacramento": "SAC", "kings": "SAC",
    "toronto": "TOR", "raptors": "TOR", "utah": "UTAH", "jazz": "UTAH",
    "washington": "WSH", "wizards": "WSH",
}
TEAM_ALIASES.update({
    "".join(ch for ch in name.lower() if ch.isalnum()): abbrev
    for abbrev, name in NAMES.items()
})


def _team_abbreviation(row: pd.Series) -> str:
    code = str(row.get("team_abbreviation", row.get("team_tricode", row.get("team", "")))).strip().upper()
    if code in NAMES:
        return code
    name = "".join(ch for ch in str(row.get("team_name", row.get("team", ""))).lower() if ch.isalnum())
    return TEAM_ALIASES.get(name, "")


def _advanced_season_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep one regular-season, per-game advanced-profile row per entity."""
    if "season_type" in frame:
        season_type = frame.season_type.astype(str).str.lower().str.replace(r"[-_]", " ", regex=True).str.strip()
        frame = frame[season_type.isin({"regular season", "2"})]
    if "measure_type" in frame:
        frame = frame[frame.measure_type.astype(str).str.lower().eq("advanced")]
    if "per_mode" in frame:
        frame = frame[frame.per_mode.astype(str).str.lower().eq("pergame")]
    return frame


def _number(row: pd.Series, *keys: str) -> float | None:
    for key in keys:
        if key in row.index:
            value = pd.to_numeric(pd.Series([row[key]]), errors="coerce").iloc[0]
            if pd.notna(value):
                return float(value)
    return None


def _shot_zone(row: pd.Series) -> str | None:
    """Classify NBA Stats shot coordinates into stable, interpretable zones."""
    action = str(row.get("action_type", "")).lower()
    if "shot" not in action:
        return None
    distance = pd.to_numeric(pd.Series([row.get("shot_distance")]), errors="coerce").iloc[0]
    x = pd.to_numeric(pd.Series([row.get("x_legacy")]), errors="coerce").iloc[0]
    y = pd.to_numeric(pd.Series([row.get("y_legacy")]), errors="coerce").iloc[0]
    value = pd.to_numeric(pd.Series([row.get("shot_value")]), errors="coerce").iloc[0]
    if pd.notna(value) and value == 3:
        if pd.notna(x) and pd.notna(y) and abs(float(x)) >= 220 and abs(float(y)) <= 100:
            return "Corner 3"
        return "Above-break 3"
    if pd.notna(distance) and distance <= 4:
        return "At rim (0–4 ft)"
    if pd.notna(distance) and distance <= 10:
        return "Short paint (5–10 ft)"
    if pd.notna(distance) and distance <= 16:
        return "Mid-range (11–16 ft)"
    if pd.notna(distance) and distance <= 22:
        return "Long mid-range (17–22 ft)"
    return "Other 2"


def _advanced_data(end_year: int) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Fetch compact NBA Stats-derived team/player advanced profiles and shots.

    Only derived aggregates are written to the site. Raw shot-by-shot and
    dashboard releases stay in the upstream repository and local cache.
    """
    team_rows: list[dict] = []
    player_rows: list[dict] = []
    shot_rows: list[dict] = []
    team_years: set[int] = set()
    player_years: set[int] = set()
    shot_years: set[int] = set()
    source = "SportsDataverse NBA Stats releases (NBA Stats-derived)"
    for year in range(max(1997, end_year - 10), end_year + 1):
        historical = year < end_year - 1
        cache_age = 24 * 365 if historical else (24 if year == end_year - 1 else 2)
        team = _read_release_csv("nba_stats_team_season_stats", f"team_season_stats_{year}.csv", cache_age)
        if len(team):
            team = _advanced_season_rows(team)
            if len(team):
                team_years.add(year)
            for _, r in team.iterrows():
                abbrev = _team_abbreviation(r)
                if abbrev not in NAMES:
                    continue
                team_rows.append({
                    "season": year, "season_type": 2, "team": abbrev, "name": NAMES[abbrev],
                    "gp": _number(r, "gp"), "wins": _number(r, "w"), "win_pct": _number(r, "w_pct"),
                    "off_rating": _number(r, "off_rating", "e_off_rating"),
                    "def_rating": _number(r, "def_rating", "e_def_rating"),
                    "net_rating": _number(r, "net_rating", "e_net_rating"), "pace": _number(r, "pace", "e_pace"),
                    "efg_pct": _number(r, "efg_pct"),
                    "ts_pct": _number(r, "ts_pct", "true_shooting_percentage"),
                    "tov_pct": _number(r, "tm_tov_pct"), "orb_pct": _number(r, "oreb_pct"),
                    "dreb_pct": _number(r, "dreb_pct"), "assist_pct": _number(r, "ast_pct"),
                    "assist_to_turnover": _number(r, "ast_to"), "assist_ratio": _number(r, "ast_ratio"),
                    "pie": _number(r, "pie"), "points_off_turnovers": _number(r, "pts_off_tov"),
                    "second_chance_points": _number(r, "pts_2nd_chance"), "fastbreak_points": _number(r, "pts_fb"),
                    "paint_points": _number(r, "pts_paint"), "opponent_points_off_turnovers": _number(r, "opp_pts_off_tov"),
                    "opponent_second_chance_points": _number(r, "opp_pts_2nd_chance"),
                    "opponent_fastbreak_points": _number(r, "opp_pts_fb"), "opponent_paint_points": _number(r, "opp_pts_paint"),
                    "source": source,
                })

        player = _read_release_csv("nba_stats_player_season_stats", f"player_season_stats_{year}.csv", cache_age)
        if len(player):
            player = _advanced_season_rows(player)
            if len(player):
                player_years.add(year)
            for _, r in player.iterrows():
                abbrev = _team_abbreviation(r)
                if abbrev not in NAMES:
                    continue
                player_name = str(r.get("player_name", r.get("player", ""))).strip()
                if not player_name:
                    continue
                player_rows.append({
                    "season": year, "season_type": 2, "team": abbrev, "player": player_name,
                    "player_id": str(r.get("player_id", "")), "gp": _number(r, "gp"), "minutes": _number(r, "min"),
                    "usage_pct": _number(r, "usg_pct", "e_usg_pct"),
                    "off_rating": _number(r, "off_rating", "e_off_rating"),
                    "def_rating": _number(r, "def_rating", "e_def_rating"),
                    "net_rating": _number(r, "net_rating", "e_net_rating"), "ts_pct": _number(r, "ts_pct"),
                    "efg_pct": _number(r, "efg_pct"), "assist_pct": _number(r, "ast_pct"),
                    "assist_to_turnover": _number(r, "ast_to"), "assist_ratio": _number(r, "ast_ratio"),
                    "off_rebound_pct": _number(r, "oreb_pct"), "def_rebound_pct": _number(r, "dreb_pct"),
                    "rebound_pct": _number(r, "reb_pct"), "turnover_pct": _number(r, "tm_tov_pct", "e_tov_pct"),
                    "pace": _number(r, "pace", "e_pace"), "pie": _number(r, "pie"), "possessions": _number(r, "poss"),
                    "source": source,
                })

        # Shot-zone breakdowns are compact and useful for team style and
        # shooting-efficiency context. Keep only aggregate zones, never raw shots.
        shots = _read_release_csv("nba_stats_shots", f"shots_{year}.csv", cache_age)
        if len(shots):
            team_col = next((c for c in ("team_tricode", "team_abbreviation") if c in shots), None)
            made_col = "shot_result" if "shot_result" in shots else None
            if team_col and made_col and "shot_value" in shots:
                s = shots.copy()
                if "season_type_id" in s:
                    s = s[pd.to_numeric(s.season_type_id, errors="coerce").eq(2)]
                if "season_type" in s:
                    s = s[s.season_type.astype(str).str.lower().isin({"regular season", "2"})]
                s[team_col] = s[team_col].astype(str).str.upper()
                s["made"] = s[made_col].astype(str).str.lower().eq("made").astype(int)
                s["shot_value"] = pd.to_numeric(s["shot_value"], errors="coerce")
                action_shot = s.action_type.astype(str).str.contains("shot", case=False, na=False)
                distance = pd.to_numeric(s.get("shot_distance"), errors="coerce")
                x = pd.to_numeric(s.get("x_legacy"), errors="coerce")
                y = pd.to_numeric(s.get("y_legacy"), errors="coerce")
                two = s.shot_value.eq(2) & action_shot
                three = s.shot_value.eq(3) & action_shot
                corner = three & x.abs().ge(220) & y.abs().le(100)
                s["zone"] = np.select(
                    [corner, three, two & distance.le(4), two & distance.gt(4) & distance.le(10),
                     two & distance.gt(10) & distance.le(16), two & distance.gt(16) & distance.le(22)],
                    ["Corner 3", "Above-break 3", "At rim (0–4 ft)", "Short paint (5–10 ft)",
                     "Mid-range (11–16 ft)", "Long mid-range (17–22 ft)"],
                    default="Other 2")
                s = s[s[team_col].isin(NAMES) & action_shot & s.zone.notna() & s.shot_value.isin([2, 3])]
                if len(s):
                    shot_years.add(year)
                for (abbr, zone), g in s.groupby([team_col, "zone"]):
                    attempts = len(g)
                    if attempts < 1:
                        continue
                    shot_rows.append({"season": year, "season_type": 2, "team": abbr,
                                      "name": NAMES[abbr], "zone": str(zone), "attempts": attempts,
                                      "makes": int(g.made.sum()), "fg_pct": float(g.made.mean()),
                                      "source": source})
    counts = {"team_advanced_rows": len(team_rows),
              "player_advanced_rows": len(player_rows),
              "shot_zone_rows": len(shot_rows), "source": source,
              "coverage_start": max(1997, end_year - 10), "coverage_end": end_year,
              "team_seasons": sorted(team_years), "player_seasons": sorted(player_years),
              "shot_seasons": sorted(shot_years),
              "status": "available" if team_rows or player_rows or shot_rows else "unavailable"}
    return team_rows, player_rows, shot_rows, counts


def _bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _regular_boxes(boxes: pd.DataFrame) -> pd.DataFrame:
    d = boxes[(pd.to_numeric(boxes.season_type, errors="coerce") == 2)
              & boxes.team_abbreviation.isin(TEAMS)
              & boxes.opponent_team_abbreviation.isin(TEAMS)].copy()
    numeric = ["season", "team_score", "field_goals_attempted", "offensive_rebounds",
               "total_turnovers", "turnovers", "free_throws_attempted"]
    for col in numeric:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    tov = d.total_turnovers.fillna(d.turnovers)
    d["poss0"] = d.field_goals_attempted - d.offensive_rebounds + tov + 0.44 * d.free_throws_attempted
    d["poss"] = d.groupby("game_id").poss0.transform("mean").clip(70, 125)
    d["ortg"] = d.team_score / d.poss * 100
    return d[d.ortg.between(70, 150) & d.poss.notna()].copy()


def _fit_ratings(boxes: pd.DataFrame, end_year: int, decay: float = 0.2, ridge: float = 24.0,
                 current_weight: float = 4.0) -> tuple[pd.DataFrame, dict]:
    d = _regular_boxes(boxes)
    train = d[d.season >= end_year - 4].copy()
    n = len(train)
    x = np.zeros((n, 61), dtype=np.float32)
    for row, (team, opp, venue) in enumerate(zip(train.team_abbreviation,
                                                  train.opponent_team_abbreviation,
                                                  train.team_home_away)):
        x[row, TIX[team]] = 1
        x[row, 30 + TIX[opp]] = 1
        x[row, 60] = 1 if venue == "home" else 0
    # Older completed seasons decay by 80% a year; current-season games get 4x weight so the model moves quickly out of
    # preseason mode (both chosen on the point-in-time backtest).
    weights = np.power(decay, np.maximum(0, (end_year - 1) - train.season.to_numpy()))
    weights = np.where(train.season.to_numpy() == end_year, current_weight, weights)
    design = np.column_stack([np.ones(n, dtype=np.float32), x]).astype(float)
    root_w = np.sqrt(weights)[:, None]
    weighted_x = design * root_w
    weighted_y = train.ortg.to_numpy(float) * root_w[:, 0]
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(weighted_x.T @ weighted_x + penalty, weighted_x.T @ weighted_y)
    intercept, coef = float(beta[0]), beta[1:]
    off = coef[:30].astype(float)
    defense = -coef[30:60].astype(float)
    off -= off.mean()
    defense -= defense.mean()
    base = intercept

    pace_rows = train.assign(w=weights)
    pace = (pace_rows.assign(wp=pace_rows.w * pace_rows.poss).groupby("team_abbreviation").wp.sum()
            / pace_rows.groupby("team_abbreviation").w.sum()).reindex(TEAMS)
    latest = train[train.season == end_year]
    last_full = train[train.season == end_year - 1]
    current_gp = latest.groupby("team_abbreviation").size().reindex(TEAMS, fill_value=0)
    prior_gp = last_full.groupby("team_abbreviation").size().reindex(TEAMS, fill_value=0)

    ratings = pd.DataFrame({"team": TEAMS, "off": off, "def": defense, "pace": pace.to_numpy(),
                            "current_gp": current_gp.to_numpy(), "prior_gp": prior_gp.to_numpy()})
    ratings["base_ortg"] = base
    ratings["raw_net"] = ratings.off + ratings["def"]
    detail = {"base_ortg": base, "home_offense_points_per_100": float(coef[60]),
              "training_rows": int(n), "training_start": int(train.season.min()),
              "training_end": int(train.season.max())}
    return ratings, detail


def _player_values(players: pd.DataFrame) -> pd.DataFrame:
    d = players[(pd.to_numeric(players.season_type, errors="coerce") == 2)
                & players.team_abbreviation.isin(TEAMS)].copy()
    cols = ["minutes", "field_goals_made", "field_goals_attempted", "free_throws_made",
            "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "rebounds", "assists",
            "steals", "blocks", "fouls", "turnovers", "points"]
    for col in cols:
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)
    d["pm"] = pd.to_numeric(d.plus_minus.astype(str).str.replace("+", "", regex=False), errors="coerce").fillna(0)
    d = d[d.minutes > 0]
    d["gmsc"] = (d.points + .4 * d.field_goals_made - .7 * d.field_goals_attempted
                 - .4 * (d.free_throws_attempted - d.free_throws_made) + .7 * d.offensive_rebounds
                 + .3 * d.defensive_rebounds + d.steals + .7 * d.assists + .7 * d.blocks
                 - .4 * d.fouls - d.turnovers)
    agg = d.groupby(["athlete_id", "athlete_display_name", "team_abbreviation"], as_index=False).agg(
        minutes=("minutes", "sum"), games=("game_id", "nunique"), points=("points", "sum"),
        rebounds=("rebounds", "sum"), assists=("assists", "sum"), gmsc=("gmsc", "sum"),
        plus_minus=("pm", "sum"))
    agg["gmsc36"] = agg.gmsc / agg.minutes * 36
    league = np.average(agg.gmsc36, weights=agg.minutes)
    agg["pm36"] = agg.plus_minus / agg.minutes * 36
    reliability = np.minimum(1, agg.minutes / 1200)
    agg["impact"] = (((agg.gmsc36 - league) * .24 + agg.pm36 * .045) * reliability).clip(-4, 6)
    agg["ppg"] = agg.points / agg.games
    agg["rpg"] = agg.rebounds / agg.games
    agg["apg"] = agg.assists / agg.games
    agg["athlete_id"] = agg.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    return agg


def _roster_adjustment(ratings: pd.DataFrame, values: pd.DataFrame, prior_roster: pd.DataFrame,
                       current_roster: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    for roster in (prior_roster, current_roster):
        roster["athlete_id"] = roster.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    val = values.sort_values("minutes", ascending=False).drop_duplicates("athlete_id")
    def strength(roster: pd.DataFrame, current: bool) -> pd.Series:
        r = roster[roster.team_abbreviation.isin(TEAMS)].drop_duplicates(["team_abbreviation", "athlete_id"]).copy()
        r = r.merge(val[["athlete_id", "minutes", "impact"]], how="left", on="athlete_id")
        r["minutes"] = r.minutes.fillna(180 if current else 0).clip(0, 2600)
        r["impact"] = r.impact.fillna(0)
        # Keep a realistic 12-player rotation and scale to an 82-game minute budget.
        r = r.sort_values(["team_abbreviation", "minutes"], ascending=[True, False]).groupby("team_abbreviation").head(12)
        def one(g):
            mins = g.minutes.to_numpy(float).copy()
            if mins.sum() > 82 * 240:
                mins *= (82 * 240) / mins.sum()
            return float(np.sum(g.impact.to_numpy(float) * mins) / (82 * 48))
        return r.groupby("team_abbreviation").apply(one, include_groups=False).reindex(TEAMS, fill_value=0)

    old = strength(prior_roster, False)
    new = strength(current_roster, True)
    adj = ((new - old) * .55).clip(-5, 5)
    adj -= adj.mean()
    ratings = ratings.copy()
    ratings["roster_adj"] = ratings.team.map(adj).fillna(0)
    ratings["rating"] = ratings.raw_net + ratings.roster_adj
    ratings["rating"] -= ratings.rating.mean()

    current = current_roster[current_roster.team_abbreviation.isin(TEAMS)].copy()
    current = current.drop_duplicates(["team_abbreviation", "athlete_id"])
    current = current.merge(val, how="left", on="athlete_id", suffixes=("", "_prior"))
    rows = []
    for _, p in current.iterrows():
        if pd.isna(p.get("minutes")) or float(p.get("minutes", 0)) < 150:
            continue
        rows.append({"team": p.team_abbreviation, "player": p.get("display_name", p.get("athlete_display_name", "")),
                     "position": p.get("position_abbreviation", ""), "games": int(p.games),
                     "minutes": round(float(p.minutes)), "ppg": round(float(p.ppg), 1),
                     "rpg": round(float(p.rpg), 1), "apg": round(float(p.apg), 1),
                     "impact": round(float(p.impact), 2)})
    rows.sort(key=lambda p: (-p["impact"], -p["minutes"]))
    return ratings, rows


def _schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    d = schedule[(pd.to_numeric(schedule.season_type, errors="coerce") == 2)
                 & schedule.home_abbreviation.isin(TEAMS)
                 & schedule.away_abbreviation.isin(TEAMS)].copy()
    d["completed"] = _bool(d.status_type_completed)
    for col in ("home_score", "away_score"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["game_date"] = pd.to_datetime(d.game_date, errors="coerce").dt.strftime("%Y-%m-%d")
    d = d.sort_values(["game_date", "id"]).drop_duplicates("id")
    return d


def _one_game(rng: np.random.Generator, home: str, away: str, strength: np.ndarray,
              neutral: bool = False) -> str:
    pace = (PACE[TIX[home]] + PACE[TIX[away]]) / 200
    margin = (strength[TIX[home]] - strength[TIX[away]] + (0 if neutral else HFA)) * pace + rng.normal(0, GAME_SIGMA)
    return home if margin > 0 else away


def _series(rng: np.random.Generator, a: str, b: str, strength: np.ndarray,
            records: dict[str, int]) -> str:
    # Better regular-season record owns Games 1, 2, 5 and 7; rating breaks ties.
    if (records[b], strength[TIX[b]]) > (records[a], strength[TIX[a]]):
        a, b = b, a
    wa = wb = 0
    for home_a in (True, True, False, False, True, False, True):
        home, away = (a, b) if home_a else (b, a)
        winner = _one_game(rng, home, away, strength)
        wa += winner == a
        wb += winner == b
        if wa == 4 or wb == 4:
            break
    return a if wa == 4 else b


def _simulate(schedule: pd.DataFrame, ratings: pd.DataFrame, n_sims: int, avail: dict | None = None) -> dict[str, dict]:
    """avail: (game_date, home, away) -> points to subtract from the home margin for known absences (nba_avail)."""
    avail = avail or {}
    base = ratings.set_index("team").rating.reindex(TEAMS).to_numpy(float)
    actual_wins = np.zeros(len(TEAMS), dtype=np.int16)
    actual_pd = np.zeros(len(TEAMS), dtype=float)
    remaining = []
    adjust = []
    for _, g in schedule.iterrows():
        h, a = g.home_abbreviation, g.away_abbreviation
        if g.completed and pd.notna(g.home_score) and pd.notna(g.away_score):
            winner = h if g.home_score > g.away_score else a
            actual_wins[TIX[winner]] += 1
            actual_pd[TIX[h]] += float(g.home_score - g.away_score)
            actual_pd[TIX[a]] += float(g.away_score - g.home_score)
        else:
            remaining.append((TIX[h], TIX[a]))
            adjust.append(avail.get((str(g.game_date)[:10], h, a), 0.0))

    # Before the NBA Cup bracket is known, the published schedule contains 80
    # named games per team. Add balanced anonymous pairings so the futures
    # simulation still completes an 82-game season; official games replace
    # these automatically as the schedule fills in.
    listed = pd.concat([schedule.home_abbreviation, schedule.away_abbreviation]).value_counts()
    deficits = {t: max(0, 82 - int(listed.get(t, 0))) for t in TEAMS}
    flex_no = 0
    while sum(deficits.values()) >= 2:
        home = max(TEAMS, key=lambda t: (deficits[t], -TIX[t]))
        if deficits[home] <= 0:
            break
        candidates = [t for t in TEAMS if t != home and deficits[t] > 0]
        if not candidates:
            break
        away = max(candidates, key=lambda t: (deficits[t], -((TIX[t] + flex_no) % len(TEAMS))))
        if flex_no % 2:
            home, away = away, home
        remaining.append((TIX[home], TIX[away]))
        adjust.append(0.0)
        deficits[home] -= 1
        deficits[away] -= 1
        flex_no += 1

    counts = {t: {"div": 0, "top6": 0, "playin": 0, "playoff": 0, "seed1": 0, "conf": 0, "title": 0,
                  "wins": np.zeros(83, dtype=np.int64)} for t in TEAMS}
    rng = np.random.default_rng(20261009)

    home_ix = np.array([g[0] for g in remaining], dtype=np.int16)
    away_ix = np.array([g[1] for g in remaining], dtype=np.int16)
    game_adj = np.array(adjust, dtype=float)
    batch_size = 2000
    done = 0
    while done < n_sims:
        size = min(batch_size, n_sims - done)
        strengths = base[None, :] + rng.normal(0, TEAM_TAU, (size, len(TEAMS)))
        wins_batch = np.tile(actual_wins, (size, 1))
        pd_batch = np.tile(actual_pd, (size, 1))
        if len(home_ix):
            game_pace = (PACE[home_ix] + PACE[away_ix]) / 200
            margins = ((strengths[:, home_ix] - strengths[:, away_ix] + HFA) * game_pace[None, :] - game_adj[None, :]
                       + rng.normal(0, GAME_SIGMA, (size, len(home_ix))))
            winner_ix = np.where(margins > 0, home_ix[None, :], away_ix[None, :])
            sim_ix = np.repeat(np.arange(size), len(home_ix))
            np.add.at(wins_batch, (sim_ix, winner_ix.ravel()), 1)
            tiled_home = np.tile(home_ix, size)
            tiled_away = np.tile(away_ix, size)
            np.add.at(pd_batch, (sim_ix, tiled_home), margins.ravel())
            np.add.at(pd_batch, (sim_ix, tiled_away), -margins.ravel())

        for local in range(size):
            strength = strengths[local]
            win_arr = wins_batch[local]
            pd_arr = pd_batch[local]
            wins = {t: int(win_arr[TIX[t]]) for t in TEAMS}
            for t in TEAMS:
                counts[t]["wins"][min(82, wins[t])] += 1
            for members in DIVS.values():
                winner = max(members, key=lambda t: (wins[t], pd_arr[TIX[t]], strength[TIX[t]], rng.random()))
                counts[winner]["div"] += 1

            conference_winners = []
            for conference in (EAST, WEST):
                order = sorted(conference, key=lambda t: (wins[t], pd_arr[TIX[t]], strength[TIX[t]], rng.random()), reverse=True)
                counts[order[0]]["seed1"] += 1
                for t in order[:6]:
                    counts[t]["top6"] += 1
                for t in order[6:10]:
                    counts[t]["playin"] += 1

                seven = _one_game(rng, order[6], order[7], strength)
                first_loser = order[7] if seven == order[6] else order[6]
                nine_winner = _one_game(rng, order[8], order[9], strength)
                eight = _one_game(rng, first_loser, nine_winner, strength)
                seeds = [order[0], order[1], order[2], order[3], order[4], order[5], seven, eight]
                for t in seeds:
                    counts[t]["playoff"] += 1

                q1 = _series(rng, seeds[0], seeds[7], strength, wins)
                q2 = _series(rng, seeds[3], seeds[4], strength, wins)
                q3 = _series(rng, seeds[2], seeds[5], strength, wins)
                q4 = _series(rng, seeds[1], seeds[6], strength, wins)
                s1 = _series(rng, q1, q2, strength, wins)
                s2 = _series(rng, q4, q3, strength, wins)
                champion = _series(rng, s1, s2, strength, wins)
                counts[champion]["conf"] += 1
                conference_winners.append(champion)
            champion = _series(rng, conference_winners[0], conference_winners[1], strength, wins)
            counts[champion]["title"] += 1
        done += size

    out = {}
    for t in TEAMS:
        c = counts[t]
        dist = c["wins"] / n_sims
        out[t] = {"mean_wins": round(float(np.dot(np.arange(83), dist)), 2),
                  "p_div": c["div"] / n_sims, "p_top6": c["top6"] / n_sims,
                  "p_playin": c["playin"] / n_sims, "p_playoff": c["playoff"] / n_sims,
                  "p_seed1": c["seed1"] / n_sims, "p_conf": c["conf"] / n_sims,
                  "p_title": c["title"] / n_sims, "win_dist": dist.tolist(),
                  "rating": round(float(base[TIX[t]]), 2)}
    return out


def _game_rows(schedule: pd.DataFrame, ratings: pd.DataFrame, avail: dict | None = None) -> list[dict]:
    avail = avail or {}
    strength = ratings.set_index("team").rating
    rows = []
    for _, g in schedule.iterrows():
        pace = (PACE[TIX[g.home_abbreviation]] + PACE[TIX[g.away_abbreviation]]) / 200
        margin = float((strength[g.home_abbreviation] - strength[g.away_abbreviation] + HFA) * pace)
        if not g.completed:
            margin -= avail.get((str(g.game_date)[:10], g.home_abbreviation, g.away_abbreviation), 0.0)
        rows.append({"date": g.game_date, "home": g.home_abbreviation, "away": g.away_abbreviation,
                     "completed": bool(g.completed),
                     "home_score": int(g.home_score) if pd.notna(g.home_score) and g.completed else None,
                     "away_score": int(g.away_score) if pd.notna(g.away_score) and g.completed else None,
                     "home_win": float(0.5 * (1 + math.erf(margin / GAME_SIGMA / math.sqrt(2)))),
                     "projected_margin": round(margin, 1)})
    return rows


def _availability(players: pd.DataFrame, end_year: int, schedule: pd.DataFrame) -> tuple[dict, dict]:
    """Known absences -> per-game points adjustments. Any failure leaves the model exactly as before (no adjustment)."""
    try:
        import nba_avail as A
        injuries, feed = A.fetch_injuries(NBA_DATA, os.environ.get("NBA_INJ_STORE"))
        if injuries is None:
            return {}, {"available": False, **feed}
        stamp = feed.get("feed_time")
        values, _ = A.player_values(players, end_year, TEAMS)
        adj, listed = A.game_adjustments(schedule, injuries, values, NAMES)
        store = os.environ.get("NBA_INJ_STORE")
        if store and not feed["stale"] and feed["age_hours"] == 0:
            A.archive(store, injuries, stamp)
        log("NBA availability", len(listed), "rotation players out or doubtful;", len(adj), "games adjusted")
        return adj, {"available": True, **feed, "beta": A.BETA, "rows": listed}
    except Exception as e:  # noqa: BLE001
        log("NBA availability skipped:", e)
        return {}, {"available": False}


def build_data() -> None:
    end_year = season_end_year()
    log("NBA season", f"{end_year - 1}-{str(end_year)[-2:]}")
    boxes, raw_schedule, players, prior_roster, current_roster = _load_inputs(end_year)
    ratings, fit = _fit_ratings(boxes, end_year)
    global HFA, PACE
    if 0 < fit["home_offense_points_per_100"] < 6:
        HFA = float(fit["home_offense_points_per_100"])
    PACE = ratings.set_index("team").pace.reindex(TEAMS).fillna(100.0).to_numpy(float)
    prior_players = players[pd.to_numeric(players.season, errors="coerce") == end_year - 1] if len(players) else players
    values = _player_values(prior_players)
    ratings, player_rows = _roster_adjustment(ratings, values, prior_roster, current_roster)
    team_stats, player_stats, team_games = _stats_data(boxes, players)
    advanced_teams, advanced_players, shot_zones, advanced_meta = _advanced_data(end_year)
    schedule = _schedule(raw_schedule)
    if len(schedule) < 1200:
        raise RuntimeError(f"NBA schedule is incomplete ({len(schedule)} regular-season games)")
    n_sims = int(os.environ.get("NBA_N_SIMS", os.environ.get("N_SIMS", "100000")))
    avail, availability = _availability(players, end_year, schedule)
    futures = _simulate(schedule, ratings, n_sims, avail)
    for team, row in futures.items():
        ratings.loc[ratings.team == team, "projected_wins"] = row["mean_wins"]

    played = int(schedule.completed.sum())
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    meta = {"league": "NBA", "season": f"{end_year - 1}-{str(end_year)[-2:]}", "season_end_year": end_year,
            "games_played": played, "games_scheduled": 1230, "listed_games": int(len(schedule)), "updated_utc": now,
            "n_sims": n_sims, "model": "NBA v0.1", **fit}
    rating_rows = []
    for _, r in ratings.sort_values("rating", ascending=False).iterrows():
        rating_rows.append({"team": r.team, "name": NAMES[r.team],
                            "off_rating": round(float(r.base_ortg + r.off), 1),
                            "def_rating": round(float(r.base_ortg - r["def"]), 1),
                            "net_rating": round(float(r.raw_net), 1), "roster_adj": round(float(r.roster_adj), 1),
                            "model_rating": round(float(r.rating), 1), "pace": round(float(r.pace), 1),
                            "projected_wins": round(float(r.projected_wins), 1)})
    write_json("nba_meta.json", meta)
    write_json("nba_futures.json", {"teams": futures, "divisions": DIVS, "east": EAST, "west": WEST, "availability": availability})
    write_json("nba_ratings.json", {"rows": rating_rows})
    write_json("nba_players.json", {"rows": player_rows})
    write_json("nba_games.json", {"rows": _game_rows(schedule, ratings, avail)})
    write_json("nba_team_stats.json", {"rows": team_stats})
    write_json("nba_advanced_team_stats.json", {"rows": advanced_teams})
    write_json("nba_advanced_player_stats.json", {"rows": advanced_players})
    write_json("nba_shot_zones.json", {"rows": shot_zones})
    write_json("nba_advanced_meta.json", {**advanced_meta, "updated_utc": now})
    write_json("nba_stats_index.json", {"seasons": {
        "teams": sorted({r["season"] for r in team_stats}, reverse=True),
        "players": sorted({r["season"] for r in player_stats}, reverse=True),
        "games": sorted({r["season"] for r in team_games}, reverse=True),
        "advanced": sorted({r["season"] for r in advanced_teams}, reverse=True),
        "shots": sorted({r["season"] for r in shot_zones}, reverse=True)}})
    for year in sorted({r["season"] for r in player_stats}):
        write_json(f"nba_player_stats_{year}.json", {"rows": [r for r in player_stats if r["season"] == year]})
    for year in sorted({r["season"] for r in team_games}):
        write_json(f"nba_team_games_{year}.json", {"rows": [r for r in team_games if r["season"] == year]})
    log("NBA simulation done", n_sims, "seasons")


def build_site() -> None:
    os.makedirs(os.path.join(NBA_SITE, "data"), exist_ok=True)
    shutil.copytree(os.path.join(NBA_SRC, "js"), os.path.join(NBA_SITE, "js"), dirs_exist_ok=True)
    for name in ("nba_meta.json", "nba_futures.json", "nba_ratings.json", "nba_players.json", "nba_games.json",
                 "nba_team_stats.json", "nba_stats_index.json"):
        shutil.copy(os.path.join(OUT, name), os.path.join(NBA_SITE, "data", name.removeprefix("nba_")))
    for prefix in ("nba_player_stats_", "nba_team_games_"):
        for path in glob.glob(os.path.join(OUT, prefix + "*.json")):
            name = os.path.basename(path)
            shutil.copy(path, os.path.join(NBA_SITE, "data", name.removeprefix("nba_")))
    for name in ("nba_advanced_team_stats.json", "nba_advanced_player_stats.json", "nba_shot_zones.json", "nba_advanced_meta.json"):
        shutil.copy(os.path.join(OUT, name), os.path.join(NBA_SITE, "data", name.removeprefix("nba_")))
    for name in ("index.html", "stats.html", "advanced.html", "ratings.html", "players.html", "games.html", "methodology.html"):
        shutil.copy(os.path.join(NBA_SRC, name), os.path.join(NBA_SITE, name))
