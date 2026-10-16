"""Trust rating for every chances column (TypeSafe, Oct 2026): how far to trust our number in that market at this stage of
the season, from the replayed past seasons (model/replay/<sport>_score.json, _slope.json, CALIBRATION_CI.md) and the
documented comparisons with market prices. Writes <sport>/data/trust.json for the chances tables and Model pages.

Rule, per market and current stage of the season:
  'Market usually better'  a documented comparison found market prices more accurate at this stage
  'Not tested'             no replay for this market
  'Weak'                   skill (log-loss gain over a flat base rate, as a share of it) under 8%
  'Mixed'                  skill 8-25%, or miscalibration costing 0.005+ log loss, or thin evidence: fewer than 8 seasons,
                           or a market with one or two winners a season whose calibration interval does not support it
  'Reliable'               otherwise
Market prices are only used here as evidence about our own accuracy; they never feed a forecast.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPLAY = os.path.join(ROOT, "model", "replay")
SITE = os.path.join(ROOT, "site")
STAGES = ["preseason", "first quarter", "second quarter", "third quarter", "last quarter"]
ORDER = ["Reliable", "Mixed", "Weak", "Market usually better", "Not tested"]
FEW_WINNERS = {"title", "finals", "seed1", "pres"}   # one or two winners a season: calibration cannot be pinned down

# sport -> (site folder, games in a season, {site column: replay market})
SPORTS = {
    "nfl": ("", 17, {"p_sb": "title", "p_conf": "finals", "p_div": "div", "p_seed1": "seed1", "p_playoff": "playoff"}),
    "nba": ("nba", 82, {"p_title": "title", "p_conf": "finals", "p_div": "div", "p_seed1": "seed1", "p_cf": "cf", "p_r2": "r2",
                        "p_playoff": "playoff", "p_top6": "top6", "p_playin": "playin"}),
    "nhl": ("nhl", 82, {"p_cup": "title", "p_final": "finals", "p_div": "div", "p_playoffs": "playoff", "p_r2": "r2", "p_r3": "r3",
                        "p_pres": "pres"}),
    "afl": ("afl", 23, {"flag": "title", "gf": "finals", "pf": "pf", "p4": "div", "p1": "seed1", "p8": "top8", "p10": "playoff"}),
    "nbl": ("nbl", 28, {"champ": "title", "gf": "finals", "p2": "div", "p1": "seed1", "p6": "playoff", "semi": "semi"}),
}

# Documented comparisons with market prices (model/replay/WORKLOG.md, the sport pages): stages where the market was more
# accurate. {sport: [(markets or '*', stages, evidence)]}
MARKET_BETTER = {
    "nfl": [("*", {"preseason", "first quarter"}, "BetMGM 2018-25 and Polymarket 2024-25: the market was more accurate before about week 5"),
            ({"title"}, set(STAGES), "Polymarket 2024-25: the market stayed more accurate on the Super Bowl all season"),
            ("*", {"last quarter"}, "BetMGM 2018-25: the model trailed the market again late in the season")],
    "nba": [({"title", "finals"}, {"preseason"}, "Polymarket 2024-26: before the season the market was much more accurate on the title and conference winners"),
            ({"title"}, {"first quarter"}, "Polymarket 2024-26: the model caught up on the title only from about 40% of the season"),
            ({"finals"}, set(STAGES), "Polymarket 2024-26: the market stayed more accurate on conference winners")],
    "nhl": [({"title", "finals"}, {"preseason"}, "Polymarket 2025-26: before the season the market was slightly more accurate on the Cup and conference winners")],
}


def _ci():
    """{sport: {(stage, market): (lo, hi)}} slope intervals from CALIBRATION_CI.md."""
    out, sport = {}, None
    try:
        text = open(os.path.join(REPLAY, "CALIBRATION_CI.md"), encoding="utf-8").read()
    except OSError:
        return out
    for line in text.splitlines():
        m = re.match(r"## (\w+)", line)
        if m:
            sport = m.group(1).lower()
            continue
        m = re.match(r"\s*(preseason|first quarter|second quarter|third quarter|last quarter)\s+(\w+)\s+slope\s+[\d.]+\s+\[([\d.]+),([\d.]+)\]", line)
        if m and sport:
            out.setdefault(sport, {})[(m.group(1), m.group(2))] = (float(m.group(3)), float(m.group(4)))
    return out


def rate(score, slope, seasons, market, stage, market_note=None, ci=None):
    """(rating, reason) for one market at one stage. score/slope: that stage's entries for the market (or None)."""
    if market_note:
        return "Market usually better", market_note
    if not score:
        return "Not tested", "Not in the replayed seasons, so there is no track record for this column."
    skill = score["gain"] / score["base"] if score.get("base") else 0.0
    cost = (slope["ll"] - slope["ll_recal"]) if slope else 0.0
    sl = slope.get("slope") if slope else None
    bits = [f"{seasons} past seasons replayed at this stage: " + (f"{100 * skill:.0f}% better than a flat guess" if skill >= 0 else f"{-100 * skill:.0f}% worse than a flat guess")]
    if sl is not None:
        bits.append(f"calibration slope {sl:.2f}" + (" (too cautious)" if sl > 1.15 else " (too confident)" if sl < 0.85 else " (about right)"))
    if skill < 0.08:
        r = "Weak"
    elif skill < 0.25 or cost >= 0.005:
        r = "Mixed"
    else:
        r = "Reliable"
    if r == "Reliable" and seasons < 8:
        r, _ = "Mixed", bits.append("fewer than 8 seasons, too few to rate higher")
    if r == "Reliable" and market in FEW_WINNERS:
        lo_hi = (ci or {}).get((stage, market))
        if not lo_hi or not (lo_hi[0] <= 1 <= lo_hi[1]) or lo_hi[1] - lo_hi[0] > 0.8:
            r = "Mixed"
            bits.append("one or two winners a season, so its calibration " + (f"interval [{lo_hi[0]:.2f}, {lo_hi[1]:.2f}]" if lo_hi else "") +
                        " cannot support a higher rating")
    return r, "; ".join(bits) + "."


def stage_of(frac):
    if frac is None or frac <= 0.001:
        return "preseason"
    return STAGES[min(4, 1 + int(min(frac, 0.999) / 0.25))]


def _frac(sport, d, games):
    try:
        if sport == "nfl":
            return json.load(open(os.path.join(d, "data", "meta.json"))).get("through_week", 0) / 18
        F = json.load(open(os.path.join(d, "data", "futures.json")))
        if sport == "nhl":
            return (F.get("games_played") or 0) / games
        gp = [t.get("gp") or 0 for t in F.get("teams", [])]
        return (sum(gp) / len(gp) / games) if gp else 0
    except (OSError, ValueError, ZeroDivisionError):
        return None


def build(site=SITE):
    ci_all = _ci()
    for sport, (folder, games, cols) in SPORTS.items():
        d = os.path.join(site, folder) if folder else site
        if not os.path.isdir(os.path.join(d, "data")):
            continue
        try:
            score = json.load(open(os.path.join(REPLAY, f"{sport}_score.json")))
            slope = json.load(open(os.path.join(REPLAY, f"{sport}_slope.json")))
        except OSError:
            continue
        frac = _frac(sport, d, games)
        stage = stage_of(frac)

        def one(col, market, st):
            note = None
            for mk, stages, ev in MARKET_BETTER.get(sport, []):
                if market and (mk == "*" or market in mk) and st in stages:
                    note = ev + "."
                    break
            if not market:
                return rate(None, None, 0, None, st)
            sc = (score.get(st) or {}).get(market)
            sl = (slope.get(st) or {}).get(market)
            return rate(sc, sl, (sc or {}).get("seasons") or (score.get(st) or {}).get("seasons", 0), market, st, note, ci_all.get(sport))
        markets = {c: dict(zip(("r", "why"), one(c, m, stage))) for c, m in cols.items()}
        table = [{"col": c, "by_stage": [one(c, m, st)[0] for st in STAGES]} for c, m in cols.items()]
        out = {"stage": stage, "stages": STAGES, "markets": markets, "table": table,
               "legend": "How far to trust each column at this stage of the season, from replaying past seasons and comparing with "
                         "market prices where we have them. Reliable: accurate and well calibrated. Mixed: useful but off in places or "
                         "thin evidence. Weak: little better than a flat guess. Market usually better: market prices were more "
                         "accurate here. Not tested: no track record yet."}
        json.dump(out, open(os.path.join(d, "data", "trust.json"), "w"), separators=(",", ":"))
        counts = {}
        for v in markets.values():
            counts[v["r"]] = counts.get(v["r"], 0) + 1
        print("trust", sport, stage, counts, flush=True)


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else SITE)
