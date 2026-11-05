"""Stints for the joint team-and-player test (research/NBA_JOINT_TEAM_PLAYER_RULE.md): same construction as
research/nba_stints.py (it is imported, not copied) plus the home and away team ids of each game.
Output: <out dir>/stints_<y>.parquet (the nba_stints.py schema plus htid, atid) and meta.json (usable-game share).
Usage: python research/nba_joint_stints.py <pbp dir with pbp_<y>.parquet> <out dir> <season> [...]"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba_stints as S0  # noqa: E402


def season(pbp_dir, out_dir, y):
    ev = pd.read_parquet(os.path.join(pbp_dir, f"pbp_{y}.parquet"),
                         columns=["game_id", "game_play_number", "sequence_number", "type_text", "period_number", "team_id",
                                  "athlete_id_1", "athlete_id_2", "athlete_id_3", "scoring_play", "score_value", "shooting_play",
                                  "start_quarter_seconds_remaining", "home_team_id", "away_team_id", "season_type", "game_date"])
    ev = ev[pd.to_numeric(ev.season_type, errors="coerce") == 2].copy()
    for c in ("athlete_id_1", "athlete_id_2", "athlete_id_3"):
        ev[c] = pd.Series([S0._id(x) for x in ev[c]], index=ev.index, dtype=object)
    ev = ev.rename(columns={"athlete_id_1": "a1", "athlete_id_2": "a2", "athlete_id_3": "a3"})
    ev["seq"] = pd.to_numeric(ev.sequence_number, errors="coerce")
    ev = ev.sort_values(["game_id", "period_number", "seq"])
    box = pd.read_csv(os.path.join(S0.BOX, f"player_box_{y}.csv"), usecols=["game_id", "athlete_id", "team_id", "starter"], low_memory=False)
    box["athlete_id"] = box.athlete_id.map(S0._id)
    box["starter"] = box.starter.astype(str).str.lower().eq("true")
    boxes = {g: b for g, b in box.groupby("game_id")}
    out, bad, ngames = [], 0, 0
    for gid, g in ev.groupby("game_id", sort=False):
        ngames += 1
        b = boxes.get(gid)
        res = S0.game_stints(g, b) if b is not None else None
        if res is None:
            bad += 1
            continue
        date = str(g.game_date.iloc[0])[:10]
        ht, at = int(g.home_team_id.iloc[0]), int(g.away_team_id.iloc[0])
        out.extend((gid, date, ht, at, *r) for r in res)
    cols = ["game_id", "date", "htid", "atid", "home5", "away5", "hpts", "apts", "hfga", "horb", "htov", "hfta", "afga", "aorb", "atov", "afta", "sec"]
    S = pd.DataFrame(out, columns=cols)
    S["poss"] = ((S.hfga - S.horb + S.htov + .44 * S.hfta) + (S.afga - S.aorb + S.atov + .44 * S.afta)) / 2
    for side in ("home5", "away5"):
        S[side] = S[side].map(lambda t: ",".join(map(str, t)))
    S.to_parquet(os.path.join(out_dir, f"stints_{y}.parquet"), index=False)
    import json
    mp = os.path.join(out_dir, "meta.json")
    meta = json.load(open(mp)) if os.path.exists(mp) else {}
    meta[str(y)] = dict(games=ngames, unusable=bad, usable_share=round(1 - bad / max(ngames, 1), 4), stints=len(S))
    json.dump(meta, open(mp, "w"), indent=1)
    print(y, "games", ngames, "unusable", bad, "usable_share", round(1 - bad / max(ngames, 1), 4), "stints", len(S), flush=True)


if __name__ == "__main__":
    pbp_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    for y in sys.argv[3:]:
        season(pbp_dir, out_dir, int(y))
