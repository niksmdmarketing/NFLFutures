"""NBL news layer, SHADOW ONLY (research/NEWS_IN_FUTURES_RULE.md). Design and code by DeepSeek (relay 033); Claude's corrections:
this season is included in the values (weight 1, then 0.6, 0.36; DeepSeek's version skipped it, so every baseline was 0); only
LISTED players cost or return anything (unlisted players keep the availability the rating reflects, as in NBA v2; DeepSeek's
version credited every player's past absences as a return); P(out) uses each game's own round, not the first game's.
Value = BETA x shrunk game score per 40 (minus the 30th-percentile replacement) x mpg / 40; BETA 0.45 is the NBA value and is
NOT validated for NBL (refit walk-forward before any promotion). No OREB/DREB split or fouls in the feed (0.3 x rebounds)."""
import re
import unicodedata

import numpy as np

BETA = 1.607   # walk-forward refit 9 Nov 2026 (research/nbl_beta_fit.py; NEWS_IN_FUTURES_RULE.md Amendment 3); was NBA's 0.45
SHRINK_MIN = 320.0
REPL_PCTL = 30.0
CAP_SD = 0.5
WEIGHTS = (1.0, 0.6, 0.36)          # this season, last, two ago


def key(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _gs(p):
    return (_f(p.get("points")) + 0.4 * _f(p.get("field_goals_made")) - 0.7 * _f(p.get("field_goals_attempted"))
            - 0.4 * (_f(p.get("free_throws_attempted")) - _f(p.get("free_throws_made"))) + 0.3 * _f(p.get("rebounds"))
            + _f(p.get("steals")) + 0.7 * _f(p.get("assists")) + 0.7 * _f(p.get("blocks")) - _f(p.get("turnovers")))


def values(seasons, y, beta=BETA):
    """seasons: {year: [regular-season leaders rows]} -> {(team, key): dict(value, baseline, mpg, gp)} for players on a team in y
    (or, before y has rows, in y - 1)."""
    raw = {}
    for i, yy in enumerate((y, y - 1, y - 2)):
        for p in seasons.get(yy, []):
            tm = str((p.get("team") or {}).get("team_code") or "")
            pl = p.get("player") or {}
            k = key(f"{pl.get('first_name', '')}{pl.get('last_name', '')}")
            mins = min(_f(p.get("minutes")), 4000.0)
            if not tm or not k or mins <= 0:
                continue
            a = raw.setdefault(k, {"gsw": 0.0, "min": 0.0, "team": {}, "gp": {}, "mpg": {}})
            a["gsw"] += WEIGHTS[i] * _gs(p) / mins * 40.0 * mins
            a["min"] += WEIGHTS[i] * mins
            a["team"].setdefault(yy, tm)
            a["gp"][yy] = _f(p.get("games"))
            a["mpg"].setdefault(yy, mins / max(_f(p.get("games")), 1.0))
    if not raw:
        return {}
    per40 = [a["gsw"] / a["min"] for a in raw.values() if a["min"] >= 200]
    repl = float(np.percentile(per40, REPL_PCTL)) if per40 else 0.0
    ref = y if any(y in a["team"] for a in raw.values()) else y - 1
    tgames = {}
    for a in raw.values():
        if ref in a["team"]:
            tgames[a["team"][ref]] = max(tgames.get(a["team"][ref], 0.0), a["gp"][ref])
    out = {}
    for k, a in raw.items():
        if ref not in a["team"]:
            continue
        tm = a["team"][ref]
        shr = (a["gsw"] + SHRINK_MIN * repl) / (a["min"] + SHRINK_MIN) - repl
        mpg = a["mpg"][ref]
        tg = tgames.get(tm, 0.0)
        base = float(np.clip(1.0 - a["gp"][ref] / tg, 0.0, 1.0)) if tg > 0 else 0.0
        out[(tm, k)] = {"value": float(beta * shr * mpg / 40.0), "baseline": base, "mpg": float(mpg), "gp": a["gp"][ref]}
    return out


def _round_no(x):
    m = re.search(r"(\d+)", str(x or ""))
    return int(m.group(1)) if m else None


def p_out(rec, r, now):
    cls = str(rec.get("return_text_class") or "").lower()
    if cls == "season":
        return 1.0
    if cls == "test":
        return 0.5 if r <= now else 0.0
    nums = [n for n in (_round_no(rec.get("return_low")), _round_no(rec.get("return_high")))
            if n is not None and str(rec.get("return_low") or rec.get("return_high") or "").strip().upper().startswith("R")]
    if nums:
        lo, hi = min(nums), max(nums)
        return float(np.mean([1.0 if v > r else 0.0 for v in range(lo, hi + 1)]))
    return float(np.mean([1.0 if now + v > r else 0.0 for v in range(3, 9)]))


def adjustments(todo, records, vals, rating, cap_sd=CAP_SD):
    """Array len(todo) added to the home-minus-away margin, or None when nothing applies."""
    if not records or not vals or not todo:
        return None
    rounds = [_round_no(g.get("round")) for g in todo]
    if all(r is None for r in rounds):
        return None
    now = min(r for r in rounds if r is not None)
    teams = sorted({t for t, _ in vals})
    cap = cap_sd * (float(np.std([rating.get(t, 0.0) for t in teams])) or 1.0)
    listed = {}
    for rec in records:
        k = key(rec.get("player_key") or rec.get("player"))
        tm = str(rec.get("team") or "")
        if not tm:
            hits = [t for (t, kk) in vals if kk == k]
            tm = hits[0] if len(hits) == 1 else ""
        if tm and (tm, k) in vals:
            listed[(tm, k)] = rec
    if not listed:
        return None
    adj = np.zeros(len(todo))
    for i, (g, r) in enumerate(zip(todo, rounds)):
        if r is None:
            continue
        for side, sign in ((g["home"], 1.0), (g["away"], -1.0)):
            d = sum(-v["value"] * (p_out(listed[(side, k)], r, now) - v["baseline"])
                    for (t, k), v in vals.items() if t == side and (t, k) in listed)
            adj[i] += sign * float(np.clip(d, -cap, cap))
    return adj
