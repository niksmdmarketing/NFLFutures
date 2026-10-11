import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import cfb_site as C


class CollegeStatsTests(unittest.TestCase):
    def test_wrong_season_rejected(self):
        with self.assertRaises(ValueError):
            C.validate(pd.DataFrame({'season': [2025]}), 2026)

    def test_excludes_allstar_and_exhibition(self):
        refs = pd.DataFrame({'team_id': [1, 2, 3, 4], 'is_fbs': [True, True, True, False],
                             'is_all_star': [False, True, False, False], 'is_exhibition': [False, False, True, False]})
        self.assertEqual(C.fbs_ids(refs), {'1'})

    def test_final_filter_and_fcs_opponent(self):
        d = dict(game_id=100, game_date='2026-09-01T00:00Z', week=1, season_type=2,
                 home_id=1, away_id=2, home_score=20, away_score=0, status='STATUS_FINAL', neutral_site=True)
        schedule = pd.DataFrame([d, {**d, 'game_id': 101, 'status': 'STATUS_SCHEDULED'}])
        rows = C.game_rows(schedule, {'1'}, {'1': 'FBS school', '2': 'FCS school'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0].opp, 'FCS school')
        self.assertEqual(rows.iloc[0].ha, 'N')
        self.assertEqual(rows.iloc[0].pf, 20)

    def test_rates_and_no_market_fields(self):
        cols = C.team_columns()
        self.assertEqual(next(c for c in cols if c['k'] == 'success_off')['f'], 'pct')
        self.assertFalse(any('odds' in c['k'] or 'spread' in c['k'] for c in cols))
        self.assertEqual(C.game_column('box', 'firstDowns')['f'], 'int')
        self.assertEqual(C.game_column('situational', 'EPA_success_rate_rz')['f'], 'pct')
        self.assertEqual(C.game_column('situational', 'EPA_success_third')['f'], 'int')
        self.assertEqual(C.game_column('advanced', 'line_yards')['f'], 'num2')
        self.assertEqual(C.col('games', count=True)['f'], 'int')
        self.assertEqual(len({c['l'] for c in cols}), len(cols))


if __name__ == '__main__':
    unittest.main()
