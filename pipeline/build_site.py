"""Assemble the static site in site/: one HTML page per section with shared navigation, plus the JSON data.

Pages fetch their numbers from site/data/*.json at load time, so the HTML only changes when this file does.
"""
import glob
import html
import os
import shutil

from common import OUT, ROOT

SRC = os.path.join(ROOT, "site_src")
SITE = os.path.join(ROOT, "site")

# slug, nav label, page title, intro (None = taken from the data), script, data file for table pages
PAGES = [
    "Model",
    ("index", "Futures", "Season futures", "Chances to win each division, make the playoffs, take the No. 1 seed, win the conference and the Super Bowl, plus every team's win-total distribution.", "futures.js", None),
    ("awards", "Awards", "Award chances", "Probability each player or coach wins the season's major awards.", "awards.js", None),
    ("matchups", "Matchups", "Matchup edges", "Every offense against the defense it faces this week, ranked 1 to 32 in five categories.", "matchups.js", None),
    "Team stats",
    ("offense", "Offense", None, None, "table.js", "offense"),
    ("defense", "Defense", None, None, "table.js", "defense"),
    ("passing", "Passing", None, None, "table.js", "passing"),
    ("rushing", "Rushing", None, None, "table.js", "rushing"),
    ("oline", "O-line", None, None, "table.js", "oline"),
    ("dline", "D-line", None, None, "table.js", "dline"),
    ("drives", "Drives", None, None, "table.js", "drives"),
    ("situational", "Situational", None, None, "table.js", "situational"),
    ("special-teams", "Special teams", None, None, "table.js", "special_teams"),
    ("coverage", "Coverage", None, None, "table.js", "coverage"),
    ("discipline", "Discipline", None, None, "table.js", "discipline"),
    ("proe", "Pass rate", None, None, "table.js", "proe"),
    ("off-tendencies", "Off. tendencies", None, None, "table.js", "off_tendencies"),
    ("def-tendencies", "Def. tendencies", None, None, "table.js", "def_tendencies"),
    ("pace", "Pace", "Team pace", "How much of the 40-second play clock each offense uses before the snap. Clock used is timed from the end of the previous play to the snap, on snaps that follow a run or pass with no penalty, timeout or other stoppage. Filter by week, quarter, down, venue and huddle; switch to Year by year to see how a team's tempo has changed since 2022.", "pace.js", None),
    ("sos", "Schedule", None, None, "table.js", "sos"),
    "Games",
    ("boxscores", "Box scores", "Advanced box scores", "Efficiency box score for every regular-season game since 2018, with notes on standout performances and a team game log that ranks any game against a team's history. The better side of each line is highlighted.", "boxscores.js", None),
    ("injuries", "Injuries", "Injury report", "The latest official practice report, and which quarterback the model expects to start for each team.", "injuries.js", None),
]

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700'
         '&family=Public+Sans:wght@400;500;600&display=swap">')


def nav(active):
    out = []
    for p in PAGES:
        if isinstance(p, str):
            if out:
                out.append("</div>")
            out.append(f'<div class="navgrp"><span class="navlab">{html.escape(p)}</span>')
            continue
        slug, label = p[0], p[1]
        cur = ' aria-current="page"' if slug == active else ""
        out.append(f'<a href="{slug if slug != "index" else "./"}{".html" if slug != "index" else ""}"{cur}>{html.escape(label)}</a>')
    return "".join(out) + "</div>"


def page_html(slug, label, title, intro, script, data):
    frag_path = os.path.join(SRC, "fragments", f"{'futures' if slug == 'index' else slug}.html")
    body = open(frag_path).read() if os.path.exists(frag_path) else '<div id="app" class="page"><p class="loading">Loading…</p></div>'
    head_title = title or label
    page_head = (f'<div class="page-head"><h1 id="pageTitle">{html.escape(head_title)}</h1>'
                 f'<p id="pageIntro">{html.escape(intro or "")}</p></div>')
    data_attr = f' data-page="{data}"' if data else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(head_title)} · NFLFutures</title>
{FONTS}
<link rel="stylesheet" href="style.css">
</head>
<body{data_attr}>
<div class="wrap">
  <header class="site-head">
    <div class="brand"><a class="brand-name" href="./">NFL<span>Futures</span></a><span class="stamp" id="stamp">Loading latest update…</span></div>
    <nav class="nav" aria-label="Sections">{nav(slug)}</nav>
  </header>
  <main class="page" id="main">
    {page_head}
    {body}
  </main>
  <footer class="stamp">Built from nflverse public data (play-by-play, schedules, player stats, rosters, injury reports, FTN and Pro Football Reference charting). An independent model. Probabilities only, not betting advice.</footer>
</div>
<script src="js/common.js"></script>
<script src="js/{script}"></script>
</body>
</html>
"""


def build():
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(os.path.join(SITE, "data"))
    shutil.copytree(os.path.join(SRC, "js"), os.path.join(SITE, "js"))
    shutil.copy(os.path.join(SRC, "style.css"), SITE)
    for f in glob.glob(os.path.join(OUT, "*.json")):
        shutil.copy(f, os.path.join(SITE, "data"))
    for p in PAGES:
        if isinstance(p, str):
            continue
        with open(os.path.join(SITE, f"{p[0]}.html"), "w") as f:
            f.write(page_html(*p))
    # Cloudflare Pages: always revalidate data, keep the site out of search engines.
    with open(os.path.join(SITE, "_headers"), "w") as f:
        f.write("/*\n  X-Robots-Tag: noindex, nofollow\n/data/*\n  Cache-Control: no-cache\n/js/*\n  Cache-Control: no-cache\n/style.css\n  Cache-Control: no-cache\n")
    with open(os.path.join(SITE, "robots.txt"), "w") as f:
        f.write("User-agent: *\nDisallow: /\n")


if __name__ == "__main__":
    build()
