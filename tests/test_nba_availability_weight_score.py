import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))


class WeightScoring(unittest.TestCase):
    def test_identical_predictions_cannot_pass(self):
        import pandas as pd
        from nba_availability_weight_test import score, YEARS, SEEDS
        rows = []
        for year in YEARS:
            for check in (.2, .4, .6, .8):
                for weight in (4, 8):
                    for seed in SEEDS:
                        for team, outcome in (("A", 1), ("B", 0)):
                            rows.append(dict(season=year, check=check, weight=weight, seed=seed, team=team,
                                             p_title=.2, p_conf=.3, p_playoff=.6,
                                             y_title=outcome, y_conf=outcome, y_playoff=outcome))
        result = score(pd.DataFrame(rows))
        self.assertEqual(result["gain"], 0.)
        self.assertEqual(result["ci95"], [0., 0.])
        self.assertFalse(result["pass_gates"])
        self.assertEqual(result["seasons"], 12)
        self.assertTrue(result["gates"]["complete_seasons"])


if __name__ == "__main__":
    unittest.main()
