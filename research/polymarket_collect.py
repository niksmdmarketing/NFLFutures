"""Collect Polymarket US-sports futures (titles, conferences, divisions, playoffs, win totals, season MVPs):
event metadata, daily price history for every market, and a dated snapshot of open markets.
Runs in GitHub Actions (writes to the market-data branch). Prices are a scorecard only; nothing here feeds a projection."""
import json, os, re, sys, time, urllib.parse, urllib.request
ROOT = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "polymarket")
G, C = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
os.makedirs(ROOT, exist_ok=True)
T0, BUDGET = time.time(), float(os.environ.get("PM_BUDGET_S", "1500"))   # stop fetching history after this; later runs continue


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFuturesResearch/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1.5 * (i + 1))
    print("failed", url[:120], err)
    return None


QUERIES = ["Super Bowl Champion", "Pro Football Champion", "AFC Champion", "NFC Champion", "AFC East", "AFC North", "AFC South",
           "AFC West", "NFC East", "NFC North", "NFC South", "NFC West", "NFL make the playoffs", "which NFL teams will make the playoffs",
           "NFL win total", "Pro Football win total", "NFL MVP", "Pro Football MVP", "Offensive Player of the Year", "Defensive Player of the Year",
           "NBA Champion", "NBA Finals", "Eastern Conference Champion", "Western Conference Champion", "NBA MVP", "NBA Rookie of the Year",
           "NBA win total", "NBA playoffs", "Stanley Cup", "NHL Champion", "NHL Eastern Conference", "NHL Western Conference",
           "NHL playoffs", "Hart Trophy", "Vezina", "Norris", "Calder", "Presidents Trophy"]
KEEP = re.compile(r"super bowl|pro football|\bnfl\b|\bafc\b|\bnfc\b|\bnba\b|\bnhl\b|stanley cup|hart|vezina|norris|calder|presidents|"
                  r"eastern conference|western conference|rookie of the year|player of the year", re.I)
DROP = re.compile(r"announcer|headlined|stage of elimination|finals (goals|points)|leader|most goals|passing yards|finals mvp|super bowl mvp|"
                  r"super bowl lx|conn smythe|halftime|commercial|coin toss|anthem|draft|game \d|series|exact|by how|margin|"
                  r"college|ncaa|wnba|mlb|week \d|vs\.?|spread|o/u|over/under", re.I)

events = {}
for q in QUERIES:
    r = get(f"{G}/public-search?q={urllib.parse.quote(q)}&limit_per_type=50&events_status=all") or {}
    for e in r.get("events") or []:
        t = e.get("title") or ""
        if KEEP.search(t) and not DROP.search(t) and float(e.get("volume") or 0) >= 5000 and (e.get("startDate") or "") >= "2024-01-01":
            events[e["slug"]] = t
    time.sleep(0.25)
for slug in ("superbowl-champion-2025", "super-bowl-champion-2026-731", "pro-football-2027-champion-20260729185915366", "afc-champion",
             "nfc-champion", "afc-champion-1", "nfc-champion-1", "nba-champion-2024-2025", "2026-nba-champion", "nba-2027-champion",
             "stanley-cup-winner", "2026-nhl-stanley-cup-champion", "nhl-2027-champion-20260612185656162"):
    events.setdefault(slug, slug)        # key markets always included even if the search ranking changes
print(len(events), "events")
index = json.load(open(os.path.join(ROOT, "index.json"))) if os.path.exists(os.path.join(ROOT, "index.json")) else {}
snap = {}
# titles and team markets first; awards (many long-shot players) last
order = sorted(events.items(), key=lambda kv: (bool(re.search(r"mvp|trophy|rookie|player of the year", kv[1], re.I)), kv[0]))
for slug, title in order:
    d = get(f"{G}/events/slug/{slug}")
    if not isinstance(d, dict):
        continue
    edir = os.path.join(ROOT, "events", slug)
    os.makedirs(edir, exist_ok=True)
    mk = []
    for m in d.get("markets") or []:
        toks = json.loads(m.get("clobTokenIds") or "[]")
        outs = json.loads(m.get("outcomes") or "[]")
        prices = json.loads(m.get("outcomePrices") or "[]")
        mk.append({k: m.get(k) for k in ("id", "question", "groupItemTitle", "closed", "active", "startDate", "endDate", "volume")} |
                  {"outcomes": outs, "prices": prices, "token_yes": toks[0] if toks else None})
        if not d.get("closed") and prices:
            snap.setdefault(slug, {})[m.get("groupItemTitle") or m.get("question")] = prices[0]
        hp = os.path.join(edir, f"{m.get('id')}.json")
        if float(m.get("volume") or 0) < 2000 or time.time() - T0 > BUDGET:
            continue
        if toks and (not os.path.exists(hp) or not m.get("closed")):
            h = get(f"{C}/prices-history?market={toks[0]}&interval=max&fidelity=1440")
            if isinstance(h, dict) and h.get("history"):
                json.dump({"question": m.get("question"), "team": m.get("groupItemTitle"), "history": h["history"]}, open(hp, "w"))
            time.sleep(0.05)
    meta = {k: d.get(k) for k in ("id", "slug", "title", "startDate", "endDate", "closed", "volume")} | {"markets": mk}
    json.dump(meta, open(os.path.join(edir, "event.json"), "w"), indent=1)
    index[slug] = {k: meta[k] for k in ("title", "startDate", "endDate", "closed")} | {"n_markets": len(mk)}
json.dump(index, open(os.path.join(ROOT, "index.json"), "w"), indent=1, sort_keys=True)
day = time.strftime("%Y-%m-%d", time.gmtime())
os.makedirs(os.path.join(ROOT, "snapshots"), exist_ok=True)
json.dump({"taken_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "prices_yes": snap}, open(os.path.join(ROOT, "snapshots", f"{day}.json"), "w"), indent=1)
print("saved", len(index), "events;", sum(len(v) for v in snap.values()), "open prices")
