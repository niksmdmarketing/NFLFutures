import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import live_check as L


def snap(day, ps):
    return {"generated_utc": f"2026-01-{day:02d}T00:00", "teams": ["A", "B", "C"], "live": {"playoff": ps}}


class LiveCheck(unittest.TestCase):
    def test_not_scored_before_half_season(self):
        r = L.settled_scores([snap(1, [0.5, 0.5, 0.0]), snap(2, [0.6, 0.4, 0.0])], ["live"], progress=0.3)
        self.assertEqual(r["markets"], {})

    def test_settled_items_scored_on_earlier_snapshots_only(self):
        s = [snap(1, [0.9, 0.5, 0.1]), snap(2, [0.95, 0.5, 0.05]), snap(3, [1.0, 0.6, 0.0])]
        r = L.settled_scores(s, ["live"], progress=0.8)["markets"]["playoff"]
        self.assertEqual(r["settled"], 2)          # A clinched, C eliminated, B open
        self.assertEqual(r["yes"], 1)
        self.assertEqual(r["by_model"]["live"]["n"], 4)   # 2 items x 2 earlier snapshots
        self.assertLess(r["by_model"]["live"]["logloss"], r["by_model"]["live"]["flat"])


if __name__ == "__main__":
    unittest.main()


class LiveGames(unittest.TestCase):
    def test_games_scored_from_latest_snapshot_before_the_day(self):
        orig = L._results
        L._results = lambda sport, season: {("2026-10-15", "A", "B"): 1, ("2026-10-16", "C", "D"): 0}
        try:
            snaps = [{"generated_utc": "2026-10-14T00:00", "games": [["2026-10-15", "A", "B", 700], ["2026-10-16", "C", "D", 600]]},
                     {"generated_utc": "2026-10-15T05:00", "games": [["2026-10-15", "A", "B", 100], ["2026-10-16", "C", "D", 400]]}]
            r = L.sport_games("nhl", 2026, snaps)
        finally:
            L._results = orig
        self.assertEqual(r["games"], 2)
        self.assertEqual(r["live"]["correct"], 1.0)   # A-B uses 0.70 (same-day snapshot ignored), C-D uses 0.40
