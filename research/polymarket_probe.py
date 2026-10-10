"""Probe the public Polymarket API from GitHub Actions (the dev sandbox cannot reach it). Output: probe/*.json artifact."""
import json, os, time, urllib.parse, urllib.request
OUT = "probe"; os.makedirs(OUT, exist_ok=True)
G, C = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SportsFuturesResearch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": repr(e), "_url": url}
log = {}
QUERIES = ["Super Bowl Champion", "Pro Football Champion", "NBA Champion", "Stanley Cup", "NHL Champion", "AFC Champion", "NFC Champion",
           "AFC East", "NFC North", "NBA Eastern Conference Champion", "NBA MVP", "NFL MVP", "make the playoffs", "Hart Trophy", "win totals"]
for q in QUERIES:
    r = get(f"{G}/public-search?q={urllib.parse.quote(q)}&limit_per_type=50&events_status=all")
    evs = r.get("events", []) if isinstance(r, dict) else []
    log[q] = [{k: e.get(k) for k in ("id", "slug", "title", "startDate", "endDate", "closed", "volume")} | {"n_markets": len(e.get("markets") or [])} for e in evs] or r
    time.sleep(0.3)
json.dump(log, open(f"{OUT}/search.json", "w"), indent=1)
# full detail + price history for the first closed Super Bowl event found
for q in ("Super Bowl Champion", "NBA Champion", "Stanley Cup"):
    evs = [e for e in log.get(q, []) if isinstance(e, dict) and e.get("slug")]
    for e in evs[:6]:
        d = get(f"{G}/events/slug/{e['slug']}")
        json.dump(d, open(f"{OUT}/event_{e['slug'][:60]}.json", "w"), indent=1)
        mk = (d.get("markets") or [])[:2] if isinstance(d, dict) else []
        for m in mk:
            toks = json.loads(m.get("clobTokenIds") or "[]")
            if toks:
                h1 = get(f"{C}/prices-history?market={toks[0]}&interval=max&fidelity=1440")
                st = int(time.mktime(time.strptime((d.get("startDate") or "2024-01-01")[:10], "%Y-%m-%d")))
                h2 = get(f"{C}/prices-history?market={toks[0]}&startTs={st}&endTs={st + 86400 * 400}&fidelity=1440")
                json.dump({"market": m.get("question"), "token": toks[0], "interval_max": h1, "start_end": h2},
                          open(f"{OUT}/hist_{m.get('id')}.json", "w"), indent=1)
print("done", {k: (len(v) if isinstance(v, list) else v) for k, v in log.items()})
