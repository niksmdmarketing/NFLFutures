"""NBA ratings, season simulation and static-site output.

The live job deliberately uses compact SportsDataverse/ESPN CSV releases rather
than the full play-by-play archive.  Ten completed seasons are available for
validation, while the production rating uses the latest four seasons plus a
conservative roster-continuity adjustment.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import shutil
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from common import DATA, OUT, ROOT, log, write_json


NBA_DATA = os.path.join(DATA, "nba")
NBA_SRC = os.path.join(ROOT, "site_src", "nba")
NBA_SITE = os.path.join(ROOT, "site", "nba")

DIVS = {
    "Atlantic": ["BOS", "BKN", "NY", "PHI", "TOR"],
    "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
    "Southeast": ["ATL", "CHA", "MIA", "ORL", "WSH"],
    "Northwest": ["DEN", "MIN", "OKC", "POR", "UTAH"],
    "Pacific": ["GS", "LAC", "LAL", "PHX", "SAC"],
    "Southwest": ["DAL", "HOU", "MEM", "NO", "SA"],
}
EAST = DIVS["Atlantic"] + DIVS["Central"] + DIVS["Southeast"]
WEST = DIVS["Northwest"] + DIVS["Pacific"] + DIVS["Southwest"]
TEAMS = sorted(EAST + WEST)
TIX = {t: i for i, t in enumerate(TEAMS)}
NAMES = {
    "ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GS": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NO": "New Orleans Pelicans", "NY": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SA": "San Antonio Spurs", "SAC": "Sacramento Kings",
    "TOR": "Toronto Raptors", "UTAH": "Utah Jazz", "WSH": "Washington Wizards",
}

RELEASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
HFA = 2.2
GAME_SIGMA = 12.2
TEAM_TAU = 2.2


def season_end_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year + 1 if today.month >= 7 else today.year


def _download(tag: str, name: str, max_age_h: float, required: bool = True) -> str | None:
    os.makedirs(NBA_DATA, exist_ok=True)
    path = os.path.join(NBA_DATA, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        return path
    url = f"{RELEASE}/{tag}/{name}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFutures/1.0"})
            tmp = path + ".part"
            with urllib.request.urlopen(req, timeout=120) as response, open(tmp, "wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            os.replace(tmp, path)
            return path
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and not required:
                return path if os.path.exists(path) else None
            if attempt == 3 and required:
                raise
        except Exception:
            if attempt == 3:
                if required:
                    raise
                return path if os.path.exists(path) else None
        time.sleep(4 * (attempt + 1))
    return path if os.path.exists(path) else None


def _csv(path: str | None) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path else pd.DataFrame()


def _load_inputs(end_year: int):
    # A decade is kept for backtesting. The live rating itself uses the latest
    # four seasons, so old team identities cannot dominate today's estimate.
    boxes = []
    for year in range(end_year - 10, end_year):
        name = f"team_box_{year}.csv"
        path = _download("espn_nba_team_boxscores", name, 24 * 365)
        frame = _csv(path)
        if len(frame):
            boxes.append(frame)
    current_box = _download("espn_nba_team_boxscores", f"team_box_{end_year}.csv", 2, required=False)
    if current_box:
        boxes.append(_csv(current_box))
    team_boxes = pd.concat(boxes, ignore_index=True)

    schedule = _csv(_download("espn_nba_schedules", f"nba_schedule_{end_year}.csv", 2))
    prior_players = _csv(_download("espn_nba_player_boxscores", f"player_box_{end_year - 1}.csv", 24 * 30))
    prior_roster = _csv(_download("espn_nba_rosters", f"rosters_{end_year - 1}.csv", 24 * 30))
    current_roster = _csv(_download("espn_nba_rosters", f"rosters_{end_year}.csv", 12))
    return team_boxes, schedule, prior_players, prior_roster, current_roster


def _bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _regular_boxes(boxes: pd.DataFrame) -> pd.DataFrame:
    d = boxes[(pd.to_numeric(boxes.season_type, errors="coerce") == 2)
              & boxes.team_abbreviation.isin(TEAMS)
              & boxes.opponent_team_abbreviation.isin(TEAMS)].copy()
    numeric = ["season", "team_score", "field_goals_attempted", "offensive_rebounds",
               "total_turnovers", "turnovers", "free_throws_attempted"]
    for col in numeric:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    tov = d.total_turnovers.fillna(d.turnovers)
    d["poss0"] = d.field_goals_attempted - d.offensive_rebounds + tov + 0.44 * d.free_throws_attempted
    d["poss"] = d.groupby("game_id").poss0.transform("mean").clip(70, 125)
    d["ortg"] = d.team_score / d.poss * 100
    return d[d.ortg.between(70, 150) & d.poss.notna()].copy()


def _fit_ratings(boxes: pd.DataFrame, end_year: int) -> tuple[pd.DataFrame, dict]:
    d = _regular_boxes(boxes)
    train = d[d.season >= end_year - 4].copy()
    n = len(train)
    x = np.zeros((n, 61), dtype=np.float32)
    for row, (team, opp, venue) in enumerate(zip(train.team_abbreviation,
                                                  train.opponent_team_abbreviation,
                                                  train.team_home_away)):
        x[row, TIX[team]] = 1
        x[row, 30 + TIX[opp]] = 1
        x[row, 60] = 1 if venue == "home" else 0
    # Completed years decay by 45%; current-season games, when present, get
    # extra weight so the model transitions naturally out of preseason mode.
    weights = np.power(0.55, np.maximum(0, (end_year - 1) - train.season.to_numpy()))
    weights = np.where(train.season.to_numpy() == end_year, 1.6, weights)
    design = np.column_stack([np.ones(n, dtype=np.float32), x]).astype(float)
    root_w = np.sqrt(weights)[:, None]
    weighted_x = design * root_w
    weighted_y = train.ortg.to_numpy(float) * root_w[:, 0]
    penalty = np.eye(design.shape[1]) * 24.0
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(weighted_x.T @ weighted_x + penalty, weighted_x.T @ weighted_y)
    intercept, coef = float(beta[0]), beta[1:]
    off = coef[:30].astype(float)
    defense = -coef[30:60].astype(float)
    off -= off.mean()
    defense -= defense.mean()
    base = intercept

    pace_rows = train.assign(w=weights)
    pace = (pace_rows.assign(wp=pace_rows.w * pace_rows.poss).groupby("team_abbreviation").wp.sum()
            / pace_rows.groupby("team_abbreviation").w.sum()).reindex(TEAMS)
    latest = train[train.season == end_year]
    last_full = train[train.season == end_year - 1]
    current_gp = latest.groupby("team_abbreviation").size().reindex(TEAMS, fill_value=0)
    prior_gp = last_full.groupby("team_abbreviation").size().reindex(TEAMS, fill_value=0)

    ratings = pd.DataFrame({"team": TEAMS, "off": off, "def": defense, "pace": pace.to_numpy(),
                            "current_gp": current_gp.to_numpy(), "prior_gp": prior_gp.to_numpy()})
    ratings["base_ortg"] = base
    ratings["raw_net"] = ratings.off + ratings["def"]
    detail = {"base_ortg": base, "home_offense_points_per_100": float(coef[60]),
              "training_rows": int(n), "training_start": int(train.season.min()),
              "training_end": int(train.season.max())}
    return ratings, detail


def _player_values(players: pd.DataFrame) -> pd.DataFrame:
    d = players[(pd.to_numeric(players.season_type, errors="coerce") == 2)
                & players.team_abbreviation.isin(TEAMS)].copy()
    cols = ["minutes", "field_goals_made", "field_goals_attempted", "free_throws_made",
            "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "rebounds", "assists",
            "steals", "blocks", "fouls", "turnovers", "points"]
    for col in cols:
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)
    d["pm"] = pd.to_numeric(d.plus_minus.astype(str).str.replace("+", "", regex=False), errors="coerce").fillna(0)
    d = d[d.minutes > 0]
    d["gmsc"] = (d.points + .4 * d.field_goals_made - .7 * d.field_goals_attempted
                 - .4 * (d.free_throws_attempted - d.free_throws_made) + .7 * d.offensive_rebounds
                 + .3 * d.defensive_rebounds + d.steals + .7 * d.assists + .7 * d.blocks
                 - .4 * d.fouls - d.turnovers)
    agg = d.groupby(["athlete_id", "athlete_display_name", "team_abbreviation"], as_index=False).agg(
        minutes=("minutes", "sum"), games=("game_id", "nunique"), points=("points", "sum"),
        rebounds=("rebounds", "sum"), assists=("assists", "sum"), gmsc=("gmsc", "sum"),
        plus_minus=("pm", "sum"))
    agg["gmsc36"] = agg.gmsc / agg.minutes * 36
    league = np.average(agg.gmsc36, weights=agg.minutes)
    agg["pm36"] = agg.plus_minus / agg.minutes * 36
    reliability = np.minimum(1, agg.minutes / 1200)
    agg["impact"] = (((agg.gmsc36 - league) * .24 + agg.pm36 * .045) * reliability).clip(-4, 6)
    agg["ppg"] = agg.points / agg.games
    agg["rpg"] = agg.rebounds / agg.games
    agg["apg"] = agg.assists / agg.games
    agg["athlete_id"] = agg.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    return agg


def _roster_adjustment(ratings: pd.DataFrame, values: pd.DataFrame, prior_roster: pd.DataFrame,
                       current_roster: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    for roster in (prior_roster, current_roster):
        roster["athlete_id"] = roster.athlete_id.astype(str).str.replace(r"\.0$", "", regex=True)
    val = values.sort_values("minutes", ascending=False).drop_duplicates("athlete_id")
    def strength(roster: pd.DataFrame, current: bool) -> pd.Series:
        r = roster[roster.team_abbreviation.isin(TEAMS)].drop_duplicates(["team_abbreviation", "athlete_id"]).copy()
        r = r.merge(val[["athlete_id", "minutes", "impact"]], how="left", on="athlete_id")
        r["minutes"] = r.minutes.fillna(180 if current else 0).clip(0, 2600)
        r["impact"] = r.impact.fillna(0)
        # Keep a realistic 12-player rotation and scale to an 82-game minute budget.
        r = r.sort_values(["team_abbreviation", "minutes"], ascending=[True, False]).groupby("team_abbreviation").head(12)
        def one(g):
            mins = g.minutes.to_numpy(float).copy()
            if mins.sum() > 82 * 240:
                mins *= (82 * 240) / mins.sum()
            return float(np.sum(g.impact.to_numpy(float) * mins) / (82 * 48))
        return r.groupby("team_abbreviation").apply(one, include_groups=False).reindex(TEAMS, fill_value=0)

    old = strength(prior_roster, False)
    new = strength(current_roster, True)
    adj = ((new - old) * .55).clip(-5, 5)
    adj -= adj.mean()
    ratings = ratings.copy()
    ratings["roster_adj"] = ratings.team.map(adj).fillna(0)
    ratings["rating"] = ratings.raw_net + ratings.roster_adj
    ratings["rating"] -= ratings.rating.mean()

    current = current_roster[current_roster.team_abbreviation.isin(TEAMS)].copy()
    current = current.drop_duplicates(["team_abbreviation", "athlete_id"])
    current = current.merge(val, how="left", on="athlete_id", suffixes=("", "_prior"))
    rows = []
    for _, p in current.iterrows():
        if pd.isna(p.get("minutes")) or float(p.get("minutes", 0)) < 150:
            continue
        rows.append({"team": p.team_abbreviation, "player": p.get("display_name", p.get("athlete_display_name", "")),
                     "position": p.get("position_abbreviation", ""), "games": int(p.games),
                     "minutes": round(float(p.minutes)), "ppg": round(float(p.ppg), 1),
                     "rpg": round(float(p.rpg), 1), "apg": round(float(p.apg), 1),
                     "impact": round(float(p.impact), 2)})
    rows.sort(key=lambda p: (-p["impact"], -p["minutes"]))
    return ratings, rows


def _schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    d = schedule[(pd.to_numeric(schedule.season_type, errors="coerce") == 2)
                 & schedule.home_abbreviation.isin(TEAMS)
                 & schedule.away_abbreviation.isin(TEAMS)].copy()
    d["completed"] = _bool(d.status_type_completed)
    for col in ("home_score", "away_score"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["game_date"] = pd.to_datetime(d.game_date, errors="coerce").dt.strftime("%Y-%m-%d")
    d = d.sort_values(["game_date", "id"]).drop_duplicates("id")
    return d


def _one_game(rng: np.random.Generator, home: str, away: str, strength: np.ndarray,
              neutral: bool = False) -> str:
    margin = strength[TIX[home]] - strength[TIX[away]] + (0 if neutral else HFA) + rng.normal(0, GAME_SIGMA)
    return home if margin > 0 else away


def _series(rng: np.random.Generator, a: str, b: str, strength: np.ndarray,
            records: dict[str, int]) -> str:
    # Better regular-season record owns Games 1, 2, 5 and 7; rating breaks ties.
    if (records[b], strength[TIX[b]]) > (records[a], strength[TIX[a]]):
        a, b = b, a
    wa = wb = 0
    for home_a in (True, True, False, False, True, False, True):
        home, away = (a, b) if home_a else (b, a)
        winner = _one_game(rng, home, away, strength)
        wa += winner == a
        wb += winner == b
        if wa == 4 or wb == 4:
            break
    return a if wa == 4 else b


def _simulate(schedule: pd.DataFrame, ratings: pd.DataFrame, n_sims: int) -> dict[str, dict]:
    base = ratings.set_index("team").rating.reindex(TEAMS).to_numpy(float)
    actual_wins = np.zeros(len(TEAMS), dtype=np.int16)
    actual_pd = np.zeros(len(TEAMS), dtype=float)
    remaining = []
    for _, g in schedule.iterrows():
        h, a = g.home_abbreviation, g.away_abbreviation
        if g.completed and pd.notna(g.home_score) and pd.notna(g.away_score):
            winner = h if g.home_score > g.away_score else a
            actual_wins[TIX[winner]] += 1
            actual_pd[TIX[h]] += float(g.home_score - g.away_score)
            actual_pd[TIX[a]] += float(g.away_score - g.home_score)
        else:
            remaining.append((TIX[h], TIX[a]))

    # Before the NBA Cup bracket is known, the published schedule contains 80
    # named games per team. Add balanced anonymous pairings so the futures
    # simulation still completes an 82-game season; official games replace
    # these automatically as the schedule fills in.
    listed = pd.concat([schedule.home_abbreviation, schedule.away_abbreviation]).value_counts()
    deficits = {t: max(0, 82 - int(listed.get(t, 0))) for t in TEAMS}
    flex_no = 0
    while sum(deficits.values()) >= 2:
        home = max(TEAMS, key=lambda t: (deficits[t], -TIX[t]))
        if deficits[home] <= 0:
            break
        candidates = [t for t in TEAMS if t != home and deficits[t] > 0]
        if not candidates:
            break
        away = max(candidates, key=lambda t: (deficits[t], -((TIX[t] + flex_no) % len(TEAMS))))
        if flex_no % 2:
            home, away = away, home
        remaining.append((TIX[home], TIX[away]))
        deficits[home] -= 1
        deficits[away] -= 1
        flex_no += 1

    counts = {t: {"div": 0, "top6": 0, "playin": 0, "playoff": 0, "seed1": 0, "conf": 0, "title": 0,
                  "wins": np.zeros(83, dtype=np.int64)} for t in TEAMS}
    rng = np.random.default_rng(20261009)

    home_ix = np.array([g[0] for g in remaining], dtype=np.int16)
    away_ix = np.array([g[1] for g in remaining], dtype=np.int16)
    batch_size = 2000
    done = 0
    while done < n_sims:
        size = min(batch_size, n_sims - done)
        strengths = base[None, :] + rng.normal(0, TEAM_TAU, (size, len(TEAMS)))
        wins_batch = np.tile(actual_wins, (size, 1))
        pd_batch = np.tile(actual_pd, (size, 1))
        if len(home_ix):
            margins = (strengths[:, home_ix] - strengths[:, away_ix] + HFA
                       + rng.normal(0, GAME_SIGMA, (size, len(home_ix))))
            winner_ix = np.where(margins > 0, home_ix[None, :], away_ix[None, :])
            sim_ix = np.repeat(np.arange(size), len(home_ix))
            np.add.at(wins_batch, (sim_ix, winner_ix.ravel()), 1)
            tiled_home = np.tile(home_ix, size)
            tiled_away = np.tile(away_ix, size)
            np.add.at(pd_batch, (sim_ix, tiled_home), margins.ravel())
            np.add.at(pd_batch, (sim_ix, tiled_away), -margins.ravel())

        for local in range(size):
            strength = strengths[local]
            win_arr = wins_batch[local]
            pd_arr = pd_batch[local]
            wins = {t: int(win_arr[TIX[t]]) for t in TEAMS}
            for t in TEAMS:
                counts[t]["wins"][min(82, wins[t])] += 1
            for members in DIVS.values():
                winner = max(members, key=lambda t: (wins[t], pd_arr[TIX[t]], strength[TIX[t]], rng.random()))
                counts[winner]["div"] += 1

            conference_winners = []
            for conference in (EAST, WEST):
                order = sorted(conference, key=lambda t: (wins[t], pd_arr[TIX[t]], strength[TIX[t]], rng.random()), reverse=True)
                counts[order[0]]["seed1"] += 1
                for t in order[:6]:
                    counts[t]["top6"] += 1
                for t in order[6:10]:
                    counts[t]["playin"] += 1

                seven = _one_game(rng, order[6], order[7], strength)
                first_loser = order[7] if seven == order[6] else order[6]
                nine_winner = _one_game(rng, order[8], order[9], strength)
                eight = _one_game(rng, first_loser, nine_winner, strength)
                seeds = [order[0], order[1], order[2], order[3], order[4], order[5], seven, eight]
                for t in seeds:
                    counts[t]["playoff"] += 1

                q1 = _series(rng, seeds[0], seeds[7], strength, wins)
                q2 = _series(rng, seeds[3], seeds[4], strength, wins)
                q3 = _series(rng, seeds[2], seeds[5], strength, wins)
                q4 = _series(rng, seeds[1], seeds[6], strength, wins)
                s1 = _series(rng, q1, q2, strength, wins)
                s2 = _series(rng, q4, q3, strength, wins)
                champion = _series(rng, s1, s2, strength, wins)
                counts[champion]["conf"] += 1
                conference_winners.append(champion)
            champion = _series(rng, conference_winners[0], conference_winners[1], strength, wins)
            counts[champion]["title"] += 1
        done += size

    out = {}
    for t in TEAMS:
        c = counts[t]
        dist = c["wins"] / n_sims
        out[t] = {"mean_wins": round(float(np.dot(np.arange(83), dist)), 2),
                  "p_div": c["div"] / n_sims, "p_top6": c["top6"] / n_sims,
                  "p_playin": c["playin"] / n_sims, "p_playoff": c["playoff"] / n_sims,
                  "p_seed1": c["seed1"] / n_sims, "p_conf": c["conf"] / n_sims,
                  "p_title": c["title"] / n_sims, "win_dist": dist.tolist(),
                  "rating": round(float(base[TIX[t]]), 2)}
    return out


def _game_rows(schedule: pd.DataFrame, ratings: pd.DataFrame) -> list[dict]:
    strength = ratings.set_index("team").rating
    rows = []
    for _, g in schedule.iterrows():
        margin = float(strength[g.home_abbreviation] - strength[g.away_abbreviation] + HFA)
        rows.append({"date": g.game_date, "home": g.home_abbreviation, "away": g.away_abbreviation,
                     "completed": bool(g.completed),
                     "home_score": int(g.home_score) if pd.notna(g.home_score) and g.completed else None,
                     "away_score": int(g.away_score) if pd.notna(g.away_score) and g.completed else None,
                     "home_win": float(0.5 * (1 + math.erf(margin / GAME_SIGMA / math.sqrt(2)))),
                     "projected_margin": round(margin, 1)})
    return rows


def build_data() -> None:
    end_year = season_end_year()
    log("NBA season", f"{end_year - 1}-{str(end_year)[-2:]}")
    boxes, raw_schedule, players, prior_roster, current_roster = _load_inputs(end_year)
    ratings, fit = _fit_ratings(boxes, end_year)
    values = _player_values(players)
    ratings, player_rows = _roster_adjustment(ratings, values, prior_roster, current_roster)
    schedule = _schedule(raw_schedule)
    if len(schedule) < 1200:
        raise RuntimeError(f"NBA schedule is incomplete ({len(schedule)} regular-season games)")
    n_sims = int(os.environ.get("NBA_N_SIMS", os.environ.get("N_SIMS", "100000")))
    futures = _simulate(schedule, ratings, n_sims)
    for team, row in futures.items():
        ratings.loc[ratings.team == team, "projected_wins"] = row["mean_wins"]

    played = int(schedule.completed.sum())
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    meta = {"league": "NBA", "season": f"{end_year - 1}-{str(end_year)[-2:]}", "season_end_year": end_year,
            "games_played": played, "games_scheduled": 1230, "listed_games": int(len(schedule)), "updated_utc": now,
            "n_sims": n_sims, "model": "NBA v0.1", **fit}
    rating_rows = []
    for _, r in ratings.sort_values("rating", ascending=False).iterrows():
        rating_rows.append({"team": r.team, "name": NAMES[r.team],
                            "off_rating": round(float(r.base_ortg + r.off), 1),
                            "def_rating": round(float(r.base_ortg - r["def"]), 1),
                            "net_rating": round(float(r.raw_net), 1), "roster_adj": round(float(r.roster_adj), 1),
                            "model_rating": round(float(r.rating), 1), "pace": round(float(r.pace), 1),
                            "projected_wins": round(float(r.projected_wins), 1)})
    write_json("nba_meta.json", meta)
    write_json("nba_futures.json", {"teams": futures, "divisions": DIVS, "east": EAST, "west": WEST})
    write_json("nba_ratings.json", {"rows": rating_rows})
    write_json("nba_players.json", {"rows": player_rows})
    write_json("nba_games.json", {"rows": _game_rows(schedule, ratings)})
    log("NBA simulation done", n_sims, "seasons")


def build_site() -> None:
    os.makedirs(os.path.join(NBA_SITE, "data"), exist_ok=True)
    shutil.copytree(os.path.join(NBA_SRC, "js"), os.path.join(NBA_SITE, "js"), dirs_exist_ok=True)
    for name in ("nba_meta.json", "nba_futures.json", "nba_ratings.json", "nba_players.json", "nba_games.json"):
        shutil.copy(os.path.join(OUT, name), os.path.join(NBA_SITE, "data", name.removeprefix("nba_")))
    for name in ("index.html", "ratings.html", "players.html", "games.html", "methodology.html"):
        shutil.copy(os.path.join(NBA_SRC, name), os.path.join(NBA_SITE, name))
