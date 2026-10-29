import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))


class WeightScoring(unittest.TestCase):
    def test_float_athlete_ids_match_live_layer_ids(self):
        import pandas as pd
        from nba_avail_futures_test import synthetic_report
        rows = [dict(date=pd.Timestamp("2026-10-01"), season=2027, season_type=2,
                     athlete_id=1234., minutes=25., game_id=1, team_abbreviation="GS")]
        rows += [dict(date=pd.Timestamp(f"2026-10-{day:02}"), season=2027, season_type=2,
                      athlete_id=5678., minutes=25., game_id=day, team_abbreviation="GS") for day in range(2, 8)]
        report = synthetic_report(pd.DataFrame(rows), pd.Timestamp("2026-10-08"), 2027)
        self.assertIn("1234", {r["athlete_id"] for r in report})
        self.assertNotIn("1234.0", {r["athlete_id"] for r in report})

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
