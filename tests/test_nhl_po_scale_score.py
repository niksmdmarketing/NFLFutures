import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research"))
import nhl_po_scale_score as S  # noqa: E402


class Score(unittest.TestCase):
    def test_slope_recovers_known_value(self):
        rng = np.random.default_rng(1)
        z = rng.normal(-1.5, 1.2, 20000)
        p = 1 / (1 + np.exp(-z))
        y = rng.random(20000) < 1 / (1 + np.exp(-(0.1 + 1.6 * z)))
        self.assertAlmostEqual(S.slope(p, y), 1.6, delta=0.12)

    def test_live_equivalence_z_not_fooled_by_noise(self):
        rng = np.random.default_rng(2)
        fails = 0
        for _ in range(300):
            p = rng.uniform(0.05, 0.9, 32)
            a = rng.binomial(2000, p) / 2000
            b = rng.binomial(2000, p) / 2000
            fails += not S.live_equivalent(a, b, 2000, 2000)[0]
        self.assertLessEqual(fails, 6)           # about 0.7% expected false fails
        self.assertFalse(S.live_equivalent(np.full(32, 0.30), np.full(32, 0.40), 2000, 2000)[0])

    def test_decision_outcomes(self):
        ok = {"movement_toward_1": {"preseason": {"point": 0.3, "lo90": -0.1}, "first_quarter": {"point": 0.0, "lo90": -0.2}},
              "combined_ll_gain": {"lo90": -0.0001}, "market_ll_gain": {"title": 0.0}}
        self.assertEqual(S.decide(ok)[0], "insufficient")
        ok["movement_toward_1"]["preseason"]["lo90"] = 0.05
        self.assertEqual(S.decide(ok)[0], "pass")
        ok["movement_toward_1"]["preseason"]["point"] = -0.1
        self.assertEqual(S.decide(ok)[0], "fail")


if __name__ == "__main__":
    unittest.main()
