import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import nba  # noqa: E402


def test_drops_postponed_originals_and_cup_final():
    d = pd.DataFrame({"id": [1, 2, 3, 4], "status_type_name": ["STATUS_FINAL", "STATUS_POSTPONED", "STATUS_SCHEDULED", "STATUS_SCHEDULED"],
                      "type_abbreviation": ["STD", "STD", "STD", "CC"]})
    assert nba._season_rows(d).id.tolist() == [1, 3]


def test_missing_columns_keep_everything():
    d = pd.DataFrame({"id": [1, 2]})
    assert nba._season_rows(d).id.tolist() == [1, 2]
