"""Validation for the NBA era fixes (research/NBA_REPLAY_STANDING_RULE.md, Amendment 4, item 5).
Inputs (after franchise mapping): 30 teams in team boxes and schedules, all in today's 6 divisions; regular-season games as played;
16 playoff teams and a champion. Outputs (after the run): per checkpoint, title sums to 1, Finals 2, No.1 seed 2, division 6,
playoffs 16, mean wins to the season's games. Usage: python research/nba_era_check.py inputs|outputs <first> <last> [output dir]"""
import glob
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nba as N  # noqa: E402
N.OVERRIDES_PATH = ""
import nba_backtest as B  # noqa: E402
import nba_title_backtest as T  # noqa: E402
from replay_nba import _fr  # noqa: E402

GAMES = {2012: 990, 2013: 1229, 2020: None, 2021: 1080}


def inputs(first, last):
    boxes = _fr(B.load_boxes(last))
    probs = []
    for y in range(first, last + 1):
        if y == 2020:
            continue
        reg = boxes[(pd.to_numeric(boxes.season, errors="coerce") == y) & (pd.to_numeric(boxes.season_type, errors="coerce") == 2)]
        teams = set(reg.team_abbreviation) & set(N.TEAMS)
        g = B.season_games(boxes, y)
        sched = N._schedule(_fr(N._csv(os.path.join(N.NBA_DATA, f"nba_schedule_{y}.csv"))))
        out = T.outcomes(boxes, y)
        exp = GAMES.get(y, 1230)
        row = dict(season=y, teams=len(teams), games=len(g), sched_games=len(sched), sched_teams=len(set(sched.home_abbreviation) | set(sched.away_abbreviation)),
                   playoff_teams=len(out["playoffs"]) if out else 0, champ=out["champ"] if out else None,
                   outside_codes=sorted(set(reg.team_abbreviation) - set(N.TEAMS)))
        print(row)
        if row["teams"] != 30 or row["sched_teams"] != 30: probs.append(f"{y}: teams {row['teams']}/{row['sched_teams']}")
        if abs(row["games"] - exp) > 6:   # box files miss a few games in some seasons and include the NBA Cup final from 2024
            probs.append(f"{y}: {row['games']} box games (expected about {exp})")
        if row["playoff_teams"] != 16 + (4 if y >= 2021 else 0) - (4 if y >= 2021 else 0): probs.append(f"{y}: {row['playoff_teams']} playoff teams")
    if probs:
        raise SystemExit("ERA INPUT CHECK FAILED:\n  " + "\n  ".join(probs))
    print("era input check passed")


def outputs(first, last, d):
    probs = []
    for f in sorted(glob.glob(os.path.join(d, "nba_*.csv"))):
        D = pd.read_csv(f)
        y = int(D.season.iloc[0])
        if not first <= y <= last:
            continue
        s = D.groupby("week")[["p_title", "p_conf", "p_seed1", "p_div", "p_playoff", "mean_wins"]].sum()
        games = {2012: 990, 2013: 1229, 2021: 1080}.get(y, 1230)
        for c, v, tol in (("p_title", 1, 0.002), ("p_conf", 2, 0.002), ("p_seed1", 2, 0.002), ("p_div", 6, 0.002), ("p_playoff", 16, 0.002), ("mean_wins", games, 1.0)):
            bad = s[(s[c] - v).abs() > tol]
            if len(bad):
                probs.append(f"{y} {c}: {len(bad)} checkpoints off (e.g. {float(bad[c].iloc[0]):.3f} vs {v})")
        print(y, "checkpoints", len(s), "teams/checkpoint", int(D.groupby("week").size().min()), "mean_wins sum", round(float(s.mean_wins.mean()), 1))
    if probs:
        raise SystemExit("ERA OUTPUT CHECK FAILED:\n  " + "\n  ".join(probs))
    print("era output check passed")


if __name__ == "__main__":
    a, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    inputs(first, last) if a == "inputs" else outputs(first, last, sys.argv[4])
