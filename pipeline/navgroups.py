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
            ("Forecast", [("futures.html", "Chances"), ("predictions.html", "Games"), ("why.html", "Why, team by team"), ("awards.html", "Awards"),
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
    "": [("Standings", [("standings.html", "Standings")]),     # NFL (site root); the landing page stays the chances page
         ("Forecast", [("index.html", "Chances"), ("why.html", "Why, team by team"), ("awards.html", "Award chances"),
                       ("award-race.html", "Award race"), ("outlook.html", "Schedule difficulty"), ("sos.html", "Strength of schedule"),
                       ("trends.html", "Winner trends")]),
         ("Teams", [(None, "Offense"), ("offense.html", "Overview"), ("passing.html", "Passing"), ("rushing.html", "Rushing"),
                    ("oline.html", "O-line"), ("drives.html", "Drives"), ("proe.html", "Pass rate"), ("off-tendencies.html", "Tendencies"),
                    ("pace.html", "Pace"),
                    (None, "Defense"), ("defense.html", "Overview"), ("dline.html", "D-line"), ("coverage.html", "Coverage"),
                    ("def-tendencies.html", "Tendencies"),
                    (None, "Other"), ("situational.html", "Situational"), ("special-teams.html", "Special teams"), ("discipline.html", "Discipline")]),
         ("Players", [("players-qb.html", "Quarterbacks"), ("players-rushing.html", "Rushing"), ("players-receiving.html", "Receiving"),
                      ("players-defense.html", "Defense"), ("players-kicking.html", "Kicking")]),
         ("Games", [("matchups.html", "Matchups"), ("boxscores.html", "Box scores"), ("injuries.html", "Injuries")]),
         ("Model", [("model.html", "How it works"), ("replay.html", "Accuracy history")])],
    "cfb": [("Standings", [("index.html", "Records")]),
            ("Teams", [("teams.html", "Team stats")]),
            ("Players", [("players.html", "Player stats")]),
            ("Games", [("games.html", "Game logs")]),
            ("More", [("trends.html", "Winner trends"), ("coverage.html", "Data coverage")])],
}

NAV_RE = re.compile(r'<nav class="nav[^"]*" aria-label="(?:([^"]*) )?[Ss]ections">(.*?)</nav>(?:\s*<nav class="nav nav-sub"[^>]*>.*?</nav>)?', re.S)
A_RE = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _file(href):
    return "index.html" if href in ("./", "") else href.split("#")[0]


def grouped(sport, layout, links, page):
    """links: [(file, label)] currently in the page's nav (flat or grouped); page: this page's file.
    A (None, label) item in a tab starts a labelled block on the second row (kept only if a page follows it)."""
    have = {f for f, _ in links}
    groups = []
    for g, items in layout:
        kept = [(f, l) for i, (f, l) in enumerate(items)
                if (f in have) or (f is None and any(x in have for x, _ in items[i + 1:next((j for j in range(i + 1, len(items)) if items[j][0] is None), len(items))]))]
        if any(f for f, _ in kept):
            groups.append((g, kept))
    known = {f for _, items in groups for f, _ in items if f}
    extra = [(f, l) for f, l in links if f not in known]
    cur = next((g for g, items in groups if any(f == page for f, _ in items)), None)
    href = lambda f: "./" if f == "index.html" else f
    first = lambda items: next(f for f, _ in items if f)
    top = "".join(f'<a href="{href(first(items))}"' + (' aria-current="page"' if g == cur else "") + f">{html.escape(g)}</a>"
                  for g, items in groups)
    top += "".join(f'<a href="{href(f)}"' + (' aria-current="page"' if f == page else "") + f">{l}</a>" for f, l in extra)
    out = f'<nav class="nav nav-top" aria-label="{sport} sections">{top}</nav>'
    sub = next((items for g, items in groups if g == cur), [])
    if sum(1 for f, _ in sub if f) > 1:
        out += (f'<nav class="nav nav-sub" aria-label="{html.escape(cur)} pages">' +
                "".join(f'<span class="navsub-lab">{html.escape(l)}</span>' if f is None else
                        f'<a href="{href(f)}"' + (' aria-current="page"' if f == page else "") + f">{html.escape(l)}</a>" for f, l in sub) + "</nav>")
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
            new, extra = grouped(m.group(1) or "NFL", lay, union, fn)
            for f, _ in extra:
                if f not in warned:
                    warned.add(f)
                    print("navgroups: page not in the layout, kept on the top row:", folder, f, flush=True)
            open(p, "w", encoding="utf-8").write(s[:m.start()] + new + s[m.end():])
        print("navgroups", folder, len(pages), "pages", flush=True)


if __name__ == "__main__":
    import sys
    apply(sys.argv[1] if len(sys.argv) > 1 else SITE)


# ---------------------------------------------------------------- 'updated' line on pages without the shared script
# Same wording and stale warning as setStamp() in site_src/js/common.js; defines setStamp for scripts that look for it.
STAMP_JS = ("<script>(function(){if(window.setStamp)return;window.setStamp=function(iso,lead,el){el=el||document.getElementById('stamp');if(!el)return;"
            "var d=new Date(String(iso).replace(' ','T').replace(/\\+00:00$/,'Z'));if(isNaN(d))return;"
            "el.textContent=(lead?lead+' \u00b7 ':'')+'updated '+d.toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'});"
            "var h=(Date.now()-d)/3.6e6;if(h>26){var b=document.createElement('b');b.className='stale';"
            "b.textContent=' \u00b7 last update '+(h<48?Math.round(h)+' hours':Math.round(h/24)+' days')+' ago, may be out of date';el.appendChild(b);}};"
            "document.addEventListener('DOMContentLoaded',function(){var el=document.getElementById('stamp');"
            "if(el&&el.dataset.utc)setStamp(el.dataset.utc,el.dataset.lead||'',el);});})();</script>")


def stamps(site=SITE):
    n = 0
    for dirpath, _, files in os.walk(site):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dirpath, fn)
            s = open(p, encoding="utf-8-sig").read()
            if 'id="stamp"' not in s or "js/common.js" in s or "window.setStamp=function" in s or "</head>" not in s:
                continue
            open(p, "w", encoding="utf-8").write(s.replace("</head>", STAMP_JS + "</head>", 1))
            n += 1
    print("stamp script added to", n, "pages", flush=True)


# ---------------------------------------------------------------- sport bar: one fixed list on every page
SPORTBAR_RE = re.compile(r'(<(?:div|nav)\b[^>]*\bclass=["\'][^"\']*\bsportbar\b[^"\']*["\'][^>]*>)(.*?)(</(?:div|nav)>)', re.S)
BAR = [("NFL", ""), ("NBA", "nba/"), ("NBL", "nbl/"), ("NHL", "nhl/"), ("AFL", "afl/"), ("CFB", "cfb/"), ("Shiv", "shiv/"), ("Updates", "updates.html")]


def _section(rel):
    """Which bar entry a page (path relative to the site root) belongs to."""
    if rel == "updates.html":
        return "Updates"
    top = rel.split("/", 1)[0] + "/" if "/" in rel else ""
    return next((n for n, p in BAR if p == top and p), "NFL")


def sportbars(site=SITE):
    n = 0
    for dirpath, _, files in os.walk(site):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, site).replace(os.sep, "/")
            if rel.startswith("data/"):
                continue
            up = "../" * rel.count("/")
            cur = _section(rel)
            links = "".join("<a" + (' class="sb-shiv"' if name == "Shiv" else "") + f' href="{(up + path) or "./"}"' +
                            (' aria-current="page"' if name == cur else "") + f">{name}</a>"
                            for name, path in BAR if name not in ("CFB", "Shiv") or os.path.exists(os.path.join(site, path)))
            text = open(p, encoding="utf-8-sig").read()
            new = SPORTBAR_RE.sub(lambda m: m[1] + "<span>SPORT</span>" + links + m[3], text, count=1)
            if new != text:
                open(p, "w", encoding="utf-8").write(new)
                n += 1
    print("sport bars", n, "pages", flush=True)
