"""NFL props v1.2 matchup factor: timing, neutral default and shrinkage direction (synthetic data)."""
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import nfl_props_v12 as V  # noqa: E402

P = json.loads(V.PARAMS12.read_text())
T0 = pd.Timestamp("2026-09-10T17:00Z")
DTAB = pd.DataFrame([dict(game_id="g1", season=2026, tip=T0, defence="D", WR=10, TE=20, RB=5, total=35)])
TARGET = T0 + pd.Timedelta(days=7)


class V12Tests(unittest.TestCase):
    def test_no_history_is_neutral(self):
        self.assertEqual(V.factor(DTAB, "X", "TE", TARGET, 2026, TARGET, P), 1.0)

    def test_game_counts_only_after_kickoff_plus_six_hours(self):
        self.assertEqual(V.factor(DTAB, "D", "TE", TARGET, 2026, T0 + pd.Timedelta(hours=5), P), 1.0)
        self.assertGreater(V.factor(DTAB, "D", "TE", TARGET, 2026, T0 + pd.Timedelta(hours=7), P), 1.0)

    def test_direction_and_fullback_group(self):
        now = TARGET
        self.assertLess(V.factor(DTAB, "D", "WR", TARGET, 2026, now, P), 1.0)    # D allowed few WR targets
        self.assertEqual(V.factor(DTAB, "D", "FB", TARGET, 2026, now, P), V.factor(DTAB, "D", "RB", TARGET, 2026, now, P))


if __name__ == "__main__":
    unittest.main()
