"""research/NHL_PO_SCALE_RULE.md: po_gap_only scales only the deterministic gap. Off by default (live unchanged)."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nhl_model as M  # noqa: E402


def run(tau, gap_only, po_scale=4.0, seed=11):
    teams = sorted(M.ALIGN)
    rng = np.random.default_rng(5)
    ratings = {t: float(rng.normal(0, 0.3)) for t in teams}
    state = pd.DataFrame({"points": 0.0, "rw": 0.0, "row": 0.0, "gd": 0.0}, index=teams)
    games = [(teams[i], teams[(i + 7) % len(teams)]) for i in range(len(teams))] * 40
    return M.simulate(teams, state, games, ratings, tau, 5.9, 0.15, 300, seed=seed, po_scale=po_scale, po_gap_only=gap_only)


class PoGapOnly(unittest.TestCase):
    def test_agree_when_no_noise(self):
        a, b = run(0.0, False), run(0.0, True)
        np.testing.assert_allclose(a["cup"], b["cup"])

    def test_diverge_with_noise(self):
        a, b = run(0.5, False), run(0.5, True)
        self.assertGreater(float(np.abs(a["cup"] - b["cup"]).max()), 0.0)

    def test_default_is_live(self):
        teams = sorted(M.ALIGN)
        self.assertFalse(M.simulate.__defaults__ is None)
        a = run(0.3, False)
        c = run(0.3, False)
        np.testing.assert_allclose(a["cup"], c["cup"])


if __name__ == "__main__":
    unittest.main()
