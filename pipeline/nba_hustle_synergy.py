"""NBA hustle and Synergy play-type statistics from SportsDataverse's NBA Stats releases (descriptive; no forecasts).

Sources (release tags in sportsdataverse/sportsdataverse-data, season files 2015-16 onward, regular season and playoffs):
  nba_stats_hustle   leaguehustlestats{player,team}_{regular-season,playoffs}_pergame_<year>.parquet
  nba_stats_synergy  {regular-season,playoffs}_<playtype>_{offensive,defensive}_pergame_<year>.parquet (player level only)
Season keys are end years (2026 = 2025-26). Values are the provider's per-game figures; players below the provider's
minimum possessions for a play type are simply absent (shown as blank, never zero).
"""
import os

import pandas as pd

TAGS = {"hustle": "nba_stats_hustle", "synergy": "nba_stats_synergy"}
SEASON_TYPES = {"regular-season": 2, "playoffs": 3}
FIRST = 2016
OFFENSE = ["cut", "handoff", "isolation", "misc", "offrebound", "offscreen", "postup", "prballhandler", "prrollman", "spotup", "transition"]
DEFENSE = ["handoff", "isolation", "offscreen", "postup", "prballhandler", "prrollman", "spotup"]
LABEL = {"cut": "Cuts", "handoff": "Hand-offs", "isolation": "Isolation", "misc": "Miscellaneous", "offrebound": "Putbacks",
         "offscreen": "Off screens", "postup": "Post-ups", "prballhandler": "P&R ball handler", "prrollman": "P&R roll man",
         "spotup": "Spot-ups", "transition": "Transition"}
HUSTLE = [("contested_shots", "Contested shots", "num1"), ("contested_shots_2_pt", "Contested 2PT", "num1"),
          ("contested_shots_3_pt", "Contested 3PT", "num1"), ("deflections", "Deflections", "num1"),
          ("charges_drawn", "Charges drawn", "num2"), ("screen_assists", "Screen assists", "num1"),
          ("screen_ast_pts", "Screen-assist PTS", "num1"), ("loose_balls_recovered", "Loose balls recovered", "num1"),
          ("off_boxouts", "Off. box-outs", "num1"), ("def_boxouts", "Def. box-outs", "num1"), ("box_outs", "Box-outs", "num1")]
TEAM_ABBR_FIX = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH", "PHO": "PHX", "BRK": "BKN", "CHO": "CHA"}


def _read(cache_get, tag, name):
    path = cache_get(tag, name)
    if not path or not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001  a corrupt or partial file is skipped, never fatal
        return None


def hustle_frames(cache_get, year):
    """-> {season_type: (team_df, player_df)} with keys: team / player(+name, team, gp) and h_<stat> columns."""
    out = {}
    for stype, code in SEASON_TYPES.items():
        P = _read(cache_get, TAGS["hustle"], f"leaguehustlestatsplayer_{stype}_pergame_{year}.parquet")
        T = _read(cache_get, TAGS["hustle"], f"leaguehustlestatsteam_{stype}_pergame_{year}.parquet")
        if P is None or T is None or P.empty or T.empty:
            continue
        ids = dict(zip(P.team_id, P.team_abbreviation.replace(TEAM_ABBR_FIX)))
        T = T.copy()
        T["team"] = T.team_id.map(ids)
        P = P.copy()
        P["team"] = P.team_abbreviation.replace(TEAM_ABBR_FIX)
        for k, _, _ in HUSTLE:
            for df in (T, P):
                df["h_" + k] = pd.to_numeric(df[k], errors="coerce") if k in df else float("nan")
        P["player"] = P.player_name
        out[code] = (T[["team"] + ["h_" + k for k, _, _ in HUSTLE]].dropna(subset=["team"]),
                     P[["player", "team"] + ["h_" + k for k, _, _ in HUSTLE]])
    return out


def synergy_frame(cache_get, year, code_name):
    """Wide per-player table for one season type: syn_<side>_<type>_{poss,ppp,freq} columns, keyed by player name."""
    wide = None
    for side, types in (("o", OFFENSE), ("d", DEFENSE)):
        for t in types:
            side_name = "offensive" if side == "o" else "defensive"
            d = _read(cache_get, TAGS["synergy"], f"{code_name}_{t}_{side_name}_pergame_{year}.parquet")
            if d is None or d.empty:
                continue
            d = d.assign(player=d.player_name)
            # a traded player has one row per team plus an overall row in some seasons: keep the row with most possessions
            d = d.sort_values("poss", ascending=False).drop_duplicates("player")
            x = d[["player", "poss", "ppp", "poss_pct"]].rename(columns={"poss": f"syn_{side}_{t}_poss", "ppp": f"syn_{side}_{t}_ppp",
                                                                          "poss_pct": f"syn_{side}_{t}_freq"})
            wide = x if wide is None else wide.merge(x, on="player", how="outer")
    return wide
