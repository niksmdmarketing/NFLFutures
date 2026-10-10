"""Probe the official NBA injury report (PDFs on ak-static.cms.nba.com) from CI: which URL patterns exist, how far back,
and whether the text parses. Writes probe/nba_official.json (+ a sample text) into the given folder.
Usage: python research/nba_official_probe.py <out_dir>"""
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import urllib.request

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pypdf"], check=False)
from pypdf import PdfReader  # noqa: E402

out = os.path.join(sys.argv[1], "probe")
os.makedirs(out, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (research; sports futures site)"}
res = {"index_pages": {}, "pdfs": {}}


def get(url, n=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, r.read(n) if n else r.read()
    except Exception as e:  # noqa: BLE001
        return getattr(e, "code", str(e)), b""


for u in ("https://official.nba.com/nba-injury-report-2025-26-season/", "https://official.nba.com/nba-injury-report-2026-27-season/",
          "https://official.nba.com/nba-injury-report-2024-25-season/", "https://official.nba.com/nba-injury-report-2021-22-season/"):
    st, body = get(u)
    links = sorted(set(re.findall(rb"https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_[^\"' ]+\.pdf", body)))
    res["index_pages"][u] = {"status": st, "n_links": len(links), "first": [l.decode() for l in links[:3]], "last": [l.decode() for l in links[-3:]]}

base = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_"
cands = []
for d in ("2026-02-26", "2026-01-15", "2025-03-10", "2024-01-10", "2023-01-10", "2022-01-10", "2021-12-10", "2020-01-10", "2026-04-10", "2026-10-05"):
    for t in ("05_15AM", "05_00PM", "05PM", "01PM", "12_00PM", "06_30PM", "06PM", "07_30PM"):
        cands.append(f"{base}{d}_{t}.pdf")
sample_done = False
for u in cands:
    st, body = get(u)
    entry = {"status": st, "bytes": len(body)}
    if st == 200 and body[:4] == b"%PDF":
        try:
            txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages)
            entry["chars"] = len(txt)
            entry["statuses"] = {s: txt.count(s) for s in ("Out", "Questionable", "Doubtful", "Probable", "Available")}
            if not sample_done:
                open(os.path.join(out, "nba_official_sample.txt"), "w").write(txt[:6000])
                sample_done = True
        except Exception as e:  # noqa: BLE001
            entry["parse_error"] = str(e)
    res["pdfs"][u] = entry
res["checked_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
json.dump(res, open(os.path.join(out, "nba_official.json"), "w"), indent=1)
print(json.dumps(res, indent=1)[:4000])
