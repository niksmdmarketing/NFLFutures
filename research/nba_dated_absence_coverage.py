"""Audit existing Git archives against daily dated-absence cutoffs. Read only.

Git commit times are NOT independent GitHub push receipts. Missing provenance
fails closed. No snapshots are generated, backfilled, or changed by this script.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import subprocess
from pathlib import Path

UTC = dt.timezone.utc
INJ_FILES = ("nba/history.jsonl", "nba/futures_shadow.jsonl", "availability/nba/changes.jsonl")


def timestamp(value):
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H%MZ").replace(tzinfo=UTC)


def evaluate(cutoff, reports, pairs, forecasts):
    start = cutoff - dt.timedelta(minutes=45)
    issues = []
    recent = [r for r in pairs if start <= timestamp(r["t"]) <= cutoff]
    pair = max(recent, key=lambda r: timestamp(r["t"])) if recent else None
    fs = [f for f in forecasts if start <= timestamp(f["generated_utc"]) <= cutoff]
    forecast = max(fs, key=lambda f: timestamp(f["generated_utc"])) if fs else None
    if pair is None:
        issues.append("no_paired_injury_futures_in_window")
    if forecast is None:
        issues.append("no_forecast_archive_snapshot_in_window")
    report = None
    if pair is not None:
        earlier = [r for r in reports if timestamp(r["collected_utc"]) <= timestamp(pair["t"])]
        report = max(earlier, key=lambda r: timestamp(r["collected_utc"])) if earlier else None
        if report is None:
            issues.append("no_report_saved_before_forecast")
        else:
            # A preceding report is not evidence it was the actual report used.
            issues.append("actual_input_hash_linkage_not_archived")
        for field in ("without", "with"):
            rows = pair.get(field, {})
            if len(rows) != 30 or any(not all(k in v for k in ("p_playoff", "p_conf", "p_title")) for v in rows.values()):
                issues.append("incomplete_30_team_pair")
        if set(pair.get("without", {})) != set(pair.get("with", {})):
            issues.append("mismatched_team_sets")
        issues.extend(["frozen_settings_identity_not_archived", "seed_specific_outputs_not_archived"])
    if pair is not None and forecast is not None:
        issues.append("cross_archive_same_build_linkage_not_archived")
    # Current schemas have no independent push event or immutable input bundle.
    issues.append("independent_pre_cutoff_push_receipts_missing")
    return dict(cutoff=cutoff.isoformat(), eligible=not issues, issues=sorted(set(issues)),
                pair_time=pair.get("t") if pair else None,
                forecast_time=forecast.get("generated_utc") if forecast else None,
                preceding_report_time=report.get("collected_utc") if report else None)


def read_git(repo, ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=repo)


def run(repo, start, end, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Refuse to overwrite an earlier coverage audit")
    refs = {b: subprocess.check_output(["git", "rev-parse", "origin/" + b], cwd=repo, text=True).strip()
            for b in ("injury-monitor", "forecast-archive")}
    evidence = {}
    raw = {}
    for p in INJ_FILES:
        raw[p] = read_git(repo, refs["injury-monitor"], p)
        evidence["injury-monitor:" + p] = hashlib.sha256(raw[p]).hexdigest()
    reports = [json.loads(x) for x in raw["nba/history.jsonl"].splitlines() if x]
    pairs = [json.loads(x) for x in raw["nba/futures_shadow.jsonl"].splitlines() if x]
    index = read_git(repo, refs["forecast-archive"], "nba/2027/index.csv")
    evidence["forecast-archive:nba/2027/index.csv"] = hashlib.sha256(index).hexdigest()
    idx = list(csv.DictReader(io.StringIO(index.decode())))
    forecasts = []
    for row in idx:
        t = timestamp(row["generated_utc"])
        in_window = (t.hour == 11 and t.minute >= 15) or (t.hour == 12 and t.minute == 0)
        if start <= t.date() <= end and in_window:
            path = "nba/2027/" + row["file"]
            b = read_git(repo, refs["forecast-archive"], path)
            evidence["forecast-archive:" + path] = hashlib.sha256(b).hexdigest()
            forecasts.append(json.loads(gzip.decompress(b)))
    rows = []
    day = start
    while day <= end:
        rows.append(evaluate(dt.datetime.combine(day, dt.time(12), UTC), reports, pairs, forecasts))
        day += dt.timedelta(days=1)
    result = dict(audited_utc=dt.datetime.now(UTC).isoformat(), refs=refs, source_hashes=evidence,
                  cutoffs=len(rows), eligible=sum(r["eligible"] for r in rows), rows=rows,
                  note="Historical coverage diagnostic only. Prospective cohort begins 2026-10-30T12:00:00Z. No backfill counts.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    p.add_argument("--start", type=dt.date.fromisoformat, required=True)
    p.add_argument("--end", type=dt.date.fromisoformat, required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    r = run(a.repo, a.start, a.end, a.output)
    print(json.dumps({"cutoffs": r["cutoffs"], "eligible": r["eligible"]}))
