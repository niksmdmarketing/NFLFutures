"""Add the round-2 / conference-final outcomes (y_r2, y_r3) to the committed NHL replay files without re-simulating: the
replays already hold p_r2 and p_r3, only the outcomes were missing (research/replay_nhl.py now writes them too).
Usage: python research/nhl_round_outcomes.py <published nhl/data dir>"""
import glob
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rounds(data_dir, y):
    J = json.load(open(os.path.join(data_dir, f"games_{y}p.json")))
    D = pd.DataFrame([r[:5] for r in J["rows"]], columns=["date", "team", "opp", "ha", "res"])   # same layout as nhl_model.read_games
    n = D.groupby("team").opp.nunique()
    return set(n[n >= 2].index), set(n[n >= 3].index)


def main(data_dir):
    for f in sorted(glob.glob(os.path.join(ROOT, "model", "replay", "nhl_20*.csv"))):
        R = pd.read_csv(f)
        y = int(R.season.iloc[0])
        r2, r3 = rounds(data_dir, y)
        R["y_r2"] = R.team.isin(r2).astype(int)
        R["y_r3"] = R.team.isin(r3).astype(int)
        R.to_csv(f, index=False)
        print(os.path.basename(f), "won a round", len(r2), "conference finalists", len(r3))


if __name__ == "__main__":
    main(sys.argv[1])
