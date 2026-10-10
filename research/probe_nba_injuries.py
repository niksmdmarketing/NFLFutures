"""Probe NBA availability sources from CI (research): ESPN injuries JSON and the official NBA injury report PDF index."""
import json, os, sys, time, urllib.request, datetime as dt
OUT = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "probe_nba_inj"); os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(OUT, "log.txt"), "w")
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (research)"}), timeout=30) as r:
        return r.read(), r.headers.get("Content-Type")
try:
    b, ct = get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries")
    j = json.loads(b); log.write(f"espn ok {ct} {len(b)} teams={len(j.get('injuries', []))}\n")
    json.dump(j, open(os.path.join(OUT, "espn_injuries_sample.json"), "w"), indent=1)
except Exception as e:
    log.write(f"espn fail {e}\n")
# official report: try recent days/times
now = dt.datetime.utcnow() - dt.timedelta(hours=5)
for days in range(0, 200, 3):
    d = (now - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    hit = False
    for t in ("05_30PM", "01_30PM", "06_30PM", "05PM", "01PM"):
        u = f"https://ak-static.cms.nba.com/referee/injury/Injury-Report_{d}_{t}.pdf"
        try:
            b, ct = get(u)
            log.write(f"pdf ok {u} {ct} {len(b)}\n"); open(os.path.join(OUT, "sample.pdf"), "wb").write(b); hit = True; break
        except Exception as e:
            log.write(f"pdf fail {u} {e}\n")
    if hit:
        break
log.close()
