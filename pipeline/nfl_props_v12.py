"""NFL player props v1.2 matchup shadow (not displayed): v1.1 plus the opponent position-matchup target factor.

Pre-registered and historically tested in research/nfl_games_props/MATCHUP_RULE.md (passed 26 Oct 2026). Each receiver's
conditional target share is multiplied by f = clip(r^beta, cap), where r is the opponent defence's shrunk ratio of targets
allowed to the receiver's position group (WR; TE; RB+FB) against the league share. Then the participation-weighted budget is
recomputed as in v1, and receptions are allocated from v1.1's team-attempt distribution. Frozen settings:
pipeline/nfl_props_v12_params.json. A defence game counts only once kickoff + 6 hours precedes both the target game's cutoff
(kickoff - 1 hour) and the forecast time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import nfl_props as base
import nfl_props_v11 as v11
from common import download

MODEL_ID = "nfl-player-props-v1.2-matchup-shadow"
PARAMS12 = Path(__file__).resolve().parent / "nfl_props_v12_params.json"


def defence_table(stats, games):
    """Targets allowed per (game, defence) to each group. stats: game_id, team, position, targets. games: v11.load_games output."""
    groups = {"WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB"}
    s = stats[stats.position.isin(groups)].copy()
    s["grp"] = s.position.map(groups)
    t = s.groupby(["game_id", "team", "grp"]).targets.sum().unstack(fill_value=0).reset_index()
    for c in ("WR", "TE", "RB"):
        if c not in t:
            t[c] = 0
    t = t.merge(games[["game_id", "season", "tip", "home_team", "away_team"]], on="game_id", validate="many_to_one")
    t["defence"] = np.where(t.team == t.home_team, t.away_team, t.home_team)
    t["total"] = t.WR + t.TE + t.RB
    return t[["game_id", "season", "tip", "defence", "WR", "TE", "RB", "total"]].sort_values("tip").reset_index(drop=True)


def factor(dtab, defence, position, tip, season, now, p):
    grp = p["groups"].get(position)
    if grp is None:
        return 1.0
    cut = min(tip - pd.Timedelta(hours=1), now)
    h = dtab[(dtab.defence == defence) & (dtab.tip + pd.Timedelta(hours=6) < cut) & (dtab.season >= season - 1)].tail(p["window_games"])
    if not len(h):
        return 1.0
    w = .5 ** (np.arange(len(h))[::-1] / p["half_life"])
    L, k = p["league_shares"][grp], p["k_pseudo_targets"]
    r = ((float(w @ h[grp].to_numpy(float)) + k * L) / (float(w @ h.total.to_numpy(float)) + k)) / L
    return float(np.clip(r ** p["beta"], *p["cap"]))


def live_inputs(season):
    sched = download("schedules/games.csv", max_age_h=.2)
    g = v11.load_games(pd.read_csv(sched, low_memory=False))
    frames, paths = [], [sched]
    for y in (season - 1, season):
        s = download(f"stats_player/stats_player_week_{y}.csv", required=False, max_age_h=.2 if y == season else 24 * 365)
        if s:
            z = pd.read_csv(s, usecols=["game_id", "season_type", "team", "position", "targets"], low_memory=False)
            z = z[z.season_type == "REG"].copy()
            z["team"] = z.team.replace(v11.FIX)
            frames.append(z)
            paths.append(s)
    stats = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["game_id", "team", "position", "targets"])
    return g, defence_table(stats, g), paths


def make_v12(v11_forecast, g=None, dtab=None, paths=()):
    now = pd.Timestamp(v11_forecast["generated_utc"])
    p = json.loads(PARAMS12.read_text(encoding="utf-8"))
    params = json.loads(base.PARAMS.read_text(encoding="utf-8"))
    if dtab is None:
        sched = base._kickoffs(base.games())
        season = int(sched[sched.kickoff <= now + pd.Timedelta(days=45)].season.max())
        g, dtab, paths = live_inputs(season)
    season_of = dict(zip(g.game_id, g.season))
    out = json.loads(json.dumps(v11_forecast))
    out["model_id"] = MODEL_ID
    out["displayed"] = False
    out["v12"] = {"base_model_id": v11_forecast["model_id"],
                  "base_forecast_sha256": hashlib.sha256(json.dumps(v11_forecast, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "change": "Receiver target shares multiplied by the opponent position-matchup factor (MATCHUP_RULE.md).",
                  "settings_sha256": v11._sha(PARAMS12), "code_sha256": v11._sha(__file__)}
    out["inputs"] = list(out.get("inputs", [])) + [{"path": str(x), "sha256": v11._sha(x)} for x in paths if x and Path(x).exists()]
    for game in out["games"]:
        tip = pd.Timestamp(game["kickoff_utc"])
        season = int(season_of.get(game["game_id"], tip.year))
        for team_row in game["teams"]:
            opp = game["home"] if team_row["team"] == game["away"] else game["away"]
            rec = [x for x in team_row["players"] if x["stat"] == "receptions"]
            for x in rec:
                x["matchup_factor"] = factor(dtab, opp, x["position"], tip, season, now, p)
                x["matchup_target_share"] = x["conditional_target_share"] * x["matchup_factor"]
            budget = sum(x["availability_probability"] * x["matchup_target_share"] for x in rec)
            team_row["expected_active_target_budget"] = budget
            volume = base._nb(team_row["expected_team_pass_attempts"], params["team_attempts"]["dispersion"])
            for x in rec:
                denom = budget + (1 - x["availability_probability"]) * x["matchup_target_share"]
                eff = x["matchup_target_share"] * min(1.0, 1.0 / max(denom, 1e-12))
                x["effective_target_share"] = eff
                x.update(base._describe(base._allocate(volume, eff * x["catch_probability"], params["receiving"]["concentration"], 30)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v11", required=True)
    ap.add_argument("--archive")
    ap.add_argument("--output")
    a = ap.parse_args()
    f = make_v12(json.loads(Path(a.v11).read_text(encoding="utf-8")))
    if a.output:
        Path(a.output).write_text(json.dumps(f, indent=2), encoding="utf-8")
    if a.archive:
        print(base.archive_forecast(a.archive, f))
    fs = [x["matchup_factor"] for gm in f["games"] for t in gm["teams"] for x in t["players"] if "matchup_factor" in x]
    print(json.dumps({"model_id": f["model_id"], "games": len(f["games"]), "receivers": len(fs),
                      "factor_range": [min(fs), max(fs)] if fs else None}))


if __name__ == "__main__":
    main()
