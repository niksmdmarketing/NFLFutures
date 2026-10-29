import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from nba_dated_absence_coverage import evaluate, timestamp


class Coverage(unittest.TestCase):
    cutoff = timestamp("2026-10-29T12:00:00Z")

    def test_empty_cutoff_fails(self):
        x = evaluate(self.cutoff, [], [], [])
        self.assertFalse(x["eligible"])
        self.assertIn("no_paired_injury_futures_in_window", x["issues"])

    def test_future_report_does_not_qualify(self):
        pair = dict(t="2026-10-29T11:50Z", without={}, **{"with": {}})
        x = evaluate(self.cutoff, [dict(collected_utc="2026-10-29T1151Z")], [pair], [])
        self.assertIsNone(x["preceding_report_time"])
        self.assertIn("no_report_saved_before_forecast", x["issues"])

    def test_two_files_without_provenance_are_not_a_pass(self):
        pair = dict(t="2026-10-29T11:50Z", without={}, **{"with": {}})
        x = evaluate(self.cutoff, [dict(collected_utc="2026-10-29T1149Z")], [pair],
                     [dict(generated_utc="2026-10-29T11:55Z")])
        self.assertFalse(x["eligible"])
        self.assertIn("actual_input_hash_linkage_not_archived", x["issues"])
        self.assertIn("independent_pre_cutoff_push_receipts_missing", x["issues"])

    def test_late_forecast_is_rejected(self):
        x = evaluate(self.cutoff, [], [], [dict(generated_utc="2026-10-29T12:01Z")])
        self.assertIsNone(x["forecast_time"])


if __name__ == "__main__":
    unittest.main()
