"""tests/test_freshness.py — unittest, no network, no pytest."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import freshness  # noqa: E402


class FreshnessTests(unittest.TestCase):
    NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.site = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, rel, obj):
        p = self.site / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def nba(self, in_progress=True, games=None, last_date="2027-04-12"):
        self.put("nba/data/meta.json", {"season": 2027,
                                        "updated_utc": "2026-11-15T06:00:00Z",
                                        "in_progress": in_progress})
        self.put("nba/data/schedule.json", {"season": 2027, "last_date": last_date,
                                            "teams": games or []})
        self.put("nba/data/games_2027.json",
                 {"rows": [["2026-11-14", "ATL", "ORL"], ["2026-11-14", "ORL", "ATL"]]})

    def sport(self, out, name):
        return next(s for s in out["sports"] if s["sport"] == name)

    def test_current(self):
        self.nba(games=[{"team": "ATL", "games": [["2026-11-16", "MIL"]]}])
        s = self.sport(freshness.build(self.site, now=self.NOW), "NBA")
        self.assertEqual(s["status"], "current")
        self.assertEqual((s["games_awaiting"], s["games_overdue"]), (0, 0))
        self.assertEqual(s["results_through"], "2026-11-14")
        self.assertTrue((self.site / "data" / "freshness.json").exists())

    def test_awaiting_yesterday(self):
        self.nba(games=[{"team": "ATL", "games": [["2026-11-14", "MIL"]]}])
        s = self.sport(freshness.build(self.site, now=self.NOW), "NBA")
        self.assertEqual(s["status"], "current")
        self.assertEqual(s["games_awaiting"], 1)

    def test_behind_counted_once_not_twice(self):
        self.nba(games=[{"team": "ATL", "games": [["2026-11-13", "MIL"]]},
                        {"team": "MIL", "games": [["2026-11-13", "ATL"]]}])
        s = self.sport(freshness.build(self.site, now=self.NOW), "NBA")
        self.assertEqual(s["status"], "behind")
        self.assertEqual(s["games_overdue"], 1)
        self.assertEqual(s["oldest_overdue"], "2026-11-13")

    def test_off_season(self):
        self.nba(in_progress=False, games=[{"team": "ATL", "games": [["2026-11-16", "MIL"]]}])
        self.assertEqual(self.sport(freshness.build(self.site, now=self.NOW), "NBA")["status"],
                         "off-season")

    def test_missing_files_unknown(self):
        out = freshness.build(self.site, now=self.NOW)   # nothing written at all
        s = self.sport(out, "NHL")
        self.assertEqual(s["status"], "unknown")
        self.assertTrue(s["note"])

    def test_bad_json_does_not_raise(self):
        p = self.site / "afl" / "data" / "meta.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.sport(freshness.build(self.site, now=self.NOW), "AFL")["status"],
                         "unknown")

    def test_nfl_week_text(self):
        self.put("data/meta.json", {"season": 2026, "updated_utc": "2026-11-15T05:00:00Z",
                                    "through_week": 9, "next_week": 10, "next_week_played": 1})
        self.put("data/schedule.json", {"season": 2026, "last_date": "2027-01-04",
                                        "teams": [{"team": "ATL", "games": [["2026-11-19", "NO"]]}]})
        s = self.sport(freshness.build(self.site, now=self.NOW), "NFL")
        self.assertEqual(s["results_through"], "week 9 (+1 game of week 10)")
        self.assertEqual(s["status"], "current")

    def test_no_fixture_list_judged_on_last_result(self):   # CFB has no schedule file (supervisor addition)
        self.put("cfb/data/meta.json", {"season": 2026, "in_progress": True})
        self.put("cfb/data/games_2026.json", {"rows": [["2026-11-14", "A", "B"]]})
        s = self.sport(freshness.build(self.site, now=self.NOW), "CFB")
        self.assertEqual(s["status"], "current")
        self.put("cfb/data/games_2026.json", {"rows": [["2026-11-01", "A", "B"]]})
        self.assertEqual(self.sport(freshness.build(self.site, now=self.NOW), "CFB")["status"], "behind")

    def test_notes_say_what_is_waiting_or_late(self):
        self.nba(games=[{"team": "ATL", "games": [["2026-11-14", "MIL"]]}])
        self.assertIn("waiting on the data source", self.sport(freshness.build(self.site, now=self.NOW), "NBA")["note"])
        self.nba(games=[{"team": "ATL", "games": [["2026-11-12", "MIL"]]}])
        self.assertIn("not in the model yet", self.sport(freshness.build(self.site, now=self.NOW), "NBA")["note"])

    def test_html_block_escapes(self):
        out = freshness.build(self.site, now=self.NOW)
        self.assertIn("<table", freshness.html_block(out))
        self.assertIn("&lt;", freshness.html_block(
            {"sports": [{"sport": "A<b", "status": "x", "note": "a & b"}]}))


if __name__ == "__main__":
    unittest.main()
