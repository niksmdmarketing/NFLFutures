"""Week-by-week history page ("History") for sports with replayed futures probabilities.

Reads model/replay/<sport>_<season>.csv (research/replay_nba.py, replay_nhl.py) plus the scored summaries
(replay_score.py, replay_slope.py) and writes, per sport, data/replay.json + replay.html/js/css in that sport's folder.
The replayed numbers are rebuilt from game data with only information available at each date (no injuries/rosters), so the
page labels them "replayed", not "as published". Probabilities are stored as per-mille integers to keep the files small.
"""
import glob
import json
import os
import re
import shutil

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "site_src", "replay")
REPLAY = os.path.join(ROOT, "model", "replay")
SITE = os.path.join(ROOT, "site")
SPORTS = {
    "nba": {"label": "NBA", "dir": "nba", "end_year": True, "markets": [("title", "p_title", "y_title", "Win the title"), ("finals", "p_conf", "y_finals", "Win the conference"),
                                                        ("div", "p_div", "y_div", "Win the division"), ("seed1", "p_seed1", "y_seed1", "Top seed in the conference"),
                                                        ("playoff", "p_playoff", "y_playoff", "Make the playoffs")]},
    "nhl": {"label": "NHL", "dir": "nhl", "markets": [("title", "p_title", "y_title", "Win the Stanley Cup"), ("finals", "p_conf", "y_finals", "Win the conference"),
                                                        ("div", "p_div", "y_div", "Win the division"), ("playoff", "p_playoff", "y_playoff", "Make the playoffs")]},
    "afl": {"label": "AFL", "dir": "afl", "end_year": None, "unit": "round",
            "markets": [("title", "p_title", "y_title", "Win the premiership"), ("finals", "p_conf", "y_finals", "Make the Grand Final"),
                        ("pf", "p_pf", "y_pf", "Make a preliminary final"), ("div", "p_div", "y_div", "Finish in the top 4"),
                        ("seed1", "p_seed1", "y_seed1", "Minor premiers"), ("top8", "p_top8", "y_top8", "Finish in the top 8"),
                        ("playoff", "p_playoff", "y_playoff", "Make the finals")]},
}


def season_label(y, end_year):
    """NBA files are named by the year the season ends; NHL by the year it starts; AFL seasons are a single year (end_year=None)."""
    if end_year is None:
        return str(y)
    y0 = y - 1 if end_year else y
    return f"{y0}-{str((y0 + 1) % 100).zfill(2)}"


def build_sport(sport, cfg):
    files = sorted(glob.glob(os.path.join(REPLAY, f"{sport}_[0-9]*.csv")))
    if not files:
        return None
    seasons = []
    for f in files:
        D = pd.read_csv(f)
        y = int(D.season.iloc[0])
        teams = sorted(D.team.unique())
        weeks = D[["week", "date", "gp_avg"]].drop_duplicates("week").sort_values("week")
        p, yy = {}, {}
        for k, pc, yc, _ in cfg["markets"]:
            if pc not in D or yc not in D:
                continue
            piv = D.pivot(index="week", columns="team", values=pc).reindex(weeks.week).reindex(columns=teams)
            p[k] = [[int(round(v * 1000)) for v in row] for row in piv.values]
            last = D[D.week == D.week.min()].set_index("team")[yc].reindex(teams)
            yy[k] = [int(v) for v in last.values]
        seasons.append({"y": y, "label": season_label(y, cfg.get("end_year", False)), "teams": teams, "weeks": [{"w": int(r.week), "d": r.date, "gp": float(r.gp_avg)} for r in weeks.itertuples()], "p": p, "o": yy})
    score = json.load(open(os.path.join(REPLAY, f"{sport}_score.json"))) if os.path.exists(os.path.join(REPLAY, f"{sport}_score.json")) else {}
    slope = json.load(open(os.path.join(REPLAY, f"{sport}_slope.json"))) if os.path.exists(os.path.join(REPLAY, f"{sport}_slope.json")) else {}
    rel = {}
    for st, r in score.items():
        rel[st] = {}
        for k, *_ in cfg["markets"]:
            if k in r:
                rel[st][k] = {"ll": r[k]["logloss"], "base": r[k]["base"], "gain": r[k]["gain"], "cal": r[k]["calibration"],
                              "slope": slope.get(st, {}).get(k, {}).get("slope"), "n": r["seasons"]}
    return {"sport": cfg["label"], "markets": [{"k": k, "l": l} for k, _, _, l in cfg["markets"] if any(k in s["p"] for s in seasons)],
            "unit": cfg.get("unit", "week"), "seasons": seasons, "reliability": rel, "stages": ["preseason", "first quarter", "second quarter", "third quarter", "last quarter"]}


def build_site():
    for sport, cfg in SPORTS.items():
        d = os.path.join(SITE, cfg["dir"])
        idx = os.path.join(d, "index.html")
        data = build_sport(sport, cfg)
        if data is None or not os.path.exists(idx):
            continue
        os.makedirs(os.path.join(d, "data"), exist_ok=True)
        json.dump(data, open(os.path.join(d, "data", "replay.json"), "w"), separators=(",", ":"))
        for fn in os.listdir(d):
            if fn.endswith(".html") and fn != "replay.html":
                p = os.path.join(d, fn)
                s = open(p, encoding="utf-8").read()
                if 'href="replay.html"' not in s:
                    s2 = re.sub(r'(<a href="trends\.html"[^>]*>Trends</a>)', r'\1<a href="replay.html">History</a>', s, count=1)
                    if s2 != s:
                        open(p, "w", encoding="utf-8").write(s2)
        src = open(idx, encoding="utf-8").read()
        head_end = src.find("</header>")
        if head_end < 0:
            continue
        top = src[:head_end + len("</header>")]
        top = re.sub(r'(<a )aria-current="?page"? ?(href="trends.html")', r"\1\2", top)
        top = re.sub(r'(<nav class="nav[^"]*"[^>]*>.*?)\saria-current=("page"|page)', r"\1", top, count=1, flags=re.S)
        if 'href="replay.html"' not in top:
            top = re.sub(r'(<a href="trends\.html"[^>]*>Trends</a>)', r'\1<a href="replay.html">History</a>', top, count=1)
        top = top.replace('href="replay.html">History', 'href="replay.html" aria-current="page">History')
        top = re.sub(r"<title>.*?</title>", f"<title>{cfg['label']} week-by-week history</title>", top, count=1, flags=re.S)
        body = f"""
<main class="page" id="main">
  <div class="page-head"><h1>{cfg['label']} week by week</h1><p>How each team's chance of winning each market changed through past seasons, rebuilt for every week of the season. Pick a season, a market and a week to see where the model stood, how much it had moved, and how things ended.</p></div>
  <div id="replay" data-src="data/replay.json"><p class="note">Loading…</p></div>
</main>
<footer class="stamp">Replayed from game results using only information available at each date. Injuries and roster moves are not included, so these are not the numbers the site showed at the time. Probabilities and history only, not betting advice.</footer>
</div>
<link rel="stylesheet" href="replay.css">
<script src="replay.js"></script>
</body></html>"""
        open(os.path.join(d, "replay.html"), "w", encoding="utf-8").write(top + body)
        for f in ("replay.js", "replay.css"):
            shutil.copy(os.path.join(SRC, f), os.path.join(d, f))
        print("replay page", sport, flush=True)


if __name__ == "__main__":
    build_site()
