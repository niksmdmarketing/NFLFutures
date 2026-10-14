"""Wrapper: the rating-engine research script now lives in pipeline/nfl_engine.py (used by the v5 candidate).
Usage: python research/nfl_rating_engine.py <tag> [H] [WP] [EXTRA]"""
import os
import runpy
import sys

sys.argv[0] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline", "nfl_engine.py")
runpy.run_path(sys.argv[0], run_name="__main__")
