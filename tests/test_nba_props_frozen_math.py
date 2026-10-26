"""Numerical invariants, NOT a new historical performance test."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import nba_props_live_core as C
import nba_props_live as L
import nba_props_simple_test as P
import nba_props_forward_timing as T
from unittest.mock import patch


class FrozenMathTests(unittest.TestCase):
    def test_minutes_pair_on_frozen_parameters(self):
        p = json.loads((ROOT / "model/nba_props_live_params_2027b.json").read_text())["m2"]
        n = 20
        z = pd.DataFrame(dict(mu1=np.linspace(2, 46, n), ewm=np.linspace(2, 40, n),
                              season_mpg=np.linspace(2, 40, n), vac_same1=0., vac_other1=0.,
                              st1=["", "Questionable", "Out", "Available"] * 5,
                              absm=5., b2b=0., s_sum=1., s_cnt=10., early=0., streak=0., start10=.5))
        q2, pi2 = C.q_m2(z, p, False)
        q3, pi3 = C.q_m2(z, p, True)
        np.testing.assert_allclose(q2.sum(axis=1), 1, atol=1e-12)
        np.testing.assert_allclose(q3.sum(axis=1), 1, atol=1e-12)
        np.testing.assert_array_equal(pi2, pi3)
        below = np.arange(1, 54)[None, :] < .6 * z.mu1.to_numpy()[:, None]
        np.testing.assert_allclose(q2[below], q3[below], atol=1e-14)
        self.assertTrue(np.isfinite(q3).all())
        self.assertTrue((q3 >= 0).all())

    def test_prop_mixtures_include_tail(self):
        q = np.zeros((3, 53))
        q[:, 19] = 1
        for rate, limit in ((.1, 35), (.25, 45), (1., 100)):
            p = P.mixture_pmf(np.full(3, rate), q, 8., limit)
            np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-12)
            means = p @ np.arange(limit + 1)
            np.testing.assert_allclose(means, 20 * rate, atol=.01)

    def test_immutable_input_detects_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = L.store_input(tmp, "test", b"original", "bin")
            file = Path(tmp) / "nba/props_forward/inputs" / (h + ".bin")
            file.write_bytes(b"corrupted")
            with self.assertRaises(ValueError):
                L.store_input(tmp, "test", b"original", "bin")

    def test_receipt_pagination(self):
        """Activity receipts follow the cursor in Link rel="next" (the page parameter is ignored by GitHub; 22 Oct fault)."""
        calls = []
        def fake_get(url):
            calls.append(url)
            if "/actions/" in url:
                return {"workflow_runs": []}, None
            if "cursor=abc" not in url:
                return ([dict(timestamp="2026-10-20T17:00:00Z", after=str(i)) for i in range(100)],
                        "https://api.github.com/repositories/1/activity?per_page=100&cursor=abc")
            return [], None
        with tempfile.TemporaryDirectory() as tmp, patch.object(T, "_get", fake_get):
            T.main(tmp)
        follow = [u for u in calls if "cursor=abc" in u]
        self.assertTrue(follow and follow[0].startswith(f"https://api.github.com/repos/{T.REPO}/activity?"))

if __name__ == "__main__":
    unittest.main()
