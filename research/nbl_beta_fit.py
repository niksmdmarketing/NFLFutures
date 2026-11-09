"""research/nbl_beta_fit.py (DeepSeek relay 036, corrected by Claude: finals filter inverted, keyword field, values input) — walk-forward refit of BETA for the NBL news shadow.
Reads build/nbl_stats_index.json only; no prices, no futures.

Sign convention. News layer adds to mu = home - away:
    delta_team = -sum_p v_p * (P(out)_p - baseline_p)         (more absences => lower mu)
Fit:
    residual = actual_margin - (SRS_home - SRS_away + HCA)
    x        = sum_{home books} v_p*(I_abs - base_p)
             - sum_{away books} v_p*(I_abs - base_p)
    residual = -beta * x + e     =>   beta = -sum(x*r) / sum(x^2)
beta > 0  : news layer's direction is right; magnitude is the fit.
beta <= 0 : inversion or no signal; recorded raw, never clipped to positive silently.
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import nbl_site as NS
import nbl_news as NN

IDX = os.environ.get("NBL_STATS_INDEX", "build/nbl_stats_index.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nbl_beta_fit_results.json")

def _pick(d, names, default=None):
    for n in names:
        try: v = d.get(n)
        except Exception: v = None
        if v not in (None, ""): return v
    return default

def _key(name):
    for attr in ("key", "_key"):
        f = getattr(NN, attr, None)
        if f: return f(name)
    return "".join(c for c in str(name).lower() if c.isalnum())

def _values_prior(seasons, y, verbose=False):
    """beta=1 values from leaders of y-1 and y-2 only. No leak."""
    # Claude: nbl_news.values takes {int year: [regular-season leaders rows]}
    src = {int(yy): [p for p in (seasons[yy].get("leaders") or []) if NS.is_reg(p)] for yy in (str(y - 1), str(y - 2)) if yy in seasons}
    if not src: return {}
    f = getattr(NN, "values", None) or getattr(NN, "nbl_values", None)
    if f is None: raise SystemExit("nbl_news.values not found")
    v = f(src, y, beta=1.0)
    if verbose: print(f"  values(y={y}): {len(v)} roster rows from {sorted(src)}")
    return v

def _regular(gx):
    try:
        m = gx.apply(NS.is_reg, axis=1)
        if getattr(m, "dtype", None) == bool and m.any(): return gx[np.asarray(m, bool)]
    except Exception: pass
    if "phase" in gx.columns:
        m = ~gx["phase"].astype(str).str.lower().str.contains(
            "final|playoff|post|semi|pre", regex=True)
        if m.any(): return gx[np.asarray(m, bool)]
    return gx

def _appearances(rows, show=True):
    if rows and show:
        print("[keys] boxscore:", sorted(rows[0].keys()))
        print("[keys] player:", sorted((rows[0].get("player") or {}).keys()))
        print("[keys] _game:", sorted((rows[0].get("_game") or {}).keys()))
    out = {}
    for r in rows:
        g = r.get("_game") or {}
        gid = _pick(g, ["id", "game_id"]) or _pick(r, ["game_id", "gid"])
        if gid is None: continue
        code = _pick(r.get("team") or {}, ["team_code", "code"])
        tm = NS.code(code) if code else ""
        pl = r.get("player") or {}
        nm = (f"{_pick(pl,['first_name','firstName'],'')} "
              f"{_pick(pl,['last_name','lastName','surname'],'')}").strip()
        pk = _key(_pick(r, ["player_key"], "") or nm)
        m = _pick(r, ["minutes", "minutes_played", "mins", "min"], None)
        try: m = float(m) if m not in (None, "") else 1.0
        except Exception: m = 1.0
        if not tm or not pk or m <= 0: continue
        out.setdefault(str(gid), set()).add((tm, pk))
    return out

def _rating_game(prev_gx, prior):
    """SRS on the season's earlier games. Returns None if too few or failure."""
    if len(prev_gx) < 5: return None
    try: return NS.srs(NS.team_rows(prev_gx), prior=prior)
    except Exception: return None

def _prior(y, seasons, verbose=False):
    yy = str(y - 1)
    if yy not in seasons: return None
    try:
        px, _, _ = NS.season_games(seasons[yy])
        px = _regular(px)
        s = NS.srs(NS.team_rows(px))
        out = {t: NS.PRIOR_REG * v for t, v in s.items()}
        if verbose: print(f"  prior({y-1}): {len(out)} teams")
        return out
    except Exception as e:
        if verbose: print(f"  prior({y-1}) failed: {e!r}")
        return None

def _season_matrix(y, seasons, verbose=False):
    """One row per regular game with boxscores: residual, x, home, away, gid."""
    Sd = seasons[str(y)]
    gx, _, _ = NS.season_games(Sd)
    if "fin" in gx.columns:   # Claude: fin flags FINALS; DeepSeek kept only finals here
        gx = gx[~gx["fin"].astype(bool)]
    away_pts = gx["as"].to_numpy(float)   # Claude: 'as' is a Python keyword; read it by position (team_rows needs the column name)
    gx = _regular(gx).sort_values("date").reset_index(drop=True)
    ap = _appearances(Sd.get("boxscores") or [], show=verbose)
    if not ap:
        if verbose: print(f"  {y}: no boxscores"); return None
    vals = _values_prior(seasons, y, verbose=verbose)
    if not vals:
        if verbose: print(f"  {y}: no prior leaders"); return None
    team_val = {}
    for (tm, pk), v in vals.items():
        team_val.setdefault(str(tm), {})[pk] = float(v.get("value") or 0.0)
    # match coverage diagnostic
    known = {pk for tk in team_val.values() for pk in tk}
    seen = {pk for st in ap.values() for (_, pk) in st}
    share = len(seen & known) / max(len(seen), 1)
    prior = _prior(y, seasons, verbose=verbose)
    order = {}                                # per-team chronological gids
    for r in gx.itertuples(index=False):
        order.setdefault(str(r.h), []).append(str(r.gid))
        order.setdefault(str(r.a), []).append(str(r.gid))
    played = {}                               # (team, pk) -> set of gids
    for gid, st in ap.items():
        for tm, pk in st: played.setdefault((tm, pk), set()).add(gid)
    pos = {str(r.gid): i for i, r in enumerate(gx.itertuples(index=False))}
    rows = []
    for r in gx.itertuples(index=False):
        gid, h, a = str(r.gid), str(r.h), str(r.a)
        i = pos[gid]
        if gid not in ap or i < 5: continue
        rat = _rating_game(gx.iloc[:i], prior)
        if not rat or h not in rat or a not in rat: continue
        x = 0.0
        for tm, sign in ((h, 1.0), (a, -1.0)):
            prev = set(order[tm][:order[tm].index(gid)])
            if not prev: continue
            here = {pk for (t, pk) in ap[gid] if t == tm}
            # players still on this team's books (last appearance for tm, not moved)
            for pk, v in team_val.get(tm, {}).items():
                if v <= 0: continue
                pg = played.get((tm, pk), set())
                on_books = pg & prev
                if not on_books: continue
                base = 1.0 - len(on_books) / len(prev)
                absent = 0.0 if pk in here else 1.0
                x += sign * v * (absent - base)
        resid = (float(r.hs) - float(away_pts[i])) - (rat[h] - rat[a] + NS.HCA)
        rows.append({"gid": gid, "h": h, "a": a, "r": resid, "x": x})
    if verbose and rows:
        xs = np.array([w["x"] for w in rows])
        print(f"  {y}: n_games {len(gx)}, used {len(rows)}, "
              f"value match {share:.1%}, x sd {xs.std():.3f}, "
              f"|x|>0 {float((np.abs(xs) > 1e-9).mean()):.1%}")
    return {"rows": rows, "share": share, "n_games": len(gx)} if rows else None

def _fit(rows_list):
    R = np.array([[r["r"], r["x"]] for r in rows_list], float)
    if len(R) < 30: return None
    x, r = R[:, 1], R[:, 0]
    sxx = float(x @ x)
    if sxx < 1e-12: return None
    beta = -float(x @ r) / sxx
    e = r + beta * x
    s2 = float(e @ e) / max(len(r) - 1, 1)
    se = float(np.sqrt(s2 / sxx))
    return {"beta": beta, "se": se, "n": int(len(r)),
            "rmse_with": float(np.sqrt(np.mean(e ** 2))),
            "rmse_without": float(np.sqrt(np.mean(r ** 2))),
            "x_sd": float(x.std()),
            "x_nonzero": float((np.abs(x) > 1e-9).mean())}

def main():
    D = json.load(open(IDX))
    seasons = D["seasons"]
    ys = sorted(int(k) for k in seasons)
    blocks = {}
    for y in ys:
        if not seasons[str(y)].get("boxscores"): continue
        blk = _season_matrix(y, seasons, verbose=True)
        if blk: blocks[y] = blk["rows"]
    if not blocks:
        print("no seasons with boxscores + leaders; nothing to fit"); return

    res = {"seasons": {}, "note": ("walk-forward beta refit for NBL news shadow; "
           "sign convention: residual = -beta*x; values from y-1/y-2 leaders; "
           "baseline from season boxscores; no leak; 5 boxscore seasons is a hard power limit"),
           "sign_check": "beta<=0 means inversion or no signal, recorded raw"}
    ys2 = sorted(blocks)
    pooled = []
    for y in ys2:
        past = [r for k in ys2 if k < y for r in blocks[k]]
        if not past:
            res["seasons"][str(y)] = {"fit": None, "n": len(blocks[y])}
            print(f"{y}: no past seasons, skipped as fit point"); continue
        f = _fit(past)
        if f is None:
            print(f"{y}: too few past rows"); continue
        x = np.array([r["x"] for r in blocks[y]], float)
        r = np.array([r["r"] for r in blocks[y]], float)
        e = r + f["beta"] * x
        row = {"fit": f, "oos": {"n": int(len(r)),
                  "x_sd": float(x.std()),
                  "rmse_with": float(np.sqrt(np.mean(e ** 2))),
                  "rmse_without": float(np.sqrt(np.mean(r ** 2)))},
               "oos_gain": float(np.mean(r ** 2) - np.mean(e ** 2))}
        res["seasons"][str(y)] = row
        pooled.append(blocks[y])
        print(f"{y}: fit beta {f['beta']:+.3f} (se {f['se']:.3f}, n {f['n']}), "
              f"oos gain {row['oos_gain']:+.5f} (x sd {x.std():.3f})")
    allrows = [r for k in ys2 for r in blocks[k]]
    full = _fit(allrows)
    res["final"] = dict(full or {}, seasons=ys2)
    if full:
        res["final"]["beta_recommended"] = full["beta"]
        res["final"]["sign_ok"] = bool(full["beta"] > 0)
    json.dump(res, open(OUT, "w"), indent=1)
    print("\nFINAL", json.dumps({k: v for k, v in res["final"].items() if k != "seasons"}))
    if full:
        print(f"Recommended BETA for the shadow: {full['beta']:+.3f} "
              f"(do NOT clip to positive without a sign check)")

if __name__ == "__main__":
    main()
