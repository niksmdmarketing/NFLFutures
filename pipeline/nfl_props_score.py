"""Score genuinely pre-cutoff NFL player forecasts from the append-only archive."""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from common import FIX, download, games


def receipt(root, rel):
    try:
        s = subprocess.check_output(["git", "-C", str(root), "log", "--diff-filter=A", "-1", "--format=%cI", "--", rel], text=True).strip()
        return pd.Timestamp(s).tz_convert("UTC") if s else None
    except Exception:
        return None


def rps(p, y):
    p = np.asarray(p, float); end = len(p) - 1; y = int(np.clip(y, 0, end))
    return float(np.mean((np.cumsum(p)[:-1] - (y <= np.arange(end))) ** 2))


def choose(root, horizon):
    rows = [json.loads(x) for x in (root / "index.jsonl").read_text().splitlines() if x.strip()]
    out = {}
    for x in rows:
        cut = pd.Timestamp(x["kickoff_utc"]) - pd.Timedelta(minutes=horizon)
        rec = receipt(root, x["file"])
        if rec is None or rec > cut:
            continue
        key = x["game_id"]
        if key not in out or rec > out[key][0]: out[key] = (rec, x)
    return out


def prepare_outcomes(stats, snaps, players, schedule, season):
    """Build labels only for final games with both teams represented in both feeds."""
    z = stats[stats.season_type.eq("REG")].copy()
    z["game_id"] = z.game_id.astype(str); z["team"] = z.team.replace(FIX).astype(str)
    stat = {(str(r.game_id), str(r.team), str(r.player_id)): r for r in z.itertuples()}
    stat_teams = set(zip(z.game_id, z.team))

    p = players.copy()
    p["pfr_id"] = p.pfr_id.astype("string"); p["gsis_id"] = p.gsis_id.astype("string")
    counts = p.dropna(subset=["pfr_id", "gsis_id"]).groupby("pfr_id").gsis_id.nunique()
    unique = p[p.pfr_id.isin(counts[counts.eq(1)].index)].drop_duplicates("pfr_id")
    mapper = unique.set_index("pfr_id").gsis_id
    mapped_players = set(mapper.dropna().astype(str))

    s = snaps.copy()
    if "game_type" in s: s = s[s.game_type.eq("REG")]
    s["game_id"] = s.game_id.astype(str); s["team"] = s.team.replace(FIX).astype(str)
    s["aid"] = s.pfr_player_id.astype("string").map(mapper)
    snap_teams = set(zip(s.game_id, s.team))
    appeared = {
        (str(r.game_id), str(r.team), str(r.aid))
        for r in s.itertuples()
        if pd.notna(r.aid) and pd.notna(r.offense_snaps) and float(r.offense_snaps) > 0
    }

    sch = schedule[schedule.season.eq(season) & schedule.game_type.eq("REG")].copy()
    sch["game_id"] = sch.game_id.astype(str)
    sch["home_team"] = sch.home_team.replace(FIX).astype(str)
    sch["away_team"] = sch.away_team.replace(FIX).astype(str)
    final = sch[sch.home_score.notna() & sch.away_score.notna()]
    complete_games = set()
    for row in final.itertuples():
        teams = {(str(row.game_id), str(row.home_team)), (str(row.game_id), str(row.away_team))}
        if teams.issubset(stat_teams) and teams.issubset(snap_teams):
            complete_games.add(str(row.game_id))
    return {"stat": stat, "appeared": appeared, "complete_games": complete_games,
            "mapped_players": mapped_players}


def outcomes(season):
    stats = pd.read_csv(download(f"stats_player/stats_player_week_{season}.csv", max_age_h=.2), low_memory=False)
    players = pd.read_csv(download("players/players.csv", max_age_h=24 * 7), low_memory=False, dtype=str)
    snaps = pd.read_csv(download(f"snap_counts/snap_counts_{season}.csv", max_age_h=.2), low_memory=False)
    return prepare_outcomes(stats, snaps, players, games(), season)


def player_outcome(game_id, team, player, labels):
    """Return an availability label and a conditional stat result when known."""
    player_id = str(player["player_id"])
    if player_id not in labels["mapped_players"]:
        return None, None, "availability_unmapped"
    key = (str(game_id), str(team), player_id)
    appeared = int(key in labels["appeared"])
    if not appeared:
        return 0, None, "did_not_appear"
    actual = labels["stat"].get(key)
    column = "attempts" if player["stat"] == "pass_attempts" else "receptions"
    # prepare_outcomes includes only complete game/team feeds. A missing stat row for
    # a confirmed appearance therefore means zero for this stat.
    value = 0 if actual is None else int(getattr(actual, column) or 0)
    return 1, value, "scored"


def score(root, horizon, output):
    root = Path(root); selected = choose(root, horizon)
    # The archive itself determines the scored season.  Do not accidentally select a
    # future schedule season merely because nflverse has already published it.
    seasons = []
    for _, idx in selected.values():
        gid = str(idx["game_id"])
        if len(gid) >= 4 and gid[:4].isdigit(): seasons.append(int(gid[:4]))
    if not seasons:
        raise ValueError("No independently received pre-cutoff forecasts are available to score")
    season = max(seasons)
    labels = outcomes(season); rows = []; missing = []; unresolved_availability = 0
    for gid, (rec, idx) in selected.items():
        if gid not in labels["complete_games"]: continue
        snap = json.loads((root / idx["file"]).read_text())
        game = next(g for g in snap["games"] if g["game_id"] == gid)
        for team in game["teams"]:
            for p in team["players"]:
                app, y, outcome_status = player_outcome(gid, team["team"], p, labels)
                if app is None: unresolved_availability += 1
                row = {"game_id": gid, "team": team["team"], "player_id": p["player_id"], "name": p["name"], "stat": p["stat"],
                       "horizon_minutes": horizon, "receipt_utc": rec.isoformat(), "kickoff_utc": game["kickoff_utc"],
                       "appearance_probability": p["availability_probability"], "appeared": app,
                       "appearance_brier": (p["availability_probability"] - app) ** 2 if app is not None else None,
                       "actual": y, "outcome_status": outcome_status,
                       "conditional_rps": rps(p["pmf"], y) if app == 1 and y is not None else None}
                rows.append(row)
                if app == 1 and y is None: missing.append(key)
    frame = pd.DataFrame(rows)
    by_stat = {}
    for stat, group in frame.groupby("stat") if len(frame) else []:
        brier = group.appearance_brier.dropna(); conditional = group.conditional_rps.dropna()
        by_stat[stat] = {"players": int(len(group)), "availability_scored": int(len(brier)),
                         "appearance_brier": float(brier.mean()) if len(brier) else None,
                         "appeared_players_scored": int(len(conditional)),
                         "mean_conditional_rps": float(conditional.mean()) if len(conditional) else None}
    n_games = len(set(frame.game_id)) if len(frame) else 0
    summary = {"horizon_minutes": horizon, "eligible_games": n_games,
               "pending_or_incomplete_games": len(selected) - n_games,
               "players": len(frame), "availability_scored": int(frame.appearance_brier.notna().sum()) if len(frame) else 0,
               "unresolved_availability": unresolved_availability,
               "appeared_players_scored": int(frame.conditional_rps.notna().sum()) if len(frame) else 0,
               "mean_conditional_rps": float(frame.conditional_rps.mean()) if len(frame) and frame.conditional_rps.notna().any() else None,
               "appearance_brier": float(frame.appearance_brier.mean()) if len(frame) and frame.appearance_brier.notna().any() else None,
               "missing_outcomes": len(missing), "by_stat": by_stat,
               "note": "Only final games with both teams in the stats and snap feeds are scored. Appearance is scored only for uniquely mapped players; conditional stat scores are limited to confirmed appearances."}
    Path(output).parent.mkdir(parents=True, exist_ok=True); Path(output).write_text(json.dumps({"summary": summary, "rows": frame.replace({np.nan: None}).to_dict("records")}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("archive"); ap.add_argument("--horizon", type=int, choices=[60, 360], default=60); ap.add_argument("--output", required=True)
    a = ap.parse_args(); score(a.archive, a.horizon, a.output)
