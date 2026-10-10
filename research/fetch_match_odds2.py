"""Probe other free historical NBA/NHL odds archives (research). Logs to match_odds/fetch_log2.txt on market-data."""
import os, re, sys, time, urllib.request
OUT = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "match_odds"); os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "fetch_log2.txt"), "a")
def log(*a):
    print(*a); LOG.write(" ".join(map(str, a)) + "\n"); LOG.flush()
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()
log("run", time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()))
for page in ("https://www.sportsbookreviewsonline.com/scoresoddsarchives/nba-odds-archives/",
             "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl-odds-archives/"):
    try:
        html = get(page).decode("utf-8", "replace")
        i = html.lower().find("xls")
        log("snippet", re.sub(r"\s+", " ", html[max(0, i - 1500):i + 1500]) if i >= 0 else html[:1500])
        links = sorted(set(re.findall(r'href=["\']([^"\']+\.xlsx?)["\']', html, re.I)))
        log("page ok", page, len(links), links[:40])
        for l in links:
            url = l if l.startswith("http") else "https://www.sportsbookreviewsonline.com" + l
            try:
                b = get(url)
                open(os.path.join(OUT, url.split("/")[-1]), "wb").write(b)
                log("ok", url, len(b))
            except Exception as e:  # noqa: BLE001
                log("fail", url, e)
            time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        log("page fail", page, e)
