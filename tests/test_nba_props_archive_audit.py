from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from nba_props_archive_audit import record_errors, pmf_errors
from nba_props_forward_score import box_players, conditional_pmf, minutes_value, rps


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.rec = dict(cutoff_utc="2026-10-20T18:00:00Z", generated_utc="2026-10-20T17:30:00Z",
                        forecast_finished_utc="2026-10-20T17:32:00Z", params_id="b", params_sha256="hash",
                        pair_check=dict(same_players=True, max_abs_pi_diff=0,
                                        max_abs_prob_diff_below_threshold_scaled=0),
                        players=[dict(aid=1, team="BOS", p_appear=.5,
                                      **{k: [.5, .5] for k in ("minutes_v2", "minutes_v3", "reb_v2", "reb_v3", "ast_v2", "ast_v3")})])

    def test_valid(self):
        self.assertEqual(record_errors(self.rec, "2026-10-20T17:33:00Z", "hash"), [])

    def test_missing_receipt(self):
        self.assertIn("no_independent_push_receipt", record_errors(self.rec, None, "hash"))

    def test_late_push(self):
        self.assertIn("push_outside_cutoff_or_before_finish", record_errors(self.rec, "2026-10-20T18:01:00Z", "hash"))

    def test_finish_late(self):
        self.rec["forecast_finished_utc"] = "2026-10-20T18:01:00Z"
        self.assertIn("outside_generation_window", record_errors(self.rec, "2026-10-20T18:02:00Z", "hash"))

    def test_outside_45_minutes(self):
        self.rec["generated_utc"] = "2026-10-20T17:14:00Z"
        self.assertIn("outside_generation_window", record_errors(self.rec, "2026-10-20T17:33:00Z", "hash"))

    def test_wrong_parameter_hash(self):
        self.assertIn("wrong_parameters", record_errors(self.rec, "2026-10-20T17:33:00Z", "other"))

    def test_bad_probability(self):
        self.assertTrue(pmf_errors([.3, .4]))
        self.assertTrue(pmf_errors([float("nan"), .5]))
        self.assertEqual(pmf_errors([.5, .500001]), [])

    def test_duplicate(self):
        self.rec["players"] *= 2
        self.assertIn("duplicate_player", record_errors(self.rec, "2026-10-20T17:33:00Z", "hash"))

    def test_different_pairs(self):
        self.rec["pair_check"]["max_abs_pi_diff"] = .1
        self.assertIn("paired_comparison_mismatch", record_errors(self.rec, "2026-10-20T17:33:00Z", "hash"))

    def test_invalid_report_team(self):
        self.rec["unknown_team_values_in_reports"] = ["UNKNOWN"]
        self.assertIn("unresolved_report_team", record_errors(self.rec, "2026-10-20T17:33:00Z", "hash"))

    def test_workflow_does_not_silently_accept_push_failure(self):
        text = (Path(__file__).resolve().parents[1] / ".github/workflows/nba-props-forward.yml").read_text()
        self.assertIn('return 1 )', text)
        self.assertNotIn('git add -A nba/props_forward || true', text)

    def test_minutes_seconds(self):
        self.assertEqual(minutes_value("12:30"), 12.5)

    def test_conditional_prop_does_not_count_dnp_as_zero(self):
        self.assertEqual(conditional_pmf([.6, .4], .5), [.19999999999999996, .8])

    def test_live_box_not_scored(self):
        with self.assertRaises(ValueError):
            box_players({"header": {"competitions": [{"status": {"type": {"completed": False}}}]}})

    def test_perfect_rps(self):
        self.assertEqual(rps([0, 1, 0], 1, 2), 0)


if __name__ == "__main__":
    unittest.main()
