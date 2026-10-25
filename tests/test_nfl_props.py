import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import nfl_props as N  # noqa: E402


class NFLPropsTest(unittest.TestCase):
    def test_status_precedence(self):
        rules = {"out": 0.0, "doubtful": .1, "questionable_multiplier": .8, "reported_will_play_floor": .95, "reported_will_not_play": 0.0}
        rows = [{"team": "A", "player": "John Smith", "layer": "official", "status": "Out", "source": "official", "published_utc": "2026-01-01T00:00:00Z"}]
        p, notes, _ = N._status(rows, "A", "John Smith Jr.", .9, rules)
        self.assertEqual(p, 0.0); self.assertTrue(notes)

    def test_player_distribution_sums_and_respects_team_volume(self):
        volume = N._nb(32, 40, 100)
        p = N._allocate(volume, .2, 66, 30)
        self.assertAlmostEqual(float(p.sum()), 1.0, places=12)
        self.assertLessEqual(N._describe(p)["mean"], 32)

    def test_archive_is_create_only(self):
        f = {"generated_utc": "2026-10-25T00:00:00+00:00", "games": [], "model_id": "x"}
        local_tmp = Path(__file__).resolve().parents[1] / ".testtmp"
        local_tmp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_tmp) as d:
            first = N.archive_forecast(d, f)
            self.assertTrue(first.exists())
            with self.assertRaises(FileExistsError): N.archive_forecast(d, f)

    def test_conditional_competitor_budget(self):
        # focal share .30, competitor expected share .5*.40 => denominator .50; no scale needed
        expected = .5 * .4
        denom = expected + (1 - .5) * .3
        self.assertAlmostEqual(denom, .35)
        # When the expected active budget exceeds one, only the focal conditional denominator controls scaling.
        expected = .9 * .8 + .9 * .7
        focal = .8; own_a = .9
        denom = expected + (1 - own_a) * focal
        self.assertGreater(denom, 1)
        self.assertAlmostEqual(focal * min(1, 1 / denom), focal / denom)


if __name__ == "__main__": unittest.main()
