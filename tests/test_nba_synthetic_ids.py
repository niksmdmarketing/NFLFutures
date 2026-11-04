"""Regression: synthetic absences must join canonical ESPN player IDs."""
import sys
from pathlib import Path
import unittest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipeline'))
sys.path.insert(0, str(ROOT / 'research'))
import nba_avail_futures_test as replay


class SyntheticIds(unittest.TestCase):
    def test_float_and_text_ids_match_the_same_missing_rotation_player(self):
        rows = []
        for i, date in enumerate(pd.date_range('2026-01-01', periods=7)):
            for player in ([999., 123.] if i < 2 else [999.]):
                rows.append({'athlete_id': player, 'minutes': 30, 'date': date,
                             'season': 2026, 'season_type': 2, 'game_id': str(i), 'team_abbreviation': 'NY'})
        frame = pd.DataFrame(rows)
        numeric = replay.synthetic_report(frame, pd.Timestamp('2026-01-07'), 2026)
        text_frame = frame.assign(athlete_id=frame.athlete_id.astype(str))
        text = replay.synthetic_report(text_frame, pd.Timestamp('2026-01-07'), 2026)
        self.assertEqual(numeric, text)
        self.assertEqual([r['athlete_id'] for r in numeric], ['123'])
        self.assertEqual(numeric[0]['status'], 'Out')
