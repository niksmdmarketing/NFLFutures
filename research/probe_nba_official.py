"""Probe the official NBA injury report from CI: find the index page and report PDF URL pattern, parse one PDF.
Writes research/nba_official_probe.json (and the parsed rows of one report) to the market-data branch folder."""
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.request

out = os.path.join(sys.argv[1], "research")
os.makedirs(out, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (SportsFutures research)"}
log = {}


def get(url, binary=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            b = r.read()
            return r.status, (b if binary else b.decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return str(e)[:200], None


for page in ("https://official.nba.com/nba-injury-report-2025-26-season/", "https://official.nba.com/nba-injury-report-2026-27-season/"):
    st, html = get(page)
    links = sorted(set(re.findall(r"https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_[^\"']+\.pdf", html or "")))
    log[page] = {"status": st, "n_links": len(links), "first": links[:3], "last": links[-5:]}

# try the known pattern directly for a few recent times
tried = {}
pdf = None
for day in ("2026-02-26", "2026-04-10", "2026-10-09", "2026-10-10"):
    for t in ("05_15AM", "01_30PM", "05_30PM", "12_00PM", "06_00PM"):
        u = f"https://ak-static.cms.nba.com/referee/injury/Injury-Report_{day}_{t}.pdf"
        st, b = get(u, binary=True)
        tried[u] = st if b is None else f"{st} {len(b)} bytes"
        if b and pdf is None:
            pdf = (u, b)
log["direct"] = tried
if pdf:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf[1])) as P:
            text = "\n".join((p.extract_text() or "") for p in P.pages)
        log["sample_url"] = pdf[0]
        log["sample_text_head"] = text[:3000]
        open(os.path.join(out, "nba_official_sample.txt"), "w").write(text)
    except Exception as e:  # noqa: BLE001
        log["parse_error"] = str(e)
log["probed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
json.dump(log, open(os.path.join(out, "nba_official_probe.json"), "w"), indent=1)
print(json.dumps(log, indent=1)[:4000])
