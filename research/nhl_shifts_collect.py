"""Collect NHL shift charts + play-by-play and turn each game into stints (research).

For every regular-season game of a season (game ids from data/research/nhl_lineups/skaters_<y>.csv.gz, or the schedule):
  shifts: https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId=<id>   (who was on the ice, start/end)
  plays:  https://api-web.nhle.com/v1/gamecenter/<id>/play-by-play                (shots with location, type, goalie)
Sequential requests with a pause; stops on 403/429. Writes to <out>/:
  stints_<y>.csv.gz: game_id, period, start, end, dur (s), home, away, home_sk, away_sk (';'-joined player ids), home_g, away_g
  shots_<y>.csv.gz:  game_id, period, t (s), stint (row index within the game's stints), team, home (1 if home team shot),
                     type (shot-on-goal|missed-shot|goal|blocked-shot), x, y, shot_type, situation, shooter, goalie, empty_net
  players_<y>.csv.gz: player_id, name, pos, team (from the game rosters)
Usage: python research/nhl_shifts_collect.py <season> <out dir>
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "SportsFutures/1.0 (private research; low volume)"
PAUSE = 0.35


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise SystemExit(f"stopped: HTTP {e.code} at {url}")
            if e.code == 404:
                return None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 * (attempt + 1))
    return None


def secs(s):
    if not s:
        return None
    m, x = s.split(":")
    return int(m) * 60 + int(x)


def game_stints(gid, shifts, pbp):
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    hid, aid = home["id"], away["id"]
    pos = {r["playerId"]: r.get("positionCode") for r in pbp.get("rosterSpots", [])}
    names = {r["playerId"]: (f'{r["firstName"]["default"]} {r["lastName"]["default"]}', r.get("positionCode"), r.get("teamId"))
             for r in pbp.get("rosterSpots", [])}
    sh = [s for s in shifts if s.get("typeCode") == 517 and s.get("startTime") and s.get("endTime")]
    stints, shots = [], []
    for per in sorted({s["period"] for s in sh}):
        if per > 4:              # shootout / extra periods beyond regular-season OT
            continue
        ps = [(secs(s["startTime"]), secs(s["endTime"]), s["playerId"], s["teamId"]) for s in sh if s["period"] == per]
        ps = [p for p in ps if p[0] is not None and p[1] is not None and p[1] > p[0]]
        cuts = sorted({p[0] for p in ps} | {p[1] for p in ps})
        prev_key = None
        for a, b in zip(cuts[:-1], cuts[1:]):
            on = [(pid, tid) for s0, s1, pid, tid in ps if s0 <= a and s1 >= b]
            hs = sorted(p for p, t in on if t == hid and pos.get(p) != "G")
            as_ = sorted(p for p, t in on if t == aid and pos.get(p) != "G")
            hg = [p for p, t in on if t == hid and pos.get(p) == "G"]
            ag = [p for p, t in on if t == aid and pos.get(p) == "G"]
            key = (tuple(hs), tuple(as_), hg[0] if hg else 0, ag[0] if ag else 0)
            if not hs and not as_:
                continue
            if key == prev_key and stints and stints[-1]["end"] == a and stints[-1]["period"] == per:
                stints[-1]["end"] = b
                stints[-1]["dur"] = b - stints[-1]["start"]
            else:
                stints.append({"game_id": gid, "period": per, "start": a, "end": b, "dur": b - a, "home": home["abbrev"],
                               "away": away["abbrev"], "home_sk": ";".join(map(str, key[0])), "away_sk": ";".join(map(str, key[1])),
                               "home_g": key[2], "away_g": key[3]})
            prev_key = key
    idx = {}
    for i, s in enumerate(stints):
        idx.setdefault(s["period"], []).append((s["start"], s["end"], i))
    for p in pbp.get("plays", []):
        k = p.get("typeDescKey")
        if k not in ("shot-on-goal", "missed-shot", "goal", "blocked-shot"):
            continue
        per = p.get("periodDescriptor", {}).get("number")
        if per is None or per > 4:
            continue
        t = secs(p.get("timeInPeriod"))
        d = p.get("details", {}) or {}
        st = None
        for a, b, i in idx.get(per, []):
            if a < t <= b or (t == 0 and a == 0):
                st = i
                break
        team = d.get("eventOwnerTeamId")
        shots.append({"game_id": gid, "period": per, "t": t, "stint": st, "team": home["abbrev"] if team == hid else away["abbrev"],
                      "home": int(team == hid), "type": k, "x": d.get("xCoord"), "y": d.get("yCoord"), "shot_type": d.get("shotType"),
                      "situation": p.get("situationCode"), "shooter": d.get("shootingPlayerId") or d.get("scoringPlayerId"),
                      "goalie": d.get("goalieInNetId"), "side": p.get("homeTeamDefendingSide")})
    return stints, shots, names


def game_ids(y):
    p = os.path.join(ROOT, "data", "research", "nhl_lineups", f"skaters_{y}.csv.gz")
    if os.path.exists(p):
        return sorted(pd.read_csv(p, usecols=["game_id"]).game_id.unique())
    return []


def main(y, out):
    os.makedirs(out, exist_ok=True)
    ids = game_ids(y)
    print(y, len(ids), "games", flush=True)
    ST, SH, PL = [], [], {}
    done_path = os.path.join(out, f"stints_{y}.csv.gz")
    have = set()
    if os.path.exists(done_path):
        have = set(pd.read_csv(done_path, usecols=["game_id"]).game_id)
        ST.append(pd.read_csv(done_path)); SH.append(pd.read_csv(os.path.join(out, f"shots_{y}.csv.gz")))
    new_st, new_sh = [], []
    for n, gid in enumerate(ids):
        if gid in have:
            continue
        s = get(f"https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={gid}")
        time.sleep(PAUSE)
        p = get(f"https://api-web.nhle.com/v1/gamecenter/{gid}/play-by-play")
        time.sleep(PAUSE)
        if not s or not p or not s.get("data"):
            print("missing", gid, flush=True)
            continue
        st, sh, names = game_stints(gid, s["data"], p)
        new_st += st; new_sh += sh
        for pid, v in names.items():
            PL[pid] = v
        if n % 100 == 0:
            print(y, n, len(new_st), flush=True)
    if new_st:
        ST.append(pd.DataFrame(new_st)); SH.append(pd.DataFrame(new_sh))
    pd.concat(ST, ignore_index=True).to_csv(done_path, index=False)
    pd.concat(SH, ignore_index=True).to_csv(os.path.join(out, f"shots_{y}.csv.gz"), index=False)
    pp = os.path.join(out, f"players_{y}.csv.gz")
    P = pd.DataFrame([(k, *v) for k, v in PL.items()], columns=["player_id", "name", "pos", "team_id"])
    if os.path.exists(pp):
        P = pd.concat([pd.read_csv(pp), P]).drop_duplicates("player_id", keep="last")
    P.to_csv(pp, index=False)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
