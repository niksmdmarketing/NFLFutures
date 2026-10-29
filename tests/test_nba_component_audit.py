import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))


class ComponentAudit(unittest.TestCase):
    def test_roster_observer_does_not_change_ratings(self):
        import numpy as np
        import pandas as pd
        import nba as N
        values = pd.DataFrame(dict(athlete_id=["1", "2"], team_abbreviation=["GS", "LAL"],
                                   minutes=[1500., 1600.], games=[50, 60], gmsc36=[12., 10.], pm36=[3., -1.],
                                   ppg=[15., 12.], rpg=[4., 3.], apg=[3., 2.], impact=[1., -1.]))
        roster = pd.DataFrame(dict(athlete_id=["1", "2"], team_abbreviation=["GS", "LAL"],
                                   display_name=["A", "B"]))
        ratings = pd.DataFrame(dict(team=N.TEAMS, raw_net=np.linspace(-5, 5, 30)))
        with patch.object(N, "OVERRIDES_ON", False):
            expected, erows = N._roster_adjustment(ratings, values, roster.copy(), roster.copy(), games_played=4)
            audit = {}
            actual, arows = N._roster_adjustment(ratings, values, roster.copy(), roster.copy(), games_played=4, audit=audit)
        pd.testing.assert_frame_equal(expected, actual)
        self.assertEqual(erows, arows)
        self.assertEqual(set(audit["after"]), set(N.TEAMS))

    def test_missing_player_feed_is_explicit(self):
        import pandas as pd
        import nba as N
        ratings = pd.DataFrame(dict(team=N.TEAMS, rating=[0.] * 30))
        audit = {}
        with patch.object(N, "_download", return_value=None):
            out = N._player_mix(ratings, pd.DataFrame(), pd.DataFrame(), None, pd.DataFrame(), 2027, 4, audit=audit)
        self.assertEqual(audit["status"], "skipped_no_stints")
        self.assertTrue(out.player_strength.isna().all())
        self.assertTrue((out.rating == ratings.rating).all())

    def test_retired_overrides_are_not_loaded(self):
        import nba as N
        with patch.object(N, "OVERRIDES_ON", True):
            active = N._overrides()
        contents = json.loads((ROOT / "model/nba_overrides.json").read_text())
        for aid in ("4291678", "4610139", "4065670"):
            self.assertNotIn(aid, active)
            self.assertIn(aid, contents["retired_minutes"])
            self.assertTrue(contents["retired_minutes"][aid]["source_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
