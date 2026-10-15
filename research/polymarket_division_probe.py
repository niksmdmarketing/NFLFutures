"""Which division / conference futures does Polymarket list for NBA and NHL (and NFL)? Writes <out>/polymarket/division_probe.json."""
import json, os, sys, time, urllib.parse, urllib.request
G = "https://gamma-api.polymarket.com"
OUT = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "polymarket")
Q = ["Atlantic Division", "Metropolitan Division", "Central Division", "Pacific Division", "Southeast Division", "Northwest Division",
     "Southwest Division", "NBA division winner", "NHL division winner", "AFC North", "AFC South", "NFC North", "NFC South",
     "Presidents Trophy", "NBA win total", "NHL points", "make the playoffs NBA", "make the playoffs NHL"]
res = {}
for q in Q:
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{G}/public-search?" + urllib.parse.urlencode({"q": q, "limit_per_type": 30, "events_status": "active"}),
                                                           headers={"User-Agent": "SportsFuturesResearch/1.0"}), timeout=30) as r:
            j = json.load(r)
        res[q] = [{"title": e.get("title"), "slug": e.get("slug"), "volume": e.get("volume"), "markets": len(e.get("markets") or [])} for e in j.get("events") or []]
    except Exception as e:  # noqa: BLE001
        res[q] = str(e)
    time.sleep(0.4)
os.makedirs(OUT, exist_ok=True)
json.dump(res, open(os.path.join(OUT, "division_probe.json"), "w"), indent=1)
print({q: len(v) if isinstance(v, list) else v for q, v in res.items()})
