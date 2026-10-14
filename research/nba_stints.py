"""Build NBA lineup stints from ESPN play-by-play (sportsdataverse espn_nba_pbp) for a player rating model (research).

Lineups: starters from the player box score; each substitution swaps the player leaving (athlete_id_2) for the one entering
(athlete_id_1). At the start of periods 2+ the five per team are the players who act or are subbed out in that period before
being subbed in, topped up from the previous period's closing five. Each stint (unchanged ten players) records points and
possessions for both teams (possessions = FGA - OREB + TOV + 0.44 FTA, averaged over the two teams).
Usage: python research/nba_stints.py <pbp dir> <out dir> <season> [...]   -> <out>/stints_<season>.parquet
Regular season only. Games whose lineups cannot be reconstructed (not exactly five a side) are skipped and counted.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOX = os.path.join(ROOT, "data", "nba")


def _id(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def game_stints(ev, box):
    home, away = int(ev.home_team_id.iloc[0]), int(ev.away_team_id.iloc[0])
    team_of = dict(zip(box.athlete_id, box.team_id))
    starters = {t: [a for a, tt, s in zip(box.athlete_id, box.team_id, box.starter) if tt == t and s] for t in (home, away)}
    if any(len(v) != 5 for v in starters.values()):
        return None
    rows = []
    closing = {t: list(starters[t]) for t in (home, away)}
    for per, pe in ev.groupby("period_number", sort=True):
        if per == 1:
            on = {t: list(starters[t]) for t in (home, away)}
        else:
            on = {home: [], away: []}
            entered = set()
            for typ, a1, a2, a3 in zip(pe.type_text, pe.a1, pe.a2, pe.a3):
                if typ == "Substitution":
                    if a2 is not None and a2 not in entered:
                        t = team_of.get(a2)
                        if t in on and a2 not in on[t]:
                            on[t].append(a2)
                    if a1 is not None:
                        entered.add(a1)
                    continue
                for a in (a1, a2, a3):
                    if a is not None and a not in entered:
                        t = team_of.get(a)
                        if t in on and a not in on[t]:
                            on[t].append(a)
            for t in (home, away):
                for a in closing[t]:
                    if len(on[t]) >= 5:
                        break
                    if a not in on[t] and a not in entered:
                        on[t].append(a)
                on[t] = on[t][:5]
        if any(len(on[t]) != 5 for t in (home, away)):
            return None
        cur = {"pts": {home: 0, away: 0}, "fga": {home: 0, away: 0}, "orb": {home: 0, away: 0}, "tov": {home: 0, away: 0},
               "fta": {home: 0, away: 0}, "sec": 0.0}
        last_clock = None

        def flush():
            if cur["sec"] <= 0 and not any(cur["fga"].values()) and not any(cur["fta"].values()):
                return
            rows.append((tuple(sorted(on[home])), tuple(sorted(on[away])), cur["pts"][home], cur["pts"][away],
                         *(cur[k][home] for k in ("fga", "orb", "tov", "fta")), *(cur[k][away] for k in ("fga", "orb", "tov", "fta")),
                         cur["sec"]))
        prev_h, prev_a = None, None
        for r in pe.itertuples(index=False):
            clock = r.start_quarter_seconds_remaining
            if last_clock is not None and clock == clock:
                cur["sec"] += max(0.0, last_clock - clock)
            if clock == clock:
                last_clock = clock
            if r.type_text == "Substitution":
                t = team_of.get(r.a1) or team_of.get(r.a2)
                if t in on and r.a2 in on[t] and r.a1 is not None and r.a1 not in on[t]:
                    flush()
                    cur = {k: ({home: 0, away: 0} if k != "sec" else 0.0) for k in cur}
                    on[t] = [r.a1 if a == r.a2 else a for a in on[t]]
                continue
            t = _id(r.team_id)
            if t not in (home, away):
                continue
            typ = str(r.type_text)
            if "Free Throw" in typ:
                cur["fta"][t] += 1
            elif r.shooting_play:
                cur["fga"][t] += 1
            if typ.startswith("Offensive Rebound"):
                cur["orb"][t] += 1
            if "Turnover" in typ:
                cur["tov"][t] += 1
            if r.scoring_play and r.score_value == r.score_value:
                cur["pts"][t] += int(r.score_value)
        flush()
        closing = {t: list(on[t]) for t in (home, away)}
    return rows


def season(pbp_dir, out_dir, y):
    ev = pd.read_parquet(os.path.join(pbp_dir, f"pbp_{y}.parquet"),
                         columns=["game_id", "game_play_number", "sequence_number", "type_text", "period_number", "team_id",
                                  "athlete_id_1", "athlete_id_2", "athlete_id_3", "scoring_play", "score_value", "shooting_play",
                                  "start_quarter_seconds_remaining", "home_team_id", "away_team_id", "season_type", "game_date"])
    ev = ev[pd.to_numeric(ev.season_type, errors="coerce") == 2].copy()
    for c in ("athlete_id_1", "athlete_id_2", "athlete_id_3"):
        ev[c] = pd.Series([_id(x) for x in ev[c]], index=ev.index, dtype=object)
    ev = ev.rename(columns={"athlete_id_1": "a1", "athlete_id_2": "a2", "athlete_id_3": "a3"})
    ev["seq"] = pd.to_numeric(ev.sequence_number, errors="coerce")
    ev = ev.sort_values(["game_id", "period_number", "seq"])
    box = pd.read_csv(os.path.join(BOX, f"player_box_{y}.csv"), usecols=["game_id", "athlete_id", "team_id", "starter"], low_memory=False)
    box["athlete_id"] = box.athlete_id.map(_id)
    box["starter"] = box.starter.astype(str).str.lower().eq("true")
    boxes = {g: b for g, b in box.groupby("game_id")}
    out, bad = [], 0
    for gid, g in ev.groupby("game_id", sort=False):
        b = boxes.get(gid)
        res = game_stints(g, b) if b is not None else None
        if res is None:
            bad += 1
            continue
        date = str(g.game_date.iloc[0])[:10]
        out.extend((gid, date, *r) for r in res)
    cols = ["game_id", "date", "home5", "away5", "hpts", "apts", "hfga", "horb", "htov", "hfta", "afga", "aorb", "atov", "afta", "sec"]
    S = pd.DataFrame(out, columns=cols)
    S["poss"] = ((S.hfga - S.horb + S.htov + .44 * S.hfta) + (S.afga - S.aorb + S.atov + .44 * S.afta)) / 2
    for side in ("home5", "away5"):
        S[side] = S[side].map(lambda t: ",".join(map(str, t)))
    S.to_parquet(os.path.join(out_dir, f"stints_{y}.parquet"), index=False)
    print(y, "games", ev.game_id.nunique(), "skipped", bad, "stints", len(S), "poss", round(S.poss.sum()), flush=True)


if __name__ == "__main__":
    pbp_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    for y in sys.argv[3:]:
        season(pbp_dir, out_dir, int(y))
