"""Shared helpers for the engine-driven sport sections (NBA, NBL, AFL): columnar JSON writer and page builder.

Pages look and behave like the NHL section: site_src/engine/sport.js + site_src/nhl/nhl.css, with everything
sport-specific in data/meta.json -> cfg.
"""
import datetime as dt
import html
import json
import math
import os
import shutil

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
ENGINE = os.path.join(ROOT, "site_src", "engine")
NHL_CSS = os.path.join(ROOT, "site_src", "nhl", "nhl.css")
SPORTS = [("NFL", ""), ("NBA", "nba/"), ("NBL", "nbl/"), ("NHL", "nhl/"), ("AFL", "afl/")]
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Public+Sans:wght@400;500;600&display=swap">')


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def C(k, l, g, f="num1", lo=False, t=None):
    """Column spec: key, label, group, format, lower-is-better, tooltip."""
    return dict(k=k, l=l, g=g, f=f, lo=lo, t=t)


def _num(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if (v != v or v in (math.inf, -math.inf)) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return _num(o)


def write_json(folder, name, obj):
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, name + ".part")
    with open(tmp, "w") as f:
        json.dump(clean(obj), f, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, os.path.join(folder, name))


def columnar(df, season, ids, cols):
    """{season, cols, rows} keeping only columns that exist and have at least one value."""
    keep = [c for c in cols if c["k"] in df.columns and df[c["k"]].notna().any()]
    rows = []
    for r in df[ids + [c["k"] for c in keep]].itertuples(index=False):
        rows.append([_num(v) if not isinstance(v, str) else v for v in r])
    return {"season": int(season), "cols": [{k: v for k, v in c.items() if v not in (None, False)} for c in keep], "rows": rows}


def page_html(sport, brand, nav, slug, title, intro, script="sport.js", css="nhl.css"):
    here = dict(SPORTS)[sport]
    up = "../" * here.count("/")
    bar = "".join(f'<a href="{"./" if s == sport else (up + p) or "./"}"' + (' aria-current="page"' if s == sport else "") + f">{s}</a>"
                  for s, p in SPORTS)
    links = "".join(f'<a href="{"./" if s == "index" else s + ".html"}"' + (' aria-current="page"' if s == slug else "") + f">{html.escape(l)}</a>"
                    for s, l in nav)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(sport)} {html.escape(title)}</title>{FONTS}
<link rel="stylesheet" href="{up}style.css"><link rel="stylesheet" href="{css}"></head>
<body data-page="{slug}"><div class="wrap">
<header class="site-head"><div class="sportbar"><span>SPORT</span>{bar}</div>
<div class="brand"><a class="brand-name" href="./">{html.escape(sport)}<span>{html.escape(brand)}</span></a><span class="stamp" id="stamp">Loading latest update…</span></div>
<nav class="nav nav-simple" aria-label="{html.escape(sport)} sections">{links}</nav></header>
<main class="page" id="main"><div class="page-head"><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p></div>
<div id="app"><p class="note">Loading…</p></div></main>
<footer class="stamp">Independent statistics and probabilities from public data. Not betting advice.</footer></div>
<script src="{up}js/common.js"></script><script src="{script}"></script></body></html>"""


def build_pages(folder, sport, brand, pages, data_src=None, keep=()):
    """pages: [(slug, nav label, title, intro)]. Copies engine script/css and data files (from data_src)."""
    os.makedirs(os.path.join(folder, "data"), exist_ok=True)
    nav = [(s, l) for s, l, _, _ in pages]
    for s, l, t, i in pages:
        name = "index.html" if s == "index" else s + ".html"
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(page_html(sport, brand, nav, s, t, i))
    # remove old pages from earlier designs (keeps trends.html and anything listed in keep)
    want = {("index.html" if s == "index" else s + ".html") for s, *_ in pages} | {"trends.html"} | set(keep)
    for fn in os.listdir(folder):
        if fn.endswith(".html") and fn not in want:
            os.remove(os.path.join(folder, fn))
    shutil.copy(os.path.join(ENGINE, "sport.js"), folder)
    shutil.copy(NHL_CSS, folder)
    if data_src and os.path.isdir(data_src):
        for fn in os.listdir(data_src):
            if fn.endswith(".json"):
                shutil.copy(os.path.join(data_src, fn), os.path.join(folder, "data", fn))


def pct(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / b, np.nan)
