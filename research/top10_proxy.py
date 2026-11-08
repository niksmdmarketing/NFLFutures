"""Top-10 backtest edges with a PROXY results-only rating model (rule: Amendment 5).
Usage: python research/top10_proxy.py nba|ncaaf|epl <data dir> <out dir>"""
import glob, json, os, re, sys
import numpy as np, pandas as pd
from scipy.stats import norm
sport, ddir, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
LL = lambda p, y: -(y * np.log(np.clip(p, 1e-4, 1 - 1e-4)) + (1 - y) * np.log(1 - np.clip(p, 1e-4, 1 - 1e-4)))


def sbr_files(pattern, reader, mlcol="ML"):
    G = []
    for f in sorted(glob.glob(os.path.join(ddir, pattern))):
        m = re.search(r"(\d{4})-(\d{2})", os.path.basename(f)); y0 = int(m.group(1))
        x = reader(f); x["Final"] = pd.to_numeric(x["Final"], errors="coerce"); x = x.dropna(subset=["Final"]).reset_index(drop=True)
        x["Date"] = x["Date"].astype(int)
        i = 0; yr = y0; prev_mo = None
        while i < len(x) - 1:
            a, b = x.iloc[i], x.iloc[i + 1]
            ok = a.VH == "V" and b.VH == "H" and a.Date == b.Date
            i += 2 if (ok or a.VH == "N") else 1   # re-sync after a break (prereg: log, do not misalign)
            if ok:
                mo, d = divmod(int(a.Date), 100)
                if prev_mo is None: yr = y0 if mo >= 8 else y0 + 1
                elif mo <= prev_mo - 6: yr += 1   # calendar wrap Dec->Jan (also handles Jul-Oct 2020 bubble/COVID seasons)
                prev_mo = mo
                try:
                    pd.Timestamp(yr, mo, d)
                except ValueError:
                    continue
                G.append(dict(season=y0, date=pd.Timestamp(yr, mo, d), home=b.Team, away=a.Team, hs=float(b.Final), as_=float(a.Final), mlh=b[mlcol], mla=a[mlcol], clh=(b["Close"] if "Close" in b.index else np.nan), cla=(a["Close"] if "Close" in a.index else np.nan)))
    return pd.DataFrame(G)


def ml_prob(m):
    m = pd.to_numeric(m, errors="coerce"); return np.where(m < 0, -m / (-m + 100), 100 / (m + 100))


if sport == "nba":
    G = sbr_files(os.path.join("csv", "nba-odds-*.csv"), lambda f: pd.read_csv(f))
elif sport == "nhl":
    G = sbr_files(os.path.join("csv", "nhl-odds-2*.csv"), lambda f: pd.read_csv(f), "Close")
elif sport == "cbb":
    G = sbr_files("ncaa-basketball-*.xlsx", lambda f: pd.read_excel(f))
elif sport == "ncaaf":
    G = sbr_files("ncaa_football_*.xlsx", lambda f: pd.read_excel(f))
else:
    rows = []
    for f in sorted(glob.glob(os.path.join(ddir, "mmz4281", "*", "E0.csv"))):
        s = os.path.basename(os.path.dirname(f)); y0 = int(s[:2]); y0 = 1900 + y0 if y0 > 90 else 2000 + y0
        x = pd.read_csv(f, encoding="latin1", on_bad_lines="skip", engine="python")
        x = x.dropna(subset=["HomeTeam", "FTHG", "FTAG"])
        x["date"] = pd.to_datetime(x.Date, dayfirst=True, errors="coerce")
        ph = [c for c in ("PSCH", "B365CH", "AvgCH", "B365H") if c in x]; 
        for r in x.itertuples():
            try:
                h = next(getattr(r, c) for c in ("PSCH", "B365CH", "AvgCH", "B365H") if hasattr(r, c) and pd.notna(getattr(r, c)))
                d = next(getattr(r, c) for c in ("PSCD", "B365CD", "AvgCD", "B365D") if hasattr(r, c) and pd.notna(getattr(r, c)))
                a = next(getattr(r, c) for c in ("PSCA", "B365CA", "AvgCA", "B365A") if hasattr(r, c) and pd.notna(getattr(r, c)))
            except StopIteration:
                h = d = a = np.nan
            rows.append(dict(season=y0, date=r.date, home=r.HomeTeam, away=r.AwayTeam, hs=float(r.FTHG), as_=float(r.FTAG), oh=h, od=d, oa=a))
    G = pd.DataFrame(rows)
G = G.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
G["margin"] = G.hs - G.as_
G["week"] = ((G.date - G.groupby("season").date.transform("min")).dt.days // 7)


def rate(g, prior, K, HOME):
    teams = sorted(set(g.home) | set(g.away) | set(prior)); ix = {t: i for i, t in enumerate(teams)}; n = len(teams)
    A = np.zeros((len(g) + n, n)); b = np.zeros(len(g) + n)
    for r, (h, a, m) in enumerate(zip(g.home, g.away, g.margin)):
        A[r, ix[h]], A[r, ix[a]], b[r] = 1, -1, m - HOME
    lam = np.sqrt(K / 2)
    for t, i in ix.items():
        A[len(g) + i, i] = lam; b[len(g) + i] = lam * prior.get(t, 0.0)
    x = np.linalg.lstsq(A, b, rcond=None)[0]; x -= x.mean()
    return dict(zip(teams, x))


def forecast(REG, K, HOME, seasons):
    rows = []
    for y in seasons:
        g = G[G.season == y]; prev = G[G.season == y - 1]
        if not len(prev): continue
        prior = {t: REG * v for t, v in rate(prev, {}, 0.01, HOME).items()}
        for w in sorted(g.week.unique()):
            played = g[g.week < w]; R = rate(played, prior, K, HOME) if len(played) else dict(prior)
            for r in g[g.week == w].itertuples():
                rows.append((r.Index, y, w, R.get(r.home, 0.0) - R.get(r.away, 0.0) + HOME))
    return pd.DataFrame(rows, columns=["i", "season", "week", "m"]).set_index("i")


disc_seasons = [y for y in sorted(G.season.unique()) if y <= 2018]
HOME0 = float(G[G.season.isin(disc_seasons)].margin.mean())
best = None
for REG in (0.3, 0.5, 0.7):
    for K in (4, 10, 20):
        F = forecast(REG, K, HOME0, disc_seasons[1:])
        mse = float(((G.loc[F.index, "margin"] - F.m) ** 2).mean())
        if best is None or mse < best[0]: best = (mse, REG, K)
mse, REG, K = best; SD = float(np.sqrt(mse)) if sport != "epl" else float(np.sqrt(mse))
print(sport, "games", len(G), "proxy settings REG", REG, "K", K, "home", round(HOME0, 2), "sd", round(SD, 2))
F = forecast(REG, K, HOME0, sorted(G.season.unique()))
J = G.join(F[["m"]].astype(float), how="inner")
J["frac"] = J.week / J.groupby("season").week.transform("max")
if sport == "epl":
    J["p_model"] = norm.cdf((J.m - 0.5) / SD)
    ih, idr, ia = 1 / J.oh, 1 / J.od, 1 / J.oa
    J["p_market"] = ih / (ih + idr + ia); J["y"] = (J.margin > 0).astype(float)
else:
    J["p_model"] = norm.cdf(J.m / SD)
    ph, pa = ml_prob(J.mlh), ml_prob(J.mla); J["p_market"] = ph / (ph + pa); J["y"] = (J.margin > 0).astype(float)
    J = J[J.margin != 0]
    if sport in ("nba", "ncaaf", "cbb"):
        # data-integrity check (prereg 8 Nov): the favourite's row carries the SPREAD (smaller number), so the moneyline favourite must agree with it
        ch, ca = pd.to_numeric(J.clh, errors="coerce"), pd.to_numeric(J.cla, errors="coerce")
        J["mismatch"] = ((ch < ca) != (pd.to_numeric(J.mlh, errors="coerce") < pd.to_numeric(J.mla, errors="coerce"))) & ch.notna() & ca.notna()
        print(sport, "moneyline-vs-spread favourite mismatches:", int(J.mismatch.sum()), "of", len(J), "(dropped, logged)")
        J = J[~J.mismatch]
J = J.dropna(subset=["p_market", "p_model"])
J["gap"] = J.p_model - J.p_market; J = J[J.gap != 0].copy()
J["side"] = np.where(J.gap > 0, "home", "away"); J["edge"] = J.gap.abs()
J["pm_side"] = np.where(J.gap > 0, J.p_model, 1 - J.p_model); J["pk_side"] = np.where(J.gap > 0, J.p_market, 1 - J.p_market)
J.to_csv(os.path.join(out, f"{sport}_proxy_edges.csv"), index=False)
DISC = J.season <= 2018
print(sport, "rated+priced games", len(J), "model LL", round(LL(J.p_model, J.y).mean(), 4), "market LL", round(LL(J.p_market, J.y).mean(), 4))
top = J[DISC].sort_values("edge", ascending=False).head(10)
print(top[["season", "date", "home", "away", "side", "pm_side", "pk_side", "edge", "m", "week", "hs", "as_"]].round(3).to_string(index=False))
rng = np.random.default_rng(0)
for name, X in (("disc", J[DISC]), ("eval", J[~DISC]), ("all", J)):
    k = int(round(len(X) * 0.05)); A = X.sort_values("edge", ascending=False).head(k); B = X.assign(g2=-X.gap).sort_values("g2", ascending=False).head(k)
    d = lambda Z: LL(Z.p_model, Z.y) - LL(Z.p_market, Z.y)
    seas = sorted(X.season.unique()); b = []
    for _ in range(2000):
        pick = rng.choice(seas, len(seas)); a = np.concatenate([d(A[A.season == s]).values for s in pick]); c = np.concatenate([d(B[B.season == s]).values for s in pick])
        if len(a) and len(c): b.append(a.mean() - c.mean())
    print(name, "n/tail", k, "D", round(d(A).mean() - d(B).mean(), 4), np.percentile(b, [5, 95]).round(3), "early(frac<.2) share of top5%", round((A.frac < .2).mean(), 3), "vs all", round((X.frac < .2).mean(), 3))
J["mk_margin"] = norm.ppf(np.clip(J.p_market, 1e-4, 1 - 1e-4)) * SD
J["gap_m"] = J.m - J.mk_margin; J["out_gap"] = J.margin - J.mk_margin
for lab, X in (("frac<.2", J[J.frac < .2]), ("frac .2-.8", J[(J.frac >= .2) & (J.frac < .8)]), ("frac>=.8", J[J.frac >= .8]), ("all", J)):
    x, yv = X.gap_m.values, X.out_gap.values; bb = (x * yv).sum() / (x * x).sum(); seas = sorted(X.season.unique()); bs = []
    for _ in range(1500):
        p = rng.choice(seas, len(seas)); Z = pd.concat([X[X.season == s] for s in p]); bs.append((Z.gap_m * Z.out_gap).sum() / (Z.gap_m ** 2).sum())
    print("weight on model gap", lab, "n", len(X), round(bb, 3), np.percentile(bs, [5, 95]).round(3))
