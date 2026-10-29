"""Private, immutable NBA futures bundles. Never writes model/site output.
Use only inside the private archive repository; raw source bytes are retained.
Independent push receipt verification necessarily follows the bundle commit.
"""
import argparse
import datetime as dt
import hashlib
import importlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import urllib.request
from unittest.mock import patch

UTC = dt.timezone.utc
START, END = dt.date(2026, 10, 30), dt.date(2027, 4, 15)
SEEDS = (20261029, 20261030, 20261031)
SIMS = 20000


def now():
    return dt.datetime.now(UTC)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pack_bytes(root, data):
    """Content-addressed <=32MiB Git blobs; never expose raw inputs publicly."""
    parts = []
    for offset in range(0, max(1, len(data)), 32 * 1024 * 1024):
        block = data[offset:offset + 32 * 1024 * 1024]
        name = "objects/" + sha(block)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != block:
            raise ValueError("Immutable object collision: " + name)
        if not path.exists():
            path.write_bytes(block)
        parts.append(name)
    return dict(sha256=sha(data), bytes=len(data), parts=parts)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)


def require_report(plan, availability, audit):
    if (not plan or not availability.get("available") or availability.get("stale")
            or not availability.get("official") or "official_pdf" not in audit):
        raise ValueError("Fresh injury feed and successfully parsed official PDF required")


def verify_bundle(root, manifest):
    m = json.loads(manifest.read_text())
    for name, item in m["files"].items():
        data = b"".join((root / p).read_bytes() for p in item["parts"])
        if sha(data) != item["sha256"] or len(data) != item["bytes"]:
            raise ValueError("Input/output hash mismatch: " + name)
    if not m["smoke"] and not (m["window_start"] <= m["completed_utc"] <= m["cutoff"]):
        raise ValueError("Outside collection window")
    identity = sha(json.dumps({k: v["sha256"] for k, v in sorted(m["files"].items()) if k != "forecasts.json"}, sort_keys=True).encode())
    if identity != m["input_identity_sha256"]:
        raise ValueError("Input-to-output identity mismatch")
    return m


def collect(model_root, cache, injury_root, archive, smoke=False):
    import numpy as np
    import pandas as pd
    model_root, cache, injury_root, archive = map(lambda p: Path(p).resolve(), (model_root, cache, injury_root, archive))
    t0 = now()
    cutoff = dt.datetime.combine(t0.date(), dt.time(12), UTC)
    if not smoke and (not START <= t0.date() <= END or not cutoff-dt.timedelta(minutes=45) <= t0 < cutoff):
        raise ValueError("Not inside a registered daily collection window")
    name = ("smoke/" + t0.strftime("%Y%m%dT%H%M%SZ")) if smoke else "runs/" + t0.date().isoformat()
    dest = archive / name
    if dest.exists():
        m = verify_bundle(archive, dest / "manifest.json")
        print("already captured", name)
        return m
    sys.path.insert(0, str(model_root / "pipeline"))
    N, A = importlib.import_module("nba"), importlib.import_module("nba_avail")
    N.NBA_DATA = str(cache)
    cache.mkdir(parents=True, exist_ok=True)
    working_injury = cache / "injury-working"
    (working_injury / "nba").mkdir(parents=True, exist_ok=True)
    original_injury_bytes = (injury_root / "nba/latest.json").read_bytes()
    for p in (injury_root / "nba").glob("*"):
        if p.is_file():
            shutil.copy2(p, working_injury / "nba" / p.name)
    seen, audit = {}, {}
    download = N._download
    def tracked(*args, **kw):
        p = download(*args, **kw)
        if p:
            seen[str(Path(p).resolve())] = now().isoformat()
        return p
    model_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=model_root, text=True).strip()
    year = N.season_end_year()
    with patch.object(N, "_download", side_effect=tracked):
        boxes, raw_schedule, players, old, roster = N._load_inputs(year)
        fit_boxes = boxes.copy()
        fit_boxes.loc[(pd.to_numeric(fit_boxes.season_type) == 3) & (pd.to_numeric(fit_boxes.season) < year), "season_type"] = 2
        ratings, fit = N._fit_ratings(fit_boxes, year)
        if 0 < fit["home_offense_points_per_100"] < 6:
            N.HFA = float(fit["home_offense_points_per_100"])
        N.PACE = ratings.set_index("team").pace.reindex(N.TEAMS).fillna(100.).to_numpy(float)
        values = N._player_values(players[pd.to_numeric(players.season) == year-1])
        older = N._player_values(players[pd.to_numeric(players.season) == year-2])
        reg = N._regular_boxes(boxes)
        gp = float((reg.season == year).sum()) / len(N.TEAMS)
        ratings, _ = N._roster_adjustment(ratings, values, old, roster, older, gp)
        ratings = N._player_mix(ratings, players, values, older, roster, year, gp)
        if "playoff_adj" not in ratings or not ratings.player_strength.notna().all():
            raise ValueError("Complete live player/rotation layer failed; refusing a simplified forecast")
        schedule = N._schedule(raw_schedule)
        if len(schedule) < 1200:
            raise ValueError("Incomplete season schedule")
        # Capture original PDF bytes actually returned to the official report parser.
        O = importlib.import_module("nba_official")
        latest = O.latest
        def official(*args, **kw):
            result = latest(*args, **kw)
            if result[1]:
                audit["official_pdf"] = result[1]
                audit["official_url"] = result[0]
            return result
        with patch.dict(os.environ, {"NBA_INJ_STORE": str(working_injury)}), patch.object(O, "latest", side_effect=official):
            plan, availability = N._availability(players, year, schedule, roster)
        require_report(plan, availability, audit)
    # All input bytes are copied before any simulation, not reconstructed later.
    files = {}
    for p, captured in seen.items():
        item = pack_bytes(archive, Path(p).read_bytes())
        item["saved_utc"] = now().isoformat()
        item["read_utc"] = captured
        files["inputs/" + Path(p).name] = item
    for p in sorted((model_root / "pipeline").glob("*.py")):
        files["code/" + p.name] = pack_bytes(archive, p.read_bytes())
    for p in [model_root / "model/nba_overrides.json", model_root / "pipeline/nba_avail_params.json",
              cache / "nba_injuries_latest.json", injury_root / "nba/latest.json"]:
        if not p.exists():
            raise ValueError("Missing required settings/report bytes: " + str(p))
        files["settings-or-report/" + p.name] = pack_bytes(archive, p.read_bytes())
    files["official.pdf"] = pack_bytes(archive, audit["official_pdf"])
    files["injury-monitor-snapshot.json"] = pack_bytes(archive, original_injury_bytes)
    files["availability.json"] = pack_bytes(archive, json.dumps(availability, allow_nan=False).encode())
    files["ratings.csv"] = pack_bytes(archive, ratings.to_csv(index=False).encode())
    files["plan.json"] = pack_bytes(archive, json.dumps(plan, default=lambda x: x.tolist(), allow_nan=False).encode())
    settings = dict(season=year, model_commit=model_sha, seeds=list(SEEDS), simulations_per_seed=SIMS,
                    constants={k: getattr(N, k) for k in ("HFA", "GAME_SIGMA", "TEAM_TAU", "TAU_PRE", "TAU_PRE_GAMES", "ROSTER_PM_W", "ROSTER_LAST_W", "ROSTER_FADE", "ROSTER_COEF")},
                    availability_baseline_weights=A.RATING_W, availability_beta=A.BETA,
                    playoff_delta=N.PO_DELTA.tolist() if N.PO_DELTA is not None else None,
                    python=sys.version, numpy=np.__version__, pandas=pd.__version__, official_url=audit["official_url"])
    files["settings.json"] = pack_bytes(archive, json.dumps(settings, allow_nan=False).encode())
    inputs_saved = now().isoformat()
    predictions = {}
    rng = np.random.default_rng
    for seed in SEEDS:
        predictions[str(seed)] = {}
        for variant, adjustments in (("base", None), ("dated_injury", plan)):
            with patch.object(N.np.random, "default_rng", side_effect=lambda *a, seed=seed, **k: rng(seed)):
                predictions[str(seed)][variant] = N._simulate(schedule, ratings, SIMS, adjustments)
    files["forecasts.json"] = pack_bytes(archive, json.dumps(predictions, allow_nan=False).encode())
    finish = now()
    if not smoke and finish > cutoff:
        raise ValueError("Forecast completed after cutoff; no eligible bundle written")
    identity = sha(json.dumps({k: v["sha256"] for k, v in sorted(files.items()) if k != "forecasts.json"}, sort_keys=True).encode())
    m = dict(schema=1, smoke=smoke, model_commit=model_sha, cutoff=cutoff.isoformat(),
             window_start=(cutoff-dt.timedelta(minutes=45)).isoformat(), started_utc=t0.isoformat(),
             inputs_saved_utc=inputs_saved,
             completed_utc=finish.isoformat(), input_identity_sha256=identity, files=files,
             seeds=list(SEEDS), simulations_per_seed=SIMS, independent_receipt="pending")
    write_json(dest / "manifest.json", m)
    verify_bundle(archive, dest / "manifest.json")
    print("verified bundle", name, identity, flush=True)
    return m


def check_due(archive, today=None):
    today = today or now().date()
    last = min(END, today if now().hour >= 12 else today-dt.timedelta(days=1))
    missing = []
    d = START
    while d <= last:
        path = Path(archive) / "runs" / d.isoformat() / "manifest.json"
        if not path.exists():
            missing.append(d.isoformat())
        else:
            verify_bundle(Path(archive), path)
            receipt = Path(archive) / "receipts" / (d.isoformat() + ".json")
            if not receipt.exists() or not json.loads(receipt.read_text()).get("eligible"):
                missing.append(d.isoformat() + " (no qualified independent receipt)")
        d += dt.timedelta(days=1)
    if missing:
        raise ValueError("MISSED CUTOFFS (never backfill): " + ", ".join(missing))
    print("all due bundles present; independent receipt checks remain mandatory")


def receipts(archive):
    """GitHub-server push times linked by exact commit ancestry, never job clock."""
    archive = Path(archive).resolve()
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}/activity?ref=nba-forward-archive&activity_type=push&per_page=100&time_period=week"
    pushes = []
    for _ in range(20):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page, link = json.load(r), r.headers.get("Link", "")
        if not isinstance(page, list):
            raise ValueError("Unexpected GitHub activity payload")
        pushes.extend(page)
        nxt = [p[p.find("<")+1:p.find(">")] for p in link.split(",") if 'rel="next"' in p]
        if not nxt:
            break
        url = nxt[0]
    pending = []
    for path in list((archive / "runs").glob("*/manifest.json")) + list((archive / "smoke").glob("*/manifest.json")):
        name = path.parent.name
        dest = archive / "receipts" / (name + ".json")
        if dest.exists():
            continue
        m = verify_bundle(archive, path)
        added = subprocess.check_output(["git", "log", "--diff-filter=A", "--format=%H", "-1", "--", str(path.relative_to(archive))], cwd=archive, text=True).strip()
        matches = []
        for p in pushes:
            after = p.get("after")
            if not after or not p.get("timestamp"):
                continue
            if subprocess.run(["git", "merge-base", "--is-ancestor", added, after], cwd=archive, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                matches.append(p)
        if not matches:
            pending.append(name)
            continue
        received = min(matches, key=lambda x: x["timestamp"])
        eligible = not m["smoke"] and dt.datetime.fromisoformat(received["timestamp"].replace("Z", "+00:00")) <= dt.datetime.fromisoformat(m["cutoff"])
        write_json(dest, dict(eligible=eligible, smoke=m["smoke"], adding_commit=added,
                             manifest_sha256=sha(path.read_bytes()), github_push=received,
                             verified_utc=now().isoformat()))
        print("server receipt", name, received["timestamp"], "eligible", eligible)
    if pending:
        raise ValueError("Independent push receipts pending (retry later): " + ", ".join(pending))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-root")
    p.add_argument("--cache")
    p.add_argument("--injury-root")
    p.add_argument("--archive", required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--receipts", action="store_true")
    a = p.parse_args()
    if a.receipts:
        receipts(a.archive)
    elif a.check:
        check_due(a.archive)
    else:
        collect(a.model_root, a.cache, a.injury_root, a.archive, a.smoke)
