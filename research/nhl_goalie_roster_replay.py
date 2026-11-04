"""Run the unchanged replay with required RAPM coverage; no silent fallback."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "pipeline"))
import nhl_rapm as RP

original = RP.ratings
identities = {}

def checked_ratings(year):
    sk, gk = original(year)
    if sk is None or gk is None or sk.empty or gk.empty:
        raise RuntimeError(f"Required RAPM skater/goalie inputs unavailable for {year}; do not score fallback")
    identities[year] = {"skater_sha256": hashlib.sha256(sk.to_csv().encode()).hexdigest(),
                        "goalie_sha256": hashlib.sha256(gk.to_csv().encode()).hexdigest(),
                        "skaters": len(sk), "goalies": len(gk)}
    return sk, gk

if __name__ == "__main__":
    RP.ratings = checked_ratings
    sys.argv[0] = str(ROOT / "research" / "replay_nhl.py")
    runpy.run_path(sys.argv[0], run_name="__main__")
    Path(os.environ["BT_OUTDIR"], "rating_identities.json").write_text(json.dumps(identities, indent=2), encoding="utf-8")
