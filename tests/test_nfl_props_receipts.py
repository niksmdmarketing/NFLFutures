import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pipeline"))
import nfl_props_receipts as R
import nfl_props_score as S

class Receipts(unittest.TestCase):
    def test_server_time_not_commit_clock_and_mutated_paths_rejected(self):
        def fake(root,*args):
            if args[0]=="log" and "--diff-filter=A" in args:return "COMMIT:a\nsnapshots/ok.json\nsnapshots/changed.json"
            if args[0]=="rev-list":return "b\na"
            if args[0]=="log":return "b\na" if args[-1].endswith("changed.json") else "a"
            raise AssertionError(args)
        pushes=[{"timestamp":"2026-11-05T11:05:00Z","after":"b","ref":"refs/heads/nfl-props-v11-archive","activity_type":"push"}]
        with patch.object(R,"identity",return_value=("owner/repo","nfl-props-v11-archive")),patch.object(R,"git",side_effect=fake):
            out=R.build_receipts(Path("."),pushes)
        self.assertEqual(out,{"snapshots/ok.json":dt.datetime(2026,11,5,11,5,tzinfo=dt.timezone.utc)})
    def test_other_branch_or_unproved_ancestry_does_not_count(self):
        push={"timestamp":"2026-11-05T10:00:00Z","after":"b","ref":"refs/heads/other","activity_type":"push"}
        with patch.object(R,"identity",return_value=("owner/repo","nfl-props-v11-archive")),patch.object(R,"git",return_value="COMMIT:a\nsnapshots/a.json"):
            self.assertEqual(R.build_receipts(Path("."),[push]),{})
    def test_late_server_push_excludes_even_with_early_generation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);row={"file":"snapshots/a.json","game_id":"g","kickoff_utc":"2026-11-05T12:00:00Z","generated_utc":"2026-11-05T10:30:00Z"};(root/"index.jsonl").write_text(json.dumps(row))
            with patch.object(S,"build_receipts",return_value={row["file"]:dt.datetime(2026,11,5,11,1,tzinfo=dt.timezone.utc)}),patch.object(S,"snapshot_valid",return_value=True):
                self.assertEqual(S.choose(root,60,[]),{})
    def test_no_evidence_and_future_generation_exclude(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);row={"file":"snapshots/a.json","game_id":"g","kickoff_utc":"2026-11-05T12:00:00Z","generated_utc":"2026-11-05T10:30:00Z"};(root/"index.jsonl").write_text(json.dumps(row))
            for evidence in [{},{row["file"]:dt.datetime(2026,11,5,10,29,tzinfo=dt.timezone.utc)}]:
                with patch.object(S,"build_receipts",return_value=evidence),patch.object(S,"snapshot_valid",return_value=True):self.assertEqual(S.choose(root,60,[]),{})
    def test_snapshot_hash_and_game_identity_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"snapshots").mkdir();snap={"generated_utc":"2026-11-05T10:30:00Z","games":[{"game_id":"g","kickoff_utc":"2026-11-05T12:00:00Z"}]};(root/"snapshots/a.json").write_text(json.dumps(snap));row={"file":"snapshots/a.json","game_id":"g","kickoff_utc":snap["games"][0]["kickoff_utc"],"generated_utc":snap["generated_utc"],"sha256":hashlib.sha256(json.dumps(snap,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
            self.assertFalse(R.snapshot_valid(root,row))
            snap["forecast_sha256"]=row["sha256"];(root/"snapshots/a.json").write_text(json.dumps(snap))
            self.assertTrue(R.snapshot_valid(root,row));row["kickoff_utc"]="2026-11-05T13:00:00Z";self.assertFalse(R.snapshot_valid(root,row));row["file"]="../escape.json";self.assertFalse(R.snapshot_valid(root,row))
    def test_naive_receipt_timestamp_rejected(self):
        with self.assertRaises(ValueError):R.timestamp("2026-11-05T10:00:00")
if __name__=="__main__":unittest.main()
