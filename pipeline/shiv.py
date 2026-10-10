"""Shiv Value Models: three separate approaches to US-sports futures, side by side, with their track records.

  1. Our model  - the independent stats model shown on each sport's Futures page (never sees prices; NFL v4 frozen).
  2. Market     - Polymarket's prices (best bid / best ask midpoint), margin removed within one-winner markets.
  3. Shiv       - an experimental 50/50 combination of the two (geometric mean, renormalised; for yes/no markets the
                  average in log-odds). It is a separately scored challenger, not a replacement for our model.

Every refresh also writes one archive record (all three numbers plus the raw quote: bid, ask, last trade, spread,
liquidity, fee schedule, timestamp) which the workflow appends to the append-only `shiv-archive` branch. Resolved markets
are scored from that archive, so the forward scoreboard uses only forecasts made before the outcome was known.
No value or edge labels: a big disagreement means "check the news", and the price you can actually get (ask + fees) is
not the same as the displayed probability. Polymarket is a prediction market, not a bookmaker, and is not legal to use
from Australia; it is used here as a public benchmark only.
"""
import datetime as dt
import glob
import gzip
import json
import math
import os
import re
import shutil
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(SITE, "shiv")
SRC = os.path.join(ROOT, "site_src", "shiv")
G = "https://gamma-api.polymarket.com"
CONFIG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shiv_markets.json")))
ARCHIVE = os.environ.get("SHIV_ARCHIVE")          # checked-out shiv-archive branch (CI); None locally


def log(*a):
    print("[shiv]", *a, flush=True)


def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SportsFuturesResearch/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1 + i)
    log("fetch failed", url[:100], err)
    return None


# ------------------------------------------------------------------ teams

def team_names():
    import nba
    from common import NAMES as NFL
    nhl = {}
    p = os.path.join(SITE, "nhl", "data", "futures.json")
    if os.path.exists(p):
        nhl = {t["team"]: t["name"] for t in json.load(open(p))["teams"]}
    return {"nfl": dict(NFL), "nba": dict(nba.NAMES), "nhl": nhl}


ALIAS = {"nhl": {"UTA": ["Utah Hockey Club", "Utah HC", "Mammoth"]}}


def team_of(names, sport, text):
    text = (text or "").lower()
    hits = []
    for code, full in names[sport].items():
        cands = [full, full.split()[-1]] + ALIAS.get(sport, {}).get(code, [])
        if full.split()[-1] in ("Jackets", "Wings", "Leafs", "Knights", "Blazers"):
            cands.append(" ".join(full.split()[-2:]))
        for c in cands:
            if c.lower() in text:
                hits.append((len(c), code))
    return max(hits)[1] if hits else None


# ------------------------------------------------------------------ inputs

def model_probs(sport, field):
    path = {"nfl": "data/futures.json", "nba": "nba/data/futures.json", "nhl": "nhl/data/futures.json"}[sport]
    j = json.load(open(os.path.join(SITE, path)))
    T = j["teams"]
    rows = T.items() if isinstance(T, dict) else ((t["team"], t) for t in T)
    return {k: v.get(field) for k, v in rows}, j.get("updated_utc") or j.get("season")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def quotes(names, sport, slug):
    """team -> quote dict for one Polymarket event, plus event metadata."""
    d = get(f"{G}/events/slug/{slug}")
    if not isinstance(d, dict):
        return None, {}
    out = {}
    for m in d.get("markets") or []:
        t = team_of(names, sport, (m.get("groupItemTitle") or "") + " " + (m.get("question") or ""))
        if not t:
            continue
        prices = json.loads(m.get("outcomePrices") or "[]")
        bid, ask, last = num(m.get("bestBid")), num(m.get("bestAsk")), num(m.get("lastTradePrice"))
        mid = (bid + ask) / 2 if bid is not None and ask is not None and ask > 0 else num(prices[0]) if prices else None
        out[t] = dict(bid=bid, ask=ask, last=last, mid=mid, spread=num(m.get("spread")), liquidity=num(m.get("liquidityNum")),
                      volume=num(m.get("volumeNum")), closed=bool(m.get("closed")), settled=num(prices[0]) if m.get("closed") and prices else None,
                      fee=m.get("feeSchedule") if m.get("feesEnabled") else None, market_id=m.get("id"))
    meta = dict(title=(d.get("title") or "").strip(), closed=bool(d.get("closed")), end=d.get("endDate"), negRisk=bool(d.get("negRisk")),
                rules=(d.get("description") or "")[:600])
    return out, meta


# ------------------------------------------------------------------ combination

def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def combine(model, market, one_winner):
    """model, market: team -> probability (same teams). Returns (market_fair, model_view, shiv)."""
    teams = [t for t in market if market[t] is not None and model.get(t) is not None]
    if one_winner:
        mk = {t: max(market[t], 1e-4) for t in teams}
        s = sum(mk.values())
        mk = {t: v / s for t, v in mk.items()}
        mo = {t: max(model[t], 1e-4) for t in teams}
        s = sum(mo.values())
        mo = {t: v / s for t, v in mo.items()}
        sh = {t: math.sqrt(mk[t] * mo[t]) for t in teams}
        s = sum(sh.values())
        return mk, mo, {t: v / s for t, v in sh.items()}
    mk = {t: market[t] for t in teams}
    mo = {t: model[t] for t in teams}
    return mk, mo, {t: 1 / (1 + math.exp(-(logit(mk[t]) + logit(mo[t])) / 2)) for t in teams}


# ------------------------------------------------------------------ forward scoring from the archive

def forward_scores(resolved):
    """resolved: slug -> {team: 1/0}. Scores every archived forecast made before settlement (last record per day)."""
    if not ARCHIVE or not os.path.isdir(ARCHIVE):
        return {}
    per_day = {}
    for f in sorted(glob.glob(os.path.join(ARCHIVE, "records", "*", "*.json.gz"))):
        rec = json.load(gzip.open(f))
        day = rec["taken_utc"][:10]
        for m in rec["markets"]:
            if m["slug"] in resolved:
                per_day[(m["slug"], day)] = (rec["sport"] if "sport" in rec else m["sport"], m)
    res = {}
    for (slug, day), (sport, m) in per_day.items():
        won = resolved[slug]
        S = res.setdefault(sport, {}).setdefault(m["label"], {"model": [], "market": [], "shiv": [], "forecasts": 0})
        rows = {r["team"]: r for r in m["rows"]}
        if m["one_winner"]:
            w = [t for t, v in won.items() if v == 1]
            if len(w) != 1 or w[0] not in rows:
                continue
            for k in ("model", "market", "shiv"):
                S[k].append(-math.log(max(rows[w[0]][k], 1e-4)))
        else:
            for t, r in rows.items():
                if t in won:
                    for k in ("model", "market", "shiv"):
                        S[k].append((r[k] - won[t]) ** 2)
        S["forecasts"] += 1
    out = {}
    for sport, D in res.items():
        for label, S in D.items():
            out.setdefault(sport, {})[label] = {k: round(sum(v) / len(v), 4) if v else None for k, v in S.items() if k != "forecasts"} | {"forecasts": S["forecasts"]}
    return out


# ------------------------------------------------------------------ build

def build_data():
    names = team_names()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    live = {"updated_utc": now, "sports": {}}
    record = {"taken_utc": now, "source": "polymarket (prediction market)", "markets": []}
    resolved = {}
    for sport, markets in CONFIG["markets"].items():
        sp = live["sports"].setdefault(sport, {"markets": [], "model_updated": None})
        for mk in markets:
            try:
                model, upd = model_probs(sport, mk["field"])
            except Exception as e:  # noqa: BLE001
                log(sport, "model file missing", e)
                continue
            sp["model_updated"] = upd
            q, meta = quotes(names, sport, mk["slug"])
            if not q:
                continue
            if meta.get("closed") or all(v["closed"] for v in q.values()):
                resolved[mk["slug"]] = {t: 1 if (v["settled"] or 0) > 0.5 else 0 for t, v in q.items()}
                continue
            market = {t: v["mid"] for t, v in q.items()}
            fair, mview, shiv = combine(model, market, mk["one_winner"])
            rows = [dict(team=t, name=names[sport].get(t, t), model=round(mview[t], 4), market=round(fair[t], 4), shiv=round(shiv[t], 4),
                         bid=q[t]["bid"], ask=q[t]["ask"], last=q[t]["last"], mid=q[t]["mid"], spread=q[t]["spread"],
                         liquidity=q[t]["liquidity"]) for t in fair]
            rows.sort(key=lambda r: -r["market"])
            fee = next((v["fee"] for v in q.values() if v["fee"]), None)
            entry = dict(label=mk["label"], group=mk.get("group", mk["label"]), slug=mk["slug"], event=meta["title"], one_winner=mk["one_winner"],
                         rules=meta["rules"], fee=fee, rows=rows)
            sp["markets"].append(entry)
            record["markets"].append(dict(entry, sport=sport, rules=None, raw={t: q[t] for t in fair}))
        log(sport, len(sp["markets"]), "markets")
    # markets that were archived earlier and have since settled
    if ARCHIVE and os.path.isdir(ARCHIVE):
        seen = set()
        for f in glob.glob(os.path.join(ARCHIVE, "records", "*", "*.json.gz"))[-400:]:
            for m in json.load(gzip.open(f))["markets"]:
                seen.add((m["sport"], m["slug"]))
        for sport, slug in seen - {(s, m["slug"]) for s, ms in CONFIG["markets"].items() for m in ms if m["slug"] not in resolved}:
            if slug in resolved:
                continue
            q, meta = quotes(names, sport, slug)
            if q and (meta.get("closed") or all(v["closed"] for v in q.values())):
                resolved[slug] = {t: 1 if (v["settled"] or 0) > 0.5 else 0 for t, v in q.items()}
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    bt = os.path.join(ROOT, "model", "market_benchmark.json")
    live["backtest"] = json.load(open(bt)) if os.path.exists(bt) else None
    live["forward"] = forward_scores(resolved)
    live["config_season"] = CONFIG.get("season_note")
    json.dump(live, open(os.path.join(OUT, "data", "live.json"), "w"), separators=(",", ":"))
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with gzip.open(os.path.join(ROOT, "build", "shiv_record.json.gz"), "wt") as f:
        json.dump(record, f, separators=(",", ":"))
    log("live data written;", sum(len(s["markets"]) for s in live["sports"].values()), "markets; resolved", len(resolved))


def _sportbar_link(html, rel):
    if 'class="sb-shiv"' in html:
        return html
    return re.sub(r'(<div class="sportbar">.*?)(</div>)', lambda m: m.group(1) + f'<a class="sb-shiv" href="{rel}shiv/">Shiv</a>' + m.group(2),
                  html, count=1, flags=re.S)


def build_site():
    if not os.path.exists(os.path.join(OUT, "data", "live.json")):
        return
    for f in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True):
        rel = os.path.relpath(SITE, os.path.dirname(f)).replace(os.sep, "/")
        rel = "" if rel == "." else rel + "/"
        if os.path.dirname(f) == OUT:
            continue
        s = open(f, encoding="utf-8").read()
        s2 = _sportbar_link(s, rel)
        if s2 != s:
            open(f, "w", encoding="utf-8").write(s2)
    for fn in ("index.html", "shiv.js", "shiv.css"):
        shutil.copy(os.path.join(SRC, fn), os.path.join(OUT, fn))
    log("page written")


if __name__ == "__main__":
    build_data()
    build_site()
