import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import nhl_model as M  # noqa: E402


def _toy(n=32):
    teams = sorted(M.ALIGN)[:n] if len(M.ALIGN) >= n else sorted(M.ALIGN)
    teams = sorted(M.ALIGN)
    rng = np.random.default_rng(5)
    ratings = {t: float(rng.normal(0, 0.25)) for t in teams}
    state = pd.DataFrame({"points": 0.0, "rw": 0.0, "row": 0.0, "gd": 0.0}, index=teams)
    games = [(a, b) for a in teams[:8] for b in teams[8:16]]
    return teams, state, games, ratings


class SeriesQ(unittest.TestCase):
    def test_analytic_matches_sampled_best_of_seven(self):
        rng = np.random.default_rng(1)
        for gap, hfa in ((0.0, 0.1), (0.4, 0.1), (-0.3, 0.15)):
            q = M.series_win_prob(np.array([gap]), hfa)[0]
            ph, pa = M.ndtr((gap + hfa) / M.GAME_SD), M.ndtr((gap - hfa) / M.GAME_SD)
            wins = np.zeros(400000, int)
            for g in range(7):
                wins += rng.random(400000) < (ph if g in (0, 1, 4, 6) else pa)
            self.assertAlmostEqual(q, float((wins >= 4).mean()), delta=0.004)

    def test_logging_leaves_every_other_output_unchanged(self):
        teams, state, games, ratings = _toy()
        kw = dict(teams=teams, state=state, games=games, ratings=ratings, tau=0.2, total=6.0, hfa=0.1, n_sims=600, seed=3, po_scale=2.5)
        a = M.simulate(**kw)
        b = M.simulate(**kw, series_pairs=[(teams[0], teams[1]), (teams[5], teams[20])])
        self.assertNotIn("series_q", a)
        self.assertEqual(set(b) - set(a), {"series_q"})
        for k in a:
            np.testing.assert_array_equal(a[k], b[k])

    def test_gap_only_equals_live_at_scale_one_and_differs_when_stretched(self):
        teams, state, games, ratings = _toy()
        pairs = [(teams[0], teams[1])]
        base = dict(teams=teams, state=state, games=games, ratings=ratings, tau=0.3, total=6.0, hfa=0.1, n_sims=400, seed=3, series_pairs=pairs)
        for scale, same in ((1.0, True), (4.0, False)):
            live = M.simulate(**base, po_scale=scale)["series_q"][0]
            gap = M.simulate(**base, po_scale=scale, po_gap_only=True)["series_q"][0]
            self.assertEqual(abs(live - gap) < 1e-12, same)

    def test_better_home_team_has_higher_q(self):
        teams, state, games, ratings = _toy()
        ratings[teams[0]], ratings[teams[1]] = 0.5, -0.5
        r = M.simulate(teams, state, games, ratings, 0.1, 6.0, 0.1, 300, seed=3, series_pairs=[(teams[0], teams[1]), (teams[1], teams[0])])
        self.assertGreater(r["series_q"][0], 0.75)
        self.assertLess(r["series_q"][1], 0.3)


if __name__ == "__main__":
    unittest.main()
