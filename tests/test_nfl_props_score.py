import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import nfl_props_score as S  # noqa: E402


def fixture(final=True, include_away_snap=True, ambiguous=False):
    stats = pd.DataFrame([
        {"game_id": "2026_01_A_B", "team": "A", "player_id": "gsis-4", "season_type": "REG", "receptions": 1, "attempts": 0},
        {"game_id": "2026_01_A_B", "team": "B", "player_id": "gsis-2", "season_type": "REG", "receptions": 0, "attempts": 1},
    ])
    snaps = pd.DataFrame([
        {"game_id": "2026_01_A_B", "team": "A", "pfr_player_id": "pfr-1", "offense_snaps": 5},
        {"game_id": "2026_01_A_B", "team": "A", "pfr_player_id": "pfr-2", "offense_snaps": 0},
        *([{"game_id": "2026_01_A_B", "team": "B", "pfr_player_id": "pfr-3", "offense_snaps": 5}] if include_away_snap else []),
    ])
    players = pd.DataFrame([
        {"pfr_id": "pfr-1", "gsis_id": "gsis-1"},
        {"pfr_id": "pfr-2", "gsis_id": "gsis-2"},
        {"pfr_id": "pfr-3", "gsis_id": "gsis-3"},
        {"pfr_id": "pfr-4", "gsis_id": "gsis-4"},
    ])
    if ambiguous:
        players = pd.concat([players, pd.DataFrame([{"pfr_id": "pfr-1", "gsis_id": "other-id"}])], ignore_index=True)
    schedule = pd.DataFrame([{
        "game_id": "2026_01_A_B", "season": 2026, "game_type": "REG",
        "home_team": "B", "away_team": "A",
        "home_score": 10 if final else None, "away_score": 7 if final else None,
    }])
    return S.prepare_outcomes(stats, snaps, players, schedule, 2026)


class NFLPropsScoreTest(unittest.TestCase):
    def test_missing_stat_row_for_confirmed_appearance_is_zero(self):
        labels = fixture()
        player = {"player_id": "gsis-1", "stat": "receptions"}
        self.assertIn("2026_01_A_B", labels["complete_games"])
        self.assertEqual(S.player_outcome("2026_01_A_B", "A", player, labels), (1, 0, "scored"))

    def test_incomplete_game_and_snap_coverage_remain_pending(self):
        self.assertNotIn("2026_01_A_B", fixture(final=False)["complete_games"])
        self.assertNotIn("2026_01_A_B", fixture(include_away_snap=False)["complete_games"])

    def test_ambiguous_player_mapping_leaves_availability_unresolved(self):
        labels = fixture(ambiguous=True)
        player = {"player_id": "gsis-1", "stat": "receptions"}
        self.assertEqual(S.player_outcome("2026_01_A_B", "A", player, labels), (None, None, "availability_unmapped"))

    def test_confirmed_nonappearance_has_no_conditional_stat_score(self):
        labels = fixture()
        player = {"player_id": "gsis-2", "stat": "receptions"}
        self.assertEqual(S.player_outcome("2026_01_A_B", "A", player, labels), (0, None, "did_not_appear"))


if __name__ == "__main__":
    unittest.main()
