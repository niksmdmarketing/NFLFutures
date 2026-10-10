"""Historical NBA/NHL closing odds from the Sportsbook Reviews Online archive, via the Internet Archive (research).
Rights to redistribute are unclear: run it with a private output folder and do NOT commit the files to this public repo."""
import os, re, sys, time, urllib.request
OUT = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "match_odds", "sbr"); os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "fetch_log.txt"), "a")
def log(*a):
    print(*a); LOG.write(" ".join(map(str, a)) + "\n"); LOG.flush()
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()
log("run", time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()))
for sport in ("nba", "nhl"):
    html, page = None, None
    for page in (f"https://web.archive.org/web/2022id_/https://www.sportsbookreviewsonline.com/scoresoddsarchives/{sport}/{sport}oddsarchives.htm",
                 f"https://web.archive.org/web/2021id_/https://www.sportsbookreviewsonline.com/scoresoddsarchives/{sport}/{sport}oddsarchives.htm",
                 f"https://web.archive.org/web/2023id_/https://www.sportsbookreviewsonline.com/scoresoddsarchives/{sport}-odds-archives/"):
        try:
            html = get(page).decode("utf-8", "replace")
            break
        except Exception as e:  # noqa: BLE001
            log(sport, "page fail", page, e)
    try:
        if html is None:
            raise ValueError("no archive page")
        links = sorted(set(re.findall(r'href=["\']([^"\']+\.xlsx?)["\']', html, re.I)))
        log(sport, "page ok", len(links), links[:5])
    except Exception as e:  # noqa: BLE001
        log(sport, "page fail", e); continue
    for l in links:
        src = re.sub(r"^https?://web\.archive\.org/web/[^/]+/", "", l)
        if src.startswith("/"):
            src = "https://www.sportsbookreviewsonline.com" + src
        elif not src.startswith("http"):
            src = f"https://www.sportsbookreviewsonline.com/scoresoddsarchives/{sport}/" + src
        fn = os.path.join(OUT, f"{sport}_" + os.path.basename(src).replace("%20", "_").replace(" ", "_"))
        if os.path.exists(fn):
            continue
        for wb in (f"https://web.archive.org/web/2023id_/{src.replace(' ', '%20')}", f"https://web.archive.org/web/2022id_/{src.replace(' ', '%20')}"):
            try:
                b = get(wb)
                if len(b) > 5000 and b[:2] in (b"PK", b"\xd0\xcf"):
                    open(fn, "wb").write(b); log("ok", src, len(b)); break
                log("not a spreadsheet", wb, len(b))
            except Exception as e:  # noqa: BLE001
                log("fail", wb, e)
        time.sleep(1)
