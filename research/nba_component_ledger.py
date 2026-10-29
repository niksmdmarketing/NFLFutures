"""Read-only NBA ledger from a private, hashed audit input directory.

Does not download, simulate, write site data, or change model settings. Published
player-mix contributions are explicitly reconstructed from rounded exports;
they are not a fresh RAPM fit. Optional audit dictionaries in nba.py expose the
exact roster/player stages when a future authorised build calls them.
"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import nba as N
import nba_rapm as R
import nba_avail as A


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    inputs = source / "inputs"
    meta = json.loads((source / "nba/data/meta.json").read_text())
    year = int(meta["season"])
    boxes = pd.concat([pd.read_csv(inputs / f"team_box_{y}.csv", low_memory=False)
                       for y in range(year - 4, year + 1)], ignore_index=True)
    fit_boxes = boxes.copy()
    mask = (pd.to_numeric(fit_boxes.season_type) == 3) & (pd.to_numeric(fit_boxes.season) < year)
    fit_boxes.loc[mask, "season_type"] = 2
    ratings, fit = N._fit_ratings(fit_boxes, year)
    prior, _ = N._fit_ratings(fit_boxes[pd.to_numeric(fit_boxes.season) < year], year)
    players = {y: pd.read_csv(inputs / f"player_box_{y}.csv", low_memory=False)
               for y in (year - 2, year - 1, year)}
    values, older = N._player_values(players[year - 1]), N._player_values(players[year - 2])
    old = pd.read_csv(inputs / f"rosters_{year - 1}.csv", low_memory=False)
    new = pd.read_csv(inputs / f"rosters_{year}.csv", low_memory=False)
    gp = float((N._regular_boxes(boxes).season == year).sum()) / len(N.TEAMS)
    saved_override_state = N.OVERRIDES_ON
    try:
        N.OVERRIDES_ON = True
        audit = {}
        adjusted, _ = N._roster_adjustment(ratings, values, old.copy(), new.copy(), older, gp, audit=audit)
        rv = N._roster_values(values, older)
        N.OVERRIDES_ON = False
        no_adjusted, _ = N._roster_adjustment(ratings, values, old.copy(), new.copy(), older, gp)
        no_rv = N._roster_values(values, older)
    finally:
        N.OVERRIDES_ON = saved_override_state
    overrides = json.loads(Path(N.OVERRIDES_PATH).read_text())
    published = {r["team"]: r for r in json.loads((source / "nba/data/futures.json").read_text())["teams"]}
    exported = {r["team"]: r for r in json.loads((source / "nba/data/ratings.json").read_text())["rows"]}
    if set(published) != set(N.TEAMS) or set(exported) != set(N.TEAMS):
        raise ValueError("Published inputs must cover all 30 teams exactly")
    shadow = json.loads((source / "selected_shadow.json").read_text())
    before = prior.set_index("team")
    after = adjusted.set_index("team")
    raw = ratings.set_index("team")
    no_adj = no_adjusted.set_index("team")
    for team in N.TEAMS:
        if abs(float(raw.loc[team].raw_net) - exported[team]["net_rating"]) > 0.051:
            raise ValueError(f"Team fit does not reproduce published input: {team}")
        if abs(float(after.loc[team].roster_adj) - exported[team]["roster_adj"]) > 0.051:
            raise ValueError(f"Roster step does not reproduce published input: {team}")
    share = R.MIX * max(0, 1 - gp / R.MIX_GAMES)
    inj = json.loads((source / "archive/latest.json").read_text())
    capture = inj["collected_utc"]
    date = dt.datetime.strptime(capture, "%Y-%m-%dT%H%MZ").date()
    roster_ids = new.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    member = dict(zip(roster_ids, new.team_abbreviation))
    rows = []
    for team in N.TEAMS:
        r, f = raw.loc[team], published[team]
        sw, si = shadow["without"][team], shadow["with"][team]
        rows.append(dict(team=team, current_games=int(r.current_gp),
                         prior_refit_raw_net=float(before.loc[team].raw_net),
                         current_raw_net=float(r.raw_net),
                         current_results_refit_difference=float(r.raw_net - before.loc[team].raw_net),
                         old_roster_strength=audit["old_strength"][team],
                         new_roster_strength=audit["new_strength"][team],
                         roster_coefficient=audit["coefficient"], roster_adjustment=float(after.loc[team].roster_adj),
                         roster_adjustment_without_overrides=float(no_adj.loc[team].roster_adj),
                         before_player_mix=float(after.loc[team].rating), player_mix_share=share,
                         published_final_rating=f["rating"],
                         player_mix_net_contribution_from_rounded_export=float(f["rating"] - after.loc[team].rating),
                         player_strength_inferred_from_rounded_export=(float(f["rating"] - (1 - share) * after.loc[team].rating) / share if share else None),
                         inferred_strength_rounding_bound=(0.005 / share if share else None),
                         exact_rapm_strength=None, exact_playoff_delta=None,
                         injury_in_published_futures=False,
                         archived_base_expected_wins=sw["mean_wins"],
                         archived_injury_expected_wins=si["mean_wins"],
                         archived_injury_win_change=si["mean_wins"] - sw["mean_wins"],
                         archived_base_playoffs=sw["p_playoff"], archived_injury_playoffs=si["p_playoff"],
                         archive_forecast_time=shadow["t"],
                         reported_absences=sum(1 for x in inj["rows"] if str(x.get("athlete_id")) in member
                                              and member[str(x["athlete_id"]) ] == team)))
    pd.DataFrame(rows).to_csv(output / "teams.csv", index=False)
    new = new.copy()
    new["athlete_id"] = roster_ids
    projected = new.drop_duplicates(["team_abbreviation", "athlete_id"]).merge(rv, on="athlete_id", how="left")
    base = dict(zip(no_rv.athlete_id.astype(str), no_rv.minutes))
    projected["minutes_without_owner_override"] = projected.athlete_id.map(base)
    projected["owner_override"] = projected.athlete_id.isin(overrides["minutes"])
    projected["override_note"] = projected.athlete_id.map(lambda a: overrides["minutes"].get(a, {}).get("note"))
    provenance_path = source / "overrides_audit.json"
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    provenance = {str(r["athlete_id"]): r for r in provenance.get("rows", [])}
    projected["override_date_evidence"] = projected.athlete_id.map(lambda a: json.dumps(provenance.get(a, {})))
    keep = [c for c in ("team_abbreviation", "athlete_id", "display_name", "minutes", "minutes_last", "impact",
                         "minutes_without_owner_override", "owner_override", "override_note", "override_date_evidence") if c in projected]
    projected[keep].to_csv(output / "players.csv", index=False)
    absent = [dict(athlete_id=a, **v) for a, v in overrides["minutes"].items() if a not in member]
    episodes = []
    for x in inj["rows"]:
        if x.get("status") != "Out" or not x.get("return_date"):
            continue
        try:
            days = (dt.date.fromisoformat(str(x["return_date"])[:10]) - date).days
        except ValueError:
            continue
        if days >= 28:
            episodes.append(dict(**x, roster_team=member.get(str(x.get("athlete_id"))),
                                 days_to_estimated_return=days, captured_utc=capture))
    (output / "dated_long_absences.json").write_text(json.dumps(episodes, indent=2))
    evidence = [*inputs.glob("*.csv"), inputs / "manifest.json", source / "selected_shadow.json",
                source / "nba/data/meta.json", source / "nba/data/futures.json", source / "archive/latest.json",
                Path(N.OVERRIDES_PATH), ROOT / "pipeline/nba.py", ROOT / "pipeline/nba_avail.py",
                Path(__file__), *([provenance_path] if provenance_path.exists() else [])]
    manifest = dict(created_utc=dt.datetime.now(dt.timezone.utc).isoformat(), season=year,
                    code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    files={str(p.resolve()): sha(p) for p in evidence}, fit=fit, league_average_games=gp,
                    inactive_current_overrides=absent, team_count=len(rows), player_count=len(projected),
                    retired_overrides=overrides.get("retired_minutes", {}),
                    published_team_and_roster_checks="30/30 agree within exported 0.1-point rounding",
                    limitations=["Prior refit is a diagnostic, not the archived opening-night forecast.",
                                 "Final player contribution uses rounded published ratings; exact RAPM and playoff deltas unavailable in old export.",
                                 "Archived injury differences move every injury together and include simulation noise; not causal player-only effects.",
                                 "Later-retrieved input files are not independently proven available at the archived forecast time.",
                                 "No historical dated-injury validation or adoption decision is possible from these snapshots."],
                    availability_rating_weights=A.RATING_W,
                    team_fit_current_weight=8.0,
                    availability_weight_mismatch=True)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True, help="New private output directory (must not exist)")
    args = parser.parse_args()
    result = build(args.source, args.output)
    print(json.dumps({k: result[k] for k in ("team_count", "player_count", "inactive_current_overrides")}))
