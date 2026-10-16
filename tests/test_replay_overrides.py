import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "research"))


class ReplayOverrides(unittest.TestCase):
    def test_historical_replay_cannot_load_owner_overrides(self):
        """The owner's overrides are this season's judgement calls; a historical replay must never apply them."""
        try:
            import nba as N
            import replay_nba  # noqa: F401  (importing it switches overrides off)
        except ImportError:
            self.skipTest("numpy/pandas not installed")
        self.assertFalse(N.OVERRIDES_ON)
        self.assertEqual(N._overrides(), {})
        self.assertEqual(N._rating_overrides(), {})


if __name__ == "__main__":
    unittest.main()
