"""Read-only, role-conditional walk-forward audit. No model selection or deployment."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import core as C
import conditional_engine as E
from build import BASE, OUT, USED, locate, player_inputs
from conditional_build import first_qb_samples
from run import model, make_priors, logscore

DEST = BASE / 'outputs/nfl_conditional_audit_20261024_corrected'
KEY = ['game_id', 'team', 'aid']
RECEIVERS = ['WR', 'TE', 'RB', 'FB']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def appearances(st, sn, games):
    """Zero-stat offensive appearances count; DNP/special-teams-only games do not."""
    # History follows the player, even when a special-teamer changes position
    # labels (e.g. FB/LB or WR/CB). Do not lose genuine zero-stat offense snaps.
    s = sn[sn.offense_snaps > 0].copy()
    s = s[KEY + ['position']]
    production = st[st.position.isin(RECEIVERS) & (st.targets > 0)]
    s = pd.concat([s, production[KEY + ['position']]], ignore_index=True).drop_duplicates(KEY)
    s = s.merge(st[KEY + ['receptions']], on=KEY, how='left', validate='one_to_one')
    s['receptions'] = s.receptions.fillna(0)
    return s.merge(games[['game_id', 'season', 'tip']], on='game_id', validate='many_to_one')


def control_means(targets, history, stat, default):
    """Only finished earlier appearances, across teams; last ten is unweighted."""
    histories = {a: z.sort_values('tip') for a, z in history.groupby('aid')}
    pooled = history.groupby(['season', 'position'])[stat].agg(['sum', 'count']).reset_index()
    out = []
    for r in targets.itertuples():
        h = histories.get(r.aid)
        if h is not None:
            h = h[h.tip + pd.Timedelta(hours=6) < r.tip - pd.Timedelta(hours=1)]
        prior = pooled[(pooled.season < r.season) & (pooled.position == r.position)]
        fallback = float(prior['sum'].sum()/prior['count'].sum()) if prior['count'].sum() else default
        n = 0 if h is None else len(h)
        if n:
            same = h[h.season == r.season]
            previous = h[h.season == r.season-1]
            season_values = same if len(same) else previous
            avg = float(season_values[stat].mean()) if len(season_values) else fallback
            recent = float(h.tail(10)[stat].mean())
            latest = str(h.tip.max())
        else:
            avg = recent = fallback
            latest = None
        out.append((avg, recent, n, latest))
    return pd.DataFrame(out, columns=['season_mean', 'recent_mean', 'earlier_appearances', 'latest_history_tip'], index=targets.index)


def budget_rates(z, pri):
    target = np.clip((z.h_targets.to_numpy()+20*z.position.map(pri['target_share']).fillna(.08).to_numpy())/(z.h_team_att.to_numpy()+20), 0, 1)
    # Budget is computed before any outcome/appearance filtering.
    sums = pd.Series(target, index=z.index).groupby([z.game_id, z.team]).transform('sum').to_numpy()
    scale = np.minimum(1., 1./np.maximum(sums, 1e-12))
    catch = np.clip((z.h_receptions.to_numpy()+8*z.position.map(pri['catch']).fillna(.65).to_numpy())/(z.h_targets.to_numpy()+8), 0, 1)
    return target*scale*catch, scale, target, catch


def score_pmf(z, pmf, name, stat, u):
    limit = pmf.shape[1]-1
    y = z[stat].to_numpy(int)
    assert np.all(y < limit), 'Observed value enters overflow bucket'
    assert np.allclose(pmf.sum(1), 1) and np.all(pmf >= 0)
    cdf = pmf.cumsum(1)
    line = np.floor(z.season_mean.to_numpy())+.5
    assert np.all(line < limit)
    out = z[KEY + ['season', 'position', 'name', 'season_mean', 'earlier_appearances']].copy()
    for col in ['rookie_diagnostic', 'budget_scale', 'latest_history_tip']:
        if col in z:
            out[col] = z[col].to_numpy()
    out['model'] = name
    out['stat'] = stat
    out['actual'] = y
    out['rps'] = C.rps(pmf, y, 60 if stat == 'attempts' else 20)
    out['log_score'] = logscore(pmf, y)
    out['pit'] = C.pit(pmf, y, u)
    out['mean'] = pmf @ np.arange(limit+1)
    out['zero_predicted'] = pmf[:, 0]
    out['line'] = line
    out['over_predicted'] = 1-cdf[np.arange(len(z)), np.floor(line).astype(int)]
    out['over_actual'] = y > line
    for label, q in [('95', .95), ('99', .99)]:
        k = (cdf < q).sum(1).clip(0, limit)
        out['exceed'+label+'_predicted'] = 1-cdf[np.arange(len(z)), k]
        out['exceed'+label+'_actual'] = y > k
    return out


def metrics(z):
    confident = z[z.over_predicted >= .8]
    return dict(n=len(z), rps=float(z.rps.mean()), log_score=float(z.log_score.mean()),
        mean_predicted=float(z['mean'].mean()), mean_actual=float(z.actual.mean()),
        mean_error=float((z['mean']-z.actual).mean()),
        pit_deciles=(np.histogram(z.pit, np.linspace(0, 1, 11))[0]/len(z)).tolist(),
        zero_predicted=float(z.zero_predicted.mean()), zero_actual=float(z.actual.eq(0).mean()),
        over_predicted=float(z.over_predicted.mean()), over_actual=float(z.over_actual.mean()),
        confident_n=len(confident), confident_over_predicted=float(confident.over_predicted.mean()) if len(confident) else None,
        confident_over_actual=float(confident.over_actual.mean()) if len(confident) else None,
        exceedances={q:dict(predicted=float(z['exceed'+q+'_predicted'].mean()), actual=float(z['exceed'+q+'_actual'].mean())) for q in ['95','99']})


def summarise(rows, old):
    result = {}
    for stat, allrows in rows.groupby('stat'):
        cand = allrows[allrows.model == 'candidate'].copy()
        item = dict(models={m:metrics(z) for m,z in allrows.groupby('model')}, by_season={}, comparisons={})
        for year, z in allrows.groupby('season'):
            item['by_season'][str(year)] = {m:metrics(x) for m,x in z.groupby('model')}
        for name in ['season', 'last10']:
            b = allrows[allrows.model == name]
            pair = cand.merge(b[KEY+['rps']], on=KEY, suffixes=('', '_baseline'), validate='one_to_one')
            gains = pair.rps_baseline-pair.rps
            item['comparisons'][name] = dict(relative_score_reduction=float(1-pair.rps.mean()/pair.rps_baseline.mean()),
                paired_season_lower=C.season_bound(gains, pair.season),
                seasons_better=int(pair.assign(gain=gains).groupby('season').gain.mean().gt(0).sum()))
        deciles = item['models']['candidate']['pit_deciles']
        item['calibration_screen'] = all(.07 <= x <= .13 for x in deciles)
        item['historical_screen_pass'] = item['calibration_screen'] and all(x['paired_season_lower'] > 0 and x['seasons_better'] >= 4 for x in item['comparisons'].values())
        groups = {'established_start_proxy':cand.earlier_appearances.ge(5), 'under_five_starts':cand.earlier_appearances.lt(5),
                  'under_three_starts':cand.earlier_appearances.lt(3)} if stat == 'attempts' else {
                  'season_mean_at_least_two':cand.season_mean.ge(2), 'season_mean_below_two':cand.season_mean.lt(2),
                  'candidate_mean_below_one':cand['mean'].lt(1), 'rookie_metadata_diagnostic':cand.rookie_diagnostic}
        item['fixed_groups'] = {}
        for label, keep in groups.items():
            ids = cand.loc[keep, KEY]
            z = allrows.merge(ids, on=KEY, validate='many_to_one')
            item['fixed_groups'][label] = dict(models={m:metrics(x) for m,x in z.groupby('model')},
                candidate_by_season={str(y):metrics(x) for y,x in z[z.model=='candidate'].groupby('season')})
        shared = cand.merge(old[old.stat == stat][KEY+['conditional_rps']], on=KEY, validate='one_to_one')
        item['prototype_descriptive_only'] = dict(n=len(shared), candidate_rps=float(shared.rps.mean()),
            old_conditional_rps=float(shared.conditional_rps.mean()), note='Different QB allocation assumptions; not a same-role control.')
        result[stat] = item
    return result


def main():
    DEST.mkdir(exist_ok=False)
    src = Path(__file__).parent
    protected = [OUT/n for n in ['games.parquet','teams.parquet','players.parquet','prop_predictions.parquet','results.json']]
    protected += [BASE/'outputs/nfl_conditional_props_20261024'/n for n in ['model.json','assumptions_ready.json','roster_model_features_ready.json']]
    inputs = {str(p):sha(p) for p in protected}
    (DEST/'rule.md').write_bytes((src/'CONDITIONAL_AUDIT_RULE.md').read_bytes())
    manifest = dict(started_utc=datetime.now(timezone.utc).isoformat(), code={p.name:sha(p) for p in src.glob('*.py')},
        rule_sha256=sha(src/'CONDITIONAL_AUDIT_RULE.md'), protected_inputs=inputs, market_inputs=False)
    (DEST/'manifest_started.json').write_text(json.dumps(manifest, indent=2))
    g = pd.read_parquet(OUT/'games.parquet')
    team = pd.read_parquet(OUT/'teams.parquet')
    p = pd.read_parquet(OUT/'players.parquet')
    old = pd.read_parquet(OUT/'prop_predictions.parquet')
    st, sn, complete, identity = player_inputs(g)
    rh = appearances(st, sn, g)
    qpath = BASE/'outputs/nfl_conditional_props_20261024/starting_role_training.parquet'
    q = pd.read_parquet(qpath)
    extra = []
    label_inputs = {str(qpath):sha(qpath)}
    for year in [2018, 2019]:
        z, used = first_qb_samples(year)
        extra.append(z)
        label_inputs.update(used)
    q = pd.concat(extra+[q], ignore_index=True).merge(g[['game_id','tip']], on='game_id', validate='many_to_one')
    q['position'] = 'QB'
    q.to_parquet(DEST/'first_role_history.parquet', index=False)
    # Controls for training and evaluation are made in one chronological pass by player.
    recv = p[p.position.isin(RECEIVERS) & p.season.between(2018, 2025)].copy().reset_index(drop=True)
    recv = recv.join(control_means(recv, rh, 'receptions', 2.))
    qc = q.merge(p[KEY+['name','app']], on=KEY, how='left', validate='one_to_one')
    qc['name'] = qc.name.fillna(qc.aid)
    qc = qc.join(control_means(qc, q, 'attempts', 35.))
    metadata = pd.read_csv(locate('players.csv'), usecols=['gsis_id','rookie_season']).dropna(subset=['gsis_id'])
    rookie = metadata.drop_duplicates('gsis_id').set_index('gsis_id').rookie_season
    recv['rookie_diagnostic'] = recv.aid.map(rookie).eq(recv.season)
    recv.to_parquet(DEST/'receiver_controls.parquet', index=False)
    qc.to_parquet(DEST/'qb_controls.parquet', index=False)
    pieces = []
    coverage = {}; folds = {}
    for year in range(2021, 2026):
        tr = team[team.season.between(2018, year-1) & team.actual_team_att.gt(0)]
        te = team[team.season == year].reset_index(drop=True)
        vm = model('volume').fit(tr[C.VOLUME_FEATURES], tr.actual_team_att)
        dispersion = C.fit_nb(tr.actual_team_att, np.clip(vm.predict(tr[C.VOLUME_FEATURES]), 5, 70))
        volume = C.nb_pmf(np.clip(vm.predict(te[C.VOLUME_FEATURES]), 5, 70), dispersion, 100)
        vid = {(r.game_id,r.team):i for i,r in enumerate(te.itertuples())}
        qt = q[q.season.between(2020, year-1)]
        share = float((qt.attempts.sum()+100*.95)/(qt.team_attempts.sum()+100))
        concentration = C.fit_concentration(qt.attempts, qt.team_attempts, np.full(len(qt), share))
        train = p[p.season.between(2018, year-1) & p.app.notna() & p.actual_team_att.notna()]
        pri = make_priors(train)
        ra = train[train.position.isin(RECEIVERS) & train.app.eq(1)]
        rc = C.fit_concentration(ra.receptions, ra.actual_team_att, C.rates(ra, pri, 'receptions'))
        allreceivers = recv[recv.season == year].copy().reset_index(drop=True)
        rate, scale, target, catch = budget_rates(allreceivers, pri)
        allreceivers['budget_scale'] = scale
        allreceivers['allocation_rate'] = rate
        # Verify the vectorised budget against the actual interactive engine.
        for _, example in allreceivers.groupby(['game_id','team'], sort=False):
            ix = example.index.to_numpy()
            enabled,_ = E.target_budget([dict(aid=allreceivers.loc[i,'aid'], default_target_share=float(target[i])) for i in ix])
            assert np.allclose([r['effective_target_share'] for r in enabled], target[ix]*scale[ix])
        rz = allreceivers[allreceivers.app.eq(1) & allreceivers.actual_team_att.notna()].copy().reset_index(drop=True)
        qz = qc[(qc.season == year) & qc.app.eq(1)].copy().reset_index(drop=True)
        expected = te[te.actual_team_att.gt(0)]
        labels = q[q.season == year]
        actual_receivers = rh[rh.season==year].merge(allreceivers[KEY].assign(in_candidates=True),on=KEY,how='left')
        actual_receivers = actual_receivers[actual_receivers.position.isin(RECEIVERS) | actual_receivers.in_candidates.eq(True)]
        coverage[str(year)] = dict(team_games_expected=len(expected), first_role_labels=len(labels),
            first_role_label_gaps=len(expected.merge(labels[['game_id','team']],on=['game_id','team'],how='left',indicator=True).query('_merge == "left_only"')),
            scored_qb_roles=len(qz), qb_unseen_or_not_appearing=int(((qc.season==year)&~qc.app.eq(1)).sum()),
            receiver_candidates=len(allreceivers), receiver_appearances=len(rz),
            actual_receiver_appearances=len(actual_receivers),
            receiver_unseen_appearances=int(actual_receivers.in_candidates.isna().sum()),
            team_budgets_scaled=int(allreceivers.groupby(['game_id','team']).budget_scale.first().lt(1).sum()))
        folds[str(year)] = dict(training_last_season=year-1, volume_dispersion=dispersion, starting_share=share,
            starting_concentration=concentration, starting_training_n=len(qt), receiver_concentration=rc, priors=pri, baseline_dispersions={})
        for stat, zz, hist in [('attempts',qz,qc), ('receptions',rz,recv)]:
            limit = 100 if stat == 'attempts' else 40
            a = hist[hist.season.between(2020 if stat=='attempts' else 2018, year-1)]
            if stat == 'receptions':
                a = a[a.app.eq(1) & a.actual_team_att.notna()]
            assert a.season.max() < year
            ds = {name:C.fit_nb(a[stat], np.maximum(a[col],.01)) for name,col in [('season','season_mean'),('last10','recent_mean')]}
            folds[str(year)]['baseline_dispersions'][stat] = ds
            rng = np.random.default_rng(20261023)
            for start in range(0,len(zz),500):
                x = zz.iloc[start:start+500]
                ids = [vid[(r.game_id,r.team)] for r in x.itertuples()]
                allocation = np.full(len(x),share) if stat=='attempts' else x.allocation_rate.to_numpy()
                pmf = C.allocation_pmf(volume[ids],allocation,concentration if stat=='attempts' else rc,limit)
                if start==0:
                    if stat=='attempts':
                        ref = E.starting_qb(volume[ids[0]],dict(share=share,concentration=concentration))
                    else:
                        ref = E.receiving(volume[ids[0]],float(allocation[0]),1.,rc)
                    assert np.allclose(pmf[0],ref)
                u = rng.random(len(x))
                pieces.append(score_pmf(x,pmf,'candidate',stat,u))
                for name,col in [('season','season_mean'),('last10','recent_mean')]:
                    b = C.nb_pmf(np.maximum(x[col],.01),ds[name],limit)
                    pieces.append(score_pmf(x,b,name,stat,u))
            print('Completed fold',year,stat,len(zz),flush=True)
    rows = pd.concat(pieces,ignore_index=True)
    rows.to_parquet(DEST/'paired_scores.parquet',index=False)
    result = dict(completed_utc=datetime.now(timezone.utc).isoformat(), conditional_role_known=True, automatic_starter_test=False,
        market_edge_established=False, live_changes=False, coverage=coverage, folds=folds, identity_audit=identity,
        results=summarise(rows,old), limitations=[
            'Actual first QB is supplied after the fact; not an automatic starter-selection test.',
            'Receiver candidate cohort is strictly lagged but not a dated depth-chart/roster replay.',
            'Revised historical files, not original publication vintages; five test seasons only.',
            'QB history counts begin in 2018; rookie metadata is retrospective diagnostic only.',
            'Initial audit retained separately; corrected audit includes offensive appearances despite position-label changes. No settings changed.',
            'No bookmaker prop prices or profitability test.'])
    for path, value in inputs.items():
        assert sha(path)==value, 'Protected artifact changed: '+path
    result['protected_artifacts_unchanged'] = True
    (DEST/'results.json').write_text(json.dumps(result,indent=2))
    manifest.update(completed_utc=result['completed_utc'], raw_inputs=USED, label_inputs=label_inputs,
        outputs={p.name:sha(p) for p in DEST.iterdir() if p.is_file()})
    (DEST/'manifest_complete.json').write_text(json.dumps(manifest,indent=2))
    report(result)


def report(result):
    lines = ['# NFL conditional projection audit', '', 'Research only. No model or website changes.', '',
        'This measures production given the supplied role, not whether the starter was known before kickoff. The actual first identifiable QB is supplied to every version. Receivers are scored conditional on playing.', '',
        '| Stat | Candidate RPS | Season-average RPS | Last-10 RPS | Seasons better (season / last10) | Calibration | Verdict |',
        '|---|---:|---:|---:|---:|---|---|']
    for stat,item in result['results'].items():
        m=item['models'];co=item['comparisons']
        lines.append(f"| {stat} | {m['candidate']['rps']:.5f} | {m['season']['rps']:.5f} | {m['last10']['rps']:.5f} | {co['season']['seasons_better']}/5 / {co['last10']['seasons_better']}/5 | {'Pass' if item['calibration_screen'] else 'Fail'} | {'Historical screen pass' if item['historical_screen_pass'] else 'Mixed/failing screen'} |")
    lines += ['', '## Limits', '']+['- '+x for x in result['limitations']]
    lines += ['', 'Full season, tail, zero-count, subgroup and paired uncertainty results: results.json. All paired row scores: paired_scores.parquet. Formula comparison lines are not bookmaker quotes.', '', 'No improvements were fitted after seeing these results.']
    (DEST/'REPORT.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
