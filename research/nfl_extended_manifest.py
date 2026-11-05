"""Manifest for the extended NFL baseline (model/replay/nfl_ext): code revision, settings, seed, simulations, input and output
fingerprints. verify: re-hash and report differences, so a matching baseline can be reused instead of regenerated.
Usage: python research/nfl_extended_manifest.py write|verify [dir]"""
import glob
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = ["research/replay_nfl.py", "pipeline/simulate.py", "pipeline/ratings.py", "pipeline/common.py", "pipeline/nfl_backtest.py",
        "model/settings.json", "model/replay/nfl_wf_coef.json", "research/nfl_extended_check.py"]
SETTINGS = {"BT_COEF": "wf", "BT_REST": "1", "BT_SIMS": "4000 (default)", "simulation seed": 7, "n_seeds": "6 to 2019, 7 from 2020"}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def inputs(first=2012, last=2025):
    d = os.path.join(ROOT, "data")
    fs = [os.path.join(d, f"play_by_play_{y}.csv.gz") for y in range(first, last + 1)] + [os.path.join(d, "games.csv"), os.path.join(d, "nfl_standings.csv")]
    return {os.path.relpath(p, ROOT): sha(p) for p in fs if os.path.exists(p)}


def write(out):
    rev = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    m = {"code_revision": rev, "settings": SETTINGS, "code_sha256": {c: sha(os.path.join(ROOT, c)) for c in CODE if os.path.exists(os.path.join(ROOT, c))},
         "inputs": inputs(), "outputs": {os.path.basename(p): sha(p) for p in sorted(glob.glob(os.path.join(out, "nfl_*.csv")))}}
    json.dump(m, open(os.path.join(out, "manifest.json"), "w"), indent=1)


def verify(out):
    m = json.load(open(os.path.join(out, "manifest.json")))
    diffs = [f"input changed or missing: {k}" for k, v in m["inputs"].items() if not os.path.exists(os.path.join(ROOT, k)) or sha(os.path.join(ROOT, k)) != v]
    diffs += [f"code changed: {k}" for k, v in m["code_sha256"].items() if sha(os.path.join(ROOT, k)) != v]
    diffs += [f"output changed: {k}" for k, v in m["outputs"].items() if not os.path.exists(os.path.join(out, k)) or sha(os.path.join(out, k)) != v]
    print("MATCH: the saved baseline can be reused" if not diffs else "NO MATCH:\n  " + "\n  ".join(diffs))
    return not diffs


if __name__ == "__main__":
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "model", "replay", "nfl_ext")
    write(out) if sys.argv[1] == "write" else sys.exit(0 if verify(out) else 1)
