"""Structure-only probe of availability pages (to write parsers without storing third-party text).

For each page: embedded JSON (__NEXT_DATA__, JSON-LD) as key paths with value types; enum-like short values for keys
named like status/strength/position/type; HTML outline: counts of tag paths for tables/lists/headings, table header
labels, and per-table column count. Article prose is never stored.
Usage: python research/probe_avail_structure.py <out_dir>
"""
import json
import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

UA = {"User-Agent": "SportsFuturesResearch/1.0 (private, low-volume)"}
PAGES = {
    "dfo_goalies": "https://www.dailyfaceoff.com/starting-goalies",
    "dfo_team_lines": "https://www.dailyfaceoff.com/teams/toronto-maple-leafs/line-combinations",
    "nhl_projected_topic": "https://www.nhl.com/news/topic/game-previews/nhl-projected-lineup-projections",
    "nbl_injury_category": "https://www.nbl.com.au/news-categories/injury",
    "nbl_injury_list": "https://www.nbl.com.au/news/nbl26-the-latest-injury-updates",
    "afl_injury_news": "https://www.afl.com.au/news/injury-news?page=1",
    "afl_medical_room": "https://www.afl.com.au/news/1484108/medical-room-the-full-afl-injury-list-r3/",
    "afl_lineups": "https://www.afl.com.au/matches/team-lineups",
    "nfl_rapoport": "https://www.nfl.com/author/ian-rapoport-talent",
    "nfl_injuries": "https://www.nfl.com/injuries/",
    "espn_nba_injuries": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
    "espn_nba_news": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news",
    "espn_nfl_tx": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/transactions",
    "espn_nhl_injuries": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries",
    "afl_api_comps": "https://aflapi.afl.com.au/afl/v2/competitions",
}
ENUM_KEY = re.compile(r"status|strength|type|position|pos$|confirm|rating|state|designation|availability", re.I)


def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return str(e)[:80], ""


def kind(v):
    if isinstance(v, str):
        if re.fullmatch(r"\d{4}-\d\d-\d\d.*", v):
            return "str:date"
        if v.startswith("http") or v.startswith("/"):
            return "str:url"
        return f"str:{min(len(v), 999)}"
    return type(v).__name__


def paths(j, prefix="", out=None, enums=None, depth=0):
    out = {} if out is None else out
    enums = {} if enums is None else enums
    if depth > 12:
        return out, enums
    if isinstance(j, dict):
        for k, v in j.items():
            p = f"{prefix}.{k}"
            if isinstance(v, (dict, list)):
                paths(v, p, out, enums, depth + 1)
            else:
                out.setdefault(p, set()).add(kind(v))
                if ENUM_KEY.search(k) and isinstance(v, str) and len(v) <= 25:
                    s = enums.setdefault(p, set())
                    if len(s) < 12:
                        s.add(v)
    elif isinstance(j, list):
        for v in j[:40]:
            paths(v, prefix + "[]", out, enums, depth + 1)
    return out, enums


class Outline(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.counts, self.th, self.tables, self.cur_row, self.in_cell = [], {}, [], [], 0, None
        self.classes = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("table", "tr", "th", "td", "ul", "ol", "li", "h1", "h2", "h3", "h4", "p", "article", "section"):
            cls = (a.get("class") or "").split()[:1]
            key = "/".join(self.stack[-3:] + [tag + ("." + cls[0] if cls else "")])
            self.counts[key] = self.counts.get(key, 0) + 1
        if tag == "table":
            self.tables.append({"rows": 0, "max_cols": 0, "headers": []})
        if tag == "tr" and self.tables:
            self.tables[-1]["rows"] += 1
            self.cur_row = 0
        if tag in ("td", "th") and self.tables:
            self.cur_row += 1
            self.tables[-1]["max_cols"] = max(self.tables[-1]["max_cols"], self.cur_row)
        if tag == "th":
            self.in_cell = []
        if tag not in ("br", "img", "meta", "link", "input", "hr", "source"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "th" and self.in_cell is not None and self.tables:
            lab = " ".join(self.in_cell).strip()
            if len(lab) <= 30 and len(self.tables[-1]["headers"]) < 12:
                self.tables[-1]["headers"].append(lab)
            self.in_cell = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                del self.stack[i:]
                break

    def handle_data(self, d):
        if self.in_cell is not None and d.strip():
            self.in_cell.append(d.strip())


def main():
    out = {}
    for name, u in PAGES.items():
        st, t = get(u)
        row = {"status": st, "chars": len(t)}
        if t[:1] in "[{":
            try:
                p, e = paths(json.loads(t))
                row["json_paths"] = {k: sorted(v) for k, v in list(p.items())[:250]}
                row["enums"] = {k: sorted(v) for k, v in e.items()}
            except ValueError:
                pass
        else:
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
            if m:
                p, e = paths(json.loads(m.group(1)))
                row["next_paths"] = {k: sorted(v) for k, v in list(p.items())[:400]}
                row["enums"] = {k: sorted(v) for k, v in e.items()}
            for i, ld in enumerate(re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', t, re.S)[:3]):
                try:
                    p, _ = paths(json.loads(ld))
                    row[f"jsonld_{i}"] = {k: sorted(v) for k, v in p.items()}
                except ValueError:
                    pass
            o = Outline()
            o.feed(t)
            row["outline"] = dict(sorted(o.counts.items(), key=lambda kv: -kv[1])[:60])
            row["tables"] = o.tables[:10]
            row["article_links_sample_paths"] = sorted(set(re.sub(r"\d+", "N", x) for x in re.findall(r'href="(/news/[^"?#]+)"', t)))[:10]
        out[name] = row
        time.sleep(1)
    d = os.path.join(sys.argv[1], "probe")
    os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "avail_structure.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
