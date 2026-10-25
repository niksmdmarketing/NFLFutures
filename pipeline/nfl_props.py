"""Experimental NFL QB-attempt and reception forecasts.

The production path deliberately keeps three things separate:
  * role (starter/depth chart and target share),
  * production (catch probability), and
  * availability (timestamped official/reporting inputs).

The model never reads betting prices.  Forecast snapshots are create-only; the website reads a
small display copy of the newest snapshot while the archive retains full discrete distributions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import betabinom, nbinom

from common import DATA, FIX, MODEL, OUT, download, games, log, write_json

ROOT = Path(__file__).resolve().parents[1]
PARAMS = Path(MODEL) / "nfl_player_props_v1.json"
POSITIONS = {"WR", "TE", "RB", "FB"}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _norm(x):
    x = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", str(x or ""), flags=re.I)
    return re.sub(r"[^a-z]", "", x.lower())


def _utc(x):
    t = pd.Timestamp(x)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _kickoffs(g):
    x = g.copy()
    clock = x.gametime.fillna("13:00") if "gametime" in x else "13:00"
    local = pd.to_datetime(x.gameday.astype(str) + " " + clock.astype(str), errors="coerce")
    x["kickoff"] = local.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return x


def _weighted(values, half=5):
    a = np.asarray(list(values), float)
    if not len(a):
        return np.nan
    w = 0.5 ** (np.arange(len(a))[::-1] / half)
    return float(w @ a / w.sum())


def _nb(mu, dispersion, end=100):
    k = np.arange(end + 1)
    p = nbinom.pmf(k, dispersion, dispersion / (dispersion + max(mu, 1e-9)))
    p[-1] += max(0.0, 1.0 - p.sum())
    return p / p.sum()


def _allocate(volume, probability, concentration, end):
    out = np.zeros(end + 1)
    probability = float(np.clip(probability, 1e-6, 1 - 1e-6))
    for n, w in enumerate(volume):
        hi = min(n, end)
        k = np.arange(hi + 1)
        q = betabinom.pmf(k, n, probability * concentration, (1 - probability) * concentration)
        if n > end:
            q[-1] = betabinom.sf(end - 1, n, probability * concentration, (1 - probability) * concentration)
        out[:hi + 1] += w * q
    return out / out.sum()


def _describe(p):
    k = np.arange(len(p)); c = np.cumsum(p); mean = float(k @ p)
    line = min(math.floor(mean) + 0.5, len(p) - 1.5)
    return {"mean": mean, "median": int(np.searchsorted(c, .5)),
            "interval80": [int(np.searchsorted(c, .1)), int(np.searchsorted(c, .9))],
            "illustrative_line": line, "over_probability": float(p[k > line].sum()),
            "zero_probability": float(p[0]), "pmf": [float(v) for v in p]}


def _linear(row, spec):
    x = np.array([row.get(c, 0.0) for c in spec["features"]], float)
    z = (x - np.array(spec["mean"])) / np.array(spec["scale"])
    return float(np.exp(spec["intercept"] + z @ np.array(spec["coef"])))


def _latest_depth(season):
    p = download(f"depth_charts/depth_charts_{season}.csv", required=False, max_age_h=.20)
    if not p:
        return pd.DataFrame(), None
    d = pd.read_csv(p, low_memory=False, dtype={"gsis_id": str})
    d["team"] = d.team.replace(FIX); d["dt"] = pd.to_datetime(d.dt, utc=True, errors="coerce")
    d = d[d.dt == d.groupby("team").dt.transform("max")]
    d = d[d.gsis_id.notna()].sort_values(["team", "pos_abb", "pos_rank"]).drop_duplicates(["team", "gsis_id"])
    return d, p


def _weekly(season):
    frames = []
    paths = []
    for y in (season - 1, season):
        p = download(f"stats_player/stats_player_week_{y}.csv", required=False, max_age_h=.20 if y == season else 24 * 365)
        if not p:
            continue
        paths.append(p)
        z = pd.read_csv(p, low_memory=False)
        z = z[z.season_type.eq("REG")].copy(); z["team"] = z.team.replace(FIX)
        if "opponent_team" in z: z["opponent_team"] = z.opponent_team.replace(FIX)
        frames.append(z)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), paths


def _snaps(season):
    mp = download("players/players.csv", max_age_h=24 * 7)
    ids = pd.read_csv(mp, low_memory=False, dtype=str)
    counts = ids.groupby("pfr_id").gsis_id.nunique()
    mapper = ids[ids.pfr_id.isin(counts[counts.eq(1)].index)].drop_duplicates("pfr_id").set_index("pfr_id").gsis_id
    out = []
    paths = [mp]
    for y in (season - 1, season):
        p = download(f"snap_counts/snap_counts_{y}.csv", required=False, max_age_h=.20 if y == season else 24 * 365)
        if not p: continue
        s = pd.read_csv(p, low_memory=False); paths.append(p)
        if "game_type" in s: s = s[s.game_type.eq("REG")]
        s["team"] = s.team.replace(FIX); s["aid"] = s.pfr_player_id.map(mapper)
        s = s[s.aid.notna()].copy(); out.append(s)
    return (pd.concat(out, ignore_index=True) if out else pd.DataFrame()), paths


def _team_states(w, current):
    if w.empty: return {}
    t = w.groupby(["season", "week", "game_id", "team"], as_index=False).agg(
        attempts=("attempts", "sum"), carries=("carries", "sum"), opponent=("opponent_team", "first"))
    allowed = t[["season", "week", "game_id", "opponent", "attempts"]].rename(columns={"attempts": "allowed"})
    t = t.merge(allowed, on=["season", "week", "game_id", "opponent"], how="left")
    t["plays"] = t.attempts + t.carries
    state = {}
    for team, z in t[t.season >= current - 1].sort_values(["season", "week"]).groupby("team"):
        z = z.tail(20)
        state[team] = {"own_att": _weighted(z.attempts), "opp_att": _weighted(z.allowed.fillna(34)),
                       "own_plays": _weighted(z.plays), "opp_plays": 63.0,
                       "own_pass_off": 0.0, "opp_pass_def": 0.0, "elo_gap": 0.0}
    return state


def _player_history(w, snaps, aid, team, season):
    z = w[(w.player_id.astype(str) == str(aid)) & (w.team == team) & (w.season >= season - 1)].sort_values(["season", "week"])
    apps = z[(z.attempts.fillna(0) > 0) | (z.targets.fillna(0) > 0) | (z.receptions.fillna(0) > 0)]
    # Snap rows preserve zero-stat appearances, so use them for availability and merge stat rates separately.
    s = snaps[(snaps.aid.astype(str) == str(aid)) & (snaps.team == team)].sort_values(["season", "week"]).tail(8) if not snaps.empty else pd.DataFrame()
    snap_values = s.offense_pct.fillna(0).astype(float).tolist() if len(s) else []
    app_rate = float(np.mean(np.array(snap_values) > 0)) if snap_values else .5
    miss = 0
    for v in reversed(snap_values):
        if v > 0: break
        miss += 1
    last_snap = snap_values[-1] if snap_values else 0.0
    mean_snap = _weighted(snap_values, 4) if snap_values else 0.0
    a = apps.tail(8)
    weights = .5 ** (np.arange(len(a))[::-1] / 4) if len(a) else np.array([])
    team_games = w[(w.team == team) & (w.season >= season - 1)].groupby(["season", "week", "game_id"]).attempts.sum().reset_index()
    if len(a):
        joined = a.merge(team_games, on=["season", "week", "game_id"], suffixes=("", "_team"))
        weights = .5 ** (np.arange(len(joined))[::-1] / 4)
        target = float(np.sum(weights * joined.targets.fillna(0)));
        rec = float(np.sum(weights * joined.receptions.fillna(0)));
        team_att = float(np.sum(weights * joined.attempts_team.fillna(0)))
    else: target = rec = team_att = 0.0
    return {"app_rate": app_rate, "last_snap_share": last_snap, "mean_snap_share": mean_snap,
            "miss_streak": miss, "target": target, "receptions": rec, "team_att": team_att,
            "history_games": int(len(apps))}


def _appearance(h, position, params):
    a = params["appearance"]
    if not a.get("coef"):
        # Honest fallback if the frozen classifier is unavailable: only historical participation, no invented certainty.
        return float(np.clip(.15 + .8 * h["app_rate"], .05, .98))
    x = np.array([h[f] if f != "is_qb" else int(position == "QB") for f in a["features"]], float)
    z = (x - np.array(a["mean"])) / np.array(a["scale"])
    eta = float(a["intercept"] + z @ np.array(a["coef"]))
    return 1 / (1 + math.exp(-np.clip(eta, -30, 30)))


def _availability(store):
    records = []
    used = []
    if not store: return records, used
    store = Path(store)
    latest = store / "availability" / "nfl" / "latest.json"
    if latest.exists():
        records += json.loads(latest.read_text(encoding="utf-8"))["records"]; used.append(latest)
    state = store / "state.json"
    if state.exists():
        st = json.loads(state.read_text(encoding="utf-8")); rp = store / st.get("report_file", "")
        if rp.exists():
            report = json.loads(rp.read_text(encoding="utf-8")); used += [state, rp]
            for r in report.get("rows", []):
                records.append({"league": "nfl", "layer": "official", "kind": "injury_report", "team": r.get("team"),
                    "player": r.get("player"), "player_id": "nfl:" + str(r.get("player_id")),
                    "status": r.get("game_status") or "no designation", "practice": r.get("practice_status"),
                    "published_utc": report.get("observed_at"), "source": "NFL official injury report"})
    return records, used


def _matched(records, team, name, season=None, week=None):
    matched = []
    for r in records:
        if r.get("team") != team or _norm(r.get("player")) != _norm(name) or r.get("stale"):
            continue
        affected = str(r.get("affected_game") or "")
        m = re.search(r"(\d{4})\s+week\s+(\d+)", affected, re.I)
        if m and season is not None and week is not None and (int(m.group(1)), int(m.group(2))) != (int(season), int(week)):
            continue
        matched.append(r)
    return matched


def _designation(records, team, name, season=None, week=None):
    """Display category from the latest status (26 Oct 2026, page shows 'if he plays' forecasts for clear players):
    out | doubtful | questionable | clear (no designation, probable, active or reported as playing)."""
    m = _matched(records, team, name, season, week)
    m.sort(key=lambda r: (str(r.get("published_utc") or r.get("collected_utc") or ""), r.get("layer") == "official"))
    cat = "clear"
    for r in m:
        s = str(r.get("status") or "").lower(); k = str(r.get("kind") or "").lower()
        if "out" in s or "injured reserve" in s or "will_not_play" in k or "injured_list" in k:
            cat = "out"
        elif "doubt" in s:
            cat = "doubtful"
        elif "question" in s:
            cat = "questionable"
        elif "will_play" in k or s in ("active", "probable", "no designation"):
            cat = "clear"
    return cat


def _status(records, team, name, base, rules, season=None, week=None):
    matched = _matched(records, team, name, season, week)
    p = base; labels = []; source_times = []
    # Later/current facts take precedence, while official designations override reported context at equal recency.
    matched.sort(key=lambda r: (str(r.get("published_utc") or r.get("collected_utc") or ""), r.get("layer") == "official"))
    for r in matched:
        s = str(r.get("status") or "").lower(); k = str(r.get("kind") or "").lower()
        source_times.append(r.get("published_utc") or r.get("collected_utc"))
        material = False
        if "out" in s or "injured reserve" in s or "will_not_play" in k or "injured_list" in k:
            p = rules["out"]; material = True
        elif "doubt" in s:
            p = min(p, rules["doubtful"]); material = True
        elif "question" in s:
            p *= rules["questionable_multiplier"]; material = True
        elif "will_play" in k:
            p = max(p, rules["reported_will_play_floor"]); material = True
        elif s == "active":
            p = max(p, rules["reported_will_play_floor"])
        if material:
            labels.append(f"{r.get('source')}: {r.get('status') or r.get('kind')}")
    return float(np.clip(p, 0, 1)), list(dict.fromkeys(labels)), [x for x in source_times if x]


def make_forecast(now=None, availability_store=None):
    now = _utc(now or pd.Timestamp.now(tz="UTC")); params = json.loads(PARAMS.read_text())
    g = _kickoffs(games()); season = int(g[g.kickoff <= now + pd.Timedelta(days=45)].season.max())
    future = g[(g.season == season) & g.game_type.eq("REG") & (g.kickoff > now) & (g.kickoff <= now + pd.Timedelta(days=8))].copy()
    depth, depth_path = _latest_depth(season); weekly, weekly_paths = _weekly(season); snaps, snap_paths = _snaps(season)
    states = _team_states(weekly, season); availability, source_paths = _availability(availability_store)
    schedule_path = Path(DATA) / "schedules" / "games.csv"
    inputs = [p for p in [schedule_path, depth_path, PARAMS] + weekly_paths + snap_paths + source_paths if p and Path(p).exists()]
    result = {"schema_version": 1, "model_id": params["model_id"], "generated_utc": now.isoformat(),
              "experimental": True, "market_inputs": False, "market_edge_established": False,
              "primary_horizon": "60 minutes", "secondary_horizon": "6 hours",
              "inputs": [{"path": str(p), "sha256": _sha(p)} for p in inputs], "games": []}
    for game in future.itertuples():
        item = {"game_id": game.game_id, "kickoff_utc": game.kickoff.isoformat(), "home": game.home_team, "away": game.away_team,
                "minutes_to_kickoff": round((game.kickoff - now).total_seconds() / 60, 1), "teams": []}
        for team in (game.away_team, game.home_team):
            opponent = game.home_team if team == game.away_team else game.away_team
            roster = depth[depth.team.eq(team)] if len(depth) else pd.DataFrame()
            qbs = roster[roster.pos_abb.eq("QB")].sort_values("pos_rank") if len(roster) else pd.DataFrame()
            # Features unavailable from the lightweight live feed are imputed at their frozen
            # training means (a neutral standardized value), never as a fabricated observation.
            means = dict(zip(params["team_attempts"]["features"], params["team_attempts"]["mean"]))
            state = {**means, **states.get(team, {})}
            if opponent in states:
                state["opp_plays"] = states[opponent]["own_plays"]
            mu = float(np.clip(_linear(state, params["team_attempts"]), 15, 55)); volume = _nb(mu, params["team_attempts"]["dispersion"])
            players = []; qb_choice = None; qb_base = None
            for q in qbs.itertuples():
                h = _player_history(weekly, snaps, q.gsis_id, team, season); base = _appearance(h, "QB", params)
                avail, notes, times = _status(availability, team, q.player_name, base, params["status_rules"], season, game.week)
                if qb_choice is None and avail >= .5:
                    qb_choice = (q, avail, notes, times); qb_base = base
            if qb_choice is None and len(qbs):
                q = next(qbs.itertuples()); qb_choice = (q, 0.0, ["No listed QB cleared the availability rule"], [])
            if qb_choice:
                q, avail, notes, times = qb_choice
                pmf = _allocate(volume, params["starting_qb"]["share"], params["starting_qb"]["concentration"], 70)
                players.append({"player_id": q.gsis_id, "name": q.player_name, "position": "QB", "stat": "pass_attempts",
                    "availability_probability": avail, "usual_availability": qb_base, "report_status": _designation(availability, team, q.player_name, season, game.week), "role": "expected starter from latest depth chart plus dated availability reports",
                    "availability_notes": notes, "source_times": times, **_describe(pmf)})
            receivers = []
            for r in roster[roster.pos_abb.isin(POSITIONS)].itertuples() if len(roster) else []:
                h = _player_history(weekly, snaps, r.gsis_id, team, season); base = _appearance(h, r.pos_abb, params)
                avail, notes, times = _status(availability, team, r.player_name, base, params["status_rules"], season, game.week)
                rp = params["receiving"]; target_prior = rp["target_share_prior"].get(r.pos_abb, .08); catch_prior = rp["catch_prior"].get(r.pos_abb, .65)
                share = (h["target"] + rp["target_share_prior_plays"] * target_prior) / (h["team_att"] + rp["target_share_prior_plays"])
                catch = (h["receptions"] + rp["catch_prior_targets"] * catch_prior) / (h["target"] + rp["catch_prior_targets"])
                receivers.append({"player_id": r.gsis_id, "name": r.player_name, "position": r.pos_abb, "availability_probability": avail,
                                  "usual_availability": float(base), "report_status": _designation(availability, team, r.player_name, season, game.week),
                                  "availability_notes": notes, "source_times": times, "conditional_target_share": float(np.clip(share, 0, 1)),
                                  "catch_probability": float(np.clip(catch, 0, 1)), "history_games": h["history_games"]})
            expected_budget = sum(x["availability_probability"] * x["conditional_target_share"] for x in receivers)
            for r in receivers:
                # Forecast is conditional on the focal player appearing: replace only that player's a*s by 1*s.
                denom = expected_budget + (1 - r["availability_probability"]) * r["conditional_target_share"]
                scale = min(1.0, 1.0 / max(denom, 1e-12)); effective = r["conditional_target_share"] * scale
                pmf = _allocate(volume, effective * r["catch_probability"], params["receiving"]["concentration"], 30)
                players.append({**r, "stat": "receptions", "role": "conditional target role with competitor participation weighting",
                                "effective_target_share": effective, **_describe(pmf)})
            item["teams"].append({"team": team, "expected_team_pass_attempts": mu, "expected_active_target_budget": expected_budget,
                                  "players": players})
        result["games"].append(item)
    return result


def archive_forecast(archive, forecast):
    archive = Path(archive); archive.mkdir(parents=True, exist_ok=True)
    stamp = forecast["generated_utc"].replace("-", "").replace(":", "").replace("+00:00", "Z").replace(".", "")
    digest = hashlib.sha256(json.dumps(forecast, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path = archive / "snapshots" / stamp[:8] / f"{stamp}_{digest[:12]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f: json.dump({**forecast, "forecast_sha256": digest}, f, separators=(",", ":"))
    index = archive / "index.jsonl"
    with index.open("a", encoding="utf-8") as f:
        for g in forecast["games"]:
            f.write(json.dumps({"file": str(path.relative_to(archive)).replace("\\", "/"), "generated_utc": forecast["generated_utc"],
                                "game_id": g["game_id"], "kickoff_utc": g["kickoff_utc"], "minutes_to_kickoff": g["minutes_to_kickoff"],
                                "sha256": digest}) + "\n")
    return path


def _display(forecast):
    out = {k: forecast[k] for k in ("schema_version", "model_id", "generated_utc", "experimental", "market_edge_established")}
    out["method_note"] = ("Every number is conditional on the player playing (most sportsbooks void a player prop if he does not play; check your "
                          "book's rules). Players are grouped by their latest injury designation from the official NFL report and dated news; "
                          "late inactive news can still arrive after this update, so check team news before acting.")
    if forecast.get("model_id") == "nfl-player-props-v1.1-experimental":
        out["method_note"] += (" Version shown: v1.1, with team pass volume using the opponent's passes allowed, both teams' passing "
                               "efficiency and Elo strength, as in the historically tested model; the original v1 keeps running as a comparison.")
    else:
        out["method_note"] += " Version shown: v1 (v1.1 could not be built for this update)."
    out["evidence"] = dict(json.loads(PARAMS.read_text())["evidence"])
    # Display-only label (26 Oct 2026; research/nfl_games_props/STATUS_CALIBRATION_RULE.md): the status probabilities are fixed
    # assumptions until calibrated. Forecast values and the parameter file are unchanged.
    out["evidence"]["availability"] = (out["evidence"].get("availability", "") + " Injury-status adjustments (Out 0%, Doubtful 10%, "
                                       "Questionable 80% of the normal chance to play) are assumptions, not yet calibrated from past reports.").strip()
    out["games"] = []
    for g in forecast["games"]:
        gg = {k: g[k] for k in ("game_id", "kickoff_utc", "home", "away", "minutes_to_kickoff")}; gg["teams"] = []
        for t in g["teams"]:
            tt = {"team": t["team"], "expected_team_pass_attempts": t["expected_team_pass_attempts"], "players": []}
            for p in t["players"]:
                tt["players"].append({k: p.get(k) for k in ("player_id", "name", "position", "stat", "availability_probability", "usual_availability", "report_status", "mean", "median", "interval80", "illustrative_line", "over_probability", "role", "availability_notes")})
            gg["teams"].append(tt)
        out["games"].append(gg)
    return out


def build_data(availability_store=None, archive=None):
    forecast = make_forecast(availability_store=availability_store or os.environ.get("NFL_AVAILABILITY_STORE"))
    # Displayed version since 26 Oct 2026: v1.1 (team-volume inputs as in the tested model; research/nfl_games_props/RULE.md
    # amendment). v1 keeps running unchanged in the forecast workflow as the comparison. If v1.1 cannot be built, the page says so
    # and shows v1, never a silent mix.
    shown = forecast
    try:
        import nfl_props_v11
        shown = nfl_props_v11.make_v11(forecast)
    except Exception as e:  # noqa: BLE001
        print("NFL props v1.1 unavailable, showing v1:", repr(e)[:300], flush=True)
    write_json("nfl_player_props.json", _display(shown))
    if archive: archive_forecast(archive, forecast)
    return forecast


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("command", choices=["forecast", "site"], nargs="?", default="forecast")
    ap.add_argument("--availability"); ap.add_argument("--archive"); ap.add_argument("--output")
    a = ap.parse_args(); f = make_forecast(availability_store=a.availability)
    if a.archive: p = archive_forecast(a.archive, f); print(p)
    if a.output: Path(a.output).write_text(json.dumps(f, indent=2), encoding="utf-8")
    if a.command == "site": write_json("nfl_player_props.json", _display(f))
    print(json.dumps({"generated_utc": f["generated_utc"], "games": len(f["games"]), "players": sum(len(t["players"]) for g in f["games"] for t in g["teams"])}, indent=2))


if __name__ == "__main__": main()
