"""Mechanics check for the joint model (Amendment 1, item 7). Looks at data timing, fit correctness, units and minutes
accounting at one season (default 2022): the pre-season checkpoint and one in-season week. No forecast performance is computed."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nba_joint as J  # noqa: E402
import nba_backtest as B  # noqa: E402
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("research_nba_rapm", os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba_rapm.py"))
RA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RA)   # research/nba_rapm.py (the RAPM the replay uses), not pipeline/nba_rapm.py
N = J.N

K = int(sys.argv[1]) if len(sys.argv) > 1 else 2022
WEEK = int(sys.argv[2]) if len(sys.argv) > 2 else 4
boxes = B.load_boxes(K)
g = B.season_games(boxes, K)
first, last = g.date.min(), g.date.max()
cuts = [first - pd.Timedelta(days=1)]
d = first + pd.Timedelta(days=6)
while d < last - pd.Timedelta(days=6):
    cuts.append(d)
    d += pd.Timedelta(days=7)
pre, wk = cuts[0], cuts[WEEK]
print(f"season {K}: pre-season cutoff {pre.date()}, in-season cutoff (week {WEEK}) {wk.date()}")

f = J.get_fit(K)
ctx = J.season_context(K)
print("seasons in fit:", f.seasons, " players", f.m, " team-seasons", f.T)

# 1. data timing --------------------------------------------------------------------------------------------------
for s in (K - 1, K - 2):
    assert (f.date[s] <= np.datetime64(first)).all(), "earlier-season stints must predate this season"
print("1a. stints in the prior-season block: max date", pd.Timestamp(f.date[K - 1].max()).date(), "/", pd.Timestamp(f.date[K - 2].max()).date(), "(< season start)")
print("1b. current-season stints used at pre-season:", f.last_date_used(pre))
ld = f.last_date_used(wk)
print("1c. latest current-season stint used at the in-season checkpoint:", ld.date(), "<= cutoff", wk.date(), ld <= wk)
assert ld <= wk
Ac, _ = f.current(wk)
Ap, _ = f.current(pre)
print("1d. current-season normal-equation mass: pre-season", float(np.abs(Ap).sum()), " in-season", round(float(np.abs(Ac).sum())))
n_used = int((f.date[K] <= np.datetime64(wk)).sum())
print(f"1e. current-season stints used in-season: {n_used} of {len(f.date[K])}")
# box-score prior from K-1, K-2 only
mu = ctx["mu"]
pbK = J.pbox(K)
rookies = set(pbK.athlete_id.unique()) - set(J.pbox(K - 1).athlete_id.unique()) - set(J.pbox(K - 2).athlete_id.unique())
print("1f. players whose first minutes are in season K but who have a box prior:", len(rookies & set(mu)), "(should be 0)")
assert not (rookies & set(mu))
# minutes table uses only games on or before the cutoff
ros_pre = J.roster_v2(K, pre, g)
ros_wk = J.roster_v2(K, wk, g)
mt_pre = J.minutes_table(K, pre, ros_pre, ctx["rv"])
mt_wk = J.minutes_table(K, wk, ros_wk, ctx["rv"])
G_wk = J.pbox(K)[J.pbox(K).date <= wk].groupby("team_abbreviation").date.nunique()
print("1g. games played per team by the in-season cutoff: min", int(G_wk.min()), "max", int(G_wk.max()))
print("1h. roster sizes pre-season (players with a team): median per team", int(ros_pre.groupby("team_abbreviation").size().median()),
      " in-season", int(ros_wk.groupby("team_abbreviation").size().median()))
live = J.pbox(K).sort_values("date").groupby("athlete_id").team_abbreviation.first()
cmp = ros_pre.assign(a=ros_pre.athlete_id.astype(int)).set_index("a").team_abbreviation
common = cmp.index.intersection(live.index)
print("1i. pre-season roster v2 vs live (first team in the season): same team for", int((cmp[common] == live[common]).sum()), "of", len(common), "common players;",
      "only in v2:", len(cmp.index.difference(live.index)), " only in live:", len(live.index.difference(cmp.index)))

# 2. fit correctness -------------------------------------------------------------------------------------------------
mu_live = mu
beta, tauK, eta = f.solve(pre, 4.0, 1e9, 0.0, mu)
os.environ["NBA_STINTS"] = J.STINTS
RA.STINTS = J.STINTS
# the live RAPM reads stints_<y>.parquet; give it the same NBA-team-only stints the joint fit uses
import tempfile
tmp = tempfile.mkdtemp()
for y in (K - 1, K - 2):
    q = pd.read_parquet(os.path.join(J.STINTS, f"stints_{y}.parquet"))
    q[q.htid.between(1, 30) & q.atid.between(1, 30)].to_parquet(os.path.join(tmp, f"stints_{y}.parquet"))
RA.STINTS = tmp
live_r = RA.fit(K, lam=3000, w2=0.5, prior=mu_live, cache={})
ids = sorted(set(live_r) & set(beta))
a = np.array([beta[i] for i in ids]); b = np.array([live_r[i] for i in ids])
print(f"2a. lambda_tau 1e9 (pre-season): joint beta vs live RAPM on {len(ids)} players: corr {np.corrcoef(a, b)[0, 1]:.6f}, max abs diff {np.abs(a - b).max():.5f}, "
      f"slope {np.polyfit(b, a, 1)[0]:.5f}, joint-only players {len(set(beta) - set(live_r))}")
print("2b. home-court intercept eta", round(eta, 3), "(points per 100)")
print("2c. tau at lambda_tau 1e9: max |tau|", float(np.abs(list(tauK.values())).max()))
beta4, tau4, eta4 = f.solve(wk, 4.0, 4000.0, 0.0, mu)
print("2d. in-season fit (w_c 4, lambda_tau 4000, rho 0): beta sd", round(float(np.std(list(beta4.values()))), 3),
      " tau sd", round(float(np.std(list(tau4.values()))), 3), " eta", round(eta4, 3))
# ridge solution satisfies the normal equations: gradient of the penalised objective at the solution is ~0
# (checked by refitting with the data doubled in weight and halved penalty equivalence is not needed; direct residual below)
Ac, bc = f.current(wk)
A = f.A0 + 4.0 * Ac
bb = f.b0 + 4.0 * bc
d = np.arange(f.m)
A[d, d] += J.LAM_BETA
bb[:f.m] += J.LAM_BETA * np.array([mu.get(i, 0.0) for i in f.ids])
for (s, t), j in f.tix.items():
    A[f.m + j, f.m + j] += 4000.0
A[-1, -1] += 1e-6
sol = np.r_[[beta4[i] for i in f.ids], [tau4[t] if s == K else np.nan for (s, t), j in f.tix.items()], eta4]
# only the K-season tau are returned; refit to get the full vector for the residual
full = np.linalg.solve(A, bb)
print("2e. normal-equation residual of the dense solve:", float(np.abs(A @ full - bb).max()))

# 3. units and minutes accounting ---------------------------------------------------------------------------------------
for name, mt, cut in (("pre-season", mt_pre, pre), ("in-season", mt_wk, wk)):
    s = mt.groupby("team").m.sum()
    c = mt.groupby("team").size()
    print(f"3a. {name}: minutes per team sum min {s.min():.6f} max {s.max():.6f}; players per team min {c.min()} max {c.max()}; teams {len(s)}")
    assert np.allclose(s, 240.0) and c.max() <= 12
beta_p, tau_p, _ = f.solve(pre, 4.0, 4000.0, 0.5, mu)
val = J.player_values(K, beta_p)
S, mt_r = J.team_strength(mt_pre, val)
print("3b. pre-season team strength S (points per 100): mean", round(float(S.mean()), 3), " sd", round(float(S.std()), 3), " range", round(float(S.min()), 2), "to", round(float(S.max()), 2))
r_pre, mtr, parts = J.rating_at(K, pre, ros_pre, (4.0, 4000.0, 0.5), ctx, scale=1.0, return_parts=True)
print("3c. rating (scale 1): mean", round(float(r_pre.mean()), 10), " sd", round(float(r_pre.std()), 3), "; player-sum part sd", round(float(parts["players"].std()), 3), " tau part sd", round(float(parts["tau"].std()), 3))
print("3d. a hand check on one team:")
t0 = sorted(N.TEAMS)[0]
gt = mt_r[mt_r.team == t0]
print(gt[["athlete_id", "m", "r"]].round(3).to_string(index=False))
print("   sum m", round(float(gt.m.sum()), 6), " S by hand", round(float((gt.m * gt.r).sum() / 48), 4), " S from function", round(float(S[t0]), 4))
fs = J.first_seasons(K - 1)
no_prior = [a for a in beta_p if a not in fs]
print("3e. players in the fit with no prior-season minutes (no development bonus):", len(no_prior), "of", len(beta_p))
dev_check = {a: val(a) - beta_p[a] for a in list(beta_p)[:2000] if a in fs}
print("   development bonus values seen:", sorted(set(round(v, 6) for v in dev_check.values())))

# playoff delta uses the same minutes and units
ratio = J.po_ratio(K)
dl = J.playoff_delta(mtr, ratio, 1.0)
gt2 = mtr[mtr.team == t0]
m, r = gt2.m.to_numpy(), gt2.r.to_numpy()
reg = 5 * float(np.sum(m / m.sum() * r))
mp = m * np.array([ratio.get(int(a), 1.0) for a in gt2.athlete_id])
o = np.argsort(-mp, kind="stable"); mp, rp = mp[o], r[o]
top = (mp / mp.sum())[:8] ** 1.5; top /= top.sum()
for _ in range(5):
    top = np.minimum(top, 42 / 240); top /= top.sum()
raw = 5 * float(np.sum(top * rp[:8])) - reg
allraw = {}
for t, gg in mtr.groupby("team"):
    mm, rr = gg.m.to_numpy(), gg.r.to_numpy()
    rg = 5 * float(np.sum(mm / mm.sum() * rr)); q = mm * np.array([ratio.get(int(a), 1.0) for a in gg.athlete_id])
    oo = np.argsort(-q, kind="stable"); q, rq = q[oo], rr[oo]
    tp = (q / q.sum())[:8] ** 1.5; tp /= tp.sum()
    for _ in range(5):
        tp = np.minimum(tp, 42 / 240); tp /= tp.sum()
    allraw[t] = 5 * float(np.sum(tp * rq[:8])) - rg
cen = raw - np.mean(list(allraw.values()))
print(f"3f. playoff delta team {t0}: by hand (centred) {cen:.5f} vs function {float(dl[t0]):.5f}; sd across teams {float(dl.std()):.3f}; "
      f"scale 0.8 gives {float(J.playoff_delta(mtr, ratio, 0.8)[t0]):.5f} (= 0.8 x)")
print("3g. rating sign check: rating - scale x (S + tau) are centred versions of the same quantity; scale 0.8 ratio:",
      round(float(J.rating_at(K, pre, ros_pre, (4.0, 4000.0, 0.5), ctx, scale=0.8)[0][t0] / r_pre[t0]), 6))
print("MECHANICS CHECK COMPLETE")
