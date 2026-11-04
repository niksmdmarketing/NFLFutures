import datetime as dt
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nfl_qb_shadow as Q

TODAY = dt.date.today()
DAYS = [TODAY + dt.timedelta(days=7 * k + 3) for k in range(8)]   # eight remaining games, weekly
RUNS = pd.DataFrame({"L": [1, 1, 2, 3, 5, 8]})


def ep(kind, date=None, m=0, res=False):
    return dict(kind=kind, date=date, m=m, res=res)


class Draws(unittest.TestCase):
    def test_season_ending_misses_everything(self):
        miss = Q.draw_missed(ep("season"), DAYS, 500, np.random.default_rng(1), RUNS)
        self.assertTrue((miss == 8).all())

    def test_date_centres_on_games_before_return(self):
        # return in 17 days: games on day 3 and 10 are before it, day 17 onwards after
        miss = Q.draw_missed(ep("date", TODAY + dt.timedelta(days=17)), DAYS, 4000, np.random.default_rng(1), RUNS)
        self.assertEqual(int(np.median(miss)), 2)
        self.assertTrue((miss >= 0).all() and (miss <= 8).all())

    def test_no_date_conditions_on_games_already_missed_and_ir(self):
        miss = Q.draw_missed(ep("nodate", m=2), DAYS, 2000, np.random.default_rng(1), RUNS)
        self.assertEqual(set(np.unique(miss)), {1, 3, 6})          # runs 3, 5, 8 minus 2 already missed
        miss = Q.draw_missed(ep("nodate", m=0, res=True), DAYS, 2000, np.random.default_rng(1), RUNS)
        self.assertTrue((miss >= 5).all())                          # IR: only runs of 4+ games (5 and 8)

    def test_no_qualifying_run_means_rest_of_season(self):
        miss = Q.draw_missed(ep("nodate", m=9), DAYS, 10, np.random.default_rng(1), RUNS)
        self.assertTrue((miss == 8).all())


class Feed(unittest.TestCase):
    def test_parser_keeps_no_unknown_team_and_reads_fields(self):
        j = {"injuries": [{"displayName": "Buffalo Bills", "injuries": [{
            "athlete": {"displayName": "Josh Allen", "position": {"abbreviation": "QB"}}, "status": "Out",
            "details": {"returnDate": "2026-12-01", "type": "Ankle"}}]}]}
        r = Q.espn_rows(j)[0]
        self.assertEqual((r["team"], r["pos"], r["status"], r["return_date"]), ("BUF", "QB", "Out", "2026-12-01"))

    def test_status_and_text_patterns(self):
        self.assertTrue(Q.OUT_STATUS.search("Injured Reserve"))
        self.assertFalse(Q.OUT_STATUS.search("Questionable"))
        self.assertTrue(Q.SEASON_TXT.search("Will miss the rest of the season"))
        self.assertTrue(Q.LONG_TXT.search("Knee - ACL"))
        self.assertEqual(Q.norm("Michael Penix Jr."), "michael penix")


if __name__ == "__main__":
    unittest.main()
