"""Week-by-week history page ("History") for sports with replayed futures probabilities.

Reads model/replay/<sport>_<season>.csv (research/replay_nba.py, replay_nhl.py) plus the scored summaries
(replay_score.py, replay_slope.py) and writes, per sport, data/replay.json + replay.html/js/css in that sport's folder.
The replayed numbers are rebuilt from game data with only information available at each date (no injuries/rosters), so the
page labels them "replayed", not "as published". Probabilities are stored as per-mille integers to keep the files small.
"""
import csv
import glob
import gzip
import json
import os
import re

import sportsite  # noqa: E402
import shutil

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "site_src", "replay")
REPLAY = os.path.join(ROOT, "model", "replay")
SITE = os.path.join(ROOT, "site")
SPORTS = {
    "nfl": {"label": "NFL", "dir": "", "end_year": None, "games": 17, "nav_after": r'(<a href="matchups\.html"[^>]*>Matchups</a>)',
            "caveat": "NFL history covers only four seasons (2022 to 2025): the rating weights were trained on 2010 to 2021, and the spread of outcomes was tuned on 2022 to 2025, so even these are not fully unseen. Four seasons is very little evidence, especially for the Super Bowl and conference markets. The live model also uses quarterback and injury adjustments that the replay cannot.",
            "markets": [("title", "p_title", "y_title", "Win the Super Bowl"), ("finals", "p_conf", "y_finals", "Win the conference"),
                        ("div", "p_div", "y_div", "Win the division"), ("seed1", "p_seed1", "y_seed1", "No. 1 seed"),
                        ("playoff", "p_playoff", "y_playoff", "Make the playoffs")]},
    "nba": {"label": "NBA", "dir": "nba", "end_year": True, "games": 82, "markets": [("title", "p_title", "y_title", "Win the title"), ("finals", "p_conf", "y_finals", "Win the conference"),
                                                        ("div", "p_div", "y_div", "Win the division"), ("seed1", "p_seed1", "y_seed1", "Top seed in the conference"),
                                                        ("cf", "p_cf", "y_cf", "Reach the conference finals"), ("r2", "p_r2", "y_r2", "Win a playoff round"),
                                                        ("playoff", "p_playoff", "y_playoff", "Make the playoffs"),
                                                        ("top6", "p_top6", "y_top6", "Top six (avoid the play-in)"), ("playin", "p_playin", "y_playin", "Finish 7th-10th (play-in places)")]},
    "nhl": {"label": "NHL", "dir": "nhl", "games": 82, "markets": [("title", "p_title", "y_title", "Win the Stanley Cup"), ("finals", "p_conf", "y_finals", "Win the conference"),
                                                        ("div", "p_div", "y_div", "Win the division"), ("playoff", "p_playoff", "y_playoff", "Make the playoffs"),
                                                        ("r3", "p_r3", "y_r3", "Reach the conference final"), ("r2", "p_r2", "y_r2", "Win a playoff round"),
                                                        ("pres", "p_pres", "y_pres", "Best record (Presidents' Trophy)")]},
    "nbl": {"label": "NBL", "dir": "nbl", "games": 28, "markets": [("title", "p_title", "y_title", "Win the championship"), ("finals", "p_conf", "y_finals", "Make the Grand Final"),
                                                        ("div", "p_div", "y_div", "Finish in the top 2"), ("seed1", "p_seed1", "y_seed1", "Minor premiers"),
                                                        ("playoff", "p_playoff", "y_playoff", "Make the finals"),
                                                        ("semi", "p_semi", "y_semi", "Reach the semi-finals (play-in era)")]},
    "afl": {"label": "AFL", "dir": "afl", "end_year": None, "unit": "round", "games": 23,
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


def live_season(sport, cfg, archive):
    """The current season from the append-only snapshot archive (pipeline/sport_archive.py): the last snapshot of each
    7-day stretch, plus the newest one. These are the numbers the site actually showed."""
    base = os.path.join(archive or "", sport)
    if not archive or not os.path.isdir(base):
        return None
    years = sorted(int(d) for d in os.listdir(base) if d.isdigit())
    if not years:
        return None
    y = years[-1]
    d = os.path.join(base, str(y))
    snaps = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json.gz"):
            try:
                snaps.append(json.load(gzip.open(os.path.join(d, f), "rt")))
            except Exception:  # noqa: BLE001
                continue
    if not snaps:
        return None
    teams = snaps[-1]["teams"]
    snaps = [x for x in snaps if x["teams"] == teams]
    t0 = pd.Timestamp(snaps[0]["generated_utc"][:10])
    keep = {}
    for x in snaps:
        keep[(pd.Timestamp(x["generated_utc"][:10]) - t0).days // 7] = x
    chosen = [keep[k] for k in sorted(keep)]
    if chosen[-1] is not snaps[-1]:
        chosen.append(snaps[-1])
    p = {}
    for k in snaps[-1]["p"]:
        if k in ("rating_x100", "top3") or k.startswith(("c_", "s_", "sens_")):
            continue
        p[k] = [x["p"][k] for x in chosen if k in x["p"]]
        if len(p[k]) != len(chosen):
            p.pop(k)
    return {"y": y, "label": season_label(y, cfg.get("end_year", False)) + " (live)", "live": True, "teams": teams,
            "weeks": [{"w": i, "d": x["generated_utc"][:10], "gp": float(x.get("gp_avg") or 0.0)} for i, x in enumerate(chosen)], "p": p, "o": {}}


def build_sport(sport, cfg, archive=None):
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
            if pc not in D or yc not in D or D[pc].isna().all():   # e.g. NBL semi-finals exist only in the play-in era
                continue
            piv = D.pivot(index="week", columns="team", values=pc).reindex(weeks.week).reindex(columns=teams)
            p[k] = [[int(round(v * 1000)) for v in row] for row in piv.values]
            last = D[D.week == D.week.min()].set_index("team")[yc].reindex(teams)
            yy[k] = [int(v) for v in last.values]
        seasons.append({"y": y, "label": season_label(y, cfg.get("end_year", False)), "teams": teams, "weeks": [{"w": int(r.week), "d": r.date, "gp": float(r.gp_avg)} for r in weeks.itertuples()], "p": p, "o": yy})
    live = live_season(sport, cfg, archive)
    if live and live["y"] not in {x["y"] for x in seasons}:
        seasons.append(live)
    score = json.load(open(os.path.join(REPLAY, f"{sport}_score.json"))) if os.path.exists(os.path.join(REPLAY, f"{sport}_score.json")) else {}
    slope = json.load(open(os.path.join(REPLAY, f"{sport}_slope.json"))) if os.path.exists(os.path.join(REPLAY, f"{sport}_slope.json")) else {}
    rel = {}
    for st, r in score.items():
        rel[st] = {}
        for k, *_ in cfg["markets"]:
            if k in r:
                rel[st][k] = {"ll": r[k]["logloss"], "base": r[k]["base"], "gain": r[k]["gain"], "cal": r[k]["calibration"],
                              "slope": slope.get(st, {}).get(k, {}).get("slope"), "n": r[k].get("seasons", r["seasons"])}
    try:
        import live_check
        check = live_check.build(sport, archive, cfg.get("games"))
    except Exception as exc:  # noqa: BLE001 - the live check must never stop the History page
        print("live check skipped", sport, exc)
        check = None
    return {"sport": cfg["label"], "live_check": check, "markets": [{"k": k, "l": l} for k, _, _, l in cfg["markets"] if any(k in s["p"] for s in seasons)],
            "unit": cfg.get("unit", "week"), "games": cfg.get("games"), "seasons": seasons, "reliability": rel, "caveat": cfg.get("caveat"), "stages": ["preseason", "first quarter", "second quarter", "third quarter", "last quarter"]}


def build_site(archive=None):
    for sport, cfg in SPORTS.items():
        d = os.path.join(SITE, cfg["dir"]) if cfg["dir"] else SITE
        nav = cfg.get("nav_after", r'(<a href="trends\.html"[^>]*>Trends</a>)')
        idx = os.path.join(d, "index.html")
        data = build_sport(sport, cfg, archive)
        if data is None or not os.path.exists(idx):
            continue
        os.makedirs(os.path.join(d, "data"), exist_ok=True)
        json.dump(data, open(os.path.join(d, "data", "replay.json"), "w"), separators=(",", ":"))
        for fn in os.listdir(d):
            if fn.endswith(".html") and fn != "replay.html":
                p = os.path.join(d, fn)
                s = open(p, encoding="utf-8").read()
                if 'href="replay.html"' not in s:
                    s2 = re.sub(nav, r'\1<a href="replay.html">History</a>', s, count=1)
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
            top = re.sub(nav, r'\1<a href="replay.html">History</a>', top, count=1)
        top = top.replace('href="replay.html">History', 'href="replay.html" aria-current="page">History')
        top = re.sub(r"<title>.*?</title>", f"<title>{cfg['label']} week-by-week history</title>", top, count=1, flags=re.S)
        top = sportsite.stamp_sub(top, None, "Accuracy history")   # the sport's JS (which fills the stamp) is not loaded on this page
        body = f"""
<main class="page" id="main">
  <div class="page-head"><h1>{cfg['label']} accuracy history</h1><p>How each team's chance of winning each market changed through past seasons, rebuilt for every week of the season. Pick a season, a market and a week to see where the model stood, how much it had moved, and how things ended.</p></div>
  <div id="replay" data-src="data/replay.json"><p class="note">Loading…</p></div>
</main>
<footer class="stamp">Seasons marked (live) are the numbers this site actually published. Earlier seasons are replayed from game results using only information available at each date, without injuries or roster moves, so they are not what the site showed at the time. Probabilities and history only, not betting advice.</footer>
</div>
<link rel="stylesheet" href="replay.css">
<script src="replay.js"></script>
</body></html>"""
        open(os.path.join(d, "replay.html"), "w", encoding="utf-8").write(top + body)
        for f in ("replay.js", "replay.css"):
            shutil.copy(os.path.join(SRC, f), os.path.join(d, f))
        print("replay page", sport, flush=True)


if __name__ == "__main__":
    import sys
    build_site(sys.argv[sys.argv.index("--live") + 1] if "--live" in sys.argv else None)
