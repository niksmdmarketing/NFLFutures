import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

try:
    import pandas as pd
    import nba_rapm as R
except ImportError:  # pragma: no cover
    R = None


@unittest.skipIf(R is None, "numpy/pandas/scipy not installed")
class RapmTest(unittest.TestCase):
    def _game(self):
        box = pd.DataFrame({"athlete_id": list(range(1, 13)), "team_id": [10] * 6 + [20] * 6,
                            "starter": [True] * 5 + [False] + [True] * 5 + [False]})
        ev = pd.DataFrame([
            dict(period_number=1, type_text="Jump Shot", team_id=10, a1=1, a2=None, a3=None, scoring_play=True, score_value=2, shooting_play=True),
            dict(period_number=1, type_text="Substitution", team_id=10, a1=6, a2=1, a3=None, scoring_play=False, score_value=0, shooting_play=False),
            dict(period_number=1, type_text="Jump Shot", team_id=20, a1=7, a2=None, a3=None, scoring_play=True, score_value=3, shooting_play=True),
            dict(period_number=2, type_text="Jump Shot", team_id=10, a1=6, a2=None, a3=None, scoring_play=False, score_value=0, shooting_play=True),
        ])
        ev["home_team_id"], ev["away_team_id"] = 10, 20
        return ev, box

    def test_substitution_and_period_start(self):
        ev, box = self._game()
        rows = R.game_stints(ev, box)
        self.assertEqual(len(rows), 3)
        self.assertIn(1, rows[0][0])
        self.assertEqual(rows[0][2], 2)
        self.assertIn(6, rows[1][0])
        self.assertNotIn(1, rows[1][0])
        self.assertEqual(rows[1][2], -3)
        self.assertIn(6, rows[2][0])          # period 2 starts with the closing five plus whoever acted

    def test_fit_ranks_the_better_player(self):
        S = pd.DataFrame({"home5": [(1, 2, 3, 4, 5), (6, 2, 3, 4, 5)] * 50, "away5": [(7, 8, 9, 10, 11)] * 100,
                          "margin": [5, -5] * 50, "poss": [10.0] * 100})
        r = R.fit([(S, 1.0)], {})
        self.assertGreater(r[1], r[6])


if __name__ == "__main__":
    unittest.main()
