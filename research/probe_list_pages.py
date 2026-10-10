"""Layout probe for the NBL and AFL injury-list articles (why the collector extracts nothing).
Stores structure only: block tags after the headline with a shape (capitalised words -> N, lower-case -> w, digits -> 9,
a small layout vocabulary kept), table/script statistics and where an article body might sit in embedded JSON.
Usage: python research/probe_list_pages.py <out_dir>"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import avail_collect as A  # noqa: E402

PAGES = ["https://www.nbl.com.au/news/nbl26-the-latest-injury-updates",
         "https://www.afl.com.au/news/1619440/copy-medical-room-the-full-afl-injury-list-pf",
         "https://www.afl.com.au/news/1606737/medical-room-the-full-afl-injury-list-fw3"]
KEEP = set("""round rounds rd week weeks month months test tbc tba season indefinite return returns returning expected
estimated injury injured out update updates status available managed minutes replacement import list player club
knee ankle hamstring calf shoulder back foot hip groin concussion surgery soreness illness suspension
adelaide brisbane cairns illawarra melbourne new zealand perth south east sydney tasmania 36ers bullets taipans hawks
united breakers wildcats phoenix kings jackjumpers carlton collingwood essendon fremantle geelong gold coast gws giants
hawthorn north port richmond st kilda west coast western bulldogs crows lions blues magpies bombers dockers cats suns
swans eagles demons kangaroos power tigers saints""".split())


def shape(t):
    out = []
    for tok in re.findall(r"[A-Za-z']+|\d+|[^\sA-Za-z\d]", t or ""):
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
    return re.sub(r"(w )+w", "w+", s)[:200]


res = {}
for u in PAGES:
    html, st = A.fetch(u)
    html = html or ""
    blocks, links, ld, _ = A.page(html)
    h1 = next((i for i, b in enumerate(blocks) if b["tag"] == "h1"), 0)
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    bodyish = []
    for s in scripts:
        for m in re.finditer(r'"(body|articleBody|content|html|text)"\s*:\s*"', s):
            bodyish.append((m.group(1), len(s)))
    res[u] = {"status": st, "html_len": len(html), "n_blocks": len(blocks), "h1_index": h1,
              "tags": {t: sum(1 for b in blocks if b["tag"] == t) for t in {b["tag"] for b in blocks}},
              "n_tables": html.count("<table"), "n_tr": html.count("<tr"), "next_data": "__NEXT_DATA__" in html,
              "ld_types": [x.get("@type") for x in ld if isinstance(x, dict)],
              "ld_has_articleBody": any(isinstance(x, dict) and "articleBody" in x for x in ld),
              "embedded_body_keys": bodyish[:20],
              "after_h1": [(b["tag"], len(b["text"] or ""), shape(b["text"]), [shape(c) for c in (b["cells"] or [])][:4])
                           for b in blocks[h1:h1 + 260]]}
d = os.path.join(sys.argv[1], "probe")
os.makedirs(d, exist_ok=True)
json.dump(res, open(os.path.join(d, "list_pages.json"), "w"), indent=0)
print(json.dumps({u: {k: v for k, v in r.items() if k != "after_h1"} for u, r in res.items()}, indent=1))
