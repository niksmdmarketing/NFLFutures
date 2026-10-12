import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import nba


def test_preseason_widening_is_fixed():
    assert nba.TAU_PRE == 2.0 and nba.TAU_PRE_GAMES == 16
