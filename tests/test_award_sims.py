import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import numpy as np
import race_sim


class RaceSim(unittest.TestCase):
    def test_probabilities_sum_to_one_and_leader_favoured(self):
        p, proj = race_sim.simulate_race([30, 28, 20], [15, 15, 15], [15, 15, 15], [8, 8, 8], [2.0, 1.8, 1.2], 4, 8, sims=4000)
        self.assertAlmostEqual(float(p.sum()), 1.0, places=6)
        self.assertGreater(p[0], p[1])
        self.assertGreater(p[1], p[2])
        self.assertTrue(np.all(proj >= np.array([30, 28, 20])))

    def test_finished_race_is_certain_and_ties_split(self):
        p, _ = race_sim.simulate_race([10, 10, 9], [20, 20, 20], [20, 20, 20], [0, 0, 0], [0.5, 0.5, 0.5], 4, 8, sims=1000)
        self.assertAlmostEqual(p[0], 0.5)
        self.assertAlmostEqual(p[1], 0.5)
        self.assertEqual(p[2], 0.0)


@unittest.skipUnless(os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nba", "player_box_2026.csv")),
                     "NBA box scores not cached")
class NbaAwardSim(unittest.TestCase):
    def test_preseason_and_in_season_probabilities(self):
        import nba_award_sim as S
        beta = np.array([1.0, .5, .5, .8, .3, .3])
        feats = ["eff_g", "ppg", "pm_g", "wp", "gshare", "ts"]
        prev = S.season_lines(S.boxes(2026))
        p = S.preseason_probs(prev, "MVP", feats, beta, 82, 2027)
        self.assertAlmostEqual(sum(p.values()), 1.0, places=3)
        self.assertEqual(S.preseason_probs(prev, "ROY", feats, beta, 82, 2027), {})


if __name__ == "__main__":
    unittest.main()
