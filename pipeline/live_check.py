"""Live check: score this season's archived forecasts (the numbers the site actually published) as outcomes come in.

Two parts, both from the append-only forecast-archive branch, so nothing here can be re-tuned after the fact:

1. Settled futures. Once a season is at least half played, a team-market counts as settled when the newest published
   snapshot shows it at exactly 0% or 100% (no simulation produces any other result; after the season this is the real
   outcome). Every earlier snapshot's probability for
   that team-market is then scored (log loss vs a flat guess at the settled share). Settled-early items are mostly the
   easy cases (clear eliminations and clinches), so this flatters every model a little; it is most useful for comparing
   models on the same items (NFL: v4 against its archived challengers).
2. NFL games. Each archived NFL snapshot carries the team ratings that drove it; the next week's games are scored with
   the simulation's own single-game probability, Phi((home - away + hfa) / S), S = sqrt(sigma^2 + 2 tau^2), for v4 and
   for the v3 challenger (its own tau/sigma/hfa). Every game is scored once, from the latest snapshot before kick-off.

Output: a "live_check" block per sport, rendered on that sport's History page.
"""
import gzip
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# sport_archive market keys -> labels (same keys as replay_site.SPORTS)
LABELS = {"title": "Title", "finals": "Conference / Grand Final", "div": "Division / top group", "seed1": "No. 1 seed / minor premier",
          "playoff": "Make the playoffs / finals", "top8": "Top 8", "pf": "Preliminary final"}


def _ll(p, y):
    p = min(max(p, 0.002), 0.998)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _snapshots(path):
    out = []
    if not os.path.isdir(path):
        return out
    for f in sorted(os.listdir(path)):
        if f.endswith(".json.gz"):
            try:
                out.append(json.load(gzip.open(os.path.join(path, f), "rt")))
            except Exception:  # noqa: BLE001
                continue
    return out


def settled_scores(snaps, models, progress=0.0, min_progress=0.5):
    """snaps: list of dicts {generated_utc, teams, <model>: {market: [p0..1 per team]}}; the first model decides settlement.
    Returns per market: settled yes/no counts and, per model, mean log loss over all snapshots, the flat-guess log loss
    and the probability first published for the items that happened."""
    if not snaps:
        return {"snapshots": 0, "markets": {}}
    if progress < min_progress:      # simulated 0% / 100% early in a season is not a settled outcome
        return {"snapshots": len(snaps), "first": snaps[0]["generated_utc"][:10], "last": snaps[-1]["generated_utc"][:10],
                "progress": round(progress, 2), "markets": {}, "note": "Futures are scored once the season is at least half played."}
    last = snaps[-1]
    lead = models[0]
    teams = last["teams"]
    res = {}
    for m, plast in last[lead].items():
        settled = {t: (1 if p >= 0.9995 else 0) for t, p in zip(teams, plast) if p <= 0.0005 or p >= 0.9995}
        if not settled:
            res[m] = {"settled": 0}
            continue
        ys = list(settled.values())
        share = sum(ys) / len(ys)
        out = {"settled": len(settled), "yes": int(sum(ys)), "by_model": {}}
        for mod in models:
            L, B, n, first_yes = 0.0, 0.0, 0, []
            for s in snaps[:-1]:                       # the settling snapshot itself is not a forecast
                pm = (s.get(mod) or {}).get(m)
                if pm is None:
                    continue
                pos = {t: i for i, t in enumerate(s["teams"])}
                for t, y in settled.items():
                    if t in pos:
                        L += _ll(pm[pos[t]], y)
                        B += _ll(share, y)
                        n += 1
            if n:
                out["by_model"][mod] = {"logloss": round(L / n, 4), "flat": round(B / n, 4), "n": n}
        first = next((s for s in snaps if s.get(lead, {}).get(m) is not None), None)
        if first:
            pos = {t: i for i, t in enumerate(first["teams"])}
            out["first_p_yes"] = [round(first[lead][m][pos[t]], 3) for t, y in settled.items() if y == 1 and t in pos]
            out["first_p_no_max"] = round(max([first[lead][m][pos[t]] for t, y in settled.items() if y == 0 and t in pos] or [0]), 3)
        res[m] = out
    return {"snapshots": len(snaps), "first": snaps[0]["generated_utc"][:10], "last": last["generated_utc"][:10], "progress": round(progress, 2), "markets": res}


def sport_snapshots(archive, sport):
    """Snapshots from pipeline/sport_archive.py (per-mille ints) -> fractions under model key 'live'."""
    base = os.path.join(archive, sport)
    if not os.path.isdir(base):
        return None, []
    years = sorted(int(d) for d in os.listdir(base) if d.isdigit())
    if not years:
        return None, []
    snaps = []
    for x in _snapshots(os.path.join(base, str(years[-1]))):
        snaps.append({"generated_utc": x["generated_utc"], "teams": x["teams"], "gp_avg": x.get("gp_avg") or 0.0,
                      "live": {k: [v / 1000 for v in vals] for k, vals in x["p"].items() if not k.startswith("c_") and k != "rating_x100"},
                      "challenger": {k[2:]: [v / 1000 for v in vals] for k, vals in x["p"].items() if k.startswith("c_")} or None})
    return years[-1], snaps


NFL_KEYS = {"title": "p_sb", "finals": "p_conf", "div": "p_div", "seed1": "p_seed1", "playoff": "p_playoff"}


def nfl_snapshots(archive):
    """Full NFL snapshots (pipeline/archive.py, <archive>/<season>/) with v4 and the archived challengers."""
    years = sorted(int(d) for d in os.listdir(archive) if d.isdigit()) if os.path.isdir(archive) else []
    if not years:
        return None, []
    snaps = []
    for x in _snapshots(os.path.join(archive, str(years[-1]))):
        teams = sorted(x["teams"])
        s = {"generated_utc": x["generated_utc"], "teams": teams, "through_week": x.get("through_week"),
             "v4": {m: [x["teams"][t].get(f, 0.0) for t in teams] for m, f in NFL_KEYS.items()},
             "ratings": {t: x["teams"][t].get("rating") for t in teams}}
        for key, name in (("challenger", "v3"), ("challenger_v5", "v5 candidate")):
            c = x.get(key)
            if c and c.get("teams"):
                s[name] = {m: [c["teams"].get(t, {}).get(f, 0.0) for t in teams] for m, f in NFL_KEYS.items()}
                if key == "challenger":
                    s["ratings_v3"] = {t: c["teams"].get(t, {}).get("rating") for t in teams}
        snaps.append(s)
    return years[-1], snaps


def nfl_games(snaps, season):
    """Score every completed regular-season game once, from the latest archived snapshot before its kick-off date."""
    try:
        import sys
        sys.path.insert(0, os.path.join(ROOT, "pipeline"))
        from common import FIX, games
        import ratings as RT
    except Exception:  # noqa: BLE001
        return None
    g = games()
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(FIX)
    g = g[(g.season == season) & g.result.notna()]
    S4 = RT.S["sim"]
    C3 = RT.S.get("challenger") or {}
    tot4 = math.sqrt(S4["sigma"] ** 2 + 2 * S4["tau"] ** 2)
    tot3 = math.sqrt(C3.get("sigma", 13) ** 2 + 2 * C3.get("tau", 3.5) ** 2) if C3 else None
    phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
    rows = []
    for r in g.itertuples():
        day = str(r.gameday)[:10]
        before = [s for s in snaps if s["generated_utc"][:10] < day]
        if not before or r.result == 0:
            continue
        s = before[-1]
        h, a = s["ratings"].get(r.home_team), s["ratings"].get(r.away_team)
        if h is None or a is None:
            continue
        neutral = str(getattr(r, "location", "")) == "Neutral"
        y = 1.0 if r.result > 0 else 0.0
        row = {"y": y, "v4": phi((h - a + (0 if neutral else S4["hfa"])) / tot4)}
        if tot3 and s.get("ratings_v3"):
            h3, a3 = s["ratings_v3"].get(r.home_team), s["ratings_v3"].get(r.away_team)
            if h3 is not None and a3 is not None:
                row["v3"] = phi((h3 - a3 + (0 if neutral else C3["hfa"])) / tot3)
        rows.append(row)
    if not rows:
        return {"games": 0}
    out = {"games": len(rows), "home_win_share": round(float(np.mean([r["y"] for r in rows])), 3)}
    for mod in ("v4", "v3"):
        rr = [r for r in rows if mod in r]
        if rr:
            out[mod] = {"games": len(rr), "logloss": round(float(np.mean([_ll(r[mod], r["y"]) for r in rr])), 4),
                        "correct": round(float(np.mean([(r[mod] > 0.5) == (r["y"] == 1) for r in rr])), 3),
                        "brier": round(float(np.mean([(r[mod] - r["y"]) ** 2 for r in rr])), 4)}
    out["coin_flip_logloss"] = round(math.log(2), 4)
    return out


SITE = os.path.join(ROOT, "site")


def _results(sport, season):
    """{(date, home, away): 1/0} for completed games, from that sport's published games files (home-side rows)."""
    d = os.path.join(SITE, sport, "data")
    out = {}
    for y in (season, season - 1):
        p = os.path.join(d, f"games_{y}.json")
        if not os.path.exists(p):
            continue
        for row in json.load(open(p)).get("rows", []):
            for i in range(2, min(len(row) - 1, 6)):
                if row[i] in ("H", "A", "R", "N") and isinstance(row[i + 1], str) and row[i + 1] in ("W", "L", "OTL", "D", "T"):
                    if row[i] == "H" and row[i + 1] in ("W", "L", "OTL"):
                        out[(str(row[0])[:10], row[i - 2], row[i - 1])] = 1 if row[i + 1] == "W" else 0
                    break
    return out


def sport_games(sport, season, raw_snaps):
    """Score the Outlook page's pre-game win chances, each game once from the latest snapshot made before its date."""
    res = _results(sport, season)
    if not res:
        return None
    pred = {}
    for x in raw_snaps:
        day0 = x["generated_utc"][:10]
        for day, h, a, p in x.get("games") or []:
            if day0 < day:
                pred[(day, h, a)] = p / 1000          # later snapshots overwrite earlier ones
    rows = [(p, res[k]) for k, p in pred.items() if k in res]
    if not rows:
        return {"games": 0}
    return {"games": len(rows), "home_win_share": round(float(np.mean([y for _, y in rows])), 3),
            "live": {"games": len(rows), "logloss": round(float(np.mean([_ll(p, y) for p, y in rows])), 4),
                     "correct": round(float(np.mean([(p > 0.5) == (y == 1) for p, y in rows])), 3),
                     "brier": round(float(np.mean([(p - y) ** 2 for p, y in rows])), 4)},
            "coin_flip_logloss": round(math.log(2), 4)}


def build(sport, archive, games_per_team=None):
    if not archive or not os.path.isdir(archive):
        return None
    if sport == "nfl":
        season, snaps = nfl_snapshots(archive)
        if not snaps:
            return None
        models = ["v4"] + [m for m in ("v3", "v5 candidate") if any(m in s for s in snaps)]
        res = settled_scores(snaps, models, progress=(snaps[-1].get("through_week") or 0) / 18)
        res["games"] = nfl_games(snaps, season)
    else:
        season, snaps = sport_snapshots(archive, sport)
        if not snaps:
            return None
        models = ["live"] + (["challenger"] if any(s.get("challenger") for s in snaps) else [])
        res = settled_scores(snaps, models, progress=float(snaps[-1].get("gp_avg") or 0) / (games_per_team or 82))
        base = os.path.join(archive, sport, str(season))
        res["games"] = sport_games(sport, season, _snapshots(base))
    res["season"] = season
    res["labels"] = LABELS
    return res
