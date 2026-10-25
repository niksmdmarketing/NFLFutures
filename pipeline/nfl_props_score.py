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


def outcomes(season):
    p = download(f"stats_player/stats_player_week_{season}.csv", max_age_h=.2)
    z = pd.read_csv(p, low_memory=False); z = z[z.season_type.eq("REG")].copy(); z["team"] = z.team.replace(FIX)
    stat = {(str(r.game_id), str(r.team), str(r.player_id)): r for r in z.itertuples()}
    players = pd.read_csv(download("players/players.csv", max_age_h=24 * 7), low_memory=False, dtype=str)
    cnt = players.groupby("pfr_id").gsis_id.nunique(); mapper = players[players.pfr_id.isin(cnt[cnt.eq(1)].index)].drop_duplicates("pfr_id").set_index("pfr_id").gsis_id
    s = pd.read_csv(download(f"snap_counts/snap_counts_{season}.csv", max_age_h=.2), low_memory=False)
    if "game_type" in s: s = s[s.game_type.eq("REG")]
    s["team"] = s.team.replace(FIX); s["aid"] = s.pfr_player_id.map(mapper)
    appeared = {(str(r.game_id), str(r.team), str(r.aid)) for r in s.itertuples() if pd.notna(r.aid) and float(r.offense_snaps or 0) > 0}
    done = set(z.game_id.astype(str))
    return stat, appeared, done


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
    stat, appeared, done = outcomes(season); rows = []; missing = []
    for gid, (rec, idx) in selected.items():
        if gid not in done: continue
        snap = json.loads((root / idx["file"]).read_text())
        game = next(g for g in snap["games"] if g["game_id"] == gid)
        for team in game["teams"]:
            for p in team["players"]:
                key = (gid, team["team"], str(p["player_id"])); app = int(key in appeared)
                actual = stat.get(key)
                y = None if actual is None else int(getattr(actual, "attempts" if p["stat"] == "pass_attempts" else "receptions") or 0)
                row = {"game_id": gid, "team": team["team"], "player_id": p["player_id"], "name": p["name"], "stat": p["stat"],
                       "horizon_minutes": horizon, "receipt_utc": rec.isoformat(), "kickoff_utc": game["kickoff_utc"],
                       "appearance_probability": p["availability_probability"], "appeared": app,
                       "appearance_brier": (p["availability_probability"] - app) ** 2,
                       "actual": y, "conditional_rps": rps(p["pmf"], y) if app and y is not None else None}
                rows.append(row)
                if app and y is None: missing.append(key)
    frame = pd.DataFrame(rows)
    summary = {"horizon_minutes": horizon, "eligible_games": len(set(frame.game_id)) if len(frame) else 0,
               "players": len(frame), "appeared_players_scored": int(frame.conditional_rps.notna().sum()) if len(frame) else 0,
               "mean_conditional_rps": float(frame.conditional_rps.mean()) if len(frame) and frame.conditional_rps.notna().any() else None,
               "appearance_brier": float(frame.appearance_brier.mean()) if len(frame) else None,
               "missing_outcomes": len(missing), "note": "Reception/attempt distributions are scored conditional on appearing; availability is scored separately."}
    Path(output).parent.mkdir(parents=True, exist_ok=True); Path(output).write_text(json.dumps({"summary": summary, "rows": frame.replace({np.nan: None}).to_dict("records")}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("archive"); ap.add_argument("--horizon", type=int, choices=[60, 360], default=60); ap.add_argument("--output", required=True)
    a = ap.parse_args(); score(a.archive, a.horizon, a.output)
