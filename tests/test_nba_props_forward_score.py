"""Forward scorer: outcome rules for candidates absent from the final box (no HTTP)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import nba_props_forward_score as F  # noqa: E402

KEYS = ["minutes", "points", "rebounds", "assists"]


def box(teams, scores=None, gid="1"):
    """teams: {abbr: [(aid, minutes)]} -> ESPN-like summary document (each player scores 10)."""
    scores = scores or {t: 10 * len(r) for t, r in teams.items()}
    players = []
    for abbr, rows in teams.items():
        players.append({"team": {"abbreviation": abbr}, "statistics": [{"keys": KEYS, "athletes": [
            {"athlete": {"id": str(a)}, "stats": [str(m), "10", "5", "3"]} for a, m in rows]}]})
    comp = {"id": gid, "status": {"type": {"completed": True}}, "competitors": [{"team": {"abbreviation": t}, "score": str(v)} for t, v in scores.items()]}
    return {"header": {"competitions": [comp]}, "boxscore": {"players": players}}


def full(base, n=8):
    per = 240 / n
    return [(base + i, per) for i in range(n)]


def pmf(n, p_appear):
    p = [0.0] * n
    p[0] = 1 - p_appear + p_appear * 0.2
    for k in range(1, n):
        p[k] = p_appear * 0.8 / (n - 1)
    return p


def player(team, aid, pa=0.3):
    return {"team": team, "aid": aid, "p_appear": pa, **{f"{s}_{v}": pmf(26, pa) for s in ("reb", "ast") for v in ("v2", "v3")}}


class Archive:
    def __init__(self, rec):
        self.rec = rec

    def read(self, path):
        return self.rec


class ScoreTests(unittest.TestCase):
    def run_case(self, teams, players, scores=None, gid="1"):
        d = tempfile.mkdtemp()
        (Path(d) / "outcomes").mkdir()
        (Path(d) / "outcomes" / "1.json").write_text(json.dumps(box(teams, scores, gid)))
        rec = {"players": players, "coverage": {"BOS": {}, "NY": {}}}
        audit = {"source_commit": "x", "selected": [{"horizon_min": 60, "game_id": 1, "path": "p"}]}
        return F.score(Archive(rec), audit, d)

    def test_missing_from_complete_box_is_dnp_in_research_version_only(self):
        r = self.run_case({"BOS": full(100), "NY": full(200)}, [player("BOS", 100), player("BOS", 999)])
        self.assertEqual(r["exclusions"].get("missing_from_complete_box_scored_as_dnp"), 1)
        self.assertEqual(r["metrics"]["research_convention:appearance_logloss"]["n"], 2)
        self.assertEqual(r["metrics"]["box_listed_only:appearance_logloss"]["n"], 1)

    def test_incomplete_box_leaves_missing_unknown(self):
        r = self.run_case({"BOS": full(100, 4), "NY": full(200)}, [player("BOS", 999)])
        self.assertEqual(r["exclusions"].get("missing_unknown_team_box_incomplete"), 1)
        self.assertEqual(r["player_games_matched"], 0)

    def test_team_mismatch_leaves_missing_unknown(self):
        r = self.run_case({"BOS": full(100), "MIA": full(200)}, [player("BOS", 999)])
        self.assertEqual(r["exclusions"].get("missing_unknown_team_mapping_mismatch"), 1)

    def test_score_mismatch_leaves_missing_unknown(self):
        r = self.run_case({"BOS": full(100), "NY": full(200)}, [player("BOS", 999)], scores={"BOS": 81, "NY": 80})
        self.assertEqual(r["exclusions"].get("missing_unknown_team_box_incomplete"), 1)

    def test_wrong_game_id_is_excluded(self):
        r = self.run_case({"BOS": full(100), "NY": full(200)}, [player("BOS", 100)], gid="2")
        self.assertEqual(r["exclusions"].get("game_id_mismatch"), 1)

    def test_overtime_box_is_complete(self):
        ok = {("__score_ok__", "BOS"): {"appeared": False, "ok": True}}
        self.assertTrue(F.box_complete({**ok, **{("BOS", i): {"appeared": True, "minutes": 265 / 8} for i in range(8)}}, "BOS"))
        self.assertFalse(F.box_complete({**ok, **{("BOS", i): {"appeared": True, "minutes": 250 / 8} for i in range(8)}}, "BOS"))


if __name__ == "__main__":
    unittest.main()
