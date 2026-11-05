"""Input guard and run manifest for the NBA futures replay (research/NBA_REPLAY_STANDING_RULE.md).

check_inputs(...) stops the replay (SystemExit) when anything a layer needs is missing or inactive: stints for the RAPM seasons,
usable rows, box scores, schedules, and an active RAPM fit. There is no silent fallback: a replay without its layers is a different
baseline. write_manifest(...) records code revision, settings, seeds, simulation count and input fingerprints next to the output.
verify_manifest(dir) re-hashes the inputs and code and says whether a saved baseline can be reused.
Usage: python research/nba_replay_guard.py verify <replay output dir>"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_STINT_ROWS = 20000     # a full regular season has 29,000-41,000 stints after filtering (the 2012 lockout season 28,900)
MIN_USABLE = 0.90
SEEDS = {"simulation_rng": 20261009, "playoff_availability_rng": 11}
CODE = ["research/replay_nba.py", "pipeline/nba.py", "pipeline/nba_rapm.py", "research/nba_rapm.py", "research/nba_joint.py",
        "research/nba_player_replay.py", "research/nba_backtest.py", "pipeline/nba_backtest.py", "pipeline/nba_title_backtest.py",
        "research/nba_stints.py", "research/nba_joint_stints.py", "research/nba_replay_guard.py"]


def stints_dir():
    return os.environ.get("NBA_STINTS", "/home/claude/nbapbp/stints")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def required_seasons(first, last, joint=False, in_season_rapm=False, era=True):
    """Seasons whose stints the run reads: y-1 and y-2 for the pre-season RAPM; also y for the joint model or in-season refits."""
    need = set()
    for y in range(first, last + 1):
        if era and y == 2020:
            continue
        need |= {y - 1, y - 2}
        if joint or in_season_rapm:
            need.add(y)
    return sorted(need)


def check_inputs(first, last, nba_data, joint=False, in_season_rapm=False, rapm_needed=True, era=True):
    problems = []
    sd = stints_dir()
    if rapm_needed or joint:
        if not os.path.isdir(sd):
            problems.append(f"stints directory {sd} does not exist (set NBA_STINTS)")
        else:
            meta_p = os.path.join(sd, "meta.json")
            meta = json.load(open(meta_p)) if os.path.exists(meta_p) else {}
            import pandas as pd
            for s in required_seasons(first, last, joint, in_season_rapm, era):
                p = os.path.join(sd, f"stints_{s}.parquet")
                if not os.path.exists(p):
                    problems.append(f"missing stints_{s}.parquet")
                    continue
                n = len(pd.read_parquet(p, columns=["poss"]))
                if n < MIN_STINT_ROWS:
                    problems.append(f"stints_{s}.parquet has only {n} rows (< {MIN_STINT_ROWS})")
                us = meta.get(str(s), {}).get("usable_share")
                if us is not None and us < MIN_USABLE:
                    problems.append(f"stints_{s}: usable game share {us} < {MIN_USABLE}")
    for y in range(max(2003, first - 5), last + 1):
        if not os.path.exists(os.path.join(nba_data, f"team_box_{y}.csv")):
            problems.append(f"missing team_box_{y}.csv")
    for y in range(first - 2, last + 1):
        if not os.path.exists(os.path.join(nba_data, f"player_box_{y}.csv")):
            problems.append(f"missing player_box_{y}.csv")
    for y in range(first, last + 1):
        if era and y == 2020:
            continue
        if not os.path.exists(os.path.join(nba_data, f"nba_schedule_{y}.csv")):
            problems.append(f"missing nba_schedule_{y}.csv")
    if not problems and (rapm_needed or joint):   # the RAPM layer must be active, not just present
        spec = importlib.util.spec_from_file_location("guard_nba_rapm", os.path.join(ROOT, "research", "nba_rapm.py"))
        RA = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(RA)
        RA.STINTS = sd
        import numpy as np
        y0 = next(y for y in range(first, last + 1) if not (era and y == 2020))
        r = RA.fit(y0, lam=3000, w2=0.5, prior=None, cache={})
        v = np.array(list(r.values())) if r else np.array([])
        if len(v) < 300 or float(np.std(v)) < 0.05:
            problems.append(f"RAPM layer inactive for {y0}: {len(v)} players, sd {float(np.std(v)) if len(v) else 0:.3f}")
    if problems:
        raise SystemExit("REPLAY STOPPED - input check failed (no silent fallback):\n  " + "\n  ".join(problems))
    print(f"input check passed: stints {sd}, seasons {required_seasons(first, last, joint, in_season_rapm, era)}", flush=True)


def _git(*a):
    try:
        return subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _inputs(first, last, nba_data, sd):
    files = {}
    for y in range(max(2003, first - 5), last + 1):
        files[f"team_box_{y}.csv"] = os.path.join(nba_data, f"team_box_{y}.csv")
    for y in range(first - 2, last + 1):
        files[f"player_box_{y}.csv"] = os.path.join(nba_data, f"player_box_{y}.csv")
        files[f"nba_schedule_{y}.csv"] = os.path.join(nba_data, f"nba_schedule_{y}.csv")
        files[f"stints_{y}.parquet"] = os.path.join(sd, f"stints_{y}.parquet")
    return {k: {"bytes": os.path.getsize(p), "sha256": _sha(p)} for k, p in files.items() if os.path.exists(p)}


def write_manifest(out_dir, first, last, nba_data, sims, seasons_written):
    sd = stints_dir()
    rev = _git("rev-parse", "HEAD")
    dirty = [l for l in (_git("status", "--porcelain", "--", "research", "pipeline") or "").splitlines() if l.strip()]
    m = {"code_revision": rev, "code_dirty_files": dirty,
         "code_sha256": {c: _sha(os.path.join(ROOT, c)) for c in CODE if os.path.exists(os.path.join(ROOT, c))},
         "settings": {k: v for k, v in sorted(os.environ.items()) if k.startswith("BT_") or k.startswith("NBA_") or k.startswith("NP_")},
         "seeds": SEEDS, "simulations": sims, "seasons_requested": [first, last], "seasons_written": seasons_written,
         "stints_dir": sd, "python": sys.version.split()[0],
         "inputs": _inputs(first, last, nba_data, sd),
         "outputs": {f"nba_{y}.csv": _sha(os.path.join(out_dir, f"nba_{y}.csv")) for y in seasons_written}}
    try:
        import numpy, pandas
        m["numpy"], m["pandas"] = numpy.__version__, pandas.__version__
    except Exception:
        pass
    json.dump(m, open(os.path.join(out_dir, "manifest.json"), "w"), indent=1)
    return m


def verify_manifest(out_dir):
    """True when inputs, code and outputs match the manifest. Reports every difference."""
    m = json.load(open(os.path.join(out_dir, "manifest.json")))
    diffs = []
    sd = m["stints_dir"]
    nba_data = os.path.join(ROOT, "data", "nba")
    first, last = m["seasons_requested"]
    now = _inputs(first, last, nba_data, sd)
    for k, v in m["inputs"].items():
        if k not in now:
            diffs.append(f"input missing now: {k}")
        elif now[k]["sha256"] != v["sha256"]:
            diffs.append(f"input changed: {k}")
    for c, h in m["code_sha256"].items():
        p = os.path.join(ROOT, c)
        if not os.path.exists(p) or _sha(p) != h:
            diffs.append(f"code changed: {c}")
    for f, h in m["outputs"].items():
        p = os.path.join(out_dir, f)
        if not os.path.exists(p) or _sha(p) != h:
            diffs.append(f"output changed or missing: {f}")
    return diffs


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "verify":
    d = verify_manifest(sys.argv[2])
    print("MATCH: the saved baseline can be reused" if not d else "NO MATCH:\n  " + "\n  ".join(d))
    sys.exit(0 if not d else 1)
