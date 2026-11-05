import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "pipeline"), str(ROOT / "research")]
import nhl_lineup as L
from nhl_preseason_roster import prior_lineups


class PreseasonRoster(unittest.TestCase):
    def test_previous_lineups_use_identical_ratings_and_no_opening(self):
        s, g, sk, gk = [pd.DataFrame({"x": [1]}) for _ in range(4)]
        expected = pd.DataFrame({"lv": [2.]})
        with patch.object(L, "game_values_ratings", return_value=expected) as value:
            last, opening = prior_lineups(s, g, sk, gk, .438)
        self.assertIs(last, expected)
        self.assertIsNone(opening)
        args = value.call_args.args
        for actual, wanted in zip(args, (s, sk, gk, .438, g)):
            self.assertIs(actual, wanted) if not isinstance(wanted, float) else self.assertEqual(actual, wanted)

    def test_missing_history_is_not_invented_and_missing_ratings_fail(self):
        frame = pd.DataFrame({"x": [1]})
        self.assertEqual(prior_lineups(None, None, frame, frame, .438), (None, None))
        with self.assertRaises(ValueError):
            prior_lineups(frame, frame, None, frame, .438)

    def test_future_lineups_do_not_change_opening_forecast(self):
        cur = pd.DataFrame({"date": pd.to_datetime(["2025-10-02", "2025-10-02"]),
                            "team": ["A", "B"], "lv": [100., -100.]})
        last = cur.assign(date=pd.to_datetime("2024-10-01"), lv=[-2., 2.])
        result = L.roster_term(cur, last, ["A", "B"], pd.Timestamp("2025-10-01"), 10, opening=None, pre=True)
        np.testing.assert_array_equal(result.to_numpy(), [0., 0.])

    def test_prior_component_has_registered_fade_and_leaves_current_part(self):
        cur = pd.DataFrame({"date": pd.to_datetime(["2025-10-01", "2025-10-02"] * 2),
                            "team": ["A", "A", "B", "B"], "lv": [2., 4., -2., -4.]})
        last = pd.DataFrame({"team": ["A", "B"], "lv": [1., -1.]})
        cut = pd.Timestamp("2025-10-03")
        a = L.roster_term(cur, last, ["A", "B"], cut, 10, n=1, opening=None, pre=True)
        b = L.roster_term(cur, last, ["A", "B"], cut, 10, n=1, opening=None, pre=False)
        np.testing.assert_allclose((a-b).to_numpy(), [10/12*3, -10/12*3])


if __name__ == "__main__":
    unittest.main()
