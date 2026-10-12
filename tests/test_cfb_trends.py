import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import trends


def test_cfp_table_is_consistent():
    for y, (champ, runner, others) in trends.CFB_CFP.items():
        assert champ != runner and champ not in others and runner not in others
        assert len(others) == (2 if y <= 2023 else 10), y
