"""Walk-forward evaluation and private previews. Never deploys or places bets."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression,Ridge,PoissonRegressor
from sklearn.metrics import log_loss,brier_score_loss
import core as C
from build import OUT,BASE


def model(kind):
    return make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000) if kind=='win' else
        Ridge(alpha=20) if kind=='score' else PoissonRegressor(alpha=.1,max_iter=1000))


def logscore(p,y):
    return -np.log(np.maximum(p[np.arange(len(p)),np.clip(np.asarray(y,int),0,p.shape[1]-1)],1e-12))


def win_score(y,p):
    keep=y!=0;v=(y[keep]>0).astype(int);p=np.clip(np.asarray(p)[keep],1e-6,1-1e-6)
    return dict(n=int(keep.sum()),log_loss=float(log_loss(v,p,labels=[0,1])),brier=float(brier_score_loss(v,p)))


def game_test(g):
    played=g[g.home_score.notna()&(g.season>=2010)].copy()
    played['margin']=played.home_score-played.away_score;played['total']=played.home_score+played.away_score
    predictions=[];residuals=[];fits={};future=[]
    for year in range(2014,2027):
        train=played[played.season<year]
        z=g[g.season==year].copy()
        if not len(z):continue
        X=train[C.GAME_FEATURES];y=train.margin
        clf=model('win').fit(X[y!=0],(y[y!=0]>0).astype(int))
        margin=model('score').fit(X,y);total=model('score').fit(X,train.total)
        z['p_osf']=clf.predict_proba(z[C.GAME_FEATURES])[:,1]
        z['margin_mean']=margin.predict(z[C.GAME_FEATURES]);z['total_mean']=total.predict(z[C.GAME_FEATURES])
        z['margin']=z.home_score-z.away_score;z['total']=z.home_score+z.away_score
        past=pd.concat(residuals,ignore_index=True) if residuals else pd.DataFrame()
        # Earlier OUT-OF-SEASON errors, not the fitted training residuals.
        if len(past)>=200:
            past=past[past.season>=year-4]
            em=C.empirical_pmf(z.margin_mean.to_numpy(),past.margin_error.to_numpy(),-70,70)
            et=C.empirical_pmf(z.total_mean.to_numpy(),past.total_error.to_numpy(),0,120)
            fm=C.empirical_pmf(z.form_margin.to_numpy(),past.form_margin_error.to_numpy(),-70,70)
            ft=C.empirical_pmf(z.form_total.to_numpy(),past.form_total_error.to_numpy(),0,120)
            z['p_margin_home']=em[:,71:].sum(1);z['p_margin_tie']=em[:,70]
            z['p_margin_home_no_tie']=z.p_margin_home/(1-z.p_margin_tie)
            z['margin_rps']=C.rps(em,z.margin.fillna(0).to_numpy()+70)
            z['total_rps']=C.rps(et,z.total.fillna(0).to_numpy())
            z['form_margin_rps']=C.rps(fm,z.margin.fillna(0).to_numpy()+70)
            z['form_total_rps']=C.rps(ft,z.total.fillna(0).to_numpy())
            if year==2026:
                now=pd.Timestamp.now(tz='UTC')
                for i,row in enumerate(z.itertuples()):
                    if row.tip>now and row.tip<now+pd.Timedelta(days=8):
                        future.append(dict(game_id=row.game_id,tip=str(row.tip),home=row.home,away=row.away,
                            home_win_osf=float(row.p_osf),home_win_elo=float(row.elo_p),
                            margin_mean=float(row.margin_mean),total_mean=float(row.total_mean),
                            margin_pmf=em[i].tolist(),margin_support_start=-70,total_pmf=et[i].tolist(),
                            margin_home_probability=float(row.p_margin_home),tie_probability=float(row.p_margin_tie),
                            experimental=True,not_joint_score_simulator=True))
        done=z[z.home_score.notna()].copy()
        residuals.append(pd.DataFrame(dict(season=year,margin_error=done.margin-done.margin_mean,
            total_error=done.total-done.total_mean,form_margin_error=done.margin-done.form_margin,form_total_error=done.total-done.form_total)))
        if year>=2018:predictions.append(done)
        fits[year]=(clf,margin,total)
        print('Game season',year,len(done),flush=True)
    p=pd.concat(predictions,ignore_index=True)
    p.to_parquet(OUT/'game_predictions.parquet',index=False)
    scored=p[p.season<=2025]
    summary={}
    for key in ('elo_p','p_osf','p_margin_home_no_tie'):
        summary[key]=dict(overall=win_score(scored.margin.to_numpy(),scored[key].to_numpy()),
            by_season={int(y):win_score(x.margin.to_numpy(),x[key].to_numpy()) for y,x in scored.groupby('season')})
    summary['distributions']={stat:dict(rmse=float(np.sqrt(np.mean((scored[stat]-scored[stat+'_mean'])**2))),
        rps=float(scored[stat+'_rps'].mean()),form_rps=float(scored['form_'+stat+'_rps'].mean()),
        paired_season_lower=C.season_bound((scored['form_'+stat+'_rps']-scored[stat+'_rps']).to_numpy(),scored.season),
        seasons_better=int(scored.groupby('season').apply(lambda x:x[stat+'_rps'].mean()<x['form_'+stat+'_rps'].mean(),include_groups=False).sum())) for stat in ('margin','total')}
    summary['tie_diagnostic']=dict(actual=float((scored.margin==0).mean()),predicted=float(scored.p_margin_tie.mean()))
    archived=pd.read_csv(BASE/'outputs/nfl-comprehensive/game_diagnostics.csv.gz')
    archived=archived[(archived.model=='fixed')&(archived.horizon=='next_week')].drop_duplicates('game_id')
    joint=scored.merge(archived[['game_id','prediction','win_log_loss']],on='game_id',validate='one_to_one')
    summary['archived_v4_shared_subset']=dict(n=len(joint),note='Earlier weekly v4 reconstruction, not entire latest live pipeline',
        v4_rmse=float(np.sqrt(np.mean((joint.prediction-joint.margin)**2))),
        new_rmse=float(np.sqrt(np.mean((joint.margin_mean-joint.margin)**2))),v4_win_log_loss=float(joint.win_log_loss.mean()),
        osf_win_log_loss=win_score(joint.margin.to_numpy(),joint.p_osf.to_numpy())['log_loss'])
    bench=pd.read_parquet(OUT/'market_benchmarks.parquet')
    b=scored.merge(bench,on='game_id')
    if 'spread_line' in b:
        valid=b.spread_line.notna()
        summary['closing_benchmark_only']=dict(n=int(valid.sum()),margin_rmse=float(np.sqrt(np.mean((b.loc[valid,'margin']-b.loc[valid,'spread_line'])**2))),
            warning='Closing prices contain later information; never used as features or training labels.')
    return summary,future


def make_priors(train):
    app=train[train.app==1]
    pri={}
    for label,num,den in [('attempt_share','attempts','actual_team_att'),('target_share','targets','actual_team_att'),('catch','receptions','targets')]:
        groups=app.groupby('position')
        pri[label]=(groups[num].sum()/groups[den].sum().replace(0,np.nan)).fillna(.65 if label=='catch' else .05).to_dict()
    return pri


def app_model(train):
    a=train[train.app.notna()]
    return make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000)).fit(a[C.APP_FEATURES],a.app.astype(int))


def props_test(teams,players):
    p=players[players.actual_team_att.notna()&players.app.notna()].copy()
    team=teams[teams.actual_team_att.notna()&(teams.actual_team_att>0)].copy()
    result=[];allrows=[];frozen={};volume_reports=[]
    for year in range(2021,2027):
        tr=team[(team.season>=2018)&(team.season<year)]
        te=teams[teams.season==year].copy()
        vm=model('volume').fit(tr[C.VOLUME_FEATURES],tr.actual_team_att)
        train_mu=np.clip(vm.predict(tr[C.VOLUME_FEATURES]),5,70)
        disp=C.fit_nb(tr.actual_team_att,train_mu)
        mu=np.clip(vm.predict(te[C.VOLUME_FEATURES]),5,70)
        vpm=C.nb_pmf(mu,disp,100)
        vid={(r.game_id,r.team):i for i,r in enumerate(te.itertuples())}
        if year<=2025:
            done=te.actual_team_att.notna().to_numpy();y=te.actual_team_att.to_numpy()[done]
            vb=C.nb_pmf(te.own_att.to_numpy()[done],C.fit_nb(tr.actual_team_att,tr.own_att),100)
            volume_reports.append(dict(season=year,n=int(done.sum()),model_rps=float(C.rps(vpm[done],y,70).mean()),baseline_rps=float(C.rps(vb,y,70).mean())))
        train=p[(p.season>=2018)&(p.season<year)];ap=app_model(train)
        pri=make_priors(train)
        # Include future candidates only for previews; no future labels in fit.
        z=players[players.season==year].copy().reset_index(drop=True)
        pa=np.clip(ap.predict_proba(z[C.APP_FEATURES])[:,1],1e-3,1-1e-3)
        for stat in ('attempts','receptions'):
            isstat=(z.position=='QB') if stat=='attempts' else z.position.isin(['WR','TE','RB','FB'])
            a=train[(train.app==1)&((train.position=='QB') if stat=='attempts' else train.position.isin(['WR','TE','RB','FB']))]
            concentration=C.fit_concentration(a[stat],a.actual_team_att,C.rates(a,pri,stat))
            dispersion={name:C.fit_nb(a[stat],np.maximum(a[name+'_'+stat],.01)) for name in ('avg','recent')}
            zz=z[isstat].reset_index(drop=True);pp=pa[isstat]
            qidx=np.array([vid[(r.game_id,r.team)] for r in zz.itertuples()])
            rate=C.rates(zz,pri,stat);limit=100 if stat=='attempts' else 40;clip=60 if stat=='attempts' else 20
            known=(zz.app.notna()&zz.actual_team_att.notna()).to_numpy()
            records=[];rng=np.random.default_rng(20261023)
            for start in range(0,len(zz),800):
                sl=slice(start,start+800);x=zz.iloc[sl];a_pa=pp[sl]
                cond=C.allocation_pmf(vpm[qidx[sl]],rate[sl],concentration,limit)
                y=x[stat].to_numpy();u=rng.random(len(x));unc=cond*a_pa[:,None];unc[:,0]+=1-a_pa
                data=x[['game_id','team','aid','season','app','position','tip']].copy()
                data['stat']=stat;data['actual']=y;data['pa']=a_pa;data['rps']=C.rps(unc,y,clip)
                data['conditional_rps']=C.rps(cond,y,clip);data['log_score']=logscore(unc,y)
                data['pit']=C.pit(cond,y,u);data['mean']=cond@np.arange(limit+1)
                base=x['avg_'+stat].to_numpy();line=np.floor(base)+.5
                data['line']=line;data['over_actual']=y>line
                data['over_probability']=1-cond.cumsum(1)[np.arange(len(x)),np.clip(np.floor(line).astype(int),0,limit)]
                data['regular_role']=base>=(10 if stat=='attempts' else 2)
                for name in ('avg','recent'):
                    b=C.nb_pmf(np.maximum(x[name+'_'+stat],.01),dispersion[name],limit)
                    bu=b*a_pa[:,None];bu[:,0]+=1-a_pa
                    data[name+'_rps']=C.rps(bu,y,clip)
                data['known']=known[sl]
                records.append(data)
            r=pd.concat(records,ignore_index=True)
            if year<=2025:
                allrows.append(r[r.known])
            else:
                now=pd.Timestamp.now(tz='UTC')
                preview=r[(r.tip>now)&(r.tip<now+pd.Timedelta(days=8))]
                preview.to_parquet(OUT/f'preview_{stat}_2026.parquet',index=False)
            frozen.setdefault(year,{})[stat]=dict(concentration=concentration,baseline_dispersions=dispersion,position_priors=pri)
            print('Props',year,stat,len(r),'concentration',round(concentration,2),flush=True)
    r=pd.concat(allrows,ignore_index=True);r.to_parquet(OUT/'prop_predictions.parquet',index=False)
    for stat,z in r.groupby('stat'):
        a=z[z.app==1];reg=z[z.regular_role]
        item=dict(stat=stat,n=len(z),appearances=len(a),rps=float(z.rps.mean()),
            baseline_rps={name:float(z[name+'_rps'].mean()) for name in ('avg','recent')},
            conditional_pit_deciles=(np.histogram(a.pit,bins=10,range=(0,1))[0]/len(a)).tolist(),
            over_predicted=float(a.over_probability.mean()),over_actual=float(a.over_actual.mean()),
            regular_role_rps=float(reg.rps.mean()),regular_role_baseline_rps={name:float(reg[name+'_rps'].mean()) for name in ('avg','recent')},
            appearance_log_loss=float(log_loss(z.app,np.clip(z.pa,1e-6,1-1e-6),labels=[0,1])),
            by_season={int(y):dict(n=len(x),rps=float(x.rps.mean()),avg_rps=float(x.avg_rps.mean()),recent_rps=float(x.recent_rps.mean())) for y,x in z.groupby('season')})
        item['season_lower']={name:C.season_bound((z[name+'_rps']-z.rps).to_numpy(),z.season) for name in ('avg','recent')}
        item['seasons_better']={name:int(z.groupby('season').apply(lambda x:x.rps.mean()<x[name+'_rps'].mean(),include_groups=False).sum()) for name in ('avg','recent')}
        item['calibration_screen']=all(.07<=d<=.13 for d in item['conditional_pit_deciles'])
        item['promising_screen']=all(v>0 for v in item['season_lower'].values()) and all(v>=4 for v in item['seasons_better'].values()) and item['calibration_screen']
        result.append(item)
    return dict(player_stats=result,team_attempts=volume_reports,frozen=frozen)


def main():
    if (OUT/'results.json').exists():raise FileExistsError('Results already exist; no tuning/overwrite')
    rule=Path(__file__).with_name('RULE.md').read_bytes()
    (OUT/'run_manifest.json').write_text(json.dumps(dict(started_utc=datetime.now(timezone.utc).isoformat(),rule_sha256=hashlib.sha256(rule).hexdigest(),
        code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},market_inputs=False),indent=2))
    g=pd.read_parquet(OUT/'games.parquet');t=pd.read_parquet(OUT/'teams.parquet');p=pd.read_parquet(OUT/'players.parquet')
    games,preview=game_test(g);props=props_test(t,p)
    result=dict(completed_utc=datetime.now(timezone.utc).isoformat(),games=games,props=props,
        evidence='lagged retrospective research; revised inputs; no original-vintage injury/roster replay',deployed=False,market_edge_established=False)
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
    (OUT/'game_preview_2026.json').write_text(json.dumps(dict(generated_utc=result['completed_utc'],research_only=True,forecasts=preview),indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='props'},indent=2))


if __name__=='__main__':main()
