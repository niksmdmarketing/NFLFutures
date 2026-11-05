import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from nba_fast_memory_audit import timing_pushes

class TimingCompatibility(unittest.TestCase):
    def test_legacy_run_list_proves_no_push(self):
        self.assertEqual(timing_pushes([{"created_at":"2026-10-20T00:00:00Z","head_sha":"abc"}]),[])
    def test_only_complete_server_push_records_count(self):
        self.assertEqual(timing_pushes({"pushes":[{"timestamp":"2026-10-22T01:00:00Z","after":"abc"},{"after":"missing_time"},{"timestamp":"missing_sha"}]}),[("2026-10-22T01:00:00Z","abc")])
    def test_empty_legacy_metadata_does_not_invent_receipts(self):
        self.assertEqual(timing_pushes({"runs":[1]}),[])
if __name__=="__main__":unittest.main()
