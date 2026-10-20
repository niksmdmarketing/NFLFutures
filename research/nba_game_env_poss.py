"""Possession durations and points from ESPN play-by-play (research/NBA_GAME_ENV_RULE.md, simulation inputs).
Possessing team per event: shots and free throws (not technical) -> shooter's team; turnovers -> that team; offensive and
defensive rebounds -> rebounder's team. Possessions = runs of the same possessing team within a period. Duration = time
from the previous possession's last event (or period start) to this possession's last event. Points = scoring plays by the
possessing team in the run (technical free throws excluded). Regulation periods only.
python research/nba_game_env_poss.py <out_dir>  -> poss_<season>.npz (dur, pts) for seasons 2014-2026
"""
import os
import sys

import numpy as np
import pandas as pd

PBP = "/home/claude/nbapbp"


def season(y):
    P = pd.read_parquet(os.path.join(PBP, f"pbp_{y}.parquet"), columns=[
        "game_id", "season_type", "sequence_number", "period_number", "type_text", "team_id", "scoring_play", "score_value",
        "shooting_play", "start_quarter_seconds_remaining"])
    P = P[(pd.to_numeric(P.season_type, errors="coerce") == 2) & (P.period_number <= 4)].copy()
    P["sequence_number"] = pd.to_numeric(P.sequence_number, errors="coerce")
    P = P.sort_values(["game_id", "period_number", "sequence_number"])
    tt = P.type_text.astype(str)
    tech = tt.str.contains("Technical")
    is_shot = P.shooting_play.astype(bool) & ~tech
    is_tov = tt.str.contains("Turnover") | tt.isin(["Traveling", "Offensive Charge", "Offensive Foul Turnover", "Kicked Ball Turnover"])
    is_reb = tt.isin(["Offensive Rebound", "Defensive Rebound"])
    P["pt"] = np.where(is_shot | is_tov | is_reb, P.team_id, np.nan)
    P["pts"] = np.where(P.scoring_play.astype(bool) & ~tech, pd.to_numeric(P.score_value, errors="coerce").fillna(0), 0)
    P["t"] = 720 - pd.to_numeric(P.start_quarter_seconds_remaining, errors="coerce")
    P = P.dropna(subset=["t"])
    # carry possessing team forward to non-possession events (fouls, subs) so their points (none) and times attach
    P["pt"] = P.groupby(["game_id", "period_number"]).pt.ffill()
    P = P.dropna(subset=["pt"])
    key = P.game_id.astype(str) + "_" + P.period_number.astype(str)
    new = (P.pt != P.pt.shift()) | (key != key.shift())
    P["run"] = new.cumsum()
    D = P.groupby("run").agg(k=("game_id", "first"), per=("period_number", "first"), pts=("pts", "sum"),
                             end=("t", "max"))
    # last possession-defining event time of each run: max time among possession events
    D["prev_end"] = D.groupby(["k", "per"]).end.shift().fillna(0.0)
    D["dur"] = (D.end - D.prev_end).clip(lower=0)
    return D.dur.to_numpy(float), D.pts.to_numpy(int)


if __name__ == "__main__":
    out = sys.argv[1]
    for y in range(2014, 2027):
        d, p = season(y)
        np.savez_compressed(os.path.join(out, f"poss_{y}.npz"), dur=d, pts=p)
        print(y, len(d), "mean dur", round(d.mean(), 2), "ppp", round(p.mean(), 3), "pmf", np.round(np.bincount(p) / len(p), 4), flush=True)
