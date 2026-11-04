import datetime as dt
import os
import sys
import unittest
from unittest.mock import patch

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



class Review(unittest.TestCase):
    def test_exact_name_match_suffix_initials_accents_and_team(self):
        known = {}
        Q.register_name(known, "HOU", "C.J. Stroud", "00-001")
        Q.register_name(known, "ATL", "Michael Penix Jr.", "00-002")
        Q.register_name(known, "BUF", "Jos\u00e9 Allen", "00-003")
        self.assertEqual(Q.resolve_name(known, "HOU", "C. J. Stroud"), "00-001")
        self.assertEqual(Q.resolve_name(known, "ATL", "Michael Penix"), "00-002")
        self.assertEqual(Q.resolve_name(known, "BUF", "Jose Allen"), "00-003")
        self.assertIsNone(Q.resolve_name(known, "NYJ", "C.J. Stroud"))

    def test_ambiguous_and_invalid_ids_never_choose_last_row(self):
        known = {}
        Q.register_name(known, "BUF", "Josh Allen", "00-001")
        Q.register_name(known, "BUF", "Josh Allen Jr", "00-002")
        Q.register_name(known, "BUF", "Bad Id", np.nan)
        Q.register_name(known, "BUF", "Bad Id", "nan")
        self.assertIsNone(Q.resolve_name(known, "BUF", "Josh Allen"))
        self.assertIsNone(Q.resolve_name(known, "BUF", "Bad Id"))

    def test_missed_games_condition_ignores_bye_and_resets_on_return(self):
        rows = []
        for week, qb in [(1, "a"), (2, "b"), (4, "b")]:
            rows.append(dict(posteam="BUF", week=week, game_id=str(week),
                             qb_dropback=1, passer_player_id=qb, rusher_player_id=np.nan))
        pbp = pd.DataFrame(rows)
        with patch.object(Q, "scrimmage", side_effect=lambda x: x):
            self.assertEqual(Q.missed_so_far(pbp, {"BUF": "a"})["BUF"], 2)
            pbp.loc[len(pbp)] = ["BUF", 5, "5", 1, "a", np.nan]
            self.assertEqual(Q.missed_so_far(pbp, {"BUF": "a"})["BUF"], 0)

    def test_no_episode_returns_exact_live_vector_without_reading_runs(self):
        import ratings
        R = pd.DataFrame({"rating": np.linspace(-4.123456789, 3.876543211, Q.NT)}, index=Q.TEAMS)
        with patch.object(ratings, "qb_values", return_value=({}, 0, {})), \
             patch.object(Q, "fetch_espn", return_value=([], True)), \
             patch.object(Q, "reference", return_value={}), \
             patch.object(Q, "episodes", return_value=[]), \
             patch.object(Q.pd, "read_csv", side_effect=AssertionError("no run table needed")):
            r, adj, eps, ok = Q.build(2026, pd.DataFrame(), None, None, None, R, None, 10)
        np.testing.assert_array_equal(r, R.rating.to_numpy())
        self.assertIsNone(adj)
        self.assertEqual(eps, [])
        self.assertTrue(ok)

    def test_episode_matching_numeric_depth_rank_and_team(self):
        depth = pd.DataFrame([
            dict(team="BUF", pos_abb="QB", dt="2026-11-04", pos_rank="1", player_name="Josh Allen", gsis_id="00-001"),
            dict(team="BUF", pos_abb="QB", dt="2026-11-04", pos_rank="10", player_name="Third QB", gsis_id="00-003"),
            dict(team="BUF", pos_abb="QB", dt="2026-11-04", pos_rank="2", player_name="Backup QB", gsis_id="00-002")])
        rows = [dict(team="BUF", name="Josh Allen Jr.", pos="QB", status="Out", return_date=None, text="ankle")]
        with patch.object(Q, "download", return_value="fixture.csv"), \
             patch.object(Q.pd, "read_csv", return_value=depth), \
             patch.object(Q, "missed_so_far", return_value={"BUF": 2}):
            eps = Q.episodes(2026, None, {"BUF": "00-001"}, None, rows)
            self.assertEqual(len(eps), 1)
            self.assertEqual((eps[0]["ref"], eps[0]["repl"], eps[0]["m"]), ("00-001", "00-002", 2))
            rows[0]["team"] = "NYJ"
            self.assertEqual(Q.episodes(2026, None, {"BUF": "00-001"}, None, rows), [])

    def test_no_future_regular_game_keeps_live_adjustment(self):
        import ratings
        R = pd.DataFrame({"rating": np.arange(Q.NT, dtype=float), "base": np.arange(Q.NT),
                          "qb_adj": 2.0, "press_adj": 0.0}, index=Q.TEAMS)
        g = pd.DataFrame([dict(week=18, gameday=str(TODAY), game_id="x", home_team="BUF", away_team="NYJ", result=7)])
        episode = dict(team="BUF", ref="a", repl="b", kind="season", m=0, res=False)
        with patch.object(ratings, "qb_values", return_value=({}, 0, {})), \
             patch.object(Q, "fetch_espn", return_value=([], True)), \
             patch.object(Q, "reference", return_value={}), \
             patch.object(Q, "episodes", return_value=[episode]), \
             patch.object(Q.pd, "read_csv", return_value=RUNS):
            r, adj, eps, _ = Q.build(2026, g, None, None, None, R, None, 10)
        np.testing.assert_array_equal(r, R.rating.to_numpy())
        self.assertIsNone(adj)
        self.assertEqual(eps, [])


if __name__ == "__main__":
    unittest.main()
