"""Grouped section navigation (Oct 2026 layout): a short row of top tabs per sport, and a second row with the pages of the
current tab. Runs last in the build, after every module has added its page links to the flat nav, so it sees them all.

Every link already in a page's nav is kept: pages missing from LAYOUT are added to the top row as they are (and logged),
so nothing disappears when a new page is added before this map is updated. Re-running on grouped pages is harmless.
"""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")

def _skeleton(players=(("players.html", "Player stats"),)):
    """The shared layout for a sport with season forecasts (TypeSafe, Oct 2026)."""
    return [("Standings", [("index.html", "Standings")]),
            ("Forecast", [("futures.html", "Chances"), ("why.html", "Why, team by team"), ("awards.html", "Awards"),
                          ("outlook.html", "Schedule difficulty"), ("trends.html", "Winner trends")]),
            ("Teams", [("teams.html", "Team stats")]),
            ("Players", list(players)),
            ("Games", [("games.html", "Game logs")]),
            ("Model", [("model.html", "How it works"), ("replay.html", "Accuracy history")])]


# sport folder -> [(top tab label, [(page file, sub-tab label)])]; the top tab links to its first page
LAYOUT = {
    "nba": _skeleton(),
    "nhl": _skeleton((("skaters.html", "Skaters"), ("goalies.html", "Goalies"))),
    "afl": _skeleton(),
    "nbl": _skeleton(),
    "cfb": [("Standings", [("index.html", "Records")]),
            ("Teams", [("teams.html", "Team stats")]),
            ("Players", [("players.html", "Player stats")]),
            ("Games", [("games.html", "Game logs")]),
            ("More", [("trends.html", "Winner trends"), ("coverage.html", "Data coverage")])],
}

NAV_RE = re.compile(r'<nav class="nav[^"]*" aria-label="([^"]*) sections">(.*?)</nav>(?:\s*<nav class="nav nav-sub"[^>]*>.*?</nav>)?', re.S)
A_RE = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _file(href):
    return "index.html" if href in ("./", "") else href.split("#")[0]


def grouped(sport, layout, links, page):
    """links: [(file, label)] currently in the page's nav (flat or grouped); page: this page's file."""
    have = {f for f, _ in links}
    groups = [(g, [(f, l) for f, l in items if f in have]) for g, items in layout]
    groups = [(g, items) for g, items in groups if items]
    known = {f for _, items in groups for f, _ in items}
    extra = [(f, l) for f, l in links if f not in known]
    cur = next((g for g, items in groups if any(f == page for f, _ in items)), None)
    href = lambda f: "./" if f == "index.html" else f
    top = "".join(f'<a href="{href(items[0][0])}"' + (' aria-current="page"' if g == cur else "") + f">{html.escape(g)}</a>"
                  for g, items in groups)
    top += "".join(f'<a href="{href(f)}"' + (' aria-current="page"' if f == page else "") + f">{l}</a>" for f, l in extra)
    out = f'<nav class="nav nav-top" aria-label="{sport} sections">{top}</nav>'
    sub = next((items for g, items in groups if g == cur), [])
    if len(sub) > 1:
        out += (f'<nav class="nav nav-sub" aria-label="{html.escape(cur)} pages">' +
                "".join(f'<a href="{href(f)}"' + (' aria-current="page"' if f == page else "") + f">{html.escape(l)}</a>" for f, l in sub) + "</nav>")
    return out, extra


def _links(nav_inner, sub_inner=""):
    out, seen = [], set()
    for h, l in A_RE.findall(nav_inner + sub_inner):
        f = _file(h)
        if f not in seen:
            seen.add(f)
            out.append((f, re.sub(r"<[^>]+>", "", l).strip()))
    return out


def apply(site=SITE, layout=LAYOUT):
    for folder, lay in layout.items():
        d = os.path.join(site, folder)
        if not os.path.isdir(d):
            continue
        pages = sorted(fn for fn in os.listdir(d) if fn.endswith(".html"))
        # the union of every page's links, so a page whose nav missed a late-added link still gets it
        union = []
        for fn in pages:
            s = open(os.path.join(d, fn), encoding="utf-8").read()
            m = NAV_RE.search(s)
            if m:
                for x in _links(m.group(0)):
                    if x[0] not in {u for u, _ in union} and os.path.exists(os.path.join(d, x[0])):
                        union.append(x)
        warned = set()
        for fn in pages:
            p = os.path.join(d, fn)
            s = open(p, encoding="utf-8").read()
            m = NAV_RE.search(s)
            if not m:
                continue
            new, extra = grouped(m.group(1), lay, union, fn)
            for f, _ in extra:
                if f not in warned:
                    warned.add(f)
                    print("navgroups: page not in the layout, kept on the top row:", folder, f, flush=True)
            open(p, "w", encoding="utf-8").write(s[:m.start()] + new + s[m.end():])
        print("navgroups", folder, len(pages), "pages", flush=True)


if __name__ == "__main__":
    import sys
    apply(sys.argv[1] if len(sys.argv) > 1 else SITE)
