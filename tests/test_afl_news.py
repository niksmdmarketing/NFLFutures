"""AFL news shadow tests (DeepSeek relay 032, adapted by Claude). No Wheelo data needed."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import afl_site as A

C = {"sd_rating": 0.5, "teams": {
    "CAR": {"lineup": ["aone", "btwo"], "c": {"aone": 2.0, "btwo": 1.0, "cthree": 0.5}},
    "HAW": {"lineup": ["xy"], "c": {"xy": 1.5, "zz": 2.0}}}}
REM, RND = [("CAR", "HAW")], [5]


def test_null():
    assert A.news_adjustments(REM, RND, C, [], now_round=5) is None
    assert A.news_adjustments(REM, RND, C, [{"player_key": "nobody"}], now_round=5) is None


def test_home_starter_out_capped():
    out = A.news_adjustments(REM, RND, C, [{"team": None, "player_key": "aone", "return_low": "R6", "return_high": "R6",
                                             "return_text_class": "weeks"}], now_round=5)
    assert abs(out[0] + 0.25) < 1e-12          # cost 2.0 - replacement 0.5 = 1.5, capped at 0.5 x 0.5


def test_away_return_lowers_home_margin():
    out = A.news_adjustments(REM, RND, C, [{"team": "HAW", "player_key": "zz", "return_low": "R5", "return_high": "R5",
                                             "return_text_class": "weeks"}], now_round=5)
    assert out[0] < 0                          # away team gets a player back


def test_simulate_null_identical():
    teams = sorted(A.NAMES)
    r = {t: float(i) for i, t in enumerate(teams)}
    rem = [(teams[i], teams[(i + 1) % len(teams)]) for i in range(len(teams))]
    a = A.simulate(teams, {}, rem, r, 5.0, n=2000)
    b = A.simulate(teams, {}, rem, r, 5.0, n=2000, game_adj=None)
    c = A.simulate(teams, {}, rem, r, 5.0, n=2000, game_adj=np.zeros(len(rem)))
    assert all(np.allclose(a[t]["w_mean"], c[t]["w_mean"]) for t in teams)
    assert all(np.allclose(a[t]["w_mean"], b[t]["w_mean"]) for t in teams)
