"""Daily private model-vs-market discrepancy report (US futures). Scorecard only: nothing here feeds a projection or the site.

Reads the live model probabilities from the published site files and today's Polymarket prices (collected by
polymarket_collect.py), and writes <market-data>/reports/<date>.md and .json listing the biggest gaps per market.
Prices in one-winner markets are normalised to sum to 1 (margin removed); playoff markets are per-team yes prices.
Usage: python research/market_report.py <market-data dir> <published site dir>
"""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
MDIR = sys.argv[1] if len(sys.argv) > 1 else "."
SITE = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "site")
import market_benchmark as B  # noqa: E402  (team-name matching and event readers)

B.MD = os.path.join(MDIR, "polymarket", "events")

# Track record from the back-tests vs Polymarket: when the model has (and has not) kept up with the market.
STAGE_NOTE = {"nfl": "Back-test vs Polymarket (2024-25): the market was more accurate before the season; from about week 4 the model "
                     "matched or beat it on divisions and playoffs, but not on the Super Bowl.",
              "nba": "Back-test vs Polymarket (2024-25, 2025-26): the market was much more accurate before the season; from about 40% of "
                     "the season the model beat it on the title, not on conferences.",
              "nhl": "Back-test vs Polymarket (2025-26): the market was slightly more accurate before the season; after about 20 games "
                     "the model was more accurate on the Cup and conferences."}

# (sport, market label, title regex for the OPEN Polymarket event, model file, model field, one-winner?)
MARKETS = [
    ("nfl", "Super Bowl", r"pro football: 20\d\d champion$", "data/futures.json", "p_sb", True),
    ("nfl", "AFC champion", r"20\d\d afc champion", "data/futures.json", "p_conf", True),
    ("nfl", "NFC champion", r"20\d\d nfc champion", "data/futures.json", "p_conf", True),
    ("nfl", "Division", r"pro football: (afc|nfc) (east|north|south|west) champion", "data/futures.json", "p_div", True),
    ("nfl", "Make playoffs", r"team to make postseason", "data/futures.json", "p_playoff", False),
    ("nba", "NBA title", r"^nba: 20\d\d champion", "nba/data/futures.json", "p_title", True),
    ("nba", "Conference", r"^nba: 20\d\d (eastern|western) conference champion", "nba/data/futures.json", "p_conf", True),
    ("nhl", "Stanley Cup", r"^nhl: 20\d\d champion", "nhl/data/futures.json", "p_cup", True),
    ("nhl", "Conference", r"^nhl: 20\d\d (eastern|western) conference champion", "nhl/data/futures.json", "p_final", True),
    ("nhl", "Make playoffs", r"which teams will make the nhl playoffs", "nhl/data/futures.json", "p_playoffs", False),
]


def model_probs(path, field):
    j = json.load(open(os.path.join(SITE, path)))
    T = j["teams"]
    return {k: v.get(field) for k, v in T.items()} if isinstance(T, dict) else {t["team"]: t.get(field) for t in T}


def latest(series):
    return series[-1][1] if series else None


def main():
    index = json.load(open(os.path.join(MDIR, "polymarket", "index.json")))
    today = dt.date.today().isoformat()
    out, lines = {"date": today, "markets": []}, [f"# Model vs Polymarket — {today}", "",
                                                 "Private scorecard. Not betting advice; the model never uses these prices.", ""]
    for sport, label, pat, path, field, one in MARKETS:
        try:
            model = model_probs(path, field)
        except Exception as e:  # noqa: BLE001
            print("no model file", path, e)
            continue
        slugs = [s for s, v in index.items() if not v.get("closed") and re.search(pat, (v.get("title") or "").strip(), re.I)]
        for slug in slugs:
            M = {t: latest(s) for t, s in B.market(slug, sport).items()}
            M = {t: p for t, p in M.items() if p is not None and t in model}
            if len(M) < 2:
                continue
            if one:
                tot = sum(M.values())
                M = {t: p / tot for t, p in M.items()}
                mtot = sum(model[t] or 0 for t in M) or 1
                mod = {t: (model[t] or 0) / mtot for t in M}
            else:
                mod = {t: model[t] or 0 for t in M}
            rows = sorted(((t, mod[t], M[t], mod[t] - M[t]) for t in M), key=lambda r: -abs(r[3]))
            title = index[slug]["title"].strip()
            out["markets"].append({"sport": sport, "market": label, "event": title, "rows": [dict(team=t, model=round(a, 4), market=round(b, 4)) for t, a, b, _ in rows]})
            lines += [f"## {sport.upper()} — {title}", STAGE_NOTE[sport], "", "| Team | Model | Market | Gap |", "|---|---|---|---|"]
            lines += [f"| {t} | {a:.1%} | {b:.1%} | {d:+.1%} |" for t, a, b, d in rows[:8]]
            lines.append("")
    os.makedirs(os.path.join(MDIR, "reports"), exist_ok=True)
    json.dump(out, open(os.path.join(MDIR, "reports", f"{today}.json"), "w"), indent=1)
    open(os.path.join(MDIR, "reports", f"{today}.md"), "w").write("\n".join(lines))
    open(os.path.join(MDIR, "reports", "latest.md"), "w").write("\n".join(lines))
    print("report:", len(out["markets"]), "markets")


if __name__ == "__main__":
    main()
