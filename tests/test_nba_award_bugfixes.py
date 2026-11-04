import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipeline'))
import nba_award_sim as sim


class AwardBugfixes(unittest.TestCase):
    def test_first_three_nba_games_retained_even_with_large_exhibition_sample(self):
        rows = []
        for team, count in [('NYK', 3), ('EXHIBITION', 45)]:
            for i in range(count):
                row = {'season_type': 2, 'game_id': f'{team}-{i}', 'minutes': 25,
                       'team_abbreviation': team, 'starter': True, 'team_winner': True,
                       'game_date': '2026-10-25', 'athlete_id': 123, 'athlete_display_name': 'Example'}
                row.update({k: 1 for k in ['points', 'rebounds', 'defensive_rebounds', 'assists',
                    'steals', 'blocks', 'turnovers', 'plus_minus', 'field_goals_attempted', 'free_throws_attempted']})
                rows.append(row)
        with tempfile.TemporaryDirectory() as tmp:
            pd.DataFrame(rows).to_csv(Path(tmp) / 'player_box_2027.csv', index=False)
            with patch.object(sim, 'DATA', tmp):
                data = sim.boxes(2027)
        self.assertEqual(len(data), 3)
        self.assertEqual(set(data.team), {'NY'})

    def candidates(self):
        data = pd.DataFrame({k: [60., 60.] for k in sim.STATS}, index=[1, 2])
        data['gp'], data['tg'], data['tw'] = 60., 82., 41.
        data['start'] = 0.
        data['mins'] = 1800.
        data['name'] = ['Candidate One', 'Candidate Two']
        data['team'] = 'NY'
        data['rookie'], data['bench'], data['wp'] = True, True, .5
        data = data.assign(**sim.features(data, 82.))
        return data

    def probs(self, award, year):
        data = self.candidates()
        with patch.object(sim, 'SIMS', 2), patch.object(sim, 'RULE65', True):
            return sim.simulate(data, data, data, award, sim.SPECS[award][3],
                                np.zeros(len(sim.SPECS[award][3])), 82., year,
                                np.random.default_rng(7))

    def test_roy_and_sixth_man_candidates_under_65_games_remain_eligible(self):
        for award in ('ROY', '6MOY'):
            p = self.probs(award, 2024)
            self.assertAlmostEqual(sum(p.values()), 1.)
            self.assertTrue(all(v > 0 for v in p.values()))

    def test_mvp_dpoy_rule_still_applies_and_pre_2024_unchanged(self):
        for award in ('MVP', 'DPOY'):
            self.assertEqual(sum(self.probs(award, 2024).values()), 0.)
            self.assertAlmostEqual(sum(self.probs(award, 2023).values()), 1.)
