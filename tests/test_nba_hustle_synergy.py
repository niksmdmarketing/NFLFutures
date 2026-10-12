import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import nba_hustle_synergy as H


class HustleSynergyTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base = {'contested_shots': 4.0, 'deflections': 1.5}
        pd.DataFrame([dict(player_name='A One', team_id=1, team_abbreviation='GSW', **base),
                      dict(player_name='B Two', team_id=2, team_abbreviation='BOS', **base)]).to_parquet(self.dir / 'leaguehustlestatsplayer_regular-season_pergame_2026.parquet')
        pd.DataFrame([dict(team_id=1, team_name='Golden State Warriors', contested_shots=40.0, deflections=15.0)]).to_parquet(
            self.dir / 'leaguehustlestatsteam_regular-season_pergame_2026.parquet')
        rows = [dict(player_name='A One', poss=5.0, ppp=1.1, poss_pct=0.2), dict(player_name='A One', poss=1.0, ppp=0.9, poss_pct=0.05),
                dict(player_name='B Two', poss=2.0, ppp=1.0, poss_pct=0.1)]
        pd.DataFrame(rows).to_parquet(self.dir / 'regular-season_isolation_offensive_pergame_2026.parquet')

    def get(self, tag, name):
        return str(self.dir / name)

    def test_team_codes_follow_site_abbreviations_and_playoffs_absent(self):
        out = H.hustle_frames(self.get, 2026)
        self.assertEqual(set(out), {2})
        team, player = out[2]
        self.assertEqual(list(team.team), ['GS'])
        self.assertEqual(set(player.team), {'GS', 'BOS'})
        self.assertAlmostEqual(float(team.h_deflections.iloc[0]), 15.0)
        self.assertTrue(team.h_charges_drawn.isna().all())          # a missing stat stays missing, never zero

    def test_synergy_keeps_the_row_with_most_possessions_and_leaves_gaps_blank(self):
        wide = H.synergy_frame(self.get, 2026, 'regular-season')
        a = wide[wide.player == 'A One'].iloc[0]
        self.assertEqual(a.syn_o_isolation_poss, 5.0)
        self.assertNotIn('syn_o_cut_ppp', wide.columns)
        self.assertIsNone(H.synergy_frame(self.get, 2026, 'playoffs'))

    def test_provider_copy_season_is_not_shown_and_untracked_zeros_are_blank(self):
        self.assertEqual(H.hustle_frames(self.get, 2016), {})        # 2015-16 file is a copy of 2016-17
        pd.DataFrame([dict(player_name='A One', team_id=1, team_abbreviation='GSW', contested_shots=4.0, box_outs=0.0),
                      dict(player_name='B Two', team_id=2, team_abbreviation='BOS', contested_shots=3.0, box_outs=0.0)]).to_parquet(
            self.dir / 'leaguehustlestatsplayer_regular-season_pergame_2017.parquet')
        pd.DataFrame([dict(team_id=1, team_name='Golden State Warriors', contested_shots=40.0, box_outs=0.0)]).to_parquet(
            self.dir / 'leaguehustlestatsteam_regular-season_pergame_2017.parquet')
        team, player = H.hustle_frames(self.get, 2017)[2]
        self.assertTrue(team.h_box_outs.isna().all() and player.h_box_outs.isna().all())
        self.assertFalse(player.h_contested_shots.isna().any())


if __name__ == '__main__':
    unittest.main()
