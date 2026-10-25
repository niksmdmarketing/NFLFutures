"""Shadow NFL player-prop challenger with correctly aligned opponent volume inputs.

The frozen baseline is generated unchanged by nfl_props.make_forecast(). This module then
recomputes only team-attempt volume and its dependent player count distributions, saving to a
separate archive when requested. It never writes the site's live forecast.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import nfl_props as base
from common import games


def team_states(weekly: pd.DataFrame, current: int) -> dict[str, dict[str, float]]:
    """Build the same two-season, last-20 EWMA state with correctly joined opponent totals."""
    if weekly.empty:
        return {}
    grouped = weekly.groupby(["season", "week", "game_id", "team"], as_index=False).agg(
        attempts=("attempts", "sum"), carries=("carries", "sum"), opponent=("opponent_team", "first")
    )
    # For team A, its allowed value is team B's attempts in the same game.
    allowed = grouped[["season", "week", "game_id", "team", "attempts"]].rename(
        columns={"team": "opponent", "attempts": "allowed"}
    )
    grouped = grouped.merge(allowed, on=["season", "week", "game_id", "opponent"], how="left", validate="one_to_one")
    grouped["plays"] = grouped.attempts + grouped.carries
    result: dict[str, dict[str, float]] = {}
    for team, z in grouped[grouped.season >= current - 1].sort_values(["season", "week"]).groupby("team"):
        z = z.tail(20)
        result[team] = {
            "own_att": base._weighted(z.attempts),
            "allowed": base._weighted(z.allowed.fillna(34)),
            "own_plays": base._weighted(z.plays),
        }
    return result


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def make_challenger(baseline):
    """Recompute the shadow from one already-created frozen baseline snapshot."""
    stamp = pd.Timestamp(baseline["generated_utc"])
    baseline_hashes = {x["path"]: x["sha256"] for x in baseline.get("inputs", [])}
    schedule = base._kickoffs(games())
    schedule_paths = [p for p in baseline_hashes if Path(p).name == "games.csv" and "schedules" in Path(p).parts]
    for p in schedule_paths:
        if _sha(Path(p)) != baseline_hashes[p]:
            raise RuntimeError("Schedule input changed after the baseline forecast was created")
    season = int(schedule[schedule.kickoff <= stamp + pd.Timedelta(days=45)].season.max())
    weekly, weekly_paths = base._weekly(season)
    for p in weekly_paths:
        if p and str(p) in baseline_hashes and _sha(Path(p)) != baseline_hashes[str(p)]:
            raise RuntimeError(f"Weekly statistics changed after the baseline forecast was created: {p}")
    if not weekly.empty:
        # Keep only games whose published result was eligible before this forecast cutoff.
        kickoff = schedule.set_index(schedule.game_id.astype(str)).kickoff
        w = weekly.copy()
        w["game_id"] = w.game_id.astype(str)
        w["kickoff"] = w.game_id.map(kickoff)
        weekly = w[w.kickoff.notna() & (w.kickoff + pd.Timedelta(hours=6) < stamp)].drop(columns="kickoff")
    states = team_states(weekly, season)
    params = json.loads(base.PARAMS.read_text(encoding="utf-8"))
    spec = params["team_attempts"]
    means = dict(zip(spec["features"], spec["mean"]))

    challenger = json.loads(json.dumps(baseline))
    challenger["model_id"] = "nfl-player-props-v1-live-input-alignment-challenger"
    challenger["challenger"] = {
        "baseline_model_id": baseline["model_id"],
        "baseline_forecast_sha256": hashlib.sha256(
            json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "feature_change": "opp_att uses the opponent team's lagged pass attempts allowed, matching the historical training feature.",
        "status": "shadow_only_not_adopted",
        "team_volume_parameters_sha256": _sha(base.PARAMS),
    }
    input_files = list(challenger.get("inputs", []))
    for p in weekly_paths:
        if p and Path(p).exists() and str(p) not in {x["path"] for x in input_files}:
            input_files.append({"path": str(p), "sha256": _sha(Path(p))})
    forward_rule = Path(__file__).resolve().parents[1] / "research" / "nfl_games_props" / "LIVE_INPUT_ALIGNMENT_FORWARD_RULE.md"
    for path in [Path(__file__), forward_rule]:
        input_files.append({"path": str(path), "sha256": _sha(path)})
    challenger["inputs"] = input_files

    for game in challenger["games"]:
        for team_row in game["teams"]:
            team = team_row["team"]
            opponent = game["home"] if team == game["away"] else game["away"]
            own = states.get(team, {})
            opp = states.get(opponent, {})
            features = dict(means)
            features.update({
                "own_att": own.get("own_att", means["own_att"]),
                "opp_att": opp.get("allowed", means["opp_att"]),
                "own_plays": own.get("own_plays", means["own_plays"]),
                "opp_plays": opp.get("own_plays", means["opp_plays"]),
            })
            mu = float(np.clip(base._linear(features, spec), 15, 55))
            volume = base._nb(mu, spec["dispersion"])
            team_row["expected_team_pass_attempts"] = mu
            team_row["volume_features"] = features
            for player in team_row["players"]:
                if player["stat"] == "pass_attempts":
                    pmf = base._allocate(volume, params["starting_qb"]["share"], params["starting_qb"]["concentration"], 70)
                elif player["stat"] == "receptions":
                    pmf = base._allocate(
                        volume,
                        player["effective_target_share"] * player["catch_probability"],
                        params["receiving"]["concentration"],
                        30,
                    )
                else:
                    raise ValueError(f"Unexpected prop in shadow archive: {player['stat']}")
                player.update(base._describe(pmf))
    return challenger


def make_forecast(now=None, availability_store=None):
    # Convenience entry point for standalone local use; scheduled runs pass a saved baseline
    # snapshot through --baseline so both archives share exact forecast inputs and cutoff.
    return make_challenger(base.make_forecast(now=now, availability_store=availability_store))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--availability")
    ap.add_argument("--archive", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--output")
    args = ap.parse_args()
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else base.make_forecast(availability_store=args.availability)
    forecast = make_challenger(baseline)
    if args.output:
        Path(args.output).write_text(json.dumps(forecast, indent=2), encoding="utf-8")
    path = base.archive_forecast(args.archive, forecast)
    print(json.dumps({
        "model_id": forecast["model_id"],
        "generated_utc": forecast["generated_utc"],
        "games": len(forecast["games"]),
        "shadow_archive_file": str(path),
    }, indent=2))


if __name__ == "__main__":
    main()
