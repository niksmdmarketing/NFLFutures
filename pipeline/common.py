"""Shared constants, data downloads and loaders for the NFLFutures pipeline."""
import datetime as dt
import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "build")
MODEL = os.path.join(ROOT, "model")
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
FIX = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "JAC": "JAX"}
DIVS = {
    "AFC East": ["BUF", "MIA", "NE", "NYJ"], "AFC North": ["BAL", "CIN", "CLE", "PIT"],
    "AFC South": ["HOU", "IND", "JAX", "TEN"], "AFC West": ["DEN", "KC", "LV", "LAC"],
    "NFC East": ["DAL", "NYG", "PHI", "WAS"], "NFC North": ["CHI", "DET", "GB", "MIN"],
    "NFC South": ["ATL", "CAR", "NO", "TB"], "NFC West": ["ARI", "LA", "SEA", "SF"],
}
TEAMS = sorted(t for v in DIVS.values() for t in v)
TIX = {t: i for i, t in enumerate(TEAMS)}
NT = 32
NAMES = {"ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
         "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
         "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
         "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
         "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
         "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
         "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
         "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def download(rel, name=None, max_age_h=2.0, required=True):
    """Download an nflverse release file into data/, reusing a fresh local copy."""
    name = name or rel.split("/")[-1]
    path = os.path.join(DATA, name)
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        return path
    url = f"{NFLVERSE}/{rel}"
    for attempt in range(4):
        try:
            tmp = path + ".part"
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                f.write(r.read())
            os.replace(tmp, path)
            return path
        except Exception as e:  # noqa: BLE001
            if "404" in str(e):
                if required:
                    raise
                return None
            time.sleep(5 * (attempt + 1))
    if os.path.exists(path):
        return path
    if required:
        raise RuntimeError(f"could not download {url}")
    return None


def games():
    g = pd.read_csv(download("schedules/games.csv"), low_memory=False)
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    return g


def current_season(g):
    """The season whose regular season has started or starts within 45 days."""
    today = dt.date.today().isoformat()
    soon = (dt.date.today() + dt.timedelta(days=45)).isoformat()
    reg = g[g.game_type == "REG"]
    starts = reg.groupby("season").gameday.min()
    cands = starts[starts <= soon]
    return int(cands.index.max())


PBP_COLS = ["game_id", "play_id", "season_type", "week", "home_team", "away_team", "posteam", "defteam", "play_type",
            "pass", "rush", "epa", "success", "yards_gained", "sack", "interception", "fumble", "fumble_lost",
            "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike", "two_point_attempt", "qb_hit",
            "passer_player_id", "passer_player_name", "rusher_player_id", "rusher_player_name",
            "down", "ydstogo", "yardline_100", "shotgun", "no_huddle", "air_yards", "xpass", "pass_oe",
            "score_differential", "game_seconds_remaining", "qtr", "wp", "third_down_converted", "third_down_failed",
            "fixed_drive", "fixed_drive_result", "touchdown", "complete_pass", "pass_attempt", "first_down",
            "total_home_score", "total_away_score", "penalty", "time_of_day", "end_clock_time", "timeout",
            "posteam_score", "posteam_score_post", "field_goal_result", "kick_distance", "extra_point_result",
            "punt_inside_twenty", "punt_blocked", "touchback", "return_yards", "kickoff_attempt", "punt_attempt",
            "field_goal_attempt", "extra_point_attempt", "penalty_team", "penalty_yards", "penalty_type",
            "fourth_down_converted", "fourth_down_failed", "pass_touchdown", "rush_touchdown", "return_team",
            "goal_to_go", "drive_time_of_possession"]


def load_pbp(season, max_age_h=2.0):
    is_cur = season >= current_season_cached()
    path = download(f"pbp/play_by_play_{season}.csv.gz", max_age_h=max_age_h if is_cur else 24 * 365,
                    required=not is_cur)
    if path is None:  # season not started yet: empty frame with the expected columns
        d = pd.DataFrame({c: pd.Series(dtype="float64") for c in PBP_COLS})
        for c in ("game_id", "season_type", "home_team", "away_team", "posteam", "defteam", "play_type",
                  "passer_player_id", "passer_player_name", "rusher_player_id", "rusher_player_name", "fixed_drive_result",
                  "time_of_day", "end_clock_time", "field_goal_result", "extra_point_result", "penalty_team",
                  "penalty_type", "return_team", "drive_time_of_possession"):
            d[c] = d[c].astype("object")
        d["season"] = season
        return d
    d = pd.read_csv(path, usecols=lambda c: c in PBP_COLS, low_memory=False)
    d = d[d.season_type == "REG"].copy()
    for c in ("posteam", "defteam", "home_team", "away_team"):
        d[c] = d[c].replace(FIX)
    d["season"] = season
    return d


_SEASON = {}


def current_season_cached():
    if "s" not in _SEASON:
        _SEASON["s"] = current_season(games())
    return _SEASON["s"]


def scrimmage(d):
    """Run/pass plays used for team efficiency (no kneels, spikes, 2-pt tries)."""
    s = d[d.posteam.isin(TIX) & d.defteam.isin(TIX) & d.epa.notna()]
    s = s[((s["pass"] == 1) | (s["rush"] == 1)) & s.play_type.isin(["pass", "run"])]
    s = s[(s.qb_kneel != 1) & (s.qb_spike != 1) & (s.two_point_attempt != 1)].copy()
    for c in ("success", "sack", "interception", "fumble", "fumble_lost", "qb_hit"):
        s[c] = s[c].fillna(0).astype(float)
    s["db"] = ((s["pass"] == 1) | (s.qb_scramble == 1)).astype(int)
    s["dr"] = ((s["rush"] == 1) & (s.qb_scramble != 1)).astype(int)
    s["to"] = ((s.interception == 1) | (s.fumble_lost == 1)).astype(int)
    s["expl"] = (((s["pass"] == 1) & (s.yards_gained >= 15)) | ((s["rush"] == 1) & (s.yards_gained >= 10))).astype(float)
    return s


def special(d):
    return d[d.play_type.isin(["punt", "field_goal", "kickoff", "extra_point"]) & d.posteam.isin(TIX)
             & d.defteam.isin(TIX) & d.epa.notna()][["week", "posteam", "defteam", "epa"]]


def write_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"), default=_np)


def _np(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def rank(series, high_good=True):
    """1 = best."""
    return series.rank(ascending=not high_good, method="min").astype(int)
