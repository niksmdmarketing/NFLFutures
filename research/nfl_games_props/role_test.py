"""Pre-specified role experiments. No deployment, no target-game starter inputs."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
import core as C
from build import OUT,locate
from run import model,make_priors
from feed_test import EXTRA
import role_models as R

DEST=OUT/'role_extension'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()

def involvement(train,z):
    tx=ColumnTransformer([('numeric',StandardScaler(),C.APP_FEATURES),('reports',OneHotEncoder(handle_unknown='ignore'),EXTRA)])
    m=make_pipeline(tx,LogisticRegression(C=1,max_iter=1000)).fit(train[C.APP_FEATURES+EXTRA],train.app.astype(int))
    def predict(x):return np.clip(m.predict_proba(x[C.APP_FEATURES+EXTRA])[:,1],.001,.999)
    return predict(train),predict(z)

def scored(x,stat,base,candidate,pa,lines,seed):
    limit=60 if stat=='attempts' else 20
    u=np.random.default_rng(seed).random(len(x));y=x[stat].to_numpy()
    b=base*pa[:,None];b[:,0]+=1-pa;c=candidate*pa[:,None];c[:,0]+=1-pa
    out=x[['game_id','team','aid','season','app','position']].copy();out['stat']=stat
    out['baseline_cond_rps']=C.rps(base,y,limit);out['candidate_cond_rps']=C.rps(candidate,y,limit)
    out['baseline_rps']=C.rps(b,y,limit);out['candidate_rps']=C.rps(c,y,limit)
    out['baseline_pit']=C.pit(base,y,u);out['candidate_pit']=C.pit(candidate,y,u)
    j=np.clip(np.floor(lines).astype(int),0,base.shape[1]-1)
    out['baseline_over']=1-base.cumsum(1)[np.arange(len(x)),j]
    out['candidate_over']=1-candidate.cumsum(1)[np.arange(len(x)),j]
    out['actual_over']=y>lines;out['line']=lines
    out['baseline_mean']=base@np.arange(base.shape[1]);out['candidate_mean']=candidate@np.arange(base.shape[1]);out['actual']=y
    return out

def summary(z):
    a=z[z.app==1];g=a.baseline_cond_rps-a.candidate_cond_rps
    year=a.groupby('season')[['baseline_cond_rps','candidate_cond_rps']].mean()
    bins=np.histogram(a.candidate_pit,bins=10,range=(0,1))[0]/len(a)
    subs={}
    for col in ['recent_primary','prior_primary_out','missing_teammates']:
        if col not in a:continue
        for flag,x in a.groupby(col):
            subs[f'{col}={flag}']=dict(n=len(x),baseline=float(x.baseline_cond_rps.mean()),candidate=float(x.candidate_cond_rps.mean()),
                relative_gain=float(1-x.candidate_cond_rps.mean()/x.baseline_cond_rps.mean()))
    bound=C.season_bound(g,a.season)
    no_group_harm=all(v['relative_gain']>=-.02 for v in subs.values())
    return dict(n=len(z),involved=len(a),conditional_baseline=float(a.baseline_cond_rps.mean()),conditional_candidate=float(a.candidate_cond_rps.mean()),
        conditional_relative_gain=float(1-a.candidate_cond_rps.mean()/a.baseline_cond_rps.mean()),
        unconditional_baseline=float(z.baseline_rps.mean()),unconditional_candidate=float(z.candidate_rps.mean()),
        season_lower=bound,seasons_better=int((year.candidate_cond_rps<year.baseline_cond_rps).sum()),
        by_season=year.reset_index().to_dict('records'),candidate_pit_deciles=bins.tolist(),
        over=dict(baseline=float(a.baseline_over.mean()),candidate=float(a.candidate_over.mean()),actual=float(a.actual_over.mean())),
        subgroups=subs,research_screen_pass=bool(bound>0 and (year.candidate_cond_rps<year.baseline_cond_rps).sum()>=3
            and z.candidate_rps.mean()<=z.baseline_rps.mean() and all((bins>=.07)&(bins<=.13)) and no_group_harm))

def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/'manifest.json').exists():raise FileExistsError('Create-only experiment')
    src=Path(__file__).parent
    p=pd.read_parquet(OUT/'feed_extension/joined_player_reports.parquet')
    games=pd.read_parquet(OUT/'games.parquet');teams=pd.read_parquet(OUT/'teams.parquet')
    original=pd.read_parquet(OUT/'players.parquet')
    manifest=dict(started=utc(),rule_sha256=sha(src/'ROLE_RULE.md'),code_sha256={n:sha(src/n) for n in ['role_models.py','role_test.py']},
        inputs={n:sha(OUT/n) for n in ['feed_extension/joined_player_reports.parquet','players.parquet','games.parquet','teams.parquet']},raw_inputs={})
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2))
    raw=[]
    for year in range(2019,2025):
        path=locate(f'stats_player_week_{year}.csv');manifest['raw_inputs'][str(path)]=sha(path)
        x=pd.read_csv(path,usecols=['game_id','team','player_id','position','attempts','season_type'])
        x=x[x.season_type=='REG'].rename(columns={'player_id':'aid'});x.team=x.team.replace(C.FIX);raw.append(x)
    stats=pd.concat(raw,ignore_index=True)
    p=R.primary_labels(R.history_features(p,stats,games),stats)
    p.to_parquet(DEST/'role_features.parquet',index=False)
    results=[];params={};extras=[]
    for year in range(2021,2025):
        tr=p[p.season<year].copy().reset_index(drop=True);z=p[p.season==year].copy().reset_index(drop=True)
        pa_tr,pa=involvement(tr,z)
        tr['pa']=pa_tr;z['pa']=pa
        # Prior-year team volume and player production estimates remain identical.
        tt=teams[(teams.season>=2018)&(teams.season<year)&teams.actual_team_att.notna()&(teams.actual_team_att>0)]
        te=teams[teams.season==year].reset_index(drop=True)
        vm=model('volume').fit(tt[C.VOLUME_FEATURES],tt.actual_team_att)
        disp=C.fit_nb(tt.actual_team_att,np.clip(vm.predict(tt[C.VOLUME_FEATURES]),5,70))
        vp=C.nb_pmf(np.clip(vm.predict(te[C.VOLUME_FEATURES]),5,70),disp,100)
        vi={(r.game_id,r.team):i for i,r in enumerate(te.itertuples())}
        orig=original[(original.season>=2018)&(original.season<year)&(original.app==1)&original.actual_team_att.notna()]
        pri=make_priors(orig)
        lead,states=R.fit_role(tr);qb=z[z.position=='QB'].reset_index(drop=True)
        weights=lead.predict_proba(qb[R.NUM+R.CAT])[:,1]
        trainqb=tr[(tr.position=='QB')&(tr.app==1)]
        k=C.fit_concentration(trainqb.attempts,trainqb.actual_team_att,C.rates(trainqb,pri,'attempts'))
        chunks=[]
        for start in range(0,len(qb),500):
            x=qb.iloc[start:start+500];v=vp[[vi[(r.game_id,r.team)] for r in x.itertuples()]]
            base=C.allocation_pmf(v,C.rates(x,pri,'attempts'),k,100)
            cand=R.qb_pmf(v,weights[start:start+500],states)
            s=scored(x,'attempts',base,cand,x.pa.to_numpy(),np.floor(x.avg_attempts)+.5,year)
            s['recent_primary']=x.last_was_primary.to_numpy().astype(bool);s['prior_primary_out']=x.prior_primary_out.to_numpy().astype(bool)
            s['primary_role_probability']=weights[start:start+500];chunks.append(s)
        results.append(pd.concat(chunks,ignore_index=True))
        rec=z[z.position.isin(['WR','TE','RB','FB'])].reset_index(drop=True)
        rtr=tr[tr.position.isin(['WR','TE','RB','FB'])].reset_index(drop=True)
        ts,catch=R.receiving_parts(rec,pri);tts,tcatch=R.receiving_parts(rtr,pri)
        beta=R.fit_redistribution(rtr,tts,rtr.pa.to_numpy())
        base_ts,repair=R.repair_budget(rec,ts,rec.pa.to_numpy())
        candidate_ts,missing,_=R.redistribute(rec,ts,rec.pa.to_numpy(),beta)
        train_base,_=R.repair_budget(rtr,tts,rtr.pa.to_numpy());train_cand,_,_=R.redistribute(rtr,tts,rtr.pa.to_numpy(),beta)
        active=(rtr.app==1).to_numpy()
        bk=C.fit_concentration(rtr.receptions[active],rtr.actual_team_att[active],(train_base*tcatch)[active])
        ck=C.fit_concentration(rtr.receptions[active],rtr.actual_team_att[active],(train_cand*tcatch)[active])
        legacy_k=C.fit_concentration(rtr.receptions[active],rtr.actual_team_att[active],(tts*tcatch)[active])
        chunks=[]
        for start in range(0,len(rec),500):
            sl=slice(start,start+500);x=rec.iloc[sl];v=vp[[vi[(r.game_id,r.team)] for r in x.itertuples()]]
            base=C.allocation_pmf(v,(base_ts*catch)[sl],bk,40)
            cand=C.allocation_pmf(v,(candidate_ts*catch)[sl],ck,40)
            legacy=C.allocation_pmf(v,(ts*catch)[sl],legacy_k,40)
            s=scored(x,'receptions',base,cand,x.pa.to_numpy(),np.floor(x.avg_receptions)+.5,year)
            s['missing_teammates']=missing[sl]>=.10;s['legacy_cond_rps']=C.rps(legacy,x.receptions,20)
            s['other_missing_share']=missing[sl];chunks.append(s)
        results.append(pd.concat(chunks,ignore_index=True))
        params[year]=dict(qb_states=states,qb_role_model=R.serial_logistic(lead),legacy_qb_concentration=k,
            redistribution_beta=beta,receiving_baseline_concentration=bk,receiving_candidate_concentration=ck,
            expected_budget_repair_rows=int(repair.sum()),receiver_rows=len(rec))
        extras.append(dict(season=year,primary_qb_candidate_coverage=float(qb.groupby(['game_id','team']).actual_primary.max().mean()),
            expected_budget_repair_rows=int(repair.sum())))
        print('Role tests completed',year,'receiver beta',round(beta,5),flush=True)
    paired=pd.concat(results,ignore_index=True);paired.to_parquet(DEST/'paired_scores.parquet',index=False)
    summaries={stat:summary(z) for stat,z in paired.groupby('stat')}
    r=paired[(paired.stat=='receptions')&(paired.app==1)]
    summaries['receptions']['legacy_conditional_rps']=float(r.legacy_cond_rps.mean())
    summaries['receptions']['budget_baseline_conditional_rps']=float(r.baseline_cond_rps.mean())
    record=dict(completed=utc(),results=summaries,parameters=params,coverage=extras,
        deployed=False,market_edge_established=False,limitations=['Four revised-data development seasons',
            'QB role probabilities are marginal, not mutually exclusive joint states','New/never-observed QBs excluded as in baseline',
            'Team passing volume held fixed: no QB-style or ability-volume effect tested','No independent forward archive',
            'Target-budget constraint is in expectation, not joint player draws'])
    (DEST/'results.json').write_text(json.dumps(record,indent=2))
    (DEST/'manifest_complete.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()
