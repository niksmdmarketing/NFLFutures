"""One pre-registered receptions matchup test: research/nfl_games_props/MATCHUP_RULE.md. No tuning, no deployment.
Disclosed implementation details (fixed before scoring): a defence's 'total' targets are the targets to the three receiver groups
(WR; TE; RB+FB), so group shares sum to one; the beta likelihood uses the receiver test's concentration and the undamped rate
(C.rates) times the factor, as the concentration itself is fitted; weekly player stats start in 2018, so 2018 defence histories are
shorter. Usage: python matchup_test.py   (needs build.py outputs in OUT)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import betaln, gammaln

import core as C
from build import BASE, OUT, player_inputs
from conditional_audit import appearances, control_means, budget_rates, score_pmf, metrics, sha, KEY, RECEIVERS
from run import model, make_priors, app_model
from receiver_allocation_test import conditional_scales, tail_gap, comparison

DEST = BASE / 'outputs/nfl_matchup_20261026'
HERE = Path(__file__).resolve().parent
GROUP = {'WR': 'WR', 'TE': 'TE', 'RB': 'RB', 'FB': 'RB'}
K_PSEUDO, PRIOR_SD, CAP = 100.0, 0.5, (0.65, 1.5)


def defence_table(st, g):
    s = st[st.position.isin(RECEIVERS)].copy()
    s['grp'] = s.position.map(GROUP)
    t = s.groupby(['game_id', 'team', 'grp']).targets.sum().unstack(fill_value=0).reset_index()
    for c in ('WR', 'TE', 'RB'):
        if c not in t:
            t[c] = 0
    gg = g[['game_id', 'season', 'tip', 'home_team', 'away_team']]
    t = t.merge(gg, on='game_id', validate='many_to_one')
    t['defence'] = np.where(t.team == t.home_team, t.away_team, t.home_team)
    t['total'] = t.WR + t.TE + t.RB
    return t[['game_id', 'season', 'tip', 'defence', 'WR', 'TE', 'RB', 'total']].sort_values('tip')


def ratios(rows, dtab, league):
    """Shrunk ratio of targets allowed to the row's group by the opponent defence, strictly before the cutoff."""
    hist = {d: z for d, z in dtab.groupby('defence')}
    out = np.ones(len(rows))
    for i, r in enumerate(rows.itertuples()):
        h = hist.get(r.opp)
        if h is None:
            continue
        cut = r.tip - pd.Timedelta(hours=1)
        h = h[(h.tip + pd.Timedelta(hours=6) < cut) & (h.season >= r.season - 1)].tail(20)
        if not len(h):
            continue
        w = .5 ** (np.arange(len(h))[::-1] / 5)
        grp = GROUP[r.position]
        num = float(w @ h[grp].to_numpy(float))
        den = float(w @ h.total.to_numpy(float))
        L = league[grp]
        out[i] = ((num + K_PSEUDO * L) / (den + K_PSEUDO)) / L
    return out


def fit_beta(y, n, p, ratio, conc):
    y = np.asarray(y, int); n = np.asarray(n, int); ok = (n >= y) & (n > 0)
    y, n, p, ratio = y[ok], n[ok], p[ok], ratio[ok]
    def loss(beta):
        q = np.clip(p * np.clip(ratio ** beta, *CAP), 1e-5, 1 - 1e-5)
        a, b = q * conc, (1 - q) * conc
        ll = gammaln(n + 1) - gammaln(y + 1) - gammaln(n - y + 1) + betaln(y + a, n - y + b) - betaln(a, b)
        return -ll.sum() + beta ** 2 / (2 * PRIOR_SD ** 2)
    return float(minimize_scalar(loss, bounds=(-3, 3), method='bounded').x)


def main():
    DEST.mkdir(exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    g = pd.read_parquet(OUT / 'games.parquet')
    teams = pd.read_parquet(OUT / 'teams.parquet')
    players = pd.read_parquet(OUT / 'players.parquet')
    st, sn, complete, _ = player_inputs(g)
    rh = appearances(st, sn, g)
    recv = players[players.position.isin(RECEIVERS) & players.season.between(2018, 2025)].copy().reset_index(drop=True)
    recv = recv.join(control_means(recv, rh, 'receptions', 2.))
    dtab = defence_table(st, g)
    pieces, folds = [], {}
    for year in range(2021, 2026):
        tr = teams[teams.season.between(2018, year - 1) & teams.actual_team_att.gt(0)]
        te = teams[teams.season.eq(year)].reset_index(drop=True)
        vm = model('volume').fit(tr[C.VOLUME_FEATURES], tr.actual_team_att)
        dispersion = C.fit_nb(tr.actual_team_att, np.clip(vm.predict(tr[C.VOLUME_FEATURES]), 5, 70))
        volume = C.nb_pmf(np.clip(vm.predict(te[C.VOLUME_FEATURES]), 5, 70), dispersion, 100)
        vid = {(r.game_id, r.team): i for i, r in enumerate(te.itertuples())}
        train = players[players.season.between(2018, year - 1) & players.app.notna() & players.actual_team_att.notna()]
        appearance = app_model(train)
        pri = make_priors(train)
        ra = train[train.position.isin(RECEIVERS) & train.app.eq(1)].reset_index(drop=True)
        conc = C.fit_concentration(ra.receptions, ra.actual_team_att, C.rates(ra, pri, 'receptions'))
        tgt = dtab[dtab.season.between(2018, year - 1)]
        tot = tgt.total.sum()
        league = {c: float(tgt[c].sum() / tot) for c in ('WR', 'TE', 'RB')}
        beta = fit_beta(ra.receptions, ra.actual_team_att.astype(int), C.rates(ra, pri, 'receptions'), ratios(ra, dtab, league), conc)
        allz = recv[recv.season.eq(year)].copy().reset_index(drop=True)
        prob = np.clip(appearance.predict_proba(allz[C.APP_FEATURES])[:, 1], 1e-3, 1 - 1e-3)
        _, _, raw_target, catch = budget_rates(allz, pri)
        factor = np.clip(ratios(allz, dtab, league) ** beta, *CAP)
        base_scale, _ = conditional_scales(allz, raw_target, prob)
        cand_target = raw_target * factor
        cand_scale, _ = conditional_scales(allz, cand_target, prob)
        allz['base_rate'] = raw_target * base_scale * catch
        allz['cand_rate'] = cand_target * cand_scale * catch
        allz['factor'] = factor
        z = allz[allz.app.eq(1) & allz.actual_team_att.notna()].reset_index(drop=True)
        idx = np.array([vid[(r.game_id, r.team)] for r in z.itertuples()])
        rng = np.random.default_rng(20261023)
        for start in range(0, len(z), 500):
            x = z.iloc[start:start + 500]; sl = slice(start, start + len(x)); u = rng.random(len(x))
            pieces.append(score_pmf(x, C.allocation_pmf(volume[idx[sl]], x.base_rate.to_numpy(), conc, 40), 'baseline', 'receptions', u))
            pieces.append(score_pmf(x, C.allocation_pmf(volume[idx[sl]], x.cand_rate.to_numpy(), conc, 40), 'matchup', 'receptions', u))
        folds[str(year)] = dict(beta=beta, concentration=conc, league_shares=league, rows=len(z),
                                factor_quantiles=[float(v) for v in np.quantile(z.factor, [.05, .25, .5, .75, .95])])
        print('fold', year, folds[str(year)], flush=True)
    rows = pd.concat(pieces, ignore_index=True)
    rows.to_parquet(DEST / 'paired_scores.parquet', index=False)
    base = rows[rows.model.eq('baseline')]; cand = rows[rows.model.eq('matchup')]
    repro = None
    ref_path = os.environ.get('RECEIVER_ALLOCATION_SCORES')   # GPT's run3 paired scores: baseline must reproduce its 'challenger' rows
    if ref_path and Path(ref_path).exists():
        ref = pd.read_parquet(ref_path)
        ref = ref[ref.model.eq('challenger')][KEY + ['rps']]
        m = base.merge(ref, on=KEY, suffixes=('', '_ref'))
        repro = dict(baseline_rows=len(base), reference_rows=len(ref), matched=len(m),
                     max_abs_rps_diff=float(np.abs(m.rps - m.rps_ref).max()) if len(m) else None,
                     share_equal_1e9=float((np.abs(m.rps - m.rps_ref) < 1e-9).mean()) if len(m) else None)
        print('reproduction', repro, flush=True)
    groups = {'established': base.season_mean.ge(2), 'low_volume': base.season_mean.lt(2), 'candidate_mean_below_one': base['mean'].lt(1)}
    gres = {}
    for label, keep in groups.items():
        ids = base.loc[keep, KEY]
        gres[label] = {m: metrics(zz.merge(ids, on=KEY, validate='one_to_one')) for m, zz in [('baseline', base), ('matchup', cand)]}
    cmp_ = comparison(cand, base)
    bm, cm = metrics(base), metrics(cand)
    low_changes = {l: float(gres[l]['matchup']['rps'] / gres[l]['baseline']['rps'] - 1) for l in ('low_volume', 'candidate_mean_below_one')}
    gates = {'1_rps_bound_and_seasons': bool(cmp_['paired_season_lower'] > 0 and cmp_['seasons_better'] >= 4),
             '2_pit_0.07_0.13': bool(all(.07 <= v <= .13 for v in cm['pit_deciles'])),
             '3_log_score_not_worse': bool(cm['log_score'] <= bm['log_score']),
             '4_low_volume_not_0.5pct_worse': bool(all(v <= .005 for v in low_changes.values())),
             '5_upper95_gap_not_worse': bool(tail_gap(cand) <= tail_gap(base) + .002)}
    res = dict(rule='research/nfl_games_props/MATCHUP_RULE.md', started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
               settings=dict(k_pseudo_targets=K_PSEUDO, beta_prior_sd=PRIOR_SD, cap=CAP), folds=folds,
               models=dict(baseline=bm, matchup=cm), comparison=cmp_, groups=gres, low_volume_rps_changes=low_changes,
               upper95_gap=dict(baseline=tail_gap(base), matchup=tail_gap(cand)), gates=gates, passes=all(gates.values()),
               market_edge_established=False, baseline_reproduction=repro, inputs={n: sha(OUT / n) for n in ('games.parquet', 'teams.parquet', 'players.parquet')},
               code_sha256=sha(__file__), rule_sha256=sha(HERE / 'MATCHUP_RULE.md'))
    (DEST / 'results.json').write_text(json.dumps(res, indent=2))
    (HERE / 'matchup_results.json').write_text(json.dumps(res, indent=2))
    print(json.dumps({k: res[k] for k in ('comparison', 'gates', 'passes', 'low_volume_rps_changes', 'upper95_gap')}, indent=2))


if __name__ == '__main__':
    main()
