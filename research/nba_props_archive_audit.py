"""Read-only, dependency-free audit of the prospective NBA props Git archive.

Uses independently recorded push receipts, NOT a job's own timestamp, to select
the last eligible forecast per game/horizon. Does not change any model or archive.
Usage: python research/nba_props_archive_audit.py --ref FETCH_HEAD --output report.json
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return result.astimezone(timezone.utc)


def pmf_errors(values, tolerance=0.00002):
    if not values or any(not math.isfinite(x) or x < 0 or x > 1 for x in values):
        return ["invalid_probability"]
    return ["probabilities_do_not_sum_to_one"] if abs(sum(values) - 1) > tolerance else []


def record_errors(record, receipt, expected_hash):
    errors = []
    try:
        cutoff = utc(record["cutoff_utc"])
        generated = utc(record["generated_utc"])
        finished = utc(record["forecast_finished_utc"])
        if not cutoff - timedelta(minutes=45) <= generated <= finished <= cutoff:
            errors.append("outside_generation_window")
        if receipt is None:
            errors.append("no_independent_push_receipt")
        elif not finished <= utc(receipt) <= cutoff:
            errors.append("push_outside_cutoff_or_before_finish")
        report_time = (record.get("report") or {}).get("retrieved_utc")
        if report_time and utc(report_time) > cutoff:
            errors.append("report_retrieved_after_cutoff")
    except (KeyError, TypeError, ValueError):
        errors.append("invalid_timing_fields")
    if record.get("params_id") != "b" or record.get("params_sha256") != expected_hash:
        errors.append("wrong_parameters")
    pair = record.get("pair_check", {})
    if not pair.get("same_players") or any(pair.get(k, 1) != 0 for k in (
            "max_abs_pi_diff", "max_abs_prob_diff_below_threshold_scaled")):
        errors.append("paired_comparison_mismatch")
    players = record.get("players", [])
    if not players:
        errors.append("empty_forecast")
    if len({(p["team"], p["aid"]) for p in players}) != len(players):
        errors.append("duplicate_player")
    for p in players:
        if not math.isfinite(p["p_appear"]) or not 0 <= p["p_appear"] <= 1:
            errors.append("invalid_appearance_probability")
        for field in ("minutes_v2", "minutes_v3", "reb_v2", "reb_v3", "ast_v2", "ast_v3"):
            errors.extend(field + ":" + e for e in pmf_errors(p.get(field, [])))
    if record.get("unknown_team_values_in_reports"):
        errors.append("unresolved_report_team")
    return sorted(set(errors))


class GitArchive:
    def __init__(self, repo, ref):
        self.repo, self.ref = str(repo), ref

    def git(self, *args):
        return subprocess.check_output(["git", "-C", self.repo, *args])

    def read(self, path):
        data = self.git("show", f"{self.ref}:{path}")
        return json.loads(gzip.decompress(data) if path.endswith(".gz") else data)

    def audit(self):
        paths = self.git("ls-tree", "-r", "--name-only", self.ref, "nba/props_forward").decode().splitlines()
        forecasts = [p for p in paths if p.endswith(".json.gz") and len(p.split("/")) == 4
                     and p.split("/")[2][:4].isdigit()]
        timings = [p for p in paths if "/timing/" in p and p.endswith(".json")]
        pushes = {}
        for p in timings:
            timing = self.read(p)
            # Earliest timing files only contained run records, not push receipts.
            for push in timing.get("pushes", []) if isinstance(timing, dict) else []:
                if push.get("timestamp") and push.get("after"):
                    pushes[(push["timestamp"], push["after"])] = push
        # Ancestor membership is calculated once per receipt, not once per player.
        ancestors = {}
        for _, head in pushes:
            try:
                ancestors[head] = set(self.git("rev-list", head).decode().splitlines())
            except subprocess.CalledProcessError:
                ancestors[head] = set()  # cannot prove -> exclude, never infer
        additions = {}
        commit = None
        history = self.git("log", "--format=COMMIT:%H", "--diff-filter=A", "--name-only",
                           self.ref, "--", "nba/props_forward").decode().splitlines()
        for line in history:
            if line.startswith("COMMIT:"):
                commit = line[7:]
            elif line:
                additions[line] = commit
        # Hash Git's exact bytes: Windows checkout CRLF conversion must not
        # falsely mark the Linux runner's unchanged parameters as different.
        expected_hash = hashlib.sha256(self.git("show", "HEAD:model/nba_props_live_params_2027b.json")).hexdigest()
        records = []
        for index, path in enumerate(forecasts, 1):
            record = self.read(path)
            receipts = [stamp for stamp, head in pushes if additions.get(path) in ancestors[head]]
            receipt = min(receipts, key=utc) if receipts else None
            errors = record_errors(record, receipt, expected_hash)
            # A path must be immutable, otherwise its adding-commit receipt cannot
            # establish when the current contents were available.
            edits = self.git("log", "--format=%H", self.ref, "--", path).decode().splitlines()
            if len(edits) > 1:
                errors.append("forecast_path_modified_after_creation")
            warnings = []
            for team, diag in record.get("report_diagnostics", {}).items():
                status = diag.get("report_status")
                if status in ("not_yet_submitted", "game_not_in_report", "no_report"):
                    warnings.append(f"{team}:report_{status}")
                elif diag.get("empty_team_flag") and status != "submitted_none_listed":
                    warnings.append(f"{team}:empty_report_needs_review")   # older records carry no submission status
                if diag.get("unmatched_names"):
                    warnings.append(f"{team}:unmatched_report_players")
            parsed = record.get("inputs", {}).get("reports_live_parsed", [])
            if any(len(p) != 64 for p in parsed):
                warnings.append("parsed_reports_are_filenames_not_hashes")
            coverage = record.get("coverage", {})
            records.append(dict(path=path, game_id=record["game_id"], horizon_min=record["horizon_min"],
                                generated_utc=record["generated_utc"], cutoff_utc=record["cutoff_utc"],
                                archive_received_utc=receipt, errors=errors, warnings=warnings,
                                players=len(record["players"]), roster=sum(v.get("roster", 0) for v in coverage.values()),
                                code_commit=record.get("code_commit")))
            if index % 20 == 0:
                print(f"Audited {index}/{len(forecasts)} snapshots", flush=True)
        selected = {}
        for r in records:
            key = (r["game_id"], r["horizon_min"])
            if not r["errors"] and (key not in selected or utc(r["generated_utc"]) > utc(selected[key]["generated_utc"])):
                selected[key] = r
        groups = defaultdict(list)
        for r in records:
            groups[(r["game_id"], r["horizon_min"])].append(r)
        return dict(source_commit=self.git("rev-parse", self.ref).decode().strip(),
                    audited_at_utc=datetime.now(timezone.utc).isoformat(), expected_parameter_hash=expected_hash,
                    snapshot_count=len(records), game_horizon_count=len(groups), eligible_game_horizons=len(selected),
                    unqualified_game_horizons=[list(k) for k in groups if k not in selected],
                    selected_player_games_primary=sum(r["players"] for k, r in selected.items() if k[1] == 60),
                    error_counts=dict(Counter(e for r in records for e in r["errors"])),
                    warning_counts=dict(Counter(e for r in records for e in r["warnings"])),
                    selected=list(selected.values()), snapshots=records,
                    limits=["Not an outcome score or evidence of profitability.",
                            "Only observed game/horizon groups audited; missing schedule games require a separate coverage check.",
                            "Input blob contents and latest schedule changes not independently verified by this audit."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--ref", default="origin/forecast-archive")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = GitArchive(args.repo, args.ref).audit()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("selected", "snapshots")}, indent=2))
