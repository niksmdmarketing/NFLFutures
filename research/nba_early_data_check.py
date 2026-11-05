"""NBA data-quality check before extending replays earlier (research/TEST_POWER_RULE.md plan, 5 Nov 2026). Report only.
Per season: regular-season games in box scores vs play-by-play vs rebuilt stints; usable-game share; possessions per team-game from
stints; correlation of each player's stint minutes with his box-score minutes; team codes outside today's 30 (era mapping);
team count. Usage: python research/nba_early_data_check.py [first] [last]   -> research/nba_early_data_check.json"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nba as N  # noqa: E402
ST = os.environ.get("NBA_STINTS", "/home/claude/nbapbp/jstints")


def season(y, meta):
    b = pd.read_csv(os.path.join(N.NBA_DATA, f"player_box_{y}.csv"), low_memory=False,
                    usecols=["game_id", "athlete_id", "team_abbreviation", "minutes", "season_type"])
    b = b[pd.to_numeric(b.season_type, errors="coerce") == 2]
    b["minutes"] = pd.to_numeric(b.minutes, errors="coerce").fillna(0)
    b["athlete_id"] = pd.to_numeric(b.athlete_id, errors="coerce")
    S = pd.read_parquet(os.path.join(ST, f"stints_{y}.parquet"))
    S = S[S.htid.between(1, 30) & S.atid.between(1, 30)]
    secs = {}
    for side in ("home5", "away5"):
        for lst, s in zip(S[side], S.sec):
            for a in lst.split(","):
                a = int(float(a))
                secs[a] = secs.get(a, 0.0) + s
    bm = b.groupby("athlete_id").minutes.sum()
    common = [a for a in bm.index if a in secs and bm[a] > 0]
    games_with_stints = S.game_id.nunique()
    r = np.corrcoef([bm[a] for a in common], [secs[a] / 60 for a in common])[0, 1]
    ratio = sum(secs[a] / 60 for a in common) / sum(bm[a] for a in common if True)
    poss_pg = S.groupby("game_id").poss.sum().mean()
    codes = sorted(b.team_abbreviation.dropna().unique())
    m = meta.get(str(y), {})
    return dict(season=y, box_games=int(b.game_id.nunique()), pbp_games=m.get("games"), stint_games=int(games_with_stints),
                usable_share=m.get("usable_share"), pbp_coverage_of_box=round(games_with_stints / b.game_id.nunique(), 4),
                poss_per_game=round(float(poss_pg), 1), minutes_corr=round(float(r), 4), minutes_ratio_stints_to_box=round(float(ratio), 3),
                teams=len(codes), codes_not_current=[c for c in codes if c not in N.TEAMS])


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2003
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    meta = json.load(open(os.path.join(ST, "meta.json")))
    rows = [season(y, meta) for y in range(first, last + 1)]
    T = pd.DataFrame(rows)
    print(T.to_string(index=False))
    json.dump(rows, open(os.path.join(ROOT, "research", "nba_early_data_check.json"), "w"), indent=1)
