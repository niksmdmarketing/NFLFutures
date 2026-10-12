"""Site-wide Updates page: a dated one-liner for each new statistic or dataset, newest first.

Entries live in site_src/updates.json (public sports only: {"date", "sport", "text"}). Private entries, such as football,
are kept in the private repository and merged into data/updates.json at deploy time. Adding an entry is adding a line.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
SRC = os.path.join(ROOT, "site_src", "updates.json")
SPORTBAR = re.compile(r'(<(?:div|nav)\b[^>]*class=["\'][^"\']*\bsportbar\b[^"\']*["\'][^>]*>)(.*?)(</(?:div|nav)>)', re.S)

PAGE_BODY = """
<main class="page" id="main">
  <div class="page-head"><h1>Updates</h1><p>New statistics and data added to the site, newest first.</p></div>
  <div id="updates"><p class="note">Loading…</p></div>
</main>
<style>
.upd{list-style:none;margin:0;padding:0;max-width:52rem}
.upd li{display:flex;gap:.9rem;align-items:baseline;padding:.55rem 0;border-bottom:1px solid var(--line,#d9dee3)}
.upd time{flex:0 0 6.2rem;font-variant-numeric:tabular-nums;color:var(--muted,#5b6773);font-size:.9rem}
.upd b{flex:0 0 3.4rem;font-size:.75rem;letter-spacing:.06em;text-transform:uppercase}
</style>
<script>
(function(){
  var el=document.getElementById('updates');
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  fetch('data/updates.json').then(function(r){return r.json();}).then(function(rows){
    rows.sort(function(a,b){return a.date<b.date?1:a.date>b.date?-1:0;});
    el.innerHTML=rows.length?'<ul class="upd">'+rows.map(function(r){
      return '<li><time datetime="'+esc(r.date)+'">'+esc(r.date)+'</time><b>'+esc(r.sport||'')+'</b><span>'+esc(r.text)+'</span></li>';}).join('')+'</ul>':'<p class="note">Nothing yet.</p>';
  }).catch(function(){el.innerHTML='<p class="note">Could not load updates.</p>';});
})();
</script>
</div></body></html>"""


def add_nav_links(root):
    """Adds an Updates link to every sports bar under root (once per page)."""
    n = 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dirpath, fn)
            text = open(p, encoding="utf-8-sig").read()
            rel = os.path.relpath(root, dirpath).replace("\\", "/")
            href = ("" if rel == "." else rel + "/") + "updates.html"
            cur = ' aria-current="page"' if os.path.abspath(p) == os.path.join(os.path.abspath(root), "updates.html") else ""

            def add(m):
                return m[0] if re.search(r">\s*Updates\s*</a>", m[2]) else m[1] + m[2] + f'<a href="{href}"{cur}>Updates</a>' + m[3]
            new = SPORTBAR.sub(add, text, count=1)
            if new != text:
                open(p, "w", encoding="utf-8").write(new)
                n += 1
    return n


def build_site(site=SITE, src=SRC):
    index = os.path.join(site, "index.html")
    if not os.path.exists(index):
        return
    rows = json.load(open(src, encoding="utf-8")) if os.path.exists(src) else []
    rows.sort(key=lambda r: r["date"], reverse=True)
    os.makedirs(os.path.join(site, "data"), exist_ok=True)
    json.dump(rows, open(os.path.join(site, "data", "updates.json"), "w", encoding="utf-8"), indent=1)
    html = open(index, encoding="utf-8-sig").read()
    end = html.find("</header>")
    if end < 0:
        return
    top = html[:end + len("</header>")]
    top = re.sub(r'\saria-current=("page"|page|\'page\')', "", top)
    top = re.sub(r"<title>.*?</title>", "<title>Updates</title>", top, count=1, flags=re.S)
    top = re.sub(r'<nav class="nav[^"]*"[^>]*>.*?</nav>', "", top, flags=re.S)        # the NFL section menu does not apply here
    top = re.sub(r'(<span class="stamp"[^>]*>).*?(</span>)', r"\1\2", top, count=1, flags=re.S)
    top = re.sub(r'(<meta name="description" content=")[^"]*', r"\1New statistics and data added to the site.", top, count=1)
    body = PAGE_BODY
    if '<div class="wrap">' not in top:
        body = body.replace("</div></body>", "</body>")
    open(os.path.join(site, "updates.html"), "w", encoding="utf-8").write(top + body)
    add_nav_links(site)


if __name__ == "__main__":
    build_site()
