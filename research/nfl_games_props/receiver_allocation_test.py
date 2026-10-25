"""One preregistered receiver-allocation test. No tuning or deployment."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import core as C
from build import BASE, OUT
from run import model, make_priors, app_model, logscore
from conditional_audit import budget_rates, score_pmf, metrics, sha

AUDIT = BASE/'outputs/nfl_conditional_audit_20261024_corrected'
DEST = BASE/'outputs/nfl_receiver_allocation_20261025_run3'
KEY = ['game_id','team','aid']


def conditional_scales(z, shares, probabilities):
    weighted = pd.Series(shares*probabilities,index=z.index).groupby([z.game_id,z.team]).transform('sum').to_numpy()
    # Conditioning on focal i appearing replaces a_i*s_i by 1*s_i.
    denominators = weighted + shares*(1-probabilities)
    return np.minimum(1.,1/np.maximum(denominators,1e-12)), denominators


def tail_gap(z, q='95'):
    return abs(float(z['exceed'+q+'_actual'].mean()-z['exceed'+q+'_predicted'].mean()))


def comparison(candidate, baseline):
    pair=candidate.merge(baseline[KEY+['rps']],on=KEY,suffixes=('','_baseline'),validate='one_to_one')
    gain=pair.rps_baseline-pair.rps
    by=pair.assign(gain=gain).groupby('season').gain.mean()
    return dict(relative_score_reduction=float(1-pair.rps.mean()/pair.rps_baseline.mean()),
        paired_season_lower=C.season_bound(gain,pair.season),seasons_better=int(by.gt(0).sum()),
        gains_by_season={str(k):float(v) for k,v in by.items()})


def main():
    DEST.mkdir(exist_ok=False)
    src=Path(__file__).parent
    (DEST/'rule.md').write_bytes((src/'RECEIVER_ALLOCATION_RULE.md').read_bytes())
    protected=[OUT/n for n in ['games.parquet','teams.parquet','players.parquet','results.json']]
    protected += [AUDIT/n for n in ['results.json','paired_scores.parquet','receiver_controls.parquet','verification.json']]
    hashes={str(p):sha(p) for p in protected}
    manifest=dict(started_utc=datetime.now(timezone.utc).isoformat(),rule_sha256=sha(src/'RECEIVER_ALLOCATION_RULE.md'),
        code_sha256=sha(__file__),protected_inputs=hashes,market_inputs=False)
    (DEST/'manifest_started.json').write_text(json.dumps(manifest,indent=2))
    teams=pd.read_parquet(OUT/'teams.parquet')
    players=pd.read_parquet(OUT/'players.parquet')
    receivers=pd.read_parquet(AUDIT/'receiver_controls.parquet')
    audited=pd.read_parquet(AUDIT/'paired_scores.parquet')
    audited=audited[audited.stat.eq('receptions')]
    original=json.loads((OUT/'results.json').read_text())
    pieces=[];folds={};participation=[]
    for year in range(2021,2026):
        tr=teams[teams.season.between(2018,year-1)&teams.actual_team_att.gt(0)]
        te=teams[teams.season.eq(year)].reset_index(drop=True)
        vm=model('volume').fit(tr[C.VOLUME_FEATURES],tr.actual_team_att)
        dispersion=C.fit_nb(tr.actual_team_att,np.clip(vm.predict(tr[C.VOLUME_FEATURES]),5,70))
        volume=C.nb_pmf(np.clip(vm.predict(te[C.VOLUME_FEATURES]),5,70),dispersion,100)
        vid={(r.game_id,r.team):i for i,r in enumerate(te.itertuples())}
        train=players[players.season.between(2018,year-1)&players.app.notna()&players.actual_team_att.notna()]
        appearance=app_model(train)
        pri=make_priors(train)
        ra=train[train.position.isin(['WR','TE','RB','FB'])&train.app.eq(1)]
        concentration=C.fit_concentration(ra.receptions,ra.actual_team_att,C.rates(ra,pri,'receptions'))
        expected=original['props']['frozen'][str(year)]['receptions']['concentration']
        assert np.isclose(concentration,expected)
        allz=receivers[receivers.season.eq(year)].copy().reset_index(drop=True)
        probabilities=np.clip(appearance.predict_proba(allz[C.APP_FEATURES])[:,1],1e-3,1-1e-3)
        old_rate,old_scale,raw_target,catch=budget_rates(allz,pri)
        new_scale,denominator=conditional_scales(allz,raw_target,probabilities)
        allz['appearance_probability']=probabilities
        allz['old_scale']=old_scale
        allz['new_scale']=new_scale
        allz['expected_active_budget']=denominator
        allz['old_rate']=old_rate
        allz['new_rate']=raw_target*new_scale*catch
        participation.append(allz[['game_id','team','aid','season','app','appearance_probability','old_scale','new_scale','expected_active_budget']])
        z=allz[allz.app.eq(1)&allz.actual_team_att.notna()].reset_index(drop=True)
        idx=np.array([vid[(r.game_id,r.team)] for r in z.itertuples()])
        rng=np.random.default_rng(20261023)
        for start in range(0,len(z),500):
            x=z.iloc[start:start+500];sl=slice(start,start+len(x));u=rng.random(len(x))
            current=C.allocation_pmf(volume[idx[sl]],x.old_rate.to_numpy(),concentration,40)
            challenger=C.allocation_pmf(volume[idx[sl]],x.new_rate.to_numpy(),concentration,40)
            pieces.append(score_pmf(x,current,'current', 'receptions',u))
            pieces.append(score_pmf(x,challenger,'challenger','receptions',u))
        folds[str(year)]=dict(training_last_season=year-1,n_train=len(train),volume_dispersion=dispersion,
            receiver_concentration=concentration,mean_appearance_probability=float(probabilities.mean()),
            mean_old_scale=float(old_scale.mean()),mean_new_conditional_scale=float(new_scale.mean()))
        print('Completed receiver allocation fold',year,len(z),flush=True)
    rows=pd.concat(pieces,ignore_index=True)
    participation=pd.concat(participation,ignore_index=True)
    rows.to_parquet(DEST/'paired_scores.parquet',index=False)
    participation.to_parquet(DEST/'participation_inputs.parquet',index=False)
    current=rows[rows.model.eq('current')]
    challenger=rows[rows.model.eq('challenger')]
    prior_current=audited[audited.model.eq('candidate')]
    check=current.merge(prior_current[KEY+['rps']],on=KEY,suffixes=('','_audit'),validate='one_to_one')
    assert len(check)==len(current)==len(prior_current)
    assert np.allclose(check.rps,check.rps_audit,atol=1e-12,rtol=0)
    last10=audited[audited.model.eq('last10')]
    groups={
        'established':current.season_mean.ge(2),
        'low_volume':current.season_mean.lt(2),
        'candidate_mean_below_one':current['mean'].lt(1)}
    group_results={}
    for label,keep in groups.items():
        ids=current.loc[keep,KEY]
        group_results[label]={m:metrics(z.merge(ids,on=KEY,validate='one_to_one')) for m,z in [('current',current),('challenger',challenger)]}
    cmp_current=comparison(challenger,current)
    cmp_last10=comparison(challenger,last10)
    cm=metrics(current);nm=metrics(challenger)
    pit_ok=all(.07<=x<=.13 for x in nm['pit_deciles'])
    established_reduction=1-abs(group_results['established']['challenger']['mean_error'])/abs(group_results['established']['current']['mean_error'])
    low_ok=True;low_changes={}
    for label in ['low_volume','candidate_mean_below_one']:
        a=group_results[label]['current']['rps'];b=group_results[label]['challenger']['rps']
        low_changes[label]=float(b/a-1);low_ok &= b/a-1<=.005
    gates=dict(beats_current=cmp_current['paired_season_lower']>0 and cmp_current['seasons_better']>=4,
        beats_last10=cmp_last10['paired_season_lower']>0 and cmp_last10['seasons_better']>=4,
        pit_calibration=pit_ok,established_bias_reduction=established_reduction>=.25,
        low_volume_not_materially_worse=bool(low_ok),log_score_not_worse=nm['log_score']<=cm['log_score'],
        upper95_gap_not_worse=tail_gap(challenger)<=tail_gap(current)+.002)
    result=dict(completed_utc=datetime.now(timezone.utc).isoformat(),folds=folds,
        models=dict(current=cm,challenger=nm,last10=metrics(last10)),
        comparisons=dict(current=cmp_current,last10=cmp_last10),fixed_groups=group_results,
        diagnostics=dict(established_absolute_mean_error_reduction=float(established_reduction),low_volume_rps_changes=low_changes,
            current_upper95_gap=tail_gap(current),challenger_upper95_gap=tail_gap(challenger)),
        gates=gates,historical_challenger_pass=all(gates.values()),market_edge_established=False,
        live_changes=False,note='One preregistered participation-weighted target-budget candidate; no tuning after results.')
    for path,digest in hashes.items():assert sha(path)==digest
    result['protected_artifacts_unchanged']=True
    (DEST/'results.json').write_text(json.dumps(result,indent=2))
    manifest.update(completed_utc=result['completed_utc'],outputs={p.name:sha(p) for p in DEST.iterdir() if p.is_file()})
    (DEST/'manifest_complete.json').write_text(json.dumps(manifest,indent=2))
    write_report(result)


def write_report(r):
    m=r['models'];c=r['comparisons'];g=r['gates']
    lines=['# Receiver participation-weighted allocation test','',
        'Research only. No live, website or market-input changes.','',
        '| Version | RPS | Mean forecast | Mean actual | Log score |','|---|---:|---:|---:|---:|',
        f"| Current | {m['current']['rps']:.6f} | {m['current']['mean_predicted']:.3f} | {m['current']['mean_actual']:.3f} | {m['current']['log_score']:.4f} |",
        f"| Challenger | {m['challenger']['rps']:.6f} | {m['challenger']['mean_predicted']:.3f} | {m['challenger']['mean_actual']:.3f} | {m['challenger']['log_score']:.4f} |",
        f"| Last 10 | {m['last10']['rps']:.6f} | {m['last10']['mean_predicted']:.3f} | {m['last10']['mean_actual']:.3f} | {m['last10']['log_score']:.4f} |",'',
        f"Versus current: {100*c['current']['relative_score_reduction']:.3f}% RPS reduction; {c['current']['seasons_better']}/5 seasons; paired lower bound {c['current']['paired_season_lower']:.6f}.",
        f"Versus last 10: {100*c['last10']['relative_score_reduction']:.3f}% RPS reduction; {c['last10']['seasons_better']}/5 seasons; paired lower bound {c['last10']['paired_season_lower']:.6f}.",'',
        '## Gates','']+[f"- {'PASS' if v else 'FAIL'} — {k}" for k,v in g.items()]
    lines += ['',f"**Verdict: {'historical challenger pass' if r['historical_challenger_pass'] else 'fail; preserve and stop this branch'}.**",'',
        'Passing would still not establish a betting edge, automatic lineup accuracy or profitability.']
    (DEST/'REPORT.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
