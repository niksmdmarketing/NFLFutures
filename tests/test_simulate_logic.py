"""Simulator options added 26 Oct 2026: playoff format and neutral-site home edge (synthetic schedule, no downloads)."""
import sys
import unittest
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import simulate  # noqa: E402
from common import TEAMS  # noqa: E402


def schedule(neutral=False):
    rng = np.random.default_rng(1)
    pairs = list(combinations(TEAMS, 2))
    idx = rng.choice(len(pairs), 272, replace=False)
    rows = [dict(game_id=f"g{i}", week=1 + i // 16, gameday="2026-09-10", home_team=pairs[k][0], away_team=pairs[k][1],
                 result=np.nan, location="Neutral" if neutral else "Home") for i, k in enumerate(idx)]
    return pd.DataFrame(rows)


class SimulateLogic(unittest.TestCase):
    def test_six_seed_format_counts(self):
        r = simulate.simulate(schedule(), np.zeros(len(TEAMS)), 200, 1., 13., 1.8, n_seeds=6)
        self.assertAlmostEqual(r["playoff"].sum(), 12.0)
        self.assertAlmostEqual(r["conf"].sum(), 2.0)
        self.assertAlmostEqual(r["seed_dist"][:, 6].sum(), 0.0)

    def test_default_is_seven_seeds(self):
        r = simulate.simulate(schedule(), np.zeros(len(TEAMS)), 200, 1., 13., 1.8)
        self.assertAlmostEqual(r["playoff"].sum(), 14.0)

    def test_neutral_games_have_no_home_edge(self):
        a = simulate.simulate(schedule(neutral=True), np.zeros(len(TEAMS)), 300, 0., 13., 30.)
        b = simulate.simulate(schedule(neutral=True), np.zeros(len(TEAMS)), 300, 0., 13., 0.)
        self.assertTrue(np.array_equal(a["wins"], b["wins"]))


if __name__ == "__main__":
    unittest.main()


class MarginAdj(unittest.TestCase):
    """Research-only per-game margin shift (research/NFL_QB_ORACLE_RULE.md, 27 Oct 2026)."""

    def test_zero_column_changes_nothing(self):
        s = schedule()
        a = simulate.simulate(s, np.zeros(len(TEAMS)), 200, 1., 13., 1.8, seed=3)
        b = simulate.simulate(s.assign(margin_adj=0.0), np.zeros(len(TEAMS)), 200, 1., 13., 1.8, seed=3)
        self.assertTrue(np.array_equal(a["wins"], b["wins"]))

    def test_shift_equals_home_edge(self):
        s = schedule()
        a = simulate.simulate(s.assign(margin_adj=5.0), np.zeros(len(TEAMS)), 200, 1., 13., 1.8, seed=3)
        b = simulate.simulate(s, np.zeros(len(TEAMS)), 200, 1., 13., 6.8, seed=3)
        self.assertTrue(np.allclose(a["wins"], b["wins"]))
