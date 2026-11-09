"""Job 2 of research/NEWS_IN_FUTURES_RULE.md: score the futures news/injury shadows.
Usage: python research/score_news_shadow.py <shadow.jsonl> [outcomes.json]
Without outcomes: weekly AUDIT only (descriptive, no decision): snapshots, per-snapshot max and mean |p_playoff with - without|,
mean |mean_wins with - without|, teams moved by >= 5 points of playoff chance.
With outcomes ({"playoff": [teams], "wins": {team: wins}}): the season-end decision statistic, read once at the last snapshot
before the playoffs: paired Brier (with - without) for playoff qualification and win-total MAE difference, bootstrap over
teams (10,000 draws, seed 20261108). Pass needs the 90% upper bound <= 0 and a negative point estimate (with better).
Power (stated on every report): one season, 30 teams, detects about 0.02 Brier; the plausible effect is under 0.005."""
import json, sys
import numpy as np
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print(f"snapshots {len(rows)}  first {rows[0]['t']}  last {rows[-1]['t']}")
mx, mn, mw, big = [], [], [], 0
for r in rows:
    d = [abs(r["with"][t]["p_playoff"] - r["without"][t]["p_playoff"]) for t in r["without"] if t in r["with"]]
    w = [abs(r["with"][t]["mean_wins"] - r["without"][t]["mean_wins"]) for t in r["without"] if t in r["with"]]
    mx.append(max(d)); mn.append(np.mean(d)); mw.append(np.mean(w)); big += sum(x >= 0.05 for x in d)
print(f"max |dp_playoff| per snapshot: median {np.median(mx):.3f}, largest {max(mx):.3f}; mean |dp_playoff| {np.mean(mn):.4f}; mean |d wins| {np.mean(mw):.2f}; team-snapshots moved >= 5 pts: {big}")
last = rows[-1]
top = sorted(last["without"], key=lambda t: -abs(last["with"][t]["p_playoff"] - last["without"][t]["p_playoff"]))[:5]
print("latest snapshot, biggest moves:", ", ".join(f"{t} {last['without'][t]['p_playoff']:.2f}->{last['with'][t]['p_playoff']:.2f} ({last['without'][t]['mean_wins']:.1f}->{last['with'][t]['mean_wins']:.1f} wins)" for t in top))
if len(sys.argv) > 2:
    o = json.load(open(sys.argv[2])); teams = sorted(last["without"])
    y = np.array([t in o["playoff"] for t in teams], float)
    pw = np.array([last["with"][t]["p_playoff"] for t in teams]); pn = np.array([last["without"][t]["p_playoff"] for t in teams])
    db = (pw - y) ** 2 - (pn - y) ** 2
    ww = np.array([abs(last["with"][t]["mean_wins"] - o["wins"][t]) for t in teams]); wn = np.array([abs(last["without"][t]["mean_wins"] - o["wins"][t]) for t in teams])
    dm = ww - wn
    rng = np.random.default_rng(20261108); W = rng.exponential(1.0, (10000, len(teams))); W /= W.sum(1, keepdims=True)
    for name, d in (("playoff Brier", db), ("win-total MAE", dm)):
        b = W @ d
        print(f"{name}: with - without {d.mean():+.4f}  90% [{np.percentile(b, 5):+.4f}, {np.percentile(b, 95):+.4f}]  pass: {np.percentile(b, 95) <= 0 and d.mean() < 0}")
print("Power: one season (30 team-seasons) detects about 0.02 Brier; the plausible effect is under 0.005; one season cannot decide.")
