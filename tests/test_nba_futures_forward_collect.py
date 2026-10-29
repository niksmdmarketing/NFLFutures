import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from nba_futures_forward_collect import pack_bytes, sha, verify_bundle, write_json, require_report


class PrivateBundles(unittest.TestCase):
    def test_pdf_bytes_without_successful_parse_do_not_qualify(self):
        with self.assertRaises(ValueError):
            require_report({"episodes": []}, {"available": True, "stale": False, "official": None}, {"official_pdf": b"pdf"})

    def test_round_trip_and_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            item = pack_bytes(root, b"actual saved input bytes")
            files = {"input": item, "forecasts.json": pack_bytes(root, b"{}")}
            identity = sha(json.dumps({"input": item["sha256"]}, sort_keys=True).encode())
            m = dict(smoke=True, files=files, input_identity_sha256=identity)
            path = root / "manifest.json"
            write_json(path, m)
            self.assertEqual(verify_bundle(root, path)["input_identity_sha256"], identity)
            (root / item["parts"][0]).write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_bundle(root, path)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manifest.json"
            write_json(p, {})
            with self.assertRaises(FileExistsError):
                write_json(p, {"changed": True})


if __name__ == "__main__":
    unittest.main()
