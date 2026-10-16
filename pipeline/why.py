"""'Why the model thinks this' pages for NFL, NBA, NHL, NBL and AFL: each team's forecast, its main drivers in plain words,
and an expected-vs-actual chart (results so far against what the scoring margin implies).

Drivers come only from numbers the forecast already uses or the site already publishes: the team rating and its rank,
this season's scoring margin against last season's, results against the scoring margin, schedule faced and still to
come (schedule.json from sos.py), and each sport's own layers (NFL quarterback adjustments, NHL injuries / roster term /
playoff route, NBA availability). Nothing here feeds a forecast. Writes site/<sport>/why.html and data/why.json.
"""
import html
import json
import math
import os
import re

import sportsite  # noqa: E402


import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")

SPORTS = {   # dir, title field, title label, second market field, label, unit, games per season, nav anchor
    "nfl": dict(dir="", title=("p_sb", "Super Bowl"), second=("p_playoff", "Playoffs"), unit="pts", games=17, label="NFL",
                nav=r'(<a href="matchups\.html"[^>]*>Matchups</a>)'),
    "nba": dict(dir="nba", title=("p_title", "Title"), second=("p_playoff", "Playoffs"), unit="pts", games=82, label="NBA"),
    "nhl": dict(dir="nhl", title=("p_cup", "Stanley Cup"), second=("p_playoffs", "Playoffs"), unit="goals", games=84, label="NHL"),
    "nbl": dict(dir="nbl", title=("champ", "Title"), second=("p6", "Finals"), unit="pts", games=33, label="NBL"),
    "afl": dict(dir="afl", title=("flag", "Premiership"), second=("p8", "Top 8"), unit="pts", games=23, label="AFL"),
}


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _games_table(sport, d, season):
    """team -> (games, mean margin, wins, points for, points against) for one season from the site's games files."""
    if sport == "nfl":
        try:
            g = pd.read_csv(os.path.join(ROOT, "data", "games.csv"), low_memory=False)
        except OSError:
            return {}
        g = g[(g.season == season) & (g.game_type == "REG") & g.home_score.notna()]
        rows = []
        for r in g.itertuples():
            rows.append((r.home_team, r.home_score, r.away_score))
            rows.append((r.away_team, r.away_score, r.home_score))
        D = pd.DataFrame(rows, columns=["team", "pf", "pa"])
    else:
        j = _load(os.path.join(SITE, d, "data", f"games_{season}.json"))
        if not j or not j.get("rows"):
            return {}
        cols = [c["k"] for c in j["cols"]]
        head = 6 if sport == "afl" else 5
        R = pd.DataFrame([r[:head + len(cols)] for r in j["rows"]], columns=(["date", "round"] if sport == "afl" else ["date"]) +
                         ["team", "opp", "ha", "res"] + cols)
        pf, pa = {"nba": ("pts", "o_pts"), "nbl": ("pf", "pa"), "afl": ("points_for", "points_against"),
                  "nhl": ("goalsFor", "goalsAgainst")}[sport]
        D = pd.DataFrame({"team": R.team, "pf": pd.to_numeric(R[pf], errors="coerce"), "pa": pd.to_numeric(R[pa], errors="coerce"),
                          "res": R.res})
        D = D.dropna(subset=["pf", "pa"])
    out = {}
    for t, x in D.groupby("team"):
        out[t] = dict(gp=len(x), margin=float((x.pf - x.pa).mean()), pf=float(x.pf.sum()), pa=float(x.pa.sum()),
                      wins=float((x.pf > x.pa).sum()))
    return out


def _teams(sport, F):
    T = F.get("teams") or {}
    if isinstance(T, dict):
        return [dict(v, team=k) for k, v in T.items()]
    return list(T)


def _ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _drivers(sport, t, cfg, ctx):
    """[(weight, sentence)] for one team; the page shows the strongest few."""
    out = []
    unit = cfg["unit"]
    n = ctx["n"]
    rk = ctx["rank"].get(t["team"])
    rating = t.get("rating")
    if rating is not None and rk:
        side = "better" if rating > 0 else "worse"
        tier = "one of the strongest teams" if rk <= max(3, n // 8) else ("one of the weakest teams" if rk > n - max(3, n // 8) else "")
        out.append((abs(ctx["z"].get(t["team"], 0)) + 0.3,
                    f"Rated {_ordinal(rk)} of {n}: {abs(rating):.1f} {unit} a game {side} than an average team" + (f", {tier}." if tier else ".")))
    cur, prev = ctx["cur"].get(t["team"]), ctx["prev"].get(t["team"])
    if cur and cur["gp"] >= 2 and prev:
        dlt = cur["margin"] - prev["margin"]
        if abs(dlt) >= ctx["margin_sd"] * 0.5:
            word = "better" if dlt > 0 else "worse"
            out.append((abs(dlt) / ctx["margin_sd"],
                        f"This season's scoring margin ({cur['margin']:+.1f} {unit} a game over {cur['gp']} games) is clearly {word} than last "
                        f"season's ({prev['margin']:+.1f}). Early on the rating still leans on last season, so it moves only part of the way."))
    elif prev and not cur:
        out.append((abs(prev["margin"]) / ctx["margin_sd"] * 0.6,
                    f"No games yet: the rating starts from last season ({prev['margin']:+.1f} {unit} a game), pulled part of the way back to average."))
    if sport == "nhl" and cur and cur["gp"] >= 3 and t.get("points") is not None:
        ex_p = cur["gp"] * 2.23 * cur["pf"] ** 2 / max(cur["pf"] ** 2 + cur["pa"] ** 2, 1e-9)
        luck = float(t["points"]) - ex_p
        if abs(luck) >= 2.0:
            tone = "results stronger than the underlying goal difference" if luck > 0 else "results weaker than the underlying goal difference"
            out.append((abs(luck) / max(2.0, math.sqrt(cur["gp"])),
                        f"Has {abs(luck):.1f} {'more' if luck > 0 else 'fewer'} points than its goals for and against suggest ({tone}). "
                        f"Shootout and one-goal results tend not to repeat, so the model rates the goals, not the points."))
    elif cur and cur["gp"] >= 3:
        exp_w = cur["gp"] * _phi(cur["margin"] / ctx["sd"])
        luck = cur["wins"] - exp_w
        if abs(luck) >= 0.8 or (cur["gp"] >= 10 and abs(luck) >= 1.5):
            word = "more" if luck > 0 else "fewer"
            tone = "results stronger than the underlying margin" if luck > 0 else "results weaker than the underlying margin"
            out.append((abs(luck) / max(1.0, math.sqrt(cur["gp"]) * 0.5),
                        f"Won {abs(luck):.1f} {word} games than its scoring margin suggests ({tone}). Close results tend not to repeat, so the model rates the margin, not the record."))
    S = ctx["sched"].get(t["team"]) or {}
    wall = S.get("wall") or {}
    if wall.get("n") and wall.get("opp") is not None and ctx["sched_rank"]:
        r_ = ctx["sched_rank"].get(t["team"])
        if r_ and (r_ <= max(3, n // 6) or r_ > n - max(3, n // 6)) and abs(wall["opp"]) >= 0.15 * ctx["margin_sd"]:
            hard = r_ <= max(3, n // 6)
            out.append((0.6 + abs(wall["opp"]) / ctx["margin_sd"],
                        f"{'One of the hardest' if hard else 'One of the easiest'} remaining schedules ({_ordinal(r_)} hardest of {n}; "
                        f"opponents average {wall['opp']:+.1f} {unit} a game)."))
    if S.get("past_opp") is not None and cur and cur["gp"] >= 3 and abs(S["past_opp"]) >= ctx["margin_sd"] * 0.25:
        out.append((abs(S["past_opp"]) / ctx["margin_sd"],
                    f"Has faced {'strong' if S['past_opp'] > 0 else 'weak'} opponents so far (average {S['past_opp']:+.1f}), which the rating corrects for."))
    # sport-specific layers
    if sport == "nfl":
        if abs(t.get("qb_adj") or 0) >= 0.5:
            out.append((abs(t["qb_adj"]) / 2 + 0.5, f"Quarterback change: {t.get('qb_note') or t.get('qb')} moves the rating {t['qb_adj']:+.1f} points a game."))
        if abs(t.get("press_adj") or 0) >= 0.7:
            out.append((abs(t["press_adj"]) / 2, f"Pass protection: the pressure-rate adjustment is {t['press_adj']:+.1f} points a game."))
    if sport == "nhl":
        inj = ctx.get("nhl_inj", {}).get(t["team"])
        if inj and inj[0] >= 1.0:
            out.append((inj[0] / 2 + 0.4, f"Injuries cost about {inj[0]:.1f} goals over the absences ({inj[1]})."))
        if abs(t.get("roster") or 0) >= 0.05:
            out.append((abs(t["roster"]) * 6, f"Recent line-ups are {'stronger' if t['roster'] > 0 else 'weaker'} than the ones behind this season's results ({t['roster']:+.2f} goals a game)."))
        if t.get("p_top3") is not None and (t.get("p_playoffs") or 0) >= 0.15:
            sh = t["p_top3"] / max(t["p_playoffs"], 1e-9)
            if sh >= 0.95 or sh <= 0.55:
                out.append((0.45, f"Playoff route: {100 * sh:.0f}% of its playoff chance comes from a top-three division finish"
                                  f"{' (league-wide about 75%)' if sh >= 0.95 else ', so it leans on a wild card more than most'}."))
    if sport == "nba":
        av = ctx.get("nba_avail", {}).get(t["team"])
        if av and av[0] >= 0.8:
            out.append((av[0] / 2 + 0.3, f"Injuries: {av[1]} out, worth about {av[0]:.1f} points a game while missing (affects game chances; season futures do not use it)."))
    out.sort(key=lambda x: -x[0])
    return out


def _nba_avail(F):
    out = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", F.get("avail_html") or "", flags=re.S):
        c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(c) >= 9:
            try:
                cost = abs(float(c[8].replace("−", "-")))
            except ValueError:
                continue
            a = out.setdefault(c[0], [0.0, []])
            a[0] += cost
            a[1].append(c[1])
    return {t: (v[0], ", ".join(v[1][:3])) for t, v in out.items()}


def _svg(points, unit_word):
    """Expected (x) vs actual (y) wins/points scatter, inline SVG with labels."""
    if not points:
        return ""
    W, H, P = 640, 420, 46
    xs = [p[1] for p in points] + [p[2] for p in points]
    lo, hi = min(xs), max(xs)
    if hi - lo < 1:
        hi = lo + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    sx = lambda v: P + (v - lo) / (hi - lo) * (W - 2 * P)
    sy = lambda v: H - P - (v - lo) / (hi - lo) * (H - 2 * P)
    el = [f'<line x1="{sx(lo)}" y1="{sy(lo)}" x2="{sx(hi)}" y2="{sy(hi)}" stroke="currentColor" stroke-opacity=".35" stroke-dasharray="4 4"/>']
    resid = sorted(points, key=lambda p: -abs(p[2] - p[1]))
    show = {p[0] for p in resid[:8]}
    for name, ex, ac in points:
        c = "var(--off-ink, #2a7)" if ac - ex >= 0.75 else ("var(--def-ink, #c44)" if ex - ac >= 0.75 else "currentColor")
        el.append(f'<circle cx="{sx(ex):.1f}" cy="{sy(ac):.1f}" r="4" fill="{c}" fill-opacity=".85"><title>{html.escape(name)}: '
                  f'{ac:.0f} actual vs {ex:.1f} expected</title></circle>')
        if name in show:
            el.append(f'<text x="{sx(ex) + 6:.1f}" y="{sy(ac) + 4:.1f}" font-size="11" fill="currentColor" fill-opacity=".85">{html.escape(name)}</text>')
    ticks = np.linspace(math.ceil(lo), math.floor(hi), 5)
    for v in ticks:
        el.append(f'<text x="{sx(v):.1f}" y="{H - P + 16}" font-size="10" text-anchor="middle" fill="currentColor" fill-opacity=".6">{v:.0f}</text>')
        el.append(f'<text x="{P - 8}" y="{sy(v) + 3:.1f}" font-size="10" text-anchor="end" fill="currentColor" fill-opacity=".6">{v:.0f}</text>')
    el.append(f'<text x="{W / 2}" y="{H - 8}" font-size="11" text-anchor="middle" fill="currentColor">Expected {unit_word} from scoring margin</text>')
    el.append(f'<text x="14" y="{H / 2}" font-size="11" text-anchor="middle" fill="currentColor" transform="rotate(-90 14 {H / 2})">Actual {unit_word}</text>')
    return (f'<div class="why-chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="Expected versus actual {unit_word}" '
            f'style="width:100%;max-width:{W}px;height:auto">{"".join(el)}</svg></div>')


def build_sport(sport, cfg):
    d = os.path.join(SITE, cfg["dir"]) if cfg["dir"] else SITE
    F = _load(os.path.join(d, "data", "futures.json"))
    Sj = _load(os.path.join(d, "data", "schedule.json")) or {}
    if not F:
        return None
    teams = _teams(sport, F)
    season = int(F.get("season") or 0)
    cur_season = season if sport != "nba" else season - 1 if not any((x.get("gp") or 0) > 0 for x in teams) else season
    # the season whose games exist: NBA labels seasons by end year (2027 = 2026-27); fall back to the latest file present
    cur = _games_table(sport, d, season if sport not in ("nba",) else season)
    prev_season = season - 1
    prev = _games_table(sport, d, prev_season)
    if not cur and sport in ("afl",):
        cur, prev = {}, _games_table(sport, d, season - 1)
    margins = [v["margin"] for v in (cur or prev).values()] or [1.0]
    margin_sd = float(np.std(margins)) or 1.0
    sd = float(Sj.get("sd") or margin_sd * 2)
    ratings = {x["team"]: x.get("rating") for x in teams if x.get("rating") is not None}
    order = sorted(ratings, key=lambda k: -ratings[k])
    rank = {k: i + 1 for i, k in enumerate(order)}
    rv = np.array(list(ratings.values()) or [0.0])
    z = {k: (v - rv.mean()) / (rv.std() or 1) for k, v in ratings.items()}
    sched = {x["team"]: x for x in Sj.get("teams") or []}
    sr = [(k, (v.get("wall") or {}).get("opp")) for k, v in sched.items() if (v.get("wall") or {}).get("opp") is not None]
    sched_rank = {k: i + 1 for i, (k, _) in enumerate(sorted(sr, key=lambda kv: -kv[1]))}
    ctx = dict(n=len(teams), rank=rank, z=z, cur=cur, prev=prev, margin_sd=margin_sd, sd=sd, sched=sched, sched_rank=sched_rank)
    if sport == "nhl":
        inj = {}
        for p in ((F.get("injuries") or {}).get("players") or []):
            a = inj.setdefault(p["team"], [0.0, []])
            a[0] += float(p.get("season_goals") or 0)
            if (p.get("season_goals") or 0) >= 0.3:
                a[1].append(p["name"])
        ctx["nhl_inj"] = {t: (v[0], ", ".join(v[1][:3]) or "several players") for t, v in inj.items()}
    if sport == "nba":
        ctx["nba_avail"] = _nba_avail(F)
    names = {x["team"]: x.get("name") or x["team"] for x in teams}
    if sport == "nfl":
        try:
            from common import NAMES
            names = {k: NAMES.get(k, k) for k in names}
        except Exception:  # noqa: BLE001
            pass
    tf, tl = cfg["title"]
    sf, sl = cfg["second"]
    rows = []
    for t in sorted(teams, key=lambda x: -(x.get(tf) or 0)):
        drv = _drivers(sport, t, cfg, ctx)
        rows.append(dict(team=t["team"], name=names.get(t["team"], t["team"]), rating=t.get("rating"), title=t.get(tf), second=t.get(sf),
                         drivers=[s for _, s in drv[:4]]))
    # expected vs actual: this season once teams have played 3+ games, otherwise last season (labelled)
    base_tab, which = (cur, "this season") if cur and np.mean([v["gp"] for v in cur.values()]) >= 3 else (prev, "last season")
    pts = []
    if base_tab:
        for tm, v in base_tab.items():
            if sport == "nhl":
                pyth = v["pf"] ** 2 / max(v["pf"] ** 2 + v["pa"] ** 2, 1e-9)
                ex = v["gp"] * 2.23 * pyth
                act = None
                for x in teams:
                    if x["team"] == tm and which == "this season":
                        act = x.get("points")
                if act is None:
                    act = 2 * v["wins"] + 0.115 * v["gp"]
            else:
                ex = v["gp"] * _phi(v["margin"] / sd)
                act = v["wins"]
            pts.append((tm, float(ex), float(act)))
    unit_word = "points" if sport == "nhl" else "wins"
    return dict(sport=sport, label=cfg["label"], rows=rows, chart=pts, chart_which=which, unit_word=unit_word, title_label=tl, second_label=sl,
                updated=F.get("updated_utc") or (Sj.get("updated_utc")))


def _rt(v):
    return "" if v is None else f"{v:+.1f}"


def _page_html(data, top):
    pc = lambda v: "–" if v is None else ("<0.1%" if v < 0.0005 else ">99.9%" if v > 0.9995 else f"{100 * v:.1f}%" if v < 0.0995 else f"{100 * v:.0f}%")
    body_rows = "".join(
        f"<tr id=\"t-{html.escape(str(r['team']))}\"><td class=\"why-team\"><b>{html.escape(r['name'])}</b></td><td>{_rt(r['rating'])}</td>"
        f"<td>{pc(r['title'])}</td><td>{pc(r['second'])}</td><td class=\"why-drv\"><ul>{''.join(f'<li>{html.escape(s)}</li>' for s in r['drivers'])}</ul></td></tr>"
        for r in data["rows"])
    chart = _svg(data["chart"], data["unit_word"])
    return top + f"""
<style>.why-tbl{{width:100%;border-collapse:collapse}}.why-tbl th,.why-tbl td{{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}
.why-tbl td:nth-child(2),.why-tbl td:nth-child(3),.why-tbl td:nth-child(4){{white-space:nowrap;font-variant-numeric:tabular-nums}}
.why-drv ul{{margin:0;padding-left:18px}}.why-drv li{{margin:2px 0;font-size:.88rem}}.why-scroll{{overflow-x:auto}}
.why-chart{{margin:10px 0 24px;color:var(--ink)}}.why-tbl tr:target td{{background:color-mix(in srgb,var(--accent) 14%,transparent)}}.why-tbl tr{{scroll-margin-top:12px}}@media(max-width:640px){{.why-tbl th,.why-tbl td{{padding:6px}}}}</style>
<main class="page" id="main">
  <div class="page-head"><h1>{data['label']}: why the model thinks this</h1>
  <p>For each team, the forecast and the few things that drive it most, in plain words: how strong the team is rated, how this season compares with last,
  whether results have run ahead of or behind the scoring margin, the schedule, and each sport's own adjustments. Nothing on this page changes a forecast.</p></div>
  <h2 class="sv-h">Results against the scoring margin ({data['chart_which']})</h2>
  <p class="note">Hover or tap a dot for the team; the eight teams furthest from the line are labelled. Each dot is a team: expected {data['unit_word']} from its scoring margin (across) against actual {data['unit_word']} (up). Above the dashed line = results
  stronger than the underlying margin; below = weaker. Teams far from the line usually drift back towards it, though not all the way.</p>
  {chart}
  <h2 class="sv-h">Drivers, team by team</h2>
  <div class="why-scroll"><table class="why-tbl"><thead><tr><th>Team</th><th>Rating</th><th>{data['title_label']}</th><th>{data['second_label']}</th><th>Why</th></tr></thead>
  <tbody>{body_rows}</tbody></table></div>
</main>
<footer class="stamp">Probabilities from this site's model; drivers are explanations of its inputs, not separate forecasts. Not betting advice.</footer>
</div></body></html>"""


def build_site():
    for sport, cfg in SPORTS.items():
        try:
            data = build_sport(sport, cfg)
        except Exception as e:  # noqa: BLE001
            print("why page failed", sport, repr(e)[:200], flush=True)
            continue
        if not data:
            continue
        d = os.path.join(SITE, cfg["dir"]) if cfg["dir"] else SITE
        os.makedirs(os.path.join(d, "data"), exist_ok=True)
        json.dump(data, open(os.path.join(d, "data", "why.json"), "w"), separators=(",", ":"))
        idx = os.path.join(d, "futures.html") if os.path.exists(os.path.join(d, "futures.html")) else os.path.join(d, "index.html")
        src = open(idx, encoding="utf-8").read()
        he = src.find("</header>")
        if he < 0:
            continue
        nav = cfg.get("nav", r'(<a href="futures\.html"[^>]*>Futures</a>)')
        top = src[:he + len("</header>")]
        top = re.sub(r'(<nav class="nav[^"]*"[^>]*>.*?)\saria-current=("page"|page)', r"\1", top, count=1, flags=re.S)
        if 'href="why.html"' not in top:
            top = re.sub(nav, r'\1<a href="why.html" aria-current="page">Why</a>', top, count=1)
        top = re.sub(r"<title>.*?</title>", f"<title>{cfg['label']}: why the model thinks this</title>", top, count=1, flags=re.S)
        top = re.sub(r'<script[^>]*>.*?</script>', "", top, flags=re.S)
        top = sportsite.stamp_sub(top, (data.get("updated") or None), "Why the model thinks this")
        open(os.path.join(d, "why.html"), "w", encoding="utf-8").write(_page_html(data, top))
        for fn in os.listdir(d):
            if fn.endswith(".html") and fn != "why.html":
                p = os.path.join(d, fn)
                s = open(p, encoding="utf-8").read()
                if 'href="why.html"' not in s:
                    s2 = re.sub(nav, r'\1<a href="why.html">Why</a>', s, count=1)
                    if s2 != s:
                        open(p, "w", encoding="utf-8").write(s2)
        print("why page", sport, len(data["rows"]), "teams", flush=True)


if __name__ == "__main__":
    build_site()
