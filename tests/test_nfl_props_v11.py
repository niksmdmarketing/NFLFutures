"""NFL props v1.1 team-volume features: timing and opponent alignment (synthetic data, no downloads)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import nfl_props_v11 as V  # noqa: E402


def games():
    t0 = pd.Timestamp("2026-09-10T17:00Z")
    rows = [("2026_01_A_B", 1, "B", "A", 20, 10, t0), ("2026_02_A_C", 2, "C", "A", None, None, t0 + pd.Timedelta(days=7))]
    return pd.DataFrame([dict(game_id=g, season=2026, week=w, home_team=h, away_team=a, home_score=hs, away_score=as_, location="Home", tip=t)
                         for g, w, h, a, hs, as_, t in rows])


AGG = pd.DataFrame([dict(game_id="2026_01_A_B", team="A", pass_off=.2, rush_off=0., pass_def=-.1, rush_def=0., plays=60, attempts=40),
                    dict(game_id="2026_01_A_B", team="B", pass_off=-.1, rush_off=0., pass_def=.3, rush_def=0., plays=50, attempts=25)])
TOTALS = {("2026_01_A_B", "A"): 40, ("2026_01_A_B", "B"): 25}


class V11Tests(unittest.TestCase):
    def row(self, now):
        F = V.team_features(games(), AGG, TOTALS, now=now)
        return F[(F.game_id == "2026_02_A_C") & (F.team == "A")].iloc[0]

    def test_game_enters_state_only_after_kickoff_plus_six_hours(self):
        early = self.row(pd.Timestamp("2026-09-10T22:00Z"))      # 5 h after kickoff: not yet observed
        late = self.row(pd.Timestamp("2026-09-11T00:00Z"))       # 7 h after kickoff
        self.assertEqual(early.own_att, 35.0)                    # prior default
        self.assertEqual(late.own_att, 40.0)
        self.assertAlmostEqual(late.own_pass_off, .2)

    def test_opponent_allowed_is_the_opponents_history_not_own(self):
        F = V.team_features(games(), AGG, TOTALS, now=pd.Timestamp("2026-09-12T00:00Z"))
        b = F[(F.game_id == "2026_02_A_C") & (F.team == "C")].iloc[0]
        self.assertEqual(b.opp_att, 25.0)                        # A allowed B's 25 attempts
        self.assertEqual(b.own_att, 35.0)                        # C has no history yet

    def test_elo_moves_after_a_win(self):
        r = self.row(pd.Timestamp("2026-09-12T00:00Z"))
        self.assertLess(r.elo_gap, -65 / 400)                    # A (away) lost: below the plain home-edge gap


if __name__ == "__main__":
    unittest.main()
