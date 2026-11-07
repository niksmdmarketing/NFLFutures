"""Amendment 14 (7 Nov 2026): placebo CLV, missing-close coverage, cluster diagnostics. Synthetic rows only; no price data."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research"))
import nba_props_price_test as PT  # noqa: E402


def rows(n=600, seed=3, missing=0.0, informed=True):
    rng = np.random.default_rng(seed)
    true = 1 / (1 + np.exp(-rng.normal(0, 0.6, n)))
    mkt = 1 / (1 + np.exp(-(np.log(true / (1 - true)) + rng.normal(0, 0.35, n))))
    mdl = 1 / (1 + np.exp(-(np.log(true / (1 - true)) + rng.normal(0, 0.35, n)))) if informed else rng.uniform(0.2, 0.8, n)
    close = 1 / (1 + np.exp(-(0.5 * np.log(mkt / (1 - mkt)) + 0.5 * np.log(true / (1 - true)))))
    close = np.where(rng.random(n) < missing, np.nan, close)
    vig = 1.045
    return pd.DataFrame(dict(over=(rng.random(n) < true).astype(int), market_over=mkt, model_over=mdl, close_market_over=close,
                             best_over=1 / (mkt * vig), best_under=1 / ((1 - mkt) * vig), date=rng.integers(0, 60, n).astype(str)))


class Amendment14(unittest.TestCase):
    def test_permutation_null_is_exceeded_by_informed_model_only(self):
        inf = PT.placebo_arms(rows(3000), n_perm=200)
        non = PT.placebo_arms(rows(3000, informed=False), n_perm=200)
        self.assertTrue(inf["exceeds_null_p95"])
        self.assertFalse(non["exceeds_null_p95"])
        self.assertLess(inf["perm_null_mean"], inf["observed_clv"])

    def test_arms_use_same_rows_and_shopping_is_unselected(self):
        a = PT.placebo_arms(rows(2000), n_perm=50)
        self.assertGreater(a["n_bets"], 0)
        self.assertIsNotNone(a["random_side_mean"])
        self.assertIsNotNone(a["shopping_all_rows_mean"])

    def test_trigger_counts_need_no_outcome(self):
        R = rows(3000).drop(columns=["over"])
        c = PT.trigger_counts(R)
        self.assertGreater(c["bets"], 0)
        self.assertGreater(c["dates"], 0)

    def test_no_skill_model_does_not_beat_the_vig_floor(self):
        s = PT.clv_summary(PT.bets(rows(4000, informed=False), 0.03))
        self.assertLess(s["clv_mean"], 0.01)

    def test_missing_close_share_flags_coverage(self):
        ok = PT.clv_summary(PT.bets(rows(4000, missing=0.10), 0.05))
        bad = PT.clv_summary(PT.bets(rows(4000, missing=0.60), 0.05))
        self.assertTrue(ok["close_coverage_ok"])
        self.assertFalse(bad["close_coverage_ok"])
        self.assertAlmostEqual(bad["missing_close_share"], 0.6, delta=0.06)

    def test_diagnostics_present(self):
        s = PT.clv_summary(PT.bets(rows(4000), 0.05))
        for k in ("bets_per_date", "date_icc", "fewer_than_40_dates", "roi_with_close"):
            self.assertIn(k, s)
        self.assertEqual(PT.BOOT, 10000)


class Amendment15Looks(unittest.TestCase):
    def test_look_refused_before_trigger_and_after_first_look(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research"))
        import nba_props_price_run as R
        R._TRIG.clear()
        self.assertFalse(R._look_allowed("pts", "b", {}))
        R._TRIG["pts|b"] = {"reached": True}
        self.assertTrue(R._look_allowed("pts", "b", {}))
        self.assertFalse(R._look_allowed("pts", "b", {"pts|b": {}}))
        R._TRIG.clear()


if __name__ == "__main__":
    unittest.main()
