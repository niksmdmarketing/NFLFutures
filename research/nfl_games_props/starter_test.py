"""One-season dated-depth pilot with rolling, earlier-game-only calibration."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
import core as C
import role_models as R
import starter_models as S
from role_test import scored
from build import OUT,locate
from run import model
from feed_test import RAW,EXTRA
from datetime import datetime,timezone

DEST=OUT/'starter_extension'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()

def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/'manifest.json').exists():raise FileExistsError('Create-only')
    src=Path(__file__).parent;dp=RAW/'depth_charts_2025.csv'
    manifest=dict(started=now(),rule_sha256=sha(src/'STARTER_RULE.md'),
        code_sha256={n:sha(src/n) for n in ['starter_models.py','starter_test.py']},
        inputs={str(dp):sha(dp)},market_inputs=False)
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2))
    games=pd.read_parquet(OUT/'games.parquet');teams=pd.read_parquet(OUT/'teams.parquet')
    base=pd.read_parquet(OUT/'players.parquet');base=base[(base.season==2025)&(base.position=='QB')].copy()
    train=pd.read_parquet(OUT/'role_extension/role_features.parquet');train=train[train.season<=2024]
    stats=[]
    for year in range(2019,2026):
        path=locate(f'stats_player_week_{year}.csv');manifest['inputs'][str(path)]=sha(path)
        z=pd.read_csv(path,usecols=['game_id','season','season_type','team','player_id','player_display_name','position','attempts'])
        z=z[z.season_type=='REG'].rename(columns={'player_id':'aid','player_display_name':'name'});z.team=z.team.replace(C.FIX);stats.append(z)
    stats=pd.concat(stats,ignore_index=True)
    totals=stats.groupby(['game_id','team']).attempts.sum().rename('team_attempts')
    qs=stats[stats.position=='QB'].merge(totals,on=['game_id','team'],validate='many_to_one').merge(games[['game_id','tip']],on='game_id',validate='many_to_one')
    qs['ready']=qs.tip+pd.Timedelta(hours=6)
    ids=pd.read_csv(OUT/'raw_fresh/players.csv',dtype=str)
    idgroups=ids.dropna(subset=['pfr_id','gsis_id']).groupby('pfr_id').gsis_id.agg(lambda x:sorted(set(x)))
    lookup={k:v[0] for k,v in idgroups.items() if len(v)==1}
    snaps=[]
    for year in (2024,2025):
        path=locate(f'snap_counts_{year}.csv');manifest['inputs'][str(path)]=sha(path)
        z=pd.read_csv(path);z=z[z.game_type=='REG'].copy();z['aid']=z.pfr_player_id.map(lookup);z.team=z.team.replace(C.FIX)
        z=z.merge(games[['game_id','season','tip']],on='game_id',validate='many_to_one',suffixes=('_raw',''))
        z['ready']=z.tip+pd.Timedelta(hours=6);snaps.append(z)
    sn=pd.concat(snaps,ignore_index=True)
    complete=sn.groupby(['game_id','team']).agg(n=('offense_snaps',lambda x:int((x>0).sum())),total=('offense_snaps','sum'),maximum=('offense_snaps','max'))
    complete['complete']=(complete.n>=11)&(complete.total>=.9*11*complete.maximum)&(complete.total<=1.2*11*complete.maximum)
    unmapped=sn.assign(bad=sn.aid.isna()&(sn.offense_snaps>0)&sn.position.isin(['QB','WR','TE','RB','FB'])).groupby(['game_id','team']).bad.sum()
    complete['complete'] &= unmapped.eq(0)
    snap={(r.game_id,r.team,r.aid):r.offense_snaps for r in sn[sn.aid.notna()].itertuples()}
    depth=pd.read_csv(dp,dtype={'gsis_id':str,'espn_id':str})
    # Crosswalk IDs only; ambiguous ESPN IDs remain missing.
    em=ids.dropna(subset=['espn_id','gsis_id']).groupby('espn_id').gsis_id.agg(lambda x:sorted(set(x)))
    em={k:v[0] for k,v in em.items() if len(v)==1}
    depth['gsis_id']=depth.gsis_id.fillna(depth.espn_id.map(em))
    index=S.DepthIndex(depth)
    base['added_candidate']=False;base['fallback_history_games']=np.nan
    base['report_status']='UNKNOWN_NO_ELIGIBLE_ROW';base['practice_status']='UNKNOWN_NO_ELIGIBLE_ROW';base['team_report_evidence']=0
    existing=set(zip(base.game_id,base.team,base.aid));added=[];depths={};coverage=[]
    for t in teams[teams.season==2025].itertuples(index=False):
        cut=pd.Timestamp(t.tip)-pd.Timedelta(hours=1);d,status=index.at(t.team,cut)
        depths[(t.game_id,t.team)]=(d,status)
        coverage.append(dict(game_id=t.game_id,team=t.team,week=int(t.week),snapshot_status=status,
            source_update=str(d.time.iloc[0]) if d is not None else None,
            rank_one_ambiguous=bool(d is not None and len(d[d.pos_rank==1])!=1)))
        if d is None:continue
        for r in d.itertuples():
            if (t.game_id,t.team,r.gsis_id) in existing:continue
            added.append(S.fallback(t._asdict(),r.gsis_id,r.player_name,qs,sn));existing.add((t.game_id,t.team,r.gsis_id))
    p=pd.concat([base,pd.DataFrame(added)],ignore_index=True)
    # Labels attached AFTER candidate construction and lagged fallback features.
    actual={(r.game_id,r.team,r.aid):r.attempts for r in qs.itertuples()}
    p['attempts']=[actual.get((r.game_id,r.team,r.aid),0.) for r in p.itertuples()]
    p['actual_team_att']=[totals.get((r.game_id,r.team),np.nan) for r in p.itertuples()]
    def label(r):
        if r.attempts>0 or snap.get((r.game_id,r.team,r.aid),0)>0:return 1.
        return 0. if (r.game_id,r.team) in complete.index and complete.loc[(r.game_id,r.team),'complete'] else np.nan
    p['app']=[label(r) for r in p.itertuples()]
    p=R.primary_labels(R.history_features(p,stats,games),stats)
    p['depth_signal']=[S.signals(depths[(r.game_id,r.team)][0]).get(r.aid,0.) for r in p.itertuples()]
    role,states=R.fit_role(train);p['base_role']=role.predict_proba(p[R.NUM+R.CAT])[:,1]
    tx=ColumnTransformer([('numeric',StandardScaler(),C.APP_FEATURES),('reports',OneHotEncoder(handle_unknown='ignore'),EXTRA)])
    app=make_pipeline(tx,LogisticRegression(C=1,max_iter=1000)).fit(train[C.APP_FEATURES+EXTRA],train.app.astype(int))
    p['pa']=np.clip(app.predict_proba(p[C.APP_FEATURES+EXTRA])[:,1],.001,.999)
    p['ready']=p.tip+pd.Timedelta(hours=6)
    ttrain=teams[(teams.season>=2018)&(teams.season<=2024)&teams.actual_team_att.notna()&(teams.actual_team_att>0)]
    vm=model('volume').fit(ttrain[C.VOLUME_FEATURES],ttrain.actual_team_att)
    disp=C.fit_nb(ttrain.actual_team_att,np.clip(vm.predict(ttrain[C.VOLUME_FEATURES]),5,70))
    te=teams[teams.season==2025].reset_index(drop=True);vp=C.nb_pmf(np.clip(vm.predict(te[C.VOLUME_FEATURES]),5,70),disp,100)
    vi={(r.game_id,r.team):i for i,r in enumerate(te.itertuples())}
    scores=[];fits=[];rngseed=20261024
    for gid,z in p.groupby('game_id',sort=False):
        z=z.reset_index(drop=True);cut=pd.Timestamp(z.tip.iloc[0])-pd.Timedelta(hours=1);week=int(z.week.iloc[0])
        earlier=p[(p.ready<cut)&(p.app==1)]
        if week<5 or earlier.week.nunique()<4:continue
        beta=S.fit_depth(earlier.base_role,earlier.depth_signal,earlier.actual_primary)
        z['candidate_role']=S.shifted_probability(z.base_role,z.depth_signal,beta)
        volume=vp[[vi[(r.game_id,r.team)] for r in z.itertuples()]]
        b=R.qb_pmf(volume,z.base_role.to_numpy(),states);c=R.qb_pmf(volume,z.candidate_role.to_numpy(),states)
        s=scored(z,'attempts',b,c,z.pa.to_numpy(),np.floor(z.avg_attempts)+.5,rngseed+week)
        for col in ['added_candidate','depth_signal','actual_primary','last_was_primary']:
            s[col]=z[col].to_numpy()
        s['week']=week;s['beta']=beta;s['known']=z.app.notna().to_numpy()
        scores.append(s);fits.append(dict(game_id=gid,week=week,cutoff=str(cut),earlier_involved=len(earlier),
            last_training_game_ready=str(earlier.ready.max()),beta=beta))
    paired=pd.concat(scores,ignore_index=True);paired.to_parquet(DEST/'paired_scores.parquet',index=False)
    p.to_parquet(DEST/'expanded_features.parquet',index=False)
    active=paired[paired.app==1];weeks=active.groupby('week')[['baseline_cond_rps','candidate_cond_rps']].mean()
    bins=np.histogram(active.candidate_pit,bins=10,range=(0,1))[0]/len(active)
    def summarise(z):
        return dict(n=len(z),baseline=float(z.baseline_cond_rps.mean()),candidate=float(z.candidate_cond_rps.mean()),
            relative_gain=float(1-z.candidate_cond_rps.mean()/z.baseline_cond_rps.mean()))
    sub={str(k):summarise(z) for k,z in active.groupby('added_candidate')}
    changed=active[(active.actual_primary==1)&(active.last_was_primary==0)]
    leads=stats[(stats.season==2025)&(stats.position=='QB')&(stats.attempts>0)].sort_values(['attempts','aid'],ascending=[False,True]).drop_duplicates(['game_id','team'])
    oldset=set(zip(base.game_id,base.team,base.aid));newset=set(zip(p.game_id,p.team,p.aid))
    primary_coverage=dict(total_team_games=len(leads),legacy_primary_covered=sum((r.game_id,r.team,r.aid) in oldset for r in leads.itertuples()),
        expanded_primary_covered=sum((r.game_id,r.team,r.aid) in newset for r in leads.itertuples()))
    main=summarise(active);main.update(pit_deciles=bins.tolist(),weeks_better=int((weeks.candidate_cond_rps<weeks.baseline_cond_rps).sum()),
        by_week=weeks.reset_index().to_dict('records'),subgroups=sub,actual_new_primary_diagnostic=summarise(changed),
        unconditional_baseline=float(paired[paired.known].baseline_rps.mean()),unconditional_candidate=float(paired[paired.known].candidate_rps.mean()),
        over=dict(baseline=float(active.baseline_over.mean()),candidate=float(active.candidate_over.mean()),actual=float(active.actual_over.mean())))
    main['promising_pilot']=bool(main['relative_gain']>0 and main['weeks_better']>=8 and all((bins>=.07)&(bins<=.13)) and all(x['relative_gain']>=-.02 for x in sub.values()))
    result=dict(completed=now(),results=main,coverage=primary_coverage,added_rows=len(added),unknown_outcomes=int(p.app.isna().sum()),
        depth_status_counts=pd.Series([x['snapshot_status'] for x in coverage]).value_counts().to_dict(),
        fitted_role_states=states,rolling_fits=fits,deployed=False,
        limits=['One revised-data season only','No dated 2025 injury statuses available','Depth order is not confirmed starter',
                'Same involvement probability in both versions; no participation improvement claimed','No original-vintage or independent forward archive'])
    (DEST/'results.json').write_text(json.dumps(result,indent=2));(DEST/'snapshot_coverage.json').write_text(json.dumps(coverage,indent=2))
    manifest['inputs']['games.parquet']=sha(OUT/'games.parquet');manifest['inputs']['players.parquet']=sha(OUT/'players.parquet')
    manifest['inputs']['role_features.parquet']=sha(OUT/'role_extension/role_features.parquet')
    (DEST/'manifest_complete.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='rolling_fits'},indent=2))

if __name__=='__main__':main()
