"""Text-shape probe: the layout of injury-list articles without their content. Each block becomes its tag plus a shape
in which names become N, other words w, digits 9, and only a small vocabulary of layout words is kept
(round, weeks, test, tbc, return, expected, status, injury ...). Usage: python research/probe_text_shapes.py <out_dir>"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import avail_collect as A  # noqa: E402

PAGES = ["https://www.nbl.com.au/news/nbl26-the-latest-injury-updates",
         "https://www.afl.com.au/news/1619440/copy-medical-room-the-full-afl-injury-list-pf"]
KEEP = set("""round rounds rd week weeks month months test tbc tba season indefinite return returns returning expected
expect estimated injury injured out update updates status available unavailable game games day days managed minutes
replacement import signed medical list player club team the of to for and is are was with on in at from by
knee ankle hamstring calf shoulder back foot hip groin concussion""".split())


def shape(t):
    out = []
    for tok in re.findall(r"[A-Za-z']+|\d+|[^\sA-Za-z\d]", t):
        lo = tok.lower()
        if lo in KEEP:
            out.append(lo)
        elif tok.isdigit():
            out.append("9")
        elif tok[0].isalpha():
            out.append("N" if tok[0].isupper() else "w")
        else:
            out.append(tok)
    s = " ".join(out)
    return re.sub(r"(N )+N", "N+", re.sub(r"(w )+w", "w+", s))[:160]


res = {}
for u in PAGES:
    html, _ = A.fetch(u)
    blocks, _, ld, _ = A.page(html)
    res[u] = [(b["tag"], shape(b["text"]), [shape(c) for c in (b["cells"] or [])][:4]) for b in blocks][:140]
d = os.path.join(sys.argv[1], "probe")
os.makedirs(d, exist_ok=True)
json.dump(res, open(os.path.join(d, "text_shapes.json"), "w"), indent=0)
