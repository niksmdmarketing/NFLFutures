import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nhl_model as M  # noqa: E402


class NHLTiebreak(unittest.TestCase):
    def test_2015_16_row_era(self):
        # Regression fixture: 2015-16 Detroit (93 pts, 39 ROW, 41 W) took the last East spot over Boston (93 pts, 38 ROW,
        # 42 W). Before 2019-20 ROW came first; a points/wins/GD order wrongly picked Boston.
        T = pd.DataFrame({"points": [93, 93], "winsInRegulation": [30, 33], "regulationAndOtWins": [39, 38], "wins": [41, 42],
                          "goalDiff": [-10, 8]}, index=["DET", "BOS"])
        c = M.final_comp(T, 2015)
        self.assertGreater(c["DET"], c["BOS"])

    def test_rw_era(self):
        # From 2019-20 regulation wins come first.
        T = pd.DataFrame({"points": [90, 90], "winsInRegulation": [35, 33], "regulationAndOtWins": [38, 40], "wins": [40, 41],
                          "goalDiff": [0, 20]}, index=["A", "B"])
        c = M.final_comp(T, 2023)
        self.assertGreater(c["A"], c["B"])


if __name__ == "__main__":
    unittest.main()
