"""Pre-registered per-play matchup test for team pass attempts: research/nfl_games_props/PER_PLAY_MATCHUP_RULE.md.
No tuning, no deployment. Usage: NFL_RESEARCH_NFLVERSE=<data dir> python per_play_matchup_test.py
Disclosed implementation details (fixed before scoring): stage-2 volume training rows use the stage-1 coefficients fitted on
2010..s-1 (in-sample for those rows, as for any fitted feature); a team-game with no play-by-play history gets the league rate.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

import core as C
from build import BASE, OUT, FIX, locate, player_inputs
from conditional_audit import appearances, control_means, budget_rates, score_pmf, metrics, sha, KEY, RECEIVERS
from run import model, make_priors, app_model, logscore
from receiver_allocation_test import conditional_scales, comparison

DEST = BASE / 'outputs/nfl_per_play_matchup_20261026'
HERE = Path(__file__).resolve().parent
K, HALF, WINDOW = 300.0, 5, 20
RATES = ('sack', 'succ')
EXTRA = ['exp_sack', 'exp_succ']


def counts(year):
    cols = {'game_id', 'posteam', 'defteam', 'epa', 'qb_dropback', 'sack', 'success', 'two_point_attempt', 'play_type', 'season_type'}
    x = pd.read_csv(locate(f'play_by_play_{year}.csv.gz'), usecols=lambda c: c in cols, low_memory=False)
    if 'season_type' in x:
        x = x[x.season_type == 'REG']
    x = x[x.posteam.notna() & x.epa.notna() & x.play_type.isin(['pass', 'run']) & (x.two_point_attempt != 1) & (x.qb_dropback == 1)].copy()
    x['posteam'] = x.posteam.replace(FIX); x['defteam'] = x.defteam.replace(FIX)
    x['sack'] = x.sack.fillna(0).eq(1).astype(int); x['succ'] = x.success.fillna(0).eq(1).astype(int)
    off = x.groupby(['game_id', 'posteam']).agg(db=('sack', 'size'), sack=('sack', 'sum'), succ=('succ', 'sum')).reset_index().rename(columns={'posteam': 'team'})
    de = x.groupby(['game_id', 'defteam']).agg(db=('sack', 'size'), sack=('sack', 'sum'), succ=('succ', 'sum')).reset_index().rename(columns={'defteam': 'team'})
    return off, de


def traits(g, off, de):
    """Pre-game shrunk offence/defence rates for every (game, team); outcome counts of that team's offence attached."""
    o = {(r.game_id, r.team): r for r in off.itertuples()}
    d = {(r.game_id, r.team): r for r in de.itertuples()}
    seas = off.merge(g[['game_id', 'season']], on='game_id').groupby('season')[['db', 'sack', 'succ']].sum()
    league = {s: {k: float(seas.loc[s, k] / seas.loc[s, 'db']) for k in RATES} for s in seas.index}
    hist = {'off': defaultdict(list), 'def': defaultdict(list)}
    pending, rows = [], []

    def flush(cut):
        nonlocal pending
        keep = []
        for p in pending:
            if p['ready'] >= cut:
                keep.append(p); continue
            for side, src in (('off', o), ('def', d)):
                for team in (p['home'], p['away']):
                    r = src.get((p['game_id'], team))
                    if r is not None:
                        hist[side][team].append((p['season'], r.db, r.sack, r.succ))
        pending = keep

    def rate(side, team, season, L):
        h = [r for r in hist[side][team] if r[0] >= season - 1][-WINDOW:]
        out = {}
        w = .5 ** (np.arange(len(h))[::-1] / HALF) if h else np.array([])
        db = float(w @ np.array([r[1] for r in h], float)) if h else 0.
        for j, k in enumerate(RATES):
            ev = float(w @ np.array([r[2 + j] for r in h], float)) if h else 0.
            out[k] = (ev + K * L[k]) / (db + K)
        return out

    for r in g.sort_values('tip').itertuples():
        flush(r.cutoff)
        L = league.get(r.season - 1)
        if L is not None:
            for team, opp in ((r.home, r.away), (r.away, r.home)):
                ot, dt = rate('off', team, r.season, L), rate('def', opp, r.season, L)
                y = o.get((r.game_id, team))
                rows.append(dict(game_id=r.game_id, team=team, season=r.season, O_sack=ot['sack'], O_succ=ot['succ'], D_sack=dt['sack'],
                                 D_succ=dt['succ'], L_sack=L['sack'], L_succ=L['succ'], db=getattr(y, 'db', np.nan),
                                 sack=getattr(y, 'sack', np.nan), succ=getattr(y, 'succ', np.nan)))
        if pd.notna(r.home_score):
            pending.append(dict(game_id=r.game_id, home=r.home, away=r.away, season=r.season, ready=r.tip + pd.Timedelta(hours=6)))
    return pd.DataFrame(rows), league


def predict(form, theta, z, k):
    a, bo, bd = theta
    O, D, L = z[f'O_{k}'].to_numpy(), z[f'D_{k}'].to_numpy(), z[f'L_{k}'].to_numpy()
    if form == 'additive':
        return np.clip(L + a + bo * (O - L) + bd * (D - L), 1e-4, 1 - 1e-4)
    return np.clip(expit(logit(L) + a + bo * (logit(O) - logit(L)) + bd * (logit(D) - logit(L))), 1e-4, 1 - 1e-4)


def loglik(p, y, n):
    return y * np.log(p) + (n - y) * np.log(1 - p)


def fit(form, z, k):
    z = z[z.db.notna() & z.db.gt(0)]
    y, n = z[k].to_numpy(float), z.db.to_numpy(float)
    res = minimize(lambda t: -loglik(predict(form, t, z, k), y, n).sum(), x0=[0., 1., 1.], method='Nelder-Mead',
                   options=dict(xatol=1e-7, fatol=1e-6, maxiter=4000))
    return res.x


def stage1(tr):
    out = {}
    for k in RATES:
        per = {f: {} for f in ('additive', 'log5')}
        for s in range(2013, 2021):
            train, test = tr[tr.season.between(2010, s - 1)], tr[tr.season.eq(s) & tr.db.gt(0)]
            for f in per:
                th = fit(f, train, k)
                per[f][str(s)] = float(loglik(predict(f, th, test, k), test[k].to_numpy(float), test.db.to_numpy(float)).sum() / test.db.sum())
        means = {f: float(np.mean(list(v.values()))) for f, v in per.items()}
        out[k] = dict(per_season_loglik_per_dropback=per, mean_season=means, chosen='log5' if means['log5'] > means['additive'] else 'additive',
                      log5_better_seasons=int(sum(per['log5'][s] > per['additive'][s] for s in per['log5'])))
        print('stage1', k, out[k]['mean_season'], out[k]['chosen'], out[k]['log5_better_seasons'], flush=True)
    return out


def team_scores(te, pmf, name, u):
    y = te.actual_team_att.to_numpy(int)
    return pd.DataFrame(dict(game_id=te.game_id, team=te.team, season=te.season, model=name, rps=C.rps(pmf, y), log_score=logscore(pmf, y),
                             pit=C.pit(pmf, y, u), mean=pmf @ np.arange(pmf.shape[1]), actual=y))


def paired(cand, base, col):
    m = cand.merge(base, on=['game_id', 'team'], suffixes=('', '_b'), validate='one_to_one')
    gain = m[col + '_b'] - m[col]
    by = m.assign(g=gain).groupby('season').g.mean()
    return dict(mean_gain=float(gain.mean()), season_lower=C.season_bound(gain.to_numpy(), m.season.to_numpy()),
                seasons_better=int((by > 0).sum()), by_season={str(k): float(v) for k, v in by.items()},
                baseline=float(m[col + '_b'].mean()), candidate=float(m[col].mean()))


def main():
    DEST.mkdir(exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    g = pd.read_parquet(OUT / 'games.parquet'); teams = pd.read_parquet(OUT / 'teams.parquet')
    players = pd.read_parquet(OUT / 'players.parquet')
    offs, defs = zip(*[counts(y) for y in range(2009, 2026)])
    tr, league = traits(g[g.season.le(2025)], pd.concat(offs, ignore_index=True), pd.concat(defs, ignore_index=True))
    tr.to_parquet(DEST / 'per_play_traits.parquet', index=False)
    s1 = stage1(tr)
    # Downstream receiver inputs as in matchup_test.py (baseline construction, no matchup factor).
    st, sn, _, _ = player_inputs(g)
    rh = appearances(st, sn, g)
    recv = players[players.position.isin(RECEIVERS) & players.season.between(2018, 2025)].copy().reset_index(drop=True)
    recv = recv.join(control_means(recv, rh, 'receptions', 2.))
    tpieces, rpieces, folds = [], [], {}
    for year in range(2021, 2026):
        tt = teams[teams.season.between(2018, year)].merge(tr[['game_id', 'team'] + [c for c in tr if c[:2] in ('O_', 'D_', 'L_')]],
                                                           on=['game_id', 'team'], how='left', validate='one_to_one')
        missing = int(tt.O_sack.isna().sum())
        for k in RATES:
            for c in ('O_', 'D_', 'L_'):
                tt[c + k] = tt[c + k].fillna(league[year - 1][k] if c != 'L_' else league[year - 1][k])
            th = fit(s1[k]['chosen'], tr[tr.season.between(2010, year - 1)], k)
            tt['exp_' + k] = predict(s1[k]['chosen'], th, tt, k)
            folds.setdefault(str(year), {})[k] = dict(form=s1[k]['chosen'], theta=[float(v) for v in th])
        trn = tt[tt.season.between(2018, year - 1) & tt.actual_team_att.gt(0)]
        te = tt[tt.season.eq(year)].reset_index(drop=True)
        vols = {}
        for name, feats in (('baseline', C.VOLUME_FEATURES), ('candidate', C.VOLUME_FEATURES + EXTRA)):
            vm = model('volume').fit(trn[feats], trn.actual_team_att)
            disp = C.fit_nb(trn.actual_team_att, np.clip(vm.predict(trn[feats]), 5, 70))
            vols[name] = C.nb_pmf(np.clip(vm.predict(te[feats]), 5, 70), disp, 100)
            folds[str(year)][name + '_dispersion'] = disp
        folds[str(year)]['missing_trait_rows'] = missing
        sc = te.actual_team_att.gt(0).to_numpy()
        u = np.random.default_rng(20261026).random(int(sc.sum()))
        for name in vols:
            tpieces.append(team_scores(te[sc], vols[name][sc], name, u))
        # Downstream receptions: identical receiver rates, each team pmf.
        vid = {(r.game_id, r.team): i for i, r in enumerate(te.itertuples())}
        train = players[players.season.between(2018, year - 1) & players.app.notna() & players.actual_team_att.notna()]
        appearance = app_model(train); pri = make_priors(train)
        ra = train[train.position.isin(RECEIVERS) & train.app.eq(1)].reset_index(drop=True)
        conc = C.fit_concentration(ra.receptions, ra.actual_team_att, C.rates(ra, pri, 'receptions'))
        allz = recv[recv.season.eq(year)].copy().reset_index(drop=True)
        prob = np.clip(appearance.predict_proba(allz[C.APP_FEATURES])[:, 1], 1e-3, 1 - 1e-3)
        _, _, raw_target, catch = budget_rates(allz, pri)
        scale, _ = conditional_scales(allz, raw_target, prob)
        allz['base_rate'] = raw_target * scale * catch
        z = allz[allz.app.eq(1) & allz.actual_team_att.notna()].reset_index(drop=True)
        idx = np.array([vid[(r.game_id, r.team)] for r in z.itertuples()])
        rng = np.random.default_rng(20261023)
        for start in range(0, len(z), 500):
            x = z.iloc[start:start + 500]; sl = slice(start, start + len(x)); uu = rng.random(len(x))
            for name in vols:
                rpieces.append(score_pmf(x, C.allocation_pmf(vols[name][idx[sl]], x.base_rate.to_numpy(), conc, 40), name, 'receptions', uu))
        print('fold', year, folds[str(year)], flush=True)
    T = pd.concat(tpieces, ignore_index=True); R = pd.concat(rpieces, ignore_index=True)
    T.to_parquet(DEST / 'team_scores.parquet', index=False); R.to_parquet(DEST / 'receiver_scores.parquet', index=False)
    tb, tc = T[T.model.eq('baseline')], T[T.model.eq('candidate')]
    rb, rc = R[R.model.eq('baseline')], R[R.model.eq('candidate')]
    repro = None
    ref_path = BASE / 'outputs/nfl_matchup_20261026/paired_scores.parquet'
    if ref_path.exists():
        ref = pd.read_parquet(ref_path); ref = ref[ref.model.eq('baseline')][KEY + ['rps']]
        m = rb.merge(ref, on=KEY, suffixes=('', '_ref'))
        repro = dict(rows=len(rb), reference_rows=len(ref), matched=len(m), max_abs_rps_diff=float(np.abs(m.rps - m.rps_ref).max()))
        print('reproduction', repro, flush=True)
    rps_cmp, log_cmp = paired(tc, tb, 'rps'), paired(tc, tb, 'log_score')
    pit_dec = np.histogram(tc.pit, bins=np.linspace(0, 1, 11))[0] / len(tc)
    rec_change = float(metrics(rc)['rps'] / metrics(rb)['rps'] - 1)
    gates = {'1_team_rps_bound_and_seasons': bool(rps_cmp['season_lower'] > 0 and rps_cmp['seasons_better'] >= 4),
             '2_team_log_bound_and_seasons': bool(log_cmp['season_lower'] > 0 and log_cmp['seasons_better'] >= 4),
             '3_pit_0.07_0.13': bool(all(.07 <= v <= .13 for v in pit_dec)),
             '4_receptions_not_0.1pct_worse': bool(rec_change <= .001)}
    res = dict(rule='research/nfl_games_props/PER_PLAY_MATCHUP_RULE.md', started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
               settings=dict(pseudo_dropbacks=K, half_life=HALF, window=WINDOW), stage1=s1, folds=folds,
               team_attempts=dict(rps=rps_cmp, log_score=log_cmp, candidate_pit_deciles=[float(v) for v in pit_dec],
                                  mean_error=dict(baseline=float((tb['mean'] - tb.actual).mean()), candidate=float((tc['mean'] - tc.actual).mean()))),
               receptions=dict(baseline=metrics(rb), candidate=metrics(rc), relative_rps_change=rec_change, comparison=comparison(rc, rb)),
               baseline_reproduction=repro, gates=gates, passes=all(gates.values()), market_edge_established=False,
               inputs={n: sha(OUT / n) for n in ('games.parquet', 'teams.parquet', 'players.parquet')},
               code_sha256=sha(__file__), rule_sha256=sha(HERE / 'PER_PLAY_MATCHUP_RULE.md'))
    (DEST / 'results.json').write_text(json.dumps(res, indent=2, default=float))
    (HERE / 'per_play_matchup_results.json').write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps(dict(stage1={k: s1[k]['chosen'] for k in RATES}, team_attempts={k: res['team_attempts'][k] for k in ('rps', 'log_score')},
                          receptions_change=rec_change, gates=gates, passes=res['passes']), indent=2, default=float))


if __name__ == '__main__':
    main()
