# tests/test_nba_futures_forward_check_due.py — unittest, tempfile, no network.
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import nba_futures_forward_collect as C  # noqa: E402

NOW = dt.datetime(2026, 11, 15, 13, 0)      # hour >= 12, so today itself is due


def due_dates():
    d, out, last = C.START, [], min(C.END, NOW.date())
    while d <= last:
        out.append(d)
        d += dt.timedelta(days=1)
    return out


class CheckDue(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [patch.object(C, "verify_bundle", lambda *a, **k: None),
                         patch.object(C, "now", lambda: NOW)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def bundle(self, d, eligible=True):
        m = self.root / "runs" / d / "manifest.json"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("{}")
        if eligible:
            r = self.root / "receipts" / (d + ".json")
            r.parent.mkdir(parents=True, exist_ok=True)
            r.write_text(json.dumps({"eligible": True}))

    def fill(self, skip=()):
        for d in due_dates():
            if d.isoformat() not in skip:
                self.bundle(d.isoformat())

    def ledger(self, dates, ack="2026-11-15T11:00:00Z"):
        entries = [{"date": d, "acknowledged_utc": ack,
                    "amendment": "Amendment 1, 15 Nov 2026",
                    "reason": "scheduled job started 5-10 h late"} for d in dates]
        (self.root / "acknowledged_missing.json").write_text(
            json.dumps({"schema": 1, "entries": entries}))

    def test_no_ledger_old_behaviour(self):
        self.fill(skip={"2026-10-31"})
        with self.assertRaises(ValueError) as cm:
            C.check_due(self.root)
        self.assertIn("MISSED CUTOFFS", str(cm.exception))
        self.assertIn("2026-10-31", str(cm.exception))

    def test_acknowledged_dates_pass(self):
        self.fill(skip={"2026-10-30", "2026-10-31"})
        self.ledger(["2026-10-30", "2026-10-31"])
        C.check_due(self.root)                       # must not raise

    def test_new_miss_still_raises(self):
        self.fill(skip={"2026-10-30", "2026-11-02"})
        self.ledger(["2026-10-30"])
        with self.assertRaises(ValueError) as cm:
            C.check_due(self.root)
        self.assertIn("2026-11-02", str(cm.exception))
        self.assertNotIn("2026-10-30", str(cm.exception))

    def test_entry_after_its_acknowledgement_raises(self):
        self.fill()
        self.ledger(["2026-11-14"], ack="2026-11-10T09:00:00Z")
        with self.assertRaises(ValueError) as cm:
            C.check_due(self.root)
        self.assertIn("PRE-EXCUSES", str(cm.exception))

    def test_ledger_against_eligible_bundle_raises(self):
        self.fill()
        self.ledger(["2026-11-01"])
        with self.assertRaises(ValueError) as cm:
            C.check_due(self.root)
        self.assertIn("CONTRADICTS", str(cm.exception))

    def test_ledger_contradiction_outside_due_window_raises(self):
        self.fill()
        self.bundle("2026-11-16")
        self.ledger(["2026-11-16"], ack="2026-11-16T12:30:00Z")   # acknowledged after its own date, so only the contradiction can fire
        with self.assertRaises(ValueError) as cm:
            C.check_due(self.root)
        self.assertIn("CONTRADICTS", str(cm.exception))

    def test_malformed_ledger_raises(self):
        self.fill()
        good = {"date": "2026-10-30", "acknowledged_utc": "2026-11-15T00:00:00Z",
                "amendment": "A1", "reason": "r"}
        for bad in ("{not json",
                    json.dumps({"schema": 2, "entries": []}),
                    json.dumps({"schema": 1, "entries": "nope"}),
                    json.dumps({"schema": 1, "entries": [{"date": "2026-10-30"}]}),
                    json.dumps({"schema": 1, "entries": [dict(good, date="2026-13-01")]}),
                    json.dumps({"schema": 1, "entries": [
                        dict(good, acknowledged_utc="2026-11-15T00:00:00")]}),
                    json.dumps({"schema": 1, "entries": [good, dict(good, reason="r2")]})):
            (self.root / "acknowledged_missing.json").write_text(bad)
            with self.assertRaises(ValueError, msg=bad):
                C.check_due(self.root)
