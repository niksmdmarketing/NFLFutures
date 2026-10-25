"""NFL player props v1.1: the live team-volume inputs computed exactly as in the historically tested model.

v1 (nfl-player-props-v1-experimental) set own pass EPA, opponent pass-defence EPA and the Elo gap to their training means and,
through a join bug, used the team's own pass attempts in place of the opponent's attempts allowed. v1.1 computes all seven
team-volume features with the definitions of research/nfl_games_props/build.py (team_pbp and make_game_features): dropback EPA
per game from play-by-play, attempts from weekly player stats, plays from play-by-play, a last-20 exponentially weighted state
over the current and previous season, and the adapted FiveThirtyEight Elo (K20, home edge 65, two-thirds carry-over). A game
enters the state only once kickoff + 6 hours has passed, both before the target's cutoff and before the forecast time.
Parameters, player allocation, availability and distributions are those of v1. Amendment: research/nfl_games_props/RULE.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import nfl_props as base
from common import download

MODEL_ID = "nfl-player-props-v1.1-experimental"
FIX = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "JAC": "JAX"}
EPA = ["pass_off", "rush_off", "pass_def", "rush_def"]


def weighted(values, half=5):
    v = np.asarray(values, float)
    if not len(v):
        return np.nan
    w = .5 ** (np.arange(len(v))[::-1] / half)
    return float(w @ v / w.sum())


def elo_probability(diff):
    return 1 / (1 + 10 ** (-np.asarray(diff) / 400))


def elo_change(diff, margin):
    outcome = 1 if margin > 0 else 0 if margin < 0 else .5
    winner_diff = diff if outcome == 1 else -diff
    mult = np.log(abs(margin) + 1) * 2.2 / (1 if outcome == .5 else winner_diff * .001 + 2.2)
    return 20 * mult * (outcome - float(elo_probability(diff)))


def load_games(raw):
    keep = ["game_id", "season", "week", "game_type", "gameday", "gametime", "home_team", "away_team", "home_score", "away_score", "location"]
    g = raw[keep].copy()
    g = g[(g.game_type == "REG") & (g.season >= 2009)]
    for col in ("home_team", "away_team"):
        g[col] = g[col].replace(FIX)
    tm = pd.to_datetime(g.gameday.astype(str) + " " + g.gametime.fillna("13:00").astype(str))
    g["tip"] = tm.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return g.sort_values(["tip", "game_id"]).reset_index(drop=True)


def team_pbp(path):
    cols = {"game_id", "posteam", "defteam", "epa", "qb_dropback", "rush_attempt", "qb_scramble", "qb_kneel", "pass_attempt", "sack",
            "two_point_attempt", "play_type"}
    x = pd.read_csv(path, usecols=lambda c: c in cols, low_memory=False)
    x = x[x.posteam.notna() & x.epa.notna() & x.play_type.isin(["pass", "run"])].copy()
    if "two_point_attempt" in x:
        x = x[x.two_point_attempt != 1]
    x["posteam"] = x.posteam.replace(FIX)
    x["defteam"] = x.defteam.replace(FIX)
    x["designed"] = (x.rush_attempt == 1) & (x.qb_scramble != 1) & (x.qb_kneel != 1)
    frames = []
    for (gid, team), z in x.groupby(["game_id", "posteam"]):
        pa = z[z.qb_dropback == 1].epa
        ru = z[z.designed].epa
        frames.append(dict(game_id=gid, team=team, pass_off=float(pa.mean()) if len(pa) else 0., rush_off=float(ru.mean()) if len(ru) else 0.,
                           plays=len(z), attempts=int(((z.pass_attempt == 1) & (z.sack != 1)).sum())))
    a = pd.DataFrame(frames)
    defs = []
    for (gid, team), z in x.groupby(["game_id", "defteam"]):
        pa = z[z.qb_dropback == 1].epa
        ru = z[z.designed].epa
        defs.append(dict(game_id=gid, team=team, pass_def=float(pa.mean()) if len(pa) else 0., rush_def=float(ru.mean()) if len(ru) else 0.))
    if a.empty:
        return pd.DataFrame(columns=["game_id", "team", *EPA, "plays", "attempts"])
    return a.merge(pd.DataFrame(defs), on=["game_id", "team"], validate="one_to_one")


def team_features(g, agg, totals, now=None):
    """make_game_features from the research build, team rows only; `now` additionally caps what has been observed.
    Returns a DataFrame with one row per (game, team): own_att, opp_att, own_plays, opp_plays, own_pass_off, opp_pass_def, elo_gap."""
    tg = {(r.game_id, r.team): r for r in agg.itertuples()}
    history = defaultdict(list)
    elos = defaultdict(lambda: 1500.)
    seasons = {}
    pending = []
    teams = []

    def flush(cut):
        nonlocal pending
        remain = []
        for old in pending:
            if old["ready"] >= cut:
                remain.append(old)
                continue
            for team, opp, side in [(old["home"], old["away"], "h"), (old["away"], old["home"], "a")]:
                r = tg.get((old["game_id"], team))
                if r:
                    o = tg.get((old["game_id"], opp))
                    history[team].append(dict(season=old["season"], **{k: getattr(r, k) for k in EPA},
                                              attempts=totals.get((old["game_id"], team), r.attempts),
                                              allowed=totals.get((old["game_id"], opp), getattr(o, "attempts", 35)),
                                              plays=r.plays, points=old[side + "_points"]))
            change = elo_change(old["elo_diff"], old["h_points"] - old["a_points"])
            elos[old["home"]] += change
            elos[old["away"]] -= change
        pending = remain

    def state(team, year):
        h = [r for r in history[team] if r["season"] >= year - 1][-20:]
        return {k: weighted([r[k] for r in h]) if h else (0. if k in EPA else 35. if k in ("attempts", "allowed") else 64. if k == "plays" else 22.)
                for k in [*EPA, "attempts", "allowed", "plays", "points"]}

    for row in g.itertuples():
        cut = row.tip - pd.Timedelta(hours=1)
        flush(min(cut, now) if now is not None else cut)
        for team in (row.home_team, row.away_team):
            if team in seasons and seasons[team] != row.season:
                elos[team] = 1505 / 3 + elos[team] * 2 / 3
            seasons[team] = row.season
        h = state(row.home_team, row.season)
        a = state(row.away_team, row.season)
        diff = elos[row.home_team] - elos[row.away_team] + (0 if str(row.location).lower() == "neutral" else 65)
        for team, opp, s, o, sign in [(row.home_team, row.away_team, h, a, 1), (row.away_team, row.home_team, a, h, -1)]:
            teams.append(dict(game_id=row.game_id, team=team, opp=opp, season=row.season, week=row.week, tip=row.tip,
                              own_att=s["attempts"], opp_att=o["allowed"], own_plays=s["plays"], opp_plays=o["plays"],
                              own_pass_off=s["pass_off"], opp_pass_def=o["pass_def"], elo_gap=sign * diff / 400))
        if pd.notna(row.home_score) and pd.notna(row.away_score) and (now is None or row.tip + pd.Timedelta(hours=6) < now):
            pending.append(dict(game_id=row.game_id, home=row.home_team, away=row.away_team, season=row.season,
                                ready=row.tip + pd.Timedelta(hours=6), h_points=row.home_score, a_points=row.away_score, elo_diff=diff))
    return pd.DataFrame(teams)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def live_features(stamp, season):
    """Download/reuse the nflverse files and compute the features for every game, observing only what had finished by `stamp`."""
    sched_path = download("schedules/games.csv", max_age_h=.2)
    g = load_games(pd.read_csv(sched_path, low_memory=False))
    g = g[g.season <= season]
    paths = [sched_path]
    agg, totals = [], {}
    for y in (season - 1, season):
        p = download(f"pbp/play_by_play_{y}.csv.gz", required=(y < season), max_age_h=.2 if y == season else 24 * 365)
        if p:
            agg.append(team_pbp(p))
            paths.append(p)
        s = download(f"stats_player/stats_player_week_{y}.csv", required=False, max_age_h=.2 if y == season else 24 * 365)
        if s:
            z = pd.read_csv(s, usecols=["game_id", "season_type", "team", "attempts"], low_memory=False)
            z = z[z.season_type == "REG"].copy()
            z["team"] = z.team.replace(FIX)
            totals.update(z.groupby(["game_id", "team"]).attempts.sum().to_dict())
            paths.append(s)
    agg = pd.concat(agg, ignore_index=True) if agg else pd.DataFrame(columns=["game_id", "team", *EPA, "plays", "attempts"])
    feats = team_features(g, agg, totals, now=stamp)
    return feats, paths


def make_v11(baseline, feats=None, paths=()):
    """v1.1 from a v1 forecast made at the same time: identical players, availability and allocation; team volume recomputed."""
    stamp = pd.Timestamp(baseline["generated_utc"])
    if feats is None:
        sched = base._kickoffs(base.games())
        season = int(sched[sched.kickoff <= stamp + pd.Timedelta(days=45)].season.max())
        feats, paths = live_features(stamp, season)
    params = json.loads(base.PARAMS.read_text(encoding="utf-8"))
    spec = params["team_attempts"]
    idx = {(str(r.game_id), r.team): r for r in feats.itertuples()}
    out = json.loads(json.dumps(baseline))
    out["model_id"] = MODEL_ID
    out["v11"] = {"baseline_model_id": baseline["model_id"],
                  "baseline_forecast_sha256": hashlib.sha256(json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "change": "All seven team-volume features computed as in the historically tested model (opponent attempts allowed, "
                            "pass EPA, opponent pass-defence EPA, Elo gap); v1 used neutral values and a join bug.",
                  "parameters_sha256": _sha(base.PARAMS), "code_sha256": _sha(__file__)}
    out["inputs"] = list(out.get("inputs", [])) + [{"path": str(p), "sha256": _sha(p)} for p in paths if p and Path(p).exists()]
    missing = []
    for game in out["games"]:
        for team_row in game["teams"]:
            r = idx.get((str(game["game_id"]), team_row["team"]))
            if r is None:
                missing.append([game["game_id"], team_row["team"]])
                continue
            features = {k: float(getattr(r, k)) for k in spec["features"]}
            mu = float(np.clip(base._linear(features, spec), 15, 55))
            volume = base._nb(mu, spec["dispersion"])
            team_row["expected_team_pass_attempts"] = mu
            team_row["volume_features"] = features
            for player in team_row["players"]:
                if player["stat"] == "pass_attempts":
                    pmf = base._allocate(volume, params["starting_qb"]["share"], params["starting_qb"]["concentration"], 70)
                elif player["stat"] == "receptions":
                    pmf = base._allocate(volume, player["effective_target_share"] * player["catch_probability"], params["receiving"]["concentration"], 30)
                else:
                    raise ValueError(f"Unexpected prop: {player['stat']}")
                player.update(base._describe(pmf))
    if missing:
        raise RuntimeError(f"v1.1 features missing for {missing[:5]} (no silent fallback to v1)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--archive")
    ap.add_argument("--output")
    a = ap.parse_args()
    f = make_v11(json.loads(Path(a.baseline).read_text(encoding="utf-8")))
    if a.output:
        Path(a.output).write_text(json.dumps(f, indent=2), encoding="utf-8")
    if a.archive:
        print(base.archive_forecast(a.archive, f))
    print(json.dumps({"model_id": f["model_id"], "generated_utc": f["generated_utc"], "games": len(f["games"])}))


if __name__ == "__main__":
    main()
