import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import replay_site as R


class Replay(unittest.TestCase):
    def test_nba_and_nhl_data(self):
        for sport, cfg in R.SPORTS.items():
            d = R.build_sport(sport, cfg)
            self.assertIsNotNone(d)
            json.dumps(d)
            for s in d["seasons"]:
                for k, rows in s["p"].items():
                    self.assertEqual(len(rows), len(s["weeks"]))
                    self.assertTrue(all(len(r) == len(s["teams"]) for r in rows))
                    self.assertTrue(all(0 <= v <= 1000 for r in rows for v in r))
                    # one title / conference winner etc: probabilities in a week sum to the number of winners
                    if k == "title":
                        self.assertAlmostEqual(sum(rows[-1]) / 1000, 1.0, delta=0.05)
                    self.assertEqual(len(s["o"][k]), len(s["teams"]))
            self.assertEqual(d["seasons"][0]["label"][:4], str(d["seasons"][0]["y"] - (1 if cfg.get("end_year") else 0)))

    def test_season_labels(self):
        self.assertEqual(R.season_label(2026, True), "2025-26")
        self.assertEqual(R.season_label(2025, False), "2025-26")


if __name__ == "__main__":
    unittest.main()


class Live(unittest.TestCase):
    def test_archive_dedupe_and_live_season(self):
        import datetime as dt, tempfile
        import sport_archive as A
        d = tempfile.mkdtemp()
        site = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")
        if not os.path.exists(os.path.join(site, "nba", "data", "futures.json")):
            self.skipTest("site not built")
        t = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)
        self.assertTrue(A.archive_one("nba", d, site, t).startswith("wrote"))
        self.assertEqual(A.archive_one("nba", d, site, t + dt.timedelta(hours=2)), "unchanged")
        L = R.live_season("nba", R.SPORTS["nba"], d)
        self.assertTrue(L["live"] and L["label"].endswith("(live)"))
        self.assertEqual(len(L["p"]["title"]), len(L["weeks"]))
        self.assertIsNone(R.live_season("nba", R.SPORTS["nba"], os.path.join(d, "missing")))
