"""Public AFL history and advanced-stat collection for the static site.

Historical box scores/results come from the fitzRoy data archive (AFL Tables
and Footywire data, maintained with permission).  The archive is checked each
pipeline run; the last good copy is retained if GitHub is temporarily down.
No odds or third-party model ratings are downloaded.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html
import json
import os
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from common import DATA, OUT, ROOT, log, write_json

AFL_DATA = os.path.join(DATA, "afl")
AFL_OUT = os.path.join(OUT, "afl")
AFL_SRC = os.path.join(ROOT, "site_src", "afl")
AFL_SITE = os.path.join(ROOT, "site", "afl")
RELEASE_API = "https://api.github.com/repos/jimmyday12/fitzroy_data/releases/tags/data"
ASSETS = {
    "afltables_player_stats.parquet": "https://github.com/jimmyday12/fitzroy_data/releases/download/data/afltables_player_stats.parquet",
    "footywire_player_stats.parquet": "https://github.com/jimmyday12/fitzroy_data/releases/download/data/footywire_player_stats.parquet",
}

# AFL Tables has player-game history from 1897; the Footywire archive adds
# modern advanced player statistics from 2010.  The site publishes the 18-team
# era only (2012 onward, chosen with TypeSafe): every season comparable, with
# advanced stats throughout, without crowding the pages with distant eras.
FIRST_SEASON = 2012
BASE_STATS = {
    "Kicks": "kicks", "Marks": "marks", "Handballs": "handballs", "Disposals": "disposals",
    "Goals": "goals", "Behinds": "behinds", "Hit.Outs": "hitouts", "Tackles": "tackles",
    "Rebounds": "rebound_50s", "Inside.50s": "inside_50s", "Clearances": "clearances",
    "Clangers": "clangers", "Frees.For": "free_kicks_for", "Frees.Against": "free_kicks_against",
    "Brownlow.Votes": "brownlow_votes", "Contested.Possessions": "contested_possessions",
    "Uncontested.Possessions": "uncontested_possessions", "Contested.Marks": "contested_marks",
    "Marks.Inside.50": "marks_inside_50", "One.Percenters": "one_percenters", "Bounces": "bounces",
    "Goal.Assists": "goal_assists", "Time.on.Ground": "time_on_ground",
}
FW_STATS = {
    "GA": "goal_assists", "CP": "contested_possessions", "UP": "uncontested_possessions",
    "ED": "effective_disposals", "DE": "disposal_efficiency_pct", "CM": "contested_marks",
    "MI5": "marks_inside_50", "One.Percenters": "one_percenters", "BO": "bounces",
    "TOG": "time_on_ground_pct", "K": "kicks", "HB": "handballs", "D": "disposals",
    "M": "marks", "G": "goals", "B": "behinds", "T": "tackles", "HO": "hitouts",
    "I50": "inside_50s", "CL": "clearances", "CG": "clangers", "R50": "rebound_50s",
    "FF": "free_kicks_for", "FA": "free_kicks_against", "AF": "afl_fantasy_points",
    "SC": "supercoach_points", "CCL": "centre_clearances", "SCL": "stoppage_clearances",
    "SI": "score_involvements", "MG": "metres_gained", "TO": "turnovers",
    "ITC": "intercepts", "T5": "tackles_inside_50",
}
FW_SUM_STATS = [k for k, v in FW_STATS.items() if v not in {"disposal_efficiency_pct", "time_on_ground_pct"}]
FW_MEAN_STATS = [k for k, v in FW_STATS.items() if v in {"disposal_efficiency_pct", "time_on_ground_pct"}]
BASE_MATCH_COLS = ["Season", "Round", "Date", "Venue", "Attendance", "Home.team", "Away.team",
                   "Home.score", "Away.score", "HQ1P", "HQ2P", "HQ3P", "HQ4P", "AQ1P", "AQ2P", "AQ3P", "AQ4P"]
BASE_PLAYER_COLS = ["Season", "Round", "Date", "Venue", "Player", "ID", "Jumper.No.", "Playing.for",
                    "Home.Away", "Age", "Career.Games", *BASE_STATS.keys()]
BASE_TEAM_SUMS = ["Kicks", "Marks", "Handballs", "Disposals", "Goals", "Behinds", "Hit.Outs", "Tackles",
                  "Rebounds", "Inside.50s", "Clearances", "Clangers", "Frees.For", "Frees.Against",
                  "Contested.Possessions", "Uncontested.Possessions", "Contested.Marks", "Marks.Inside.50",
                  "One.Percenters", "Bounces", "Goal.Assists"]
FINALS = {"EF", "QF", "SF", "PF", "GF", "ELIMINATIONFINAL", "QUALIFYINGFINAL", "SEMIFINAL",
          "PRELIMINARYFINAL", "GRANDFINAL", "WILDCARDFINAL"}


def _clean_team(value: object) -> str:
    text = str(value or "").strip()
    return {"Brisbane": "Brisbane Lions", "GWS": "Greater Western Sydney",
            "Greater Western Sydney": "Greater Western Sydney"}.get(text, text)


def _token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _round_kind(value: object) -> tuple[str, bool]:
    raw = str(value or "").strip()
    token = _token(raw).upper()
    if token in FINALS or "FINAL" in token:
        return "FIN", True
    if any(k in token for k in ("PRESEASON", "PRACTICE", "NABCHALLENGE", "COMMUNITYSERIES")):
        return "PRE", False
    return "REG", False


def _season_int(value: object) -> int:
    return int(float(value))


def _release_assets() -> tuple[dict[str, dict], str | None]:
    req = urllib.request.Request(RELEASE_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "NFLFutures-AFL-collector/1.0",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {asset["name"]: asset for asset in payload.get("assets", [])}, payload.get("published_at")


def _ensure_archives(warnings: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    os.makedirs(AFL_DATA, exist_ok=True)
    version_path = os.path.join(AFL_DATA, "source_versions.json")
    try:
        with open(version_path, encoding="utf-8") as f:
            versions = json.load(f)
    except (OSError, ValueError):
        versions = {}
    try:
        assets, release_date = _release_assets()
    except Exception as exc:  # noqa: BLE001 - retain cached data during source outages
        assets, release_date = {}, None
        warnings.append(f"fitzRoy release metadata unavailable: {type(exc).__name__}: {exc}")

    paths: dict[str, str] = {}
    updated: dict[str, str] = {}
    for name, fallback_url in ASSETS.items():
        path = os.path.join(AFL_DATA, name)
        asset = assets.get(name, {})
        asset_updated = str(asset.get("updated_at") or "")
        same_version = bool(asset_updated) and versions.get(name, {}).get("updated_at") == asset_updated
        # If release metadata is unreachable, prefer the existing archive over
        # repeatedly hitting the same download URL. A first-ever run still tries
        # the direct asset URL below, and the next scheduled run checks again.
        if os.path.exists(path) and not assets:
            paths[name] = path
            updated[name] = str(versions.get(name, {}).get("updated_at") or "")
            continue
        if not (os.path.exists(path) and same_version):
            url = asset.get("browser_download_url") or fallback_url
            req = urllib.request.Request(url, headers={
                "User-Agent": "NFLFutures-AFL-collector/1.0", "Accept": "application/octet-stream",
                "Cache-Control": "no-cache",
            })
            err = None
            for attempt in range(3):
                try:
                    tmp = path + ".part"
                    with urllib.request.urlopen(req, timeout=120) as response, open(tmp, "wb") as f:
                        shutil.copyfileobj(response, f, length=1024 * 1024)
                    if os.path.getsize(tmp) < 1024:
                        raise ValueError("Downloaded archive was unexpectedly small")
                    os.replace(tmp, path)
                    versions[name] = {"updated_at": asset_updated, "size": os.path.getsize(path)}
                    break
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
                    try:
                        if os.path.exists(path + ".part"):
                            os.remove(path + ".part")
                    except OSError:
                        pass
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
            else:
                if os.path.exists(path):
                    warnings.append(f"{name} refresh failed; using cached copy ({err})")
                else:
                    warnings.append(f"{name} unavailable and no cached copy exists ({err})")
        if os.path.exists(path):
            paths[name] = path
            updated[name] = str(versions.get(name, {}).get("updated_at") or release_date or "")
    with open(version_path + ".part", "w", encoding="utf-8") as f:
        json.dump(versions, f, separators=(",", ":"))
    os.replace(version_path + ".part", version_path)
    return paths, updated


def _load_frame(path: str, columns: list[str]) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=columns, engine="pyarrow")
    if "Season" in frame:
        frame["Season"] = pd.to_numeric(frame["Season"], errors="coerce").astype("Int64")
    if "Date" in frame:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame


def _match_key(row: pd.Series) -> str:
    return "|".join((str(int(row.Season)), str(row.Date), _token(row.Round), _token(row["Home.team"]), _token(row["Away.team"])))


def _matches_and_team_games(base: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    base = base.dropna(subset=["Season", "Date", "Home.team", "Away.team", "Home.score", "Away.score"]).copy()
    base["game_key"] = base.apply(_match_key, axis=1)
    match_cols = [c for c in BASE_MATCH_COLS if c in base]
    info = base[match_cols + ["game_key"]].drop_duplicates("game_key").copy()
    matches: list[dict] = []
    by_key: dict[str, dict] = {}
    for r in info.to_dict("records"):
        kind, is_final = _round_kind(r.get("Round"))
        year = _season_int(r["Season"])
        match_id = f"{year}-{r['Date']}-{_token(r['Round'])}-{_token(r['Home.team'])}-{_token(r['Away.team'])}"
        row = {"match_id": match_id, "season": year, "season_type": kind, "round": str(r.get("Round", "")),
               "date": r["Date"], "venue": r.get("Venue"), "attendance": r.get("Attendance"),
               "home_team": _clean_team(r["Home.team"]), "away_team": _clean_team(r["Away.team"]),
               "home_score": int(r["Home.score"]), "away_score": int(r["Away.score"]), "is_final": is_final}
        for q in range(1, 5):
            home_cum = r.get(f"HQ{q}P")
            away_cum = r.get(f"AQ{q}P")
            home_prev = r.get(f"HQ{q - 1}P") if q > 1 else 0
            away_prev = r.get(f"AQ{q - 1}P") if q > 1 else 0
            row[f"home_q{q}"] = (home_cum - home_prev) if pd.notna(home_cum) and pd.notna(home_prev) else home_cum
            row[f"away_q{q}"] = (away_cum - away_prev) if pd.notna(away_cum) and pd.notna(away_prev) else away_cum
        matches.append(row)
        by_key[r["game_key"]] = row

    team_games: list[dict] = []
    stat_cols = [c for c in BASE_TEAM_SUMS if c in base]
    for (game_key, side), group in base.groupby(["game_key", "Home.Away"], dropna=False, sort=False):
        match = by_key.get(game_key)
        if not match or str(side).strip().lower() not in {"home", "away"}:
            continue
        home = str(side).strip().lower() == "home"
        team = match["home_team"] if home else match["away_team"]
        opp = match["away_team"] if home else match["home_team"]
        points = match["home_score"] if home else match["away_score"]
        against = match["away_score"] if home else match["home_score"]
        row = {"match_id": match["match_id"], "season": match["season"], "season_type": match["season_type"],
               "date": match["date"], "round": match["round"], "team": team, "opponent": opp,
               "home_away": "Home" if home else "Away", "venue": match.get("venue"), "points_for": points,
               "points_against": against, "margin": points - against, "result": "W" if points > against else "L" if points < against else "D"}
        for q in range(1, 5):
            row[f"q{q}_for"] = match.get(f"home_q{q}" if home else f"away_q{q}")
            row[f"q{q}_against"] = match.get(f"away_q{q}" if home else f"home_q{q}")
        for col in stat_cols:
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            row[BASE_STATS[col]] = float(vals.sum()) if len(vals) else None
        team_games.append(row)
    team_games.sort(key=lambda r: (r["season"], r["date"], r["team"]))
    matches.sort(key=lambda r: (r["season"], r["date"], r["round"]))
    return matches, team_games


def _team_seasons(team_games: list[dict]) -> list[dict]:
    frame = pd.DataFrame(team_games)
    if frame.empty:
        return []
    rows: list[dict] = []
    premiers: dict[int, str] = {}
    stage_rank = {"EF": 1, "ELIMINATIONFINAL": 1, "QF": 2, "QUALIFYINGFINAL": 2,
                  "SF": 3, "SEMIFINAL": 3, "PF": 4, "PRELIMINARYFINAL": 4, "GF": 5, "GRANDFINAL": 5}
    last_stage: dict[tuple[int, str], str] = {}
    for (year, team), group in frame[frame.season_type == "FIN"].groupby(["season", "team"], sort=False):
        for round_name in group["round"].astype(str):
            token = _token(round_name).upper()
            rank = stage_rank.get(token, 0)
            if rank and rank > stage_rank.get(_token(last_stage.get((int(year), team), "")).upper(), 0):
                last_stage[(int(year), team)] = round_name
        gf = group[group["round"].map(lambda x: _token(x).upper() in {"GF", "GRANDFINAL"})]
        if not gf.empty:
            winner = gf.sort_values("margin", ascending=False).iloc[0]
            if winner.margin > 0:
                premiers[int(year)] = team
    base_profile = [BASE_STATS[c] for c in BASE_TEAM_SUMS if c in BASE_STATS]
    adv_profile = [FW_STATS[c] for c in FW_SUM_STATS if c in FW_STATS]
    numeric_profile = list(dict.fromkeys(base_profile + adv_profile))
    for (year, kind, team), group in frame.groupby(["season", "season_type", "team"], sort=False):
        gp = len(group)
        wins = int((group.result == "W").sum())
        losses = int((group.result == "L").sum())
        draws = int((group.result == "D").sum())
        pf = int(group.points_for.sum())
        pa = int(group.points_against.sum())
        row = {"season": int(year), "season_type": kind, "team": team, "games": gp, "wins": wins, "losses": losses,
               "draws": draws, "win_pct": (wins + draws * 0.5) / gp if gp else None, "points_for": pf,
               "points_against": pa, "percentage": 100 * pf / pa if pa else None,
               "points_for_pg": pf / gp if gp else None, "points_against_pg": pa / gp if gp else None,
               "margin_pg": float(group.margin.mean()) if gp else None,
               "home_wins": int(((group.home_away == "Home") & (group.result == "W")).sum()),
               "away_wins": int(((group.home_away == "Away") & (group.result == "W")).sum()),
               "finals_wins": int(((group.season_type == "FIN") & (group.result == "W")).sum()),
               # Premiership is a season outcome, not a separate result for
               # both the regular-season and finals profile rows.
               "premiership": kind == "REG" and team == premiers.get(int(year)),
               "finals_stage": last_stage.get((int(year), team))}
        for stat in numeric_profile:
            if stat not in group:
                continue
            values = pd.to_numeric(group[stat], errors="coerce").dropna()
            row[f"{stat}_pg"] = float(values.mean()) if len(values) else None
        rows.append(row)
    # Traditional ladder places only regular-season teams.
    regular_by_year: dict[int, list[dict]] = {}
    for row in rows:
        if row["season_type"] == "REG":
            regular_by_year.setdefault(row["season"], []).append(row)
    for year_rows in regular_by_year.values():
        for rank, row in enumerate(sorted(year_rows, key=lambda r: (r["wins"] + 0.5 * r["draws"], r["percentage"], r["points_for"]), reverse=True), 1):
            row["ladder_position"] = rank
            row["minor_premier"] = rank == 1
    return sorted(rows, key=lambda r: (r["season"], r["season_type"], r.get("ladder_position", 99), r["team"]))


def _player_seasons(base: pd.DataFrame, advanced: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    frame = base.copy()
    frame["season_type"] = frame["Round"].map(lambda x: _round_kind(x)[0])
    keys = ["Season", "season_type", "ID"]
    present_sums = [col for col in BASE_STATS if col in frame]
    present_profile = [col for col in ("Age", "Career.Games") if col in frame]
    frame[present_sums + present_profile] = frame[present_sums + present_profile].apply(pd.to_numeric, errors="coerce")
    grouped = frame.groupby(keys, dropna=False, sort=False)
    profile = grouped.agg(player=("Player", "last"), games=("Player", "size"),
                          team=("Playing.for", lambda s: " / ".join(dict.fromkeys(s.dropna().astype(str)))))
    if "Age" in frame:
        profile["age"] = grouped["Age"].mean()
    if "Career.Games" in frame:
        profile["career_games"] = grouped["Career.Games"].max()
    totals = grouped[present_sums].sum(min_count=1) if present_sums else pd.DataFrame(index=profile.index)
    player_frame = profile.join(totals).reset_index()
    player_rows: list[dict] = []
    for record in player_frame.to_dict("records"):
        year, kind, pid = record["Season"], record["season_type"], record["ID"]
        if pd.isna(year):
            continue
        games = int(record["games"])
        row = {"season": _season_int(year), "season_type": kind, "player_id": int(pid) if pd.notna(pid) else None,
               "player": record.get("player") or "Unknown", "team": record.get("team") or "", "games": games,
               "age": float(record["age"]) if pd.notna(record.get("age")) else None,
               "career_games": int(record["career_games"]) if pd.notna(record.get("career_games")) else None}
        for col, field in BASE_STATS.items():
            value = record.get(col)
            row[field] = float(value) if pd.notna(value) else None
            if row[field] is not None:
                row[f"{field}_pg"] = row[field] / games if games else None
        goals, behinds = row.get("goals") or 0, row.get("behinds") or 0
        row["scoring_accuracy_pct"] = 100 * goals / (goals + behinds) if goals + behinds else None
        player_rows.append(row)

    adv_rows: list[dict] = []
    if not advanced.empty:
        advanced = advanced.copy()
        advanced["season_type"] = advanced["Round"].map(lambda x: _round_kind(x)[0])
        present_fw = [col for col in FW_STATS if col in advanced]
        advanced[present_fw] = advanced[present_fw].apply(pd.to_numeric, errors="coerce")
        advanced["Season"] = pd.to_numeric(advanced["Season"], errors="coerce")
        present_fw = [col for col in FW_STATS if col in advanced]
        advanced[present_fw] = advanced[present_fw].apply(pd.to_numeric, errors="coerce")
        adv_groups = advanced.groupby(["Season", "season_type", "Player"], sort=False)
        adv_profile = adv_groups.agg(games=("Player", "size"),
                                     team=("Team", lambda s: " / ".join(dict.fromkeys(s.dropna().astype(str)))))
        sum_cols = [c for c in FW_SUM_STATS if c in advanced]
        mean_cols = [c for c in FW_MEAN_STATS if c in advanced]
        adv_totals = adv_groups[sum_cols].sum(min_count=1) if sum_cols else pd.DataFrame(index=adv_profile.index)
        adv_means = adv_groups[mean_cols].mean() if mean_cols else pd.DataFrame(index=adv_profile.index)
        adv_frame = adv_profile.join(adv_totals).join(adv_means).reset_index()
        for record in adv_frame.to_dict("records"):
            year, kind, player = record["Season"], record["season_type"], record["Player"]
            if pd.isna(year):
                continue
            games = int(record["games"])
            row = {"season": _season_int(year), "season_type": kind, "player": str(player),
                   "team": record.get("team") or "", "games": games}
            for col, field in FW_STATS.items():
                if col not in record:
                    continue
                value = record.get(col)
                row[field] = float(value) if pd.notna(value) else None
                if row[field] is not None and col in FW_SUM_STATS:
                    row[f"{field}_pg"] = row[field] / games if games else None
            if row.get("disposals"):
                row["disposal_efficiency_pct"] = 100 * row.get("effective_disposals", 0) / row["disposals"]
            adv_rows.append(row)
    return player_rows, adv_rows


def _footywire_team_games(advanced: pd.DataFrame, result_lookup: dict[tuple, dict]) -> list[dict]:
    if advanced.empty:
        return []
    frame = advanced.copy()
    frame["season_type"] = frame["Round"].map(lambda x: _round_kind(x)[0])
    groups = ["Season", "Date", "Round", "Venue", "Team", "Opposition", "Status"]
    rows = []
    for keys, group in frame.groupby(groups, dropna=False, sort=False):
        year, date, round_name, venue, team, opp, status = keys
        if pd.isna(year) or pd.isna(date):
            continue
        team, opp = _clean_team(team), _clean_team(opp)
        row = {"season": _season_int(year), "season_type": _round_kind(round_name)[0], "date": str(date),
               "round": str(round_name), "venue": str(venue or ""), "team": team, "opponent": opp,
               "home_away": str(status or ""), "games": 1}
        for col, field in FW_STATS.items():
            if col not in group:
                continue
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            if not len(vals):
                row[field] = None
            elif col in FW_MEAN_STATS:
                row[field] = float(vals.mean())
            else:
                row[field] = float(vals.sum())
        d = group.iloc[0]
        row["match_id"] = int(d["Match_id"]) if pd.notna(d.get("Match_id")) else None
        row["effective_disposal_pct"] = (100 * row.get("effective_disposals", 0) / row.get("disposals", 0)
                                         if row.get("disposals") else row.get("disposal_efficiency_pct"))
        row["disposal_efficiency_pct"] = row["effective_disposal_pct"]
        result = result_lookup.get((_season_int(year), str(date), _token(team), _token(opp)))
        if result:
            row.update({k: result[k] for k in ("points_for", "points_against", "margin", "result")})
        rows.append(row)
    return sorted(rows, key=lambda r: (r["season"], r["date"], r["team"]))


def _native(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return value.isoformat()[:10]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value


def _records(frame: pd.DataFrame, keep: list[str] | None = None) -> list[dict]:
    if keep is not None:
        frame = frame[[c for c in keep if c in frame.columns]]
    return [{k: _native(v) for k, v in row.items()} for row in frame.to_dict("records")]


def _json_safe(value):
    """Convert pandas/numpy scalars and missing values to strict JSON values."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return value.isoformat()[:10]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            return None
    except (TypeError, ValueError):
        pass
    return value


def _write_compressed_json(name: str, value: dict) -> None:
    path = os.path.join(AFL_OUT, name)
    tmp = path + ".part"
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(value, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)


def _result_lookup(matches: list[dict]) -> dict[tuple, dict]:
    lookup = {}
    for m in matches:
        home = {"points_for": m["home_score"], "points_against": m["away_score"], "margin": m["home_score"] - m["away_score"],
                "result": "W" if m["home_score"] > m["away_score"] else "L" if m["home_score"] < m["away_score"] else "D"}
        away = {"points_for": m["away_score"], "points_against": m["home_score"], "margin": m["away_score"] - m["home_score"],
                "result": "W" if m["away_score"] > m["home_score"] else "L" if m["away_score"] < m["home_score"] else "D"}
        lookup[(m["season"], m["date"], _token(m["home_team"]), _token(m["away_team"]))] = home
        lookup[(m["season"], m["date"], _token(m["away_team"]), _token(m["home_team"]))] = away
    return lookup


def _award_rows(players: list[dict]) -> list[dict]:
    leaders = []
    for row in players:
        if row.get("season_type") != "REG":
            continue
        if row.get("brownlow_votes"):
            leaders.append({"season": row["season"], "season_type": "REG", "award": "Brownlow vote leader", "player": row["player"],
                            "team": row["team"], "value": row["brownlow_votes"], "unit": "votes"})
        if row.get("goals"):
            leaders.append({"season": row["season"], "season_type": "REG", "award": "Goal leader", "player": row["player"],
                            "team": row["team"], "value": row["goals"], "unit": "goals"})
    return leaders


def build_data() -> None:
    os.makedirs(AFL_OUT, exist_ok=True)
    warnings: list[str] = []
    paths, source_updated = _ensure_archives(warnings)
    if "afltables_player_stats.parquet" not in paths:
        write_json("afl_stats_index.json", {"meta": {"league": "AFL", "updated_utc": "", "seasons": [],
                                                       "source": "fitzRoy archive: AFL Tables + Footywire", "errors": warnings}})
        log("AFL data unavailable:", "; ".join(warnings[:2]))
        return
    try:
        base = _load_frame(paths["afltables_player_stats.parquet"], list(dict.fromkeys(BASE_MATCH_COLS + BASE_PLAYER_COLS)))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unable to read AFL Tables archive; install pyarrow: {exc}") from exc
    log("AFL source loaded", len(base), "AFL Tables player-game rows")
    # Keep the published research window focused on modern AFL seasons.
    base = base[base["Season"].ge(FIRST_SEASON)].copy()
    advanced = pd.DataFrame()
    if "footywire_player_stats.parquet" in paths:
        try:
            advanced = _load_frame(paths["footywire_player_stats.parquet"], ["Date", "Season", "Round", "Venue", "Player", "Team", "Opposition", "Status", "Match_id", *FW_STATS.keys()])
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Footywire advanced archive could not be read: {type(exc).__name__}: {exc}")
    if not advanced.empty:
        advanced = advanced[pd.to_numeric(advanced["Season"], errors="coerce").ge(FIRST_SEASON)].copy()

    matches, base_team_games = _matches_and_team_games(base)
    log("AFL outcomes prepared", len(matches), "matches")
    lookup = _result_lookup(matches)
    advanced_team_games = _footywire_team_games(advanced, lookup)
    advanced_team_keys = {(r["season"], r["date"], _token(r["team"]), _token(r["opponent"])): r for r in advanced_team_games}
    for row in base_team_games:
        extra = advanced_team_keys.get((row["season"], row["date"], _token(row["team"]), _token(row["opponent"])))
        if extra:
            for key, value in extra.items():
                if key not in {"season", "season_type", "date", "round", "venue", "team", "opponent", "home_away", "games", "match_id", "points_for", "points_against", "margin", "result"}:
                    row[key] = value
    players, advanced_players = _player_seasons(base, advanced)

    # Publish compact, season-addressable files: match and player logs from
    # 2010 onward; outcomes and player-season summaries for the full archive.
    seasons = sorted({_season_int(y) for y in base.Season.dropna().unique()
                      if _season_int(y) >= FIRST_SEASON}, reverse=True)
    team_season_rows = _team_seasons(base_team_games)
    base_year_col = base["Season"].astype("Int64")
    adv_fields = {}
    if not advanced.empty:
        for col, field in FW_STATS.items():
            if col not in advanced:
                continue
            coverage = advanced.loc[advanced[col].notna()].groupby("Season").size()
            years = sorted({_season_int(y) for y in coverage.index if pd.notna(y)})
            if years:
                adv_fields[field] = {"from": min(years), "through": max(years)}
    for year in seasons:
        year_matches = [r for r in matches if r["season"] == year]
        year_teams = [r for r in team_season_rows if r["season"] == year]
        year_team_games = [r for r in base_team_games if r["season"] == year]
        year_players = [r for r in players if r["season"] == year]
        year_adv_players = [r for r in advanced_players if r["season"] == year]
        # Older per-game rows are retained in the source archive but not copied
        # to the site; season totals and historical results remain available.
        year_player_games = []
        if year >= 2010:
            subset = base[base_year_col == year].copy()
            team_game_lookup = {(tg["date"], _token(tg["team"]), tg["home_away"].lower()): tg
                                for tg in year_team_games}
            for _, r in subset.iterrows():
                kind, _ = _round_kind(r.get("Round"))
                team = str(r.get("Playing.for") or r.get("Team") or "")
                row = {"season": year, "season_type": kind, "date": r.get("Date"), "round": r.get("Round"),
                       "venue": r.get("Venue"), "player": r.get("Player"), "player_id": r.get("ID"),
                       "team": team, "home_away": r.get("Home.Away"), "age": r.get("Age"),
                       "career_games": r.get("Career.Games")}
                for col, field in BASE_STATS.items():
                    if col in r:
                        row[field] = r.get(col)
                # Match outcomes are added from the side-specific team-game record.
                side = str(r.get("Home.Away") or "").lower()
                tg = team_game_lookup.get((str(r.get("Date")), _token(team), side))
                if tg:
                    row.update({k: tg[k] for k in ("opponent", "points_for", "points_against", "margin", "result")})
                year_player_games.append(row)
        year_advanced_team_games = [r for r in advanced_team_games if r["season"] == year]
        year_advanced_player_games = []
        if not advanced.empty and year >= 2010:
            fw_year = advanced[advanced["Season"] == year]
            for _, r in fw_year.iterrows():
                kind, _ = _round_kind(r.get("Round"))
                row = {"season": year, "season_type": kind, "date": r.get("Date"), "round": r.get("Round"),
                       "venue": r.get("Venue"), "player": r.get("Player"), "team": _clean_team(r.get("Team")),
                       "opponent": _clean_team(r.get("Opposition")), "home_away": r.get("Status"),
                       "match_id": r.get("Match_id")}
                for col, field in FW_STATS.items():
                    if col in r:
                        row[field] = r.get(col)
                year_advanced_player_games.append(row)
        # Normalize pandas/numpy values before the shared JSON writer.
        data = {"matches": year_matches, "team_seasons": year_teams, "team_games": year_team_games,
                "player_seasons": year_players, "advanced_player_seasons": year_adv_players,
                "player_games": year_player_games, "advanced_team_games": year_advanced_team_games,
                "advanced_player_games": year_advanced_player_games,
                "award_leaders": _award_rows(year_players)}
        _write_compressed_json(f"season_{year}.json.gz", _json_safe(data))

    updated = max((x for x in source_updated.values() if x), default="")
    meta = {"league": "AFL", "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "source_updated": source_updated, "seasons": seasons, "basic_from": min(seasons) if seasons else None,
            "advanced_from": min((v["from"] for v in adv_fields.values()), default=None),
            "advanced_through": max((v["through"] for v in adv_fields.values()), default=None),
            "advanced_field_coverage": adv_fields,
            "sources": ["AFL Tables via fitzRoy data archive", "Footywire via fitzRoy data archive"],
            "archive_updated": updated, "errors": warnings[:10],
            "note": f"Published seasons run from {FIRST_SEASON} onward (current archive through 2026). Detailed Footywire match stats begin in 2012; field coverage varies by metric and season. Missing values are not zero. No odds or third-party ratings are included."}
    write_json("afl_stats_index.json", {"meta": meta})
    log("AFL data", len(seasons), "seasons", len(matches), "matches", len(players), "player-season rows",
        len(advanced_team_games), "advanced team game rows", "source warnings", len(warnings))


def build_site() -> None:
    data_dir = os.path.join(AFL_SITE, "data")
    os.makedirs(data_dir, exist_ok=True)
    # Drop stale generated files from older local builds outside the selected
    # 2012+ window so they cannot be copied into a later published artifact.
    for name in os.listdir(data_dir):
        match = re.fullmatch(r"season_(\d+)\.json\.gz", name)
        if match and int(match.group(1)) < FIRST_SEASON:
            os.remove(os.path.join(data_dir, name))
    shutil.copy(os.path.join(AFL_SRC, "index.html"), AFL_SITE)
    shutil.copy(os.path.join(AFL_SRC, "stats.js"), AFL_SITE)
    index = os.path.join(OUT, "afl_stats_index.json")
    if os.path.exists(index):
        shutil.copy(index, os.path.join(AFL_SITE, "data", "stats_index.json"))
    for name in os.listdir(AFL_OUT) if os.path.isdir(AFL_OUT) else []:
        if name.startswith("season_") and name.endswith(".json.gz"):
            try:
                year = int(name.removeprefix("season_").removesuffix(".json.gz"))
            except ValueError:
                continue
            if year < FIRST_SEASON:
                continue
            shutil.copy(os.path.join(AFL_OUT, name), os.path.join(data_dir, name))


if __name__ == "__main__":
    build_data()
    build_site()
