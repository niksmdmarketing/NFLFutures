import os, sys, unittest
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nhl_model as M


class Backtest(unittest.TestCase):
    def test_checkpoint_is_a_date_not_per_team_count(self):
        src = open(M.__file__).read()
        self.assertIn("g.date < cut", src)
        self.assertNotIn("g.n <= N", src.split("def backtest")[1].split("# ----")[0])

    def test_dated_partition_covers_every_game_once(self):
        d = pd.to_datetime(["2024-10-01", "2024-10-03", "2024-10-05", "2024-10-07"])
        g = pd.DataFrame({"date": list(d) * 2, "team": ["A"] * 4 + ["B"] * 4})
        cut = d[2]
        self.assertEqual(len(g[g.date < cut]) + len(g[g.date >= cut]), len(g))


if __name__ == "__main__":
    unittest.main()
