"""Compute completed seasons once and store them in history/ (committed), so the 3-hourly job only computes
the current season.

    python pipeline/history.py            # every season from 2018 to last season
    python pipeline/history.py 2024 2025  # just these
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import team_season  # noqa: E402
from common import ROOT, current_season, games, load_pbp, log  # noqa: E402

HIST = os.path.join(ROOT, "history")
FIRST = 2018


def clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, 4)


def values_json(V):
    return {page: {t: {c: clean(v) for c, v in row.items()} for t, row in df.iterrows()} for page, df in V.items()}


def build(season, g):
    pbp = load_pbp(season, max_age_h=24 * 365)
    V = team_season.season_values(season, g, pbp, current=False)
    cube = team_season.pace_cube(season, g, pbp)
    os.makedirs(HIST, exist_ok=True)
    with open(os.path.join(HIST, f"{season}.json"), "w") as f:
        json.dump({"season": season, "values": values_json(V)}, f, separators=(",", ":"))
    if cube:
        with open(os.path.join(HIST, f"pace_{season}.json"), "w") as f:
            json.dump(cube, f, separators=(",", ":"))
    log("history", season, "done")


if __name__ == "__main__":
    g = games()
    seasons = [int(a) for a in sys.argv[1:]] or list(range(FIRST, current_season(g)))
    for y in seasons:
        build(y, g)
