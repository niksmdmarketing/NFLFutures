"""Hourly NHL news trigger: re-run the site refresh straight away when big injury news arrives.

Runs inside the hourly availability job. Reads a fresh CBS injury list (the same source the NHL model uses), compares it
with the injury list in the last published NHL forecast, and values each change with the model's own absence costs
(nhl_absence.player_costs: goals per game x games missed). If any new absence or return is worth at least
THRESHOLD_GOALS over the season (2.0, chosen with TypeSafe), it starts the 'Refresh site' workflow, so the model and the
private Movers page show the change within about an hour instead of at the next 2-hourly run.
The same player is not re-triggered within COOLDOWN_H hours. Every decision is appended to <store>/availability/
news_trigger.jsonl. Usage: python pipeline/nhl_news_trigger.py <published dir> <store dir>
"""
import datetime as dt
import json
import os
import subprocess
import sys

THRESHOLD_GOALS = 2.0
COOLDOWN_H = 6
GAMES_PER_DAY = 84 / 190     # a team's regular season: 84 games (from 2026-27) in about 190 days


def games_missed(r, today, left):
    if r.season_out:
        return left
    if r.ret is not None and r.ret == r.ret:      # not NaN
        return max(0, min(left, round((r.ret - today).days * GAMES_PER_DAY)))
    if r.dtd:
        return 1
    return min(left, 7)


def main(pub, store):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ["NHL_INJ_MAX_AGE_H"] = "0"
    import nhl
    nhl.NHL_OUT = os.path.join(pub, "nhl", "data")      # published skater/goalie tables for player values
    import nhl_absence as A
    import nhl_injuries
    F = json.load(open(os.path.join(pub, "nhl", "data", "futures.json"), encoding="utf-8"))
    y = int(F["season"])
    pub_inj = {(p["team"], p["name"]): p for p in (F.get("injuries") or {}).get("players") or []}
    import nhl_model
    left = {t["team"]: max(0, nhl_model.season_games(y) - int(t.get("gp") or 0)) for t in F["teams"]}
    inj = nhl_injuries.current(y)
    if inj is None:
        print("NHL injury list unavailable; no trigger")
        return
    inj = inj[inj.team.isin(left)]
    today = dt.date.today()
    new = inj[[(t, n) not in pub_inj for t, n in zip(inj.team, inj.name)]]
    events = []
    if len(new):
        C = A.player_costs(y, new, A.values(y), *A._usage(y))
        for r, c in zip(new.itertuples(), C.itertuples()):
            g = games_missed(r, today, left.get(r.team, 0))
            events.append({"kind": "out", "team": r.team, "name": r.name, "status": r.status, "games": g, "goals": round(c.cost * g, 3)})
    now_keys = set(zip(inj.team, inj.name))
    for (t, n), p in pub_inj.items():
        if (t, n) not in now_keys:
            events.append({"kind": "back", "team": t, "name": n, "status": p.get("status"), "games": p.get("games_missed"),
                           "goals": round(float(p.get("season_goals") or 0), 3)})
    log_p = os.path.join(store, "availability", "news_trigger.jsonl")
    recent = {}
    if os.path.exists(log_p):
        for line in open(log_p, encoding="utf-8"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("triggered"):
                for k in e.get("keys", []):
                    recent[k] = e["utc"]
    now = dt.datetime.now(dt.timezone.utc)
    big = []
    for e in events:
        k = f"{e['kind']}|{e['team']}|{e['name']}"
        last = recent.get(k)
        if abs(e["goals"]) >= THRESHOLD_GOALS and not (last and now - dt.datetime.fromisoformat(last) < dt.timedelta(hours=COOLDOWN_H)):
            big.append(k)
    trig = False
    if big:
        r = subprocess.run(["gh", "workflow", "run", "refresh.yml", "--ref", "main"], capture_output=True, text=True)
        trig = r.returncode == 0
        print("trigger:", big, "ok" if trig else r.stderr[:300])
    if not events:
        print("NHL news: no changes vs published")
        return
    os.makedirs(os.path.dirname(log_p), exist_ok=True)
    with open(log_p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"utc": now.isoformat(timespec="minutes"), "events": events, "keys": big, "triggered": trig}) + "\n")
    print(f"NHL news: {len(events)} changes vs published, {len(big)} big; triggered={trig}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
