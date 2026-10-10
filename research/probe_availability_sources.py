"""Probe the availability/news sources for all five sports from CI (access check before any collector relies on them).

For every source: robots.txt verdict for our user agent and '*', HTTP status, content type, size, whether the page is
server-rendered or carries embedded JSON (__NEXT_DATA__, JSON-LD, Nuxt state), dated article links, and candidate
structured endpoints. Terms-of-use pages are fetched only to count keywords that need a human read (scrap*, automated,
crawl*, robot*); no third-party text is stored. Writes probe/availability_sources.json.
Usage: python research/probe_availability_sources.py <out_dir>
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.robotparser

UA = "SportsFuturesResearch/1.0 (private, low-volume; contact via GitHub niksmdmarketing)"
H = {"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}

SOURCES = {
    "nfl": [
        ("official", "NFL injuries page", "https://www.nfl.com/injuries/"),
        ("official", "NFL transactions page", "https://www.nfl.com/transactions/"),
        ("context", "Ian Rapoport author page", "https://www.nfl.com/author/ian-rapoport-talent"),
        ("context", "Tom Pelissero author page", "https://www.nfl.com/author/tom-pelissero-0ap3000000820340"),
        ("structured", "ESPN NFL injuries JSON", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"),
        ("structured", "ESPN NFL transactions JSON", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/transactions"),
        ("structured", "nflverse injuries 2026", "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.csv"),
        ("structured", "nflverse depth charts 2026", "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv"),
    ],
    "nba": [
        ("official", "NBA injury report page 2026-27", "https://official.nba.com/nba-injury-report-2026-27-season/"),
        ("official", "NBA injury report page 2025-26", "https://official.nba.com/nba-injury-report-2025-26-season/"),
        ("structured", "ESPN NBA injuries JSON", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"),
        ("structured", "ESPN NBA transactions JSON", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/transactions"),
        ("context", "ESPN example story", "https://www.espn.com/nba/story/_/id/47637904/grizzlies-coach-optimistic-ja-morant-play-london-game"),
        ("structured", "ESPN NBA news JSON", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"),
    ],
    "nhl": [
        ("context", "NHL projected lineups topic", "https://www.nhl.com/news/topic/game-previews/nhl-projected-lineup-projections"),
        ("structured", "NHL API roster (TOR)", "https://api-web.nhle.com/v1/roster/TOR/current"),
        ("structured", "NHL API schedule now", "https://api-web.nhle.com/v1/schedule/now"),
        ("context", "Daily Faceoff starting goalies", "https://www.dailyfaceoff.com/starting-goalies"),
        ("context", "Daily Faceoff teams", "https://www.dailyfaceoff.com/teams"),
        ("structured", "ESPN NHL injuries JSON", "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries"),
        ("structured", "ESPN NHL transactions JSON", "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/transactions"),
    ],
    "nbl": [
        ("official", "NBL injury news category", "https://www.nbl.com.au/news-categories/injury"),
        ("official", "NBL latest injury list", "https://www.nbl.com.au/news/nbl26-the-latest-injury-updates"),
        ("context", "NBL example: Kuol", "https://www.nbl.com.au/news/sydney-kings-in-difficult-situation-with-injured-star-bul-kuol"),
        ("context", "NBL example: Sydney star", "https://www.nbl.com.au/news/sydney-star-to-miss-opening-weeks"),
        ("official", "NBL news index", "https://www.nbl.com.au/news"),
    ],
    "afl": [
        ("official", "AFL injury news", "https://www.afl.com.au/news/injury-news?page=1"),
        ("official", "AFL team line-ups", "https://www.afl.com.au/matches/team-lineups"),
        ("context", "AFL Medical Room example", "https://www.afl.com.au/news/1484108/medical-room-the-full-afl-injury-list-r3/"),
        ("structured", "AFL public API (aflapi) comps", "https://aflapi.afl.com.au/afl/v2/competitions"),
    ],
}
TERMS = {
    "nfl.com": ["https://www.nfl.com/legal/terms/"],
    "nba.com": ["https://www.nba.com/termsofuse"],
    "official.nba.com": ["https://www.nba.com/termsofuse"],
    "espn.com": ["https://disneytermsofuse.com/english/"],
    "nhl.com": ["https://www.nhl.com/info/terms-of-service"],
    "dailyfaceoff.com": ["https://www.dailyfaceoff.com/terms-of-use", "https://www.dailyfaceoff.com/terms"],
    "nbl.com.au": ["https://www.nbl.com.au/terms-and-conditions", "https://www.nbl.com.au/terms-of-use"],
    "afl.com.au": ["https://www.afl.com.au/termsofuse", "https://www.afl.com.au/terms-and-conditions"],
}
KEYWORDS = ("scrap", "automated", "crawl", "robot", "spider", "data mining", "commercial use")


def fetch(url, n=3_000_000):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r:
            return r.status, dict(r.headers), r.read(n)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), b""
    except Exception as e:  # noqa: BLE001
        return str(e)[:120], {}, b""


robots_cache = {}


def robots(url):
    p = urllib.parse.urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    if root not in robots_cache:
        st, _, body = fetch(root + "/robots.txt", 500_000)
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.decode("utf-8", "replace").splitlines() if st == 200 else [])
        robots_cache[root] = (st, rp, len(body))
    st, rp, n = robots_cache[root]
    return {"robots_status": st, "robots_bytes": n, "allowed_ua": rp.can_fetch(UA, url), "allowed_star": rp.can_fetch("*", url),
            "crawl_delay": rp.crawl_delay("*")}


def describe(body, ctype):
    t = body.decode("utf-8", "replace")
    d = {"bytes": len(body)}
    if "json" in (ctype or "") or t[:1] in "[{":
        try:
            j = json.loads(t)
            d["json_top_keys"] = list(j.keys())[:15] if isinstance(j, dict) else f"list[{len(j)}]"
        except ValueError:
            pass
        return d
    d["next_data"] = "__NEXT_DATA__" in t
    d["nuxt"] = "__NUXT__" in t
    d["json_ld"] = t.count("application/ld+json")
    d["title_len"] = len((re.search(r"<title[^>]*>(.*?)</title>", t, re.S) or [None, ""])[1])
    d["text_chars_est"] = len(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)).split())
    d["article_links"] = len(set(re.findall(r'href="(/news/[^"]+)"', t)))
    d["pdf_links"] = len(set(re.findall(r"Injury-Report_[0-9_\-APM]+\.pdf", t)))
    d["iso_dates"] = len(re.findall(r"20\d\d-\d\d-\d\dT\d\d:\d\d", t))
    d["has_published_meta"] = bool(re.search(r'article:published_time|"datePublished"', t))
    d["has_modified_meta"] = bool(re.search(r'article:modified_time|"dateModified"', t))
    return d


def main():
    out_dir = os.path.join(sys.argv[1], "probe")
    os.makedirs(out_dir, exist_ok=True)
    res = {"checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "user_agent": UA, "sources": {}, "terms": {}}
    for sport, items in SOURCES.items():
        res["sources"][sport] = []
        for kind, name, url in items:
            st, hd, body = fetch(url)
            row = {"kind": kind, "name": name, "url": url, "status": st, "content_type": hd.get("Content-Type"),
                   "last_modified": hd.get("Last-Modified"), **robots(url)}
            if body:
                row.update(describe(body, hd.get("Content-Type")))
            res["sources"][sport].append(row)
            print(sport, name, st, row.get("allowed_star"), row.get("bytes"), flush=True)
    for host, urls in TERMS.items():
        for u in urls:
            st, _, body = fetch(u)
            t = re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace")).lower()
            res["terms"].setdefault(host, []).append({"url": u, "status": st, "keyword_counts": {k: t.count(k) for k in KEYWORDS}})
    json.dump(res, open(os.path.join(out_dir, "availability_sources.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
