"""Weekly point-in-time replay of the NHL futures model (research / archive builder).

Same settings as nhl_model.backtest (params_before: earlier seasons only), but a checkpoint every 7 days from the season
start, one league-wide date per checkpoint, regulation wins counted from the opponent's OTL. No injuries (not in the model).
Outputs model/replay/nhl_<season>.csv: season, week, date, gp_avg, team, p_playoff, p_div, p_pres, p_r2, p_r3, p_conf
(= wins the conference, reaches the Final), p_title, then 0/1 outcomes y_playoff, y_div, y_pres, y_conf, y_title, y_r2 (won a round), y_r3 (reached the conference final).
'p_conf' is mapped to the replay score's 'finals' market (y_finals = y_conf).
Usage: python research/replay_nhl.py <published nhl/data dir> [first] [last]    (env BT_SIMS, default 2000)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import nhl  # noqa: E402
import nhl_model as M  # noqa: E402
import nhl_absence  # noqa: E402
import nhl_lineup  # noqa: E402

nhl.NHL_OUT = M.nhl.NHL_OUT = sys.argv[1]
SIMS = int(os.environ.get("BT_SIMS", "2000"))
# Research knobs: NHL_TAU_PRE (preseason widening), NHL_PRIOR_SCALE (stretch preseason prior), NHL_PO_SCALE (playoff gaps).
if os.environ.get("NHL_TAU_PRE"):
    M.TAU_PRE = float(os.environ["NHL_TAU_PRE"])
def _git_commit():
    import subprocess
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return "unknown"


PRIOR_SCALE = float(os.environ.get("NHL_PRIOR_SCALE", "1"))
PO_SCALE = float(os.environ.get("NHL_PO_SCALE", "1"))
SERIES_LOG = os.environ.get("NHL_SERIES_LOG") == "1"   # research/NHL_SERIES_CALIBRATION_RULE.md: log P(home-ice team wins | meet) for realised series
SERIES_ROWS = []
PO_GAP_ONLY = os.environ.get("NHL_PO_GAP_ONLY") == "1"   # research/NHL_PO_SCALE_RULE.md: po_scale on the rating gap only, not the tau draw
PO_FADE = float(os.environ.get("NHL_PO_FADE", "0"))   # extra playoff-gap multiplier at season start, fading to 0 by game 82
SHOT_W = float(os.environ.get("NHL_SHOT_W", "0"))
SHOT_PO = os.environ.get("NHL_SHOT_PO") == "1"   # use the shot-blended rate only in playoff series (regular season on goals)   # share of the in-season rate from shot differential (x league shooting %)
RS_SHOT_W = float(os.environ.get("NHL_RS_SHOT_W", "0"))   # with NHL_SHOT_PO: shot share in the regular-season rating
# NHL_RS_XG=raw|adj (with NHL_SHOT_PO and NHL_RS_SHOT_W): the regular-season share uses MoneyPuck game xG differential, as live
# (nhl_model.XG_SHARE on the team table's MoneyPuck xG), while the playoff rating keeps shots x league shooting %, as live.
RS_XG = os.environ.get("NHL_RS_XG", "")
LINEUP_C = float(os.environ.get("NHL_LINEUP_C", "0"))     # roster term from lineups (pipeline/nhl_lineup.py), x this
LINEUP_N = int(os.environ.get("NHL_LINEUP_N", "5"))
LINEUP_PRE = os.environ.get("NHL_LINEUP_PRE", "1") == "1"   # include roster change vs last season (prior part)
LINEUP_MIN = int(os.environ.get("NHL_LINEUP_MIN", "0"))     # games played before the term applies
PO_PRIOR_K = float(os.environ.get("NHL_PO_PRIOR_K", "0"))   # playoff-only last-season playoff GD, K pseudo-games (0 = off)
XG = os.environ.get("NHL_XG", "")   # "" = shots x league shooting % as the xG stand-in; raw | adj = MoneyPuck game xG
MP_ALIAS = {"L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL"}
_MP = None


def mp_xg(y):
    """MoneyPuck regular-season game xG differential by (date, team) for season y."""
    global _MP
    if _MP is None:
        d = pd.read_csv(os.path.join(ROOT, "data", "research", "mp", "team_games.csv.gz"))
        d = d[d.gameId.astype(str).str[4:6] == "02"].copy()
        d["team"] = d.team.replace(MP_ALIAS)
        d["date"] = pd.to_datetime(d.gameDate.astype(str), format="%Y%m%d")
        pre = "scoreVenueAdjustedxGoals" if XG == "adj" else "xGoals"
        d["xgd"] = d[pre + "For"] - d[pre + "Against"]
        _MP = d
    x = _MP[_MP.season == y]
    return x.set_index(["date", "team"]).xgd


_MPK = {}


def mp_xg_kind(y, kind):
    """As mp_xg, but for an explicit kind (raw | adj), independent of NHL_XG (used by NHL_RS_XG)."""
    if kind not in _MPK:
        d = pd.read_csv(os.path.join(ROOT, "data", "research", "mp", "team_games.csv.gz"))
        d = d[(d.gameId.astype(str).str[4:6] == "02") & (d.situation == "all")].copy()
        d["team"] = d.team.replace(MP_ALIAS)
        d["date"] = pd.to_datetime(d.gameDate.astype(str), format="%Y%m%d")
        pre = "scoreVenueAdjustedxGoals" if kind == "adj" else "xGoals"
        d["xgd"] = d[pre + "For"] - d[pre + "Against"]
        _MPK[kind] = d
    x = _MPK[kind][_MPK[kind].season == y]
    s = x.set_index(["date", "team"]).xgd
    return s[~s.index.duplicated()]


UPD_EVERY = int(os.environ.get("NHL_UPD_EVERY", "0"))   # refit player ratings with this season's games every N weeks
UPD_W = float(os.environ.get("NHL_UPD_W", "1"))
UPD_MIX = float(os.environ.get("NHL_UPD_MIX", "0"))      # blend team rating toward current-lineup player strength
PS_B = float(os.environ.get("NHL_PS_B", "0.4"))          # player strength -> goals per game (preseason fit about 0.35-0.5)
PS = os.environ.get("NHL_PS") == "1"          # preseason prior blended with player-based strength (research/nhl_rapm.py)
K_MULT = float(os.environ.get("NHL_K_MULT", "1"))
_PS = {}


def ps_table(TT, GG, fit_years, done):
    """season, team, prior, ps, gd for every season with shift data (point-in-time ratings)."""
    if "D" in _PS:
        return _PS["D"]
    sys.path.insert(0, os.path.join(ROOT, "research"))
    import nhl_player_strength_test as PST
    import nhl_rapm as RP
    rows = []
    for y in done:
        if RP.load(y - 1) is None:
            continue
        beta = M.fit_prior(TT, [z for z in fit_years if z < y])[0]
        teams = sorted(TT[y].index)
        prior = pd.Series(M.prior_features(y, TT).reindex(teams).fillna(0).values @ beta, index=teams)
        ps, _ = PST.opening_strength(y, teams)
        g = GG[y]
        gd = ((M.numcol(g, "goalsFor") - M.numcol(g, "goalsAgainst")).groupby(g.team).mean()).reindex(teams)
        for t in teams:
            rows.append(dict(season=y, team=t, gd=gd[t] - gd.mean(), prior=prior[t] - prior.mean(), ps=ps[t] - ps.mean()))
    _PS["D"] = pd.DataFrame(rows)
    return _PS["D"]


def ps_prior(TT, GG, fit_years, done, y, prior):
    D = ps_table(TT, GG, fit_years, done)
    tr = D[D.season < y]
    te = D[D.season == y].set_index("team")
    if tr.season.nunique() < 2 or te.empty:
        return prior
    X = np.c_[np.ones(len(tr)), tr.prior, tr.ps]
    b = np.linalg.lstsq(X, tr.gd, rcond=None)[0]
    sh = float(os.environ.get("NHL_PS_SHRINK", "1"))
    b1 = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr.prior], tr.gd, rcond=None)[0][1]
    new = (sh * b[1] + (1 - sh) * b1) * prior + sh * b[2] * te.ps.reindex(prior.index).fillna(0)
    print(y, "prior blend b_prior %.3f b_players %.3f" % (b[1], b[2]), flush=True)
    return new - new.mean()


LINEUP_DIR = os.path.join(ROOT, "data", "research", "nhl_lineups")
OT_FIX = os.environ.get("NHL_OT_FIX") == "1"            # research/NHL_OT_RATE_RULE.md
OT_EDGE = float(os.environ.get("NHL_OT_EDGE", "0.5"))   # OT winner edge with the fix (sensitivity: 1.0, 0.25)


def ot_share(GG, years):
    """Share of games that went to OT/shootout in the given seasons (OTL results / games)."""
    n = o = 0
    for z in years:
        g = GG.get(z)
        if g is None or g.empty:
            continue
        n += len(g) / 2
        o += int((g.res == "OTL").sum())
    return o / n if n else None


G_UPD = float(os.environ.get("NHL_G_UPD", "0"))   # in-season goalie values, prior weight in hours (research/NHL_GOALIE_INSEASON_RULE.md)


def goalie_games(G):
    """Per-game goalie rows with goals saved above expected (team MoneyPuck xGA x his share of goalie ice time - goals allowed)."""
    mp = pd.read_csv(os.path.join(ROOT, "data", "research", "mp", "team_games.csv.gz"))
    mp = mp[mp.situation == "all"].copy()
    mp["team"] = mp.team.replace(MP_ALIAS)
    xga = mp.set_index(["gameId", "team"]).xGoalsAgainst
    xga = xga[~xga.index.duplicated()]
    g = G.copy()
    g["toi"] = pd.to_numeric(g.toi, errors="coerce").fillna(0.0)
    tot = g.groupby(["game_id", "team"]).toi.transform("sum")
    g["xga"] = [xga.get((gid, t), np.nan) for gid, t in zip(g.game_id, g.team)]
    g["xga"] = g.xga * g.toi / tot.where(tot > 0, 1.0)
    g["gsax"] = g.xga - pd.to_numeric(g.ga, errors="coerce")
    g["h"] = g.toi / 3600.0
    g["key"] = g.name.astype(str).str.strip().str.lower() + "|G"
    g["date"] = pd.to_datetime(g.date)
    return g.dropna(subset=["gsax"])


def goalie_values_at(val, gg, cut):
    """Start-of-season values with every goalie updated by this season's games before `cut`."""
    pl = gg[gg.date < cut]
    if not len(pl):
        return val
    a = pl.groupby("key").agg(h=("h", "sum"), gs=("gsax", "sum"))
    a = a[a.h > 0]
    r = a.gs / a.h
    v0 = val.reindex(a.index).fillna(0.0)
    new = (G_UPD * v0 + a.h * r) / (G_UPD + a.h)
    out = val.copy()
    out = out.reindex(out.index.union(new.index)).fillna(0.0)
    out.loc[new.index] = new
    return out
OUT = os.environ.get("BT_OUTDIR") or os.path.join(ROOT, "model", "replay")


def alignment(y, teams):
    """Divisions as they stood in season y (start year). 2013-16: 30 teams; 2017-18: 31 teams (VGK). 2021+: the current map."""
    if y >= 2021:
        return {t: M.ALIGN[t] for t in teams}
    if y > 2018 or y < 2014:
        return None
    a = {t: M.ALIGN[t] for t in teams if t in M.ALIGN}
    a["ARI"] = "Pacific"
    a["WPG"] = "Central"
    return a if all(t in a for t in teams) else None


def playoff_outcomes(y, teams):
    path = os.path.join(sys.argv[1], f"games_{y}p.json")
    if not os.path.exists(path):
        return None
    pg = M.read_games(f"{y}p")
    if pg.empty:
        return None
    pg = pg.copy()
    pg["date"] = pd.to_datetime(pg.date)
    last = pg[pg.date == pg.date.max()]
    final_pair = set(last.team) | set(last.opp)
    fin = pg[pg.team.isin(final_pair) & pg.opp.isin(final_pair)]
    wins = fin[fin.res == "W"].groupby("team").size()
    rounds = pg.groupby("team").opp.nunique()          # series played: 2+ = won the first round, 3+ = reached the conference final
    return {"po": set(pg.team), "finalists": final_pair, "champ": wins.idxmax(),
            "r2": set(rounds[rounds >= 2].index), "r3": set(rounds[rounds >= 3].index)}


def realised_series(y):
    """Realised playoff series from games_<y>p.json: home-ice team (hosts the first game), opponent, round, winner."""
    pg = M.read_games(f"{y}p")
    if pg.empty:
        return []
    pg = pg.copy(); pg["date"] = pd.to_datetime(pg.date)
    ser = {}
    for _, r in pg.sort_values("date", kind="stable").iterrows():
        key = frozenset((r.team, r.opp))
        e = ser.setdefault(key, {"first": r.date, "home": None, "wins": {}})
        if e["home"] is None and r.ha == "H":
            e["home"] = r.team
        if r.res == "W":
            e["wins"][r.team] = e["wins"].get(r.team, 0) + 1
    out, played = [], {}
    for key, e in sorted(ser.items(), key=lambda kv: (kv[1]["first"], sorted(kv[0]))):
        a, b = sorted(key)
        home = e["home"] or a
        away = b if home == a else a
        rnd = 1 + max(played.get(a, 0), played.get(b, 0))
        win = max(e["wins"], key=e["wins"].get) if e["wins"] else None
        for t in (a, b):
            played[t] = rnd
        out.append({"home": home, "away": away, "round": rnd, "home_won": int(win == home), "wins_home": e["wins"].get(home, 0), "wins_away": e["wins"].get(away, 0)})
    return out



# --- NHL_CARRY=1: Job 3 honest history test (research/NEWS_IN_FUTURES_RULE.md). Code by DeepSeek (relay 031); Claude's
# corrections: history runs only between a player's first and last game for the team (no pre-arrival or post-trade
# runs; a trailing run counts as rest-of-season only if he played for no other team after), the chance he is still out
# is CONDITIONAL on the run so far (DeepSeek's was unconditional), values and lineups cached. Expected cost per game
# (probability still out minus his season-to-date missing share, times cost), capped 0.30 goals per team-game.
CARRY = os.environ.get("NHL_CARRY") == "1"
CARRY_K, CARRY_CAP = 3, 0.30
_C3 = {}


def _c3_lineups(y):
    if ("l", y) not in _C3:
        out = []
        for kind in ("skaters", "goalies"):
            f = os.path.join(LINEUP_DIR, f"{kind}_{y}.csv.gz")
            df = pd.read_csv(f) if os.path.exists(f) else pd.DataFrame()
            if len(df):
                df["date"] = pd.to_datetime(df["date"]); df["player_id"] = df["player_id"].astype(str)
            out.append(df)
        allg = pd.concat([d[["team", "game_id", "date"]] for d in out if len(d)]).drop_duplicates() if any(len(d) for d in out) else pd.DataFrame()
        _C3[("l", y)] = (out, allg)
    return _C3[("l", y)]


def _c3_hist(y):
    """Completed absence runs (team games, >= K) and runs that reached the season end, seasons before y only."""
    if ("h", y) in _C3:
        return _C3[("h", y)]
    dur, n_end = [], 0
    for yy in range(2014, y):
        (frames, allg) = _c3_lineups(yy)
        if allg.empty:
            continue
        tgames = {t: tt.sort_values("date").game_id.tolist() for t, tt in allg.groupby("team")}
        for df in frames:
            if df.empty:
                continue
            lastteam = df.sort_values("date").groupby("player_id").team.last()
            for (pid, team), pp in df.groupby(["player_id", "team"]):
                order = tgames.get(team, []); played = set(pp.game_id)
                idx = [i for i, gid in enumerate(order) if gid in played]
                if not idx:
                    continue
                run = 0
                for gid in order[idx[0]:idx[-1] + 1]:
                    if gid in played:
                        if run >= CARRY_K:
                            dur.append(run)
                        run = 0
                    else:
                        run += 1
                trail = len(order) - 1 - idx[-1]
                if trail >= CARRY_K and lastteam.get(pid) == team:
                    n_end += 1
    _C3[("h", y)] = (np.asarray(dur, float), n_end)
    return _C3[("h", y)]


def _c3_key(name, pos):
    return f"{str(name).strip().lower()}|{'G' if pos == 'G' else ('D' if pos == 'D' else 'F')}"


def _c3_out(y, cut):
    """team -> [(cost per game, run so far, baseline missing share)] for players out >= K games at cut."""
    if ("v", y) not in _C3:
        _C3[("v", y)] = nhl_absence.values(y)
    vals = _C3[("v", y)]
    (frames, allg) = _c3_lineups(y)
    res = {}
    if allg.empty:
        return res
    a = allg[allg.date < cut]
    tgames = {t: tt.sort_values("date").game_id.tolist() for t, tt in a.groupby("team")}
    for df in frames:
        if df.empty:
            continue
        d = df[df.date < cut]
        lastteam = d.sort_values("date").groupby("player_id").team.last()
        for (pid, team), pp in d.groupby(["player_id", "team"]):
            if lastteam.get(pid) != team:
                continue
            order = tgames.get(team, []); played = set(pp.game_id)
            idx = [i for i, gid in enumerate(order) if gid in played]
            if not idx:
                continue
            run = len(order) - 1 - idx[-1]
            if run < CARRY_K:
                continue
            pos = str(pp.pos.iloc[-1]); v = vals.get(_c3_key(pp.name.iloc[-1], pos))
            if v is None or not np.isfinite(v):
                continue
            if pos == "G":
                share = float(pp.get("started", pd.Series(0, index=pp.index)).sum()) / max(len(order), 1)
                others = d[(d.team == team) & (d.player_id != pid)].drop_duplicates("player_id")
                bk = [vals.get(_c3_key(r.name, "G")) for r in others.itertuples()]
                bk = [b for b in bk if b is not None and np.isfinite(b)]
                cost = nhl_absence.SCALE_G * max(0.0, v - (max(bk) if bk else nhl_absence.REPL_G)) * share
            else:
                cost = nhl_absence.SCALE_SK * float(pp.toi.mean()) / 3600.0 * max(0.0, v - nhl_absence.REPL_SK)
            span = order[idx[0]:]
            base = 1.0 - len(played & set(span)) / max(len(span), 1)
            res.setdefault(team, []).append((cost, run, base))
    return res


def _c3_game_adj(y, cut, rm):
    dur, n_end = _c3_hist(y)
    per = _c3_out(y, pd.Timestamp(cut))
    def p_out(r, k):     # P(still out at his team's k-th remaining game | out r games so far)
        alive = n_end + int((dur >= r).sum())
        return (n_end + int((dur >= r + k).sum())) / alive if alive else 0.0
    order = rm.sort_values("date")
    rank = {}
    for t in pd.unique(pd.concat([rm.team, rm.opp])):
        m = order[(order.team == t) | (order.opp == t)]
        rank[t] = {gid: i + 1 for i, gid in enumerate(m.index)}
    adj = np.zeros(len(rm))
    for i, (gid, row) in enumerate(rm.iterrows()):
        for side, sign in ((row.team, -1.0), (row.opp, 1.0)):
            s_ = sum(c * max(0.0, p_out(r, rank[side][gid]) - b) for c, r, b in per.get(side, []))
            adj[i] += sign * min(s_, CARRY_CAP)
    CARRY_ROWS.append(dict(season=y, date=str(pd.Timestamp(cut).date()), players=sum(len(v) for v in per.values()),
                           mean_abs=round(float(np.abs(adj).mean()), 4)))
    return adj


CARRY_ROWS = []

def run_season(TT, GG, fit_years, done, y):
    beta_y, k, tau, total, hfa = M.params_before(TT, GG, fit_years, done, y)
    T = TT[y]
    teams = sorted(T.index)
    align = alignment(y, teams)
    if align is None:
        return None
    out = playoff_outcomes(y, teams)
    if out is None:
        return None
    g = GG[y].copy()
    g["date"] = pd.to_datetime(g.date)
    g["gd"] = M.numcol(g, "goalsFor") - M.numcol(g, "goalsAgainst")
    shots = g.set_index(["date", "team"]).shots if "shots" in g else None
    if SHOT_W and shots is not None:
        g["sa"] = [shots.get((d_, o), np.nan) for d_, o in zip(g.date, g.opp)]
        sh_pct = M.numcol(g, "goalsFor").sum() / pd.to_numeric(g.shots, errors="coerce").sum()
        g["sd"] = (pd.to_numeric(g.shots, errors="coerce") - g.sa) * sh_pct
        if XG:
            xg = mp_xg(y)
            g["sd"] = [xg.get((d_, t_), np.nan) for d_, t_ in zip(g.date, g.team)]
            print(y, "xG coverage", round(float(g.sd.notna().mean()), 3), flush=True)
        g["rate"] = (1 - SHOT_W) * g.gd + SHOT_W * g.sd.fillna(g.gd)
        if RS_XG:
            xr = mp_xg_kind(y, RS_XG)
            g["rsx"] = [xr.get((d_, t_), np.nan) for d_, t_ in zip(g.date, g.team)]
            print(y, "regular-season MoneyPuck xG coverage", round(float(g.rsx.notna().mean()), 3), flush=True)
    else:
        g["rate"] = g.gd
    g["pts"] = g.res.map({"W": 2, "OTL": 1, "L": 0}).fillna(0)
    opp_res = g.set_index(["date", "team"]).res
    g["opp_otl"] = [opp_res.get((d_, o)) == "OTL" for d_, o in zip(g.date, g.opp)]
    fin = g.groupby("team").agg(pts=("pts", "sum"), wins=("res", lambda r: (r == "W").sum()), gd=("gd", "sum"))
    comp = M.final_comp(TT[y], y).reindex(teams).fillna(fin.pts * 1e12)   # official order (2015: DET over BOS on ROW)
    divwin = {d: max([t for t in teams if align[t] == d], key=lambda t: comp[t]) for d in set(align.values())}
    pres = comp.idxmax()
    prior = PRIOR_SCALE * pd.Series(M.prior_features(y, TT).reindex(teams).fillna(0).values @ beta_y, index=teams)
    if PS:
        prior = ps_prior(TT, GG, fit_years, done, y, prior)
    k = k * K_MULT
    first, last = g.date.min(), g.date.max()
    cur_lv = last_lv = opening = None
    S = None
    if LINEUP_C:
        val = nhl_absence.values(y)
        S, G = nhl_lineup.load_lineups(LINEUP_DIR, y)
        S1, G1 = nhl_lineup.load_lineups(LINEUP_DIR, y - 1)
        if S is not None and os.environ.get("NHL_LINEUP_VAL") == "rapm":
            sys.path.insert(0, os.path.join(ROOT, "research"))
            import nhl_rapm as RP
            sk_r, gk_r = RP.ratings(y)
            cur_lv = nhl_lineup.game_values_ratings(S, sk_r, gk_r, float(os.environ.get("NHL_LINEUP_GS", "0")), G) if sk_r is not None else nhl_lineup.game_values(S, G, val)
            opening = cur_lv.groupby("team").lv.first()
        elif S is not None:
            cur_lv = nhl_lineup.game_values(S, G, val)
            opening = cur_lv.groupby("team").lv.first()
            gg_upd = goalie_games(G) if G_UPD else None
            if G_UPD:
                print(y, "goalie GSAx coverage", round(len(gg_upd) / max(len(G), 1), 3), flush=True)
        if S1 is not None:
            last_lv = nhl_lineup.game_values(S1, G1, val)
    po_prev = pd.Series(0.0, index=teams)
    if PO_PRIOR_K:
        pp = os.path.join(nhl.NHL_OUT, f"team_{y - 1}p.json")
        if os.path.exists(pp):
            import json as _json
            d_ = _json.load(open(pp))
            P = pd.DataFrame(d_["rows"], columns=["team", "name"] + [c["k"] for c in d_["cols"]]).set_index("team")
            gdp = M.numcol(P, "goalsFor") - M.numcol(P, "goalsAgainst")
            po_prev = (gdp / (M.numcol(P, "gamesPlayed") + PO_PRIOR_K)).reindex(teams).fillna(0.0)   # n games x mean / (n + K)
    ot_tgt = ot_share(GG, [z for z in done if z < y]) if OT_FIX else None
    if OT_FIX:
        print(y, "OT target", round(ot_tgt, 3), flush=True)
    cuts = [first]
    d = first + pd.Timedelta(days=7)
    while d < last - pd.Timedelta(days=6):
        cuts.append(d)
        d += pd.Timedelta(days=7)
    n_regular = len(cuts)
    sr = [x for x in realised_series(y) if x["home"] in teams and x["away"] in teams] if SERIES_LOG else []
    if SERIES_LOG:
        cuts.append(last + pd.Timedelta(days=1))   # end of regular season: series log only, never written to the futures CSV
    rows = []
    for wk, cut in enumerate(cuts):
        pl = g[g.date < cut]
        rm = g[(g.date >= cut) & (g.ha == "H")]
        gadj = _c3_game_adj(y, cut, rm) if (CARRY and wk > 0) else None
        gp = pl.groupby("team").size().reindex(teams).fillna(0)
        cur = pl.groupby("team").rate.mean().reindex(teams).fillna(0) if len(pl) else pd.Series(0.0, index=teams)
        cur = cur - cur.mean()
        rating = (gp * cur + k * prior) / (gp + k)
        rating = rating - rating.mean()
        po_delta = None
        if SHOT_PO:
            rs_src = pl.rsx if (RS_XG and "rsx" in pl) else (pl.sd if "sd" in pl else None)
            rs_rate = (1 - RS_SHOT_W) * pl.gd + RS_SHOT_W * rs_src.fillna(pl.gd) if (RS_SHOT_W and rs_src is not None) else pl.gd
            curg = rs_rate.groupby(pl.team).mean().reindex(teams).fillna(0) if len(pl) else pd.Series(0.0, index=teams)
            curg = curg - curg.mean()
            rg = (gp * curg + k * prior) / (gp + k)
            rg = rg - rg.mean()
            po_delta = (rating - rg).reindex(teams).to_numpy(float)
            rating = rg
        if UPD_EVERY and wk > 0 and wk % UPD_EVERY == 0 and S is not None:
            import nhl_rapm as RP
            gids = set(S[pd.to_datetime(S.date) < cut].game_id)
            sk_u = RP.ratings_at(y, cut.date(), gids, UPD_W)
            if sk_u is not None:
                cur_lv = nhl_lineup.game_values_ratings(S, sk_u)
                print(y, wk, "ratings updated", flush=True)
        if UPD_MIX and cur_lv is not None and wk > 0:
            recent = cur_lv[cur_lv.date < cut].groupby("team").lv.apply(lambda v: v.iloc[-5:].mean()).reindex(teams).fillna(0)
            recent = (recent - recent.mean()) * PS_B
            rating = (1 - UPD_MIX) * rating + UPD_MIX * recent
        if G_UPD and LINEUP_C and S is not None and os.environ.get("NHL_LINEUP_VAL") != "rapm" and wk > 0:
            cur_lv = nhl_lineup.game_values(S, G, goalie_values_at(val, gg_upd, cut))
        if LINEUP_C and cur_lv is not None:
            adj = LINEUP_C * nhl_lineup.roster_term(cur_lv, last_lv, teams, cut, k, LINEUP_N, opening, LINEUP_PRE, LINEUP_MIN)
            rating = rating + adj.reindex(teams).fillna(0)
        win = pl.res == "W"
        state = pd.DataFrame({"points": pl.groupby("team").pts.sum().reindex(teams).fillna(0),
                              "rw": pl.assign(x=(win & ~pl.opp_otl).astype(float)).groupby("team").x.sum().reindex(teams).fillna(0),
                              "gd": pl.groupby("team").gd.sum().reindex(teams).fillna(0)}, index=teams)
        state["row"] = pl.assign(x=win.astype(float)).groupby("team").x.sum().reindex(teams).fillna(0)
        n_avg = float(gp.mean())
        if PO_PRIOR_K and po_delta is not None:   # playoff-only: last season's playoff goal difference, shrunk, faded like the prior
            po_delta = po_delta + (po_prev * (k / (gp + k))).reindex(teams).fillna(0).to_numpy(float)
        ot_kw = dict(ot_target=ot_tgt, ot_edge=OT_EDGE) if OT_FIX else {}
        sim = M.simulate(teams, state, list(zip(rm.team, rm.opp)), rating.to_dict(), M.tau_at(tau, n_avg), total, hfa, SIMS, seed=3, po_gap_only=PO_GAP_ONLY, series_pairs=([(x['home'], x['away']) for x in sr] or None), div_map=align, po_scale=PO_SCALE + PO_FADE * max(0.0, 1 - n_avg / 82), po_delta=po_delta, **ot_kw, game_adj=gadj)
        if SERIES_LOG and sr:
            for x, q in zip(sr, sim["series_q"]):
                SERIES_ROWS.append(dict(season=y, checkpoint=wk, label=("end" if wk >= n_regular else ("pre" if wk == 0 else "wk")), date=str(cut.date()),
                                        gp_avg=round(n_avg, 1), po_scale=round(PO_SCALE + PO_FADE * max(0.0, 1 - n_avg / 82), 4), round=x["round"],
                                        home=x["home"], away=x["away"], q=float(q), home_won=x["home_won"]))
        if wk >= n_regular:
            continue
        for i, t in enumerate(teams):
            rows.append(dict(season=y, week=wk, date=str(cut.date()), gp_avg=round(n_avg, 1), team=t, p_playoff=sim["playoffs"][i],
                             p_div=sim["div"][i], p_pres=sim["pres"][i], p_r2=sim["r2"][i], p_r3=sim["r3"][i], p_conf=sim["final"][i],
                             p_title=sim["cup"][i], y_playoff=int(t in out["po"]), y_div=int(divwin[align[t]] == t), y_pres=int(t == pres),
                             y_finals=int(t in out["finalists"]), y_title=int(t == out["champ"]),
                             y_r2=int(t in out["r2"]), y_r3=int(t in out["r3"]),
                             pts_mean=round(float(sim["pts_mean"][i]), 2), y_pts=float(fin.pts[t])))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    cur = nhl.start_year()
    TT, GG = {}, {}
    for y in range(nhl.FIRST, cur + 1):
        t = M.read_team(y)
        if not t.empty:
            TT[y] = t
        gg = M.read_games(y)
        if not gg.empty:
            GG[y] = gg
    done = [y for y in TT if y < cur and y in GG and GG[y].groupby("team").size().min() >= 40]
    fit_years = [y for y in done if y - 1 in TT]
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 2014
    last = int(sys.argv[3]) if len(sys.argv) > 3 else max(done)
    os.makedirs(OUT, exist_ok=True)
    for y in [z for z in done if first <= z <= last]:
        D = run_season(TT, GG, fit_years, done, y) if not (PS and y < int(os.environ.get("NHL_PS_FIRST", "0"))) else None
        if D is None:
            print("skip", y)
            continue
        D.to_csv(os.path.join(OUT, f"nhl_{y}.csv"), index=False)
        if CARRY:
            pd.DataFrame(CARRY_ROWS).to_csv(os.path.join(OUT, "carry_log.csv"), index=False)
        if SERIES_LOG:
            pd.DataFrame([r for r in SERIES_ROWS if r["season"] == y]).to_csv(os.path.join(OUT, f"series_{y}.csv"), index=False)
        json.dump({**{k: v for k, v in os.environ.items() if k.startswith(("NHL_", "BT_", "RAPM_"))}, "git_commit": _git_commit(),
                   "rapm_cache_sha256_file": "research/nhl_goalie_canonical_cache_sha256.txt"}, open(os.path.join(OUT, "knobs.json"), "w"), indent=1, sort_keys=True)
        print("season", y, "weeks", D.week.nunique(), flush=True)
