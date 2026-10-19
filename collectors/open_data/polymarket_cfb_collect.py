# Open-data collector, run from the public repo (free Actions minutes). Writes under $DATA_ROOT/collected_data/... (the open-data branch).
"""Polymarket college football market snapshots (public Gamma API). Comparison and a separately labelled market-informed model only; NEVER an input to the statistical model.

The public repo's collector deliberately excludes college/NCAA; college football is private here. Sequential, honest user agent, stops at once on HTTP 403/429.
Writes collected_data/polymarket_cfb/<UTC date>.json (one per day, last run wins): per open market the question, outcome prices, best bid/ask, last trade, volume and liquidity
so wide-spread and thin markets can be filtered later.
Usage: python pipeline/polymarket_cfb_collect.py
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.environ.get("DATA_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "collected_data", "polymarket_cfb")
G = "https://gamma-api.polymarket.com"
UA = "SportsFuturesPrivate/1.0 (private research; low volume)"
PAUSE = 0.3
QUERIES = ["College Football Champion", "College Football Playoff", "CFP national champion", "NCAAF champion", "Big Ten Champion football", "SEC Champion football",
           "ACC Champion football", "Big 12 Champion football", "college football playoff teams", "college football national championship"]
KEEP = re.compile(r"college football|\bcfp\b|ncaaf|cfb|national champion(ship)? .*football|football.*national champion", re.I)
DROP = re.compile(r"heisman|coach of the year|player of the year|draft|nfl|nba|basketball|march madness|\bvs\.?\b|spread|o/u|over/under|week \d|halftime|first td|mvp|womens?|baseball|hockey", re.I)


class Blocked(Exception):
    pass


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise Blocked(f"HTTP {e.code} from Polymarket; stopping without retry")
            time.sleep(1.5 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (i + 1))
    return None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def collect(fetcher=get, pause=PAUSE):
    events = {}
    for q in QUERIES:
        r = fetcher(f"{G}/public-search?q={urllib.parse.quote(q)}&limit_per_type=50&events_status=open") or {}
        for e in r.get("events") or []:
            t = e.get("title") or ""
            if KEEP.search(t) and not DROP.search(t) and not e.get("closed"):
                events[e["slug"]] = t
        time.sleep(pause)
    out = []
    for slug, title in sorted(events.items()):
        d = fetcher(f"{G}/events/slug/{slug}")
        time.sleep(pause)
        if not isinstance(d, dict) or d.get("closed"):
            continue
        for m in d.get("markets") or []:
            if m.get("closed"):
                continue
            outs, prices = json.loads(m.get("outcomes") or "[]"), json.loads(m.get("outcomePrices") or "[]")
            out.append({"event_slug": slug, "event_title": title, "question": m.get("question"), "name": m.get("groupItemTitle"), "end": m.get("endDate"),
                        "outcomes": outs, "prices": [num(p) for p in prices], "best_bid": num(m.get("bestBid")), "best_ask": num(m.get("bestAsk")),
                        "last": num(m.get("lastTradePrice")), "volume": num(m.get("volume")), "liquidity": num(m.get("liquidity"))})
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        rows = collect()
    except Blocked as e:
        print(e)
        return 0
    if not rows:
        print("no college football markets found; not saving")
        return 0
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, now.strftime("%Y-%m-%d") + ".json")
    json.dump({"observed_at_utc": now.isoformat(timespec="minutes"), "markets": rows}, open(p, "w"), separators=(",", ":"))
    print("saved", p, len(rows), "markets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
