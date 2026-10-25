"""Private existing-feed audit and one pre-specified availability comparison."""
import hashlib,json,sys,re,unicodedata,urllib.request
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
import core as C
from build import OUT,OLD
from run import model,make_priors,app_model

DEST=OUT/'feed_extension'
RAW=OLD/'nfl_availability_v5/raw'
EXTRA=['report_status','practice_status','team_report_evidence']

def digest(b):return hashlib.sha256(b).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def team(s):return {'WSH':'WAS','LAR':'LA','JAC':'JAX','OAK':'LV','SD':'LAC'}.get(str(s),str(s))
def norm(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]','',re.sub(r'\b(jr|sr|ii|iii|iv)\b','',s))

def temporal_join(p,r):
    """Final-file row eligible only if its own modification predates cutoff."""
    p=p.copy();p['_order']=np.arange(len(p))
    p['cutoff']=pd.to_datetime(p.tip,utc=True)-pd.Timedelta(hours=1)
    for c in ('report_status','practice_status'):p[c]='UNKNOWN_NO_ELIGIBLE_ROW'
    p['team_report_evidence']=0
    groups={(int(y),int(w),t):z for (y,w,t),z in r.groupby(['season','week','team'])}
    for (gid,t),ix in p.groupby(['game_id','team']).groups.items():
        first=p.loc[ix[0]];z=groups.get((int(first.season),int(first.week),t))
        if z is None:continue
        z=z[z.source_modified_at<first.cutoff].sort_values('source_modified_at').drop_duplicates('aid',keep='last')
        if not len(z):continue
        p.loc[ix,'team_report_evidence']=1
        z=z.set_index('aid')
        for c in ('report_status','practice_status'):
            value=p.loc[ix,'aid'].map(z[c])
            has=p.loc[ix,'aid'].isin(z.index)
            p.loc[p.loc[ix].index[has],c]=value[has].fillna('LISTED_BLANK').to_numpy()
    return p.sort_values('_order').drop(columns='_order')

def audit_history():
    audits=[];reports=[]
    for path in sorted(RAW.glob('*.csv')):
        if not path.name.startswith(('injuries_','depth_charts_','roster_weekly_')):continue
        raw=path.read_bytes();z=pd.read_csv(path,low_memory=False)
        ts=next((c for c in ('date_modified','dt') if c in z),None)
        item=dict(path=str(path),sha256=digest(raw),rows=len(z),timestamp_column=ts,
                  timestamp_meaning='source modification/update, not historical collection' if ts else 'none; weekly/final snapshot only')
        if ts:
            d=pd.to_datetime(z[ts],utc=True,errors='coerce');item.update(min_time=str(d.min()),max_time=str(d.max()),missing_timestamps=int(d.isna().sum()))
        audits.append(item)
        if path.name.startswith('injuries_') and ts and int(path.stem[-4:]) in range(2020,2025):
            z=z[z.game_type=='REG'].copy();z['team']=z.team.map(team);z=z.rename(columns={'gsis_id':'aid'})
            z['source_modified_at']=pd.to_datetime(z[ts],utc=True,errors='coerce')
            reports.append(z[['season','week','team','aid','report_status','practice_status','source_modified_at']])
    return audits,pd.concat(reports,ignore_index=True)

def fetch(url,label):
    checked=stamp()
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'PrivateNFLResearch/1.0'})
        with urllib.request.urlopen(req,timeout=40) as response:
            data=response.read(150_000_001);final=response.url
        if len(data)>150_000_000:raise ValueError('Size limit')
        name=f'{label}_{digest(data)[:16]}.raw';path=DEST/name
        if not path.exists():path.write_bytes(data)
        return dict(source_url=url,final_url=final,retrieved_at_utc=stamp(),checked_at_utc=checked,
                    source_published_at_utc=None,sha256=digest(data),file=str(path),bytes=len(data),ok=True)
    except Exception as e:return dict(source_url=url,checked_at_utc=checked,ok=False,error=str(e))

def live_audit(output_name='live_feed_audit.json'):
    captures=[fetch('https://www.nfl.com/injuries/','official_injuries'),
              fetch('https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv','depth_2026')]
    ps=pd.read_csv(OUT/'raw_fresh/players.csv',dtype=str)
    candidates=pd.read_parquet(OUT/'players.parquet')
    now=pd.Timestamp.now(tz='UTC');candidates=candidates[(candidates.tip>now)&(candidates.tip<now+pd.Timedelta(days=8))]
    known=candidates[['aid','team','position','name']].drop_duplicates()
    aliases={}
    for r in ps.itertuples():
        for col in ('display_name','first_name','football_name'):
            val=getattr(r,col,None)
            if not isinstance(val,str):continue
            name=val if col=='display_name' else val+' '+str(r.last_name)
            aliases.setdefault(norm(name),set()).add(r.gsis_id)
    rows=[];parse_error=None
    if captures[0]['ok']:
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'pipeline'))
        import nfl_injuries
        try:
            report=nfl_injuries.parse_report(Path(captures[0]['file']).read_bytes().decode('utf-8',errors='replace'))
            for r in report['rows']:
                ids=aliases.get(norm(r['player']),set())
                pool=known[(known.team==team(r['team']))&known.aid.isin(ids)]
                pool=pool[pool.position==r['position']]
                unique=pool.aid.unique()
                rows.append({**r,'aid':str(unique[0]) if len(unique)==1 else None,
                    'mapping':'unique_alias_plus_candidate_team_position' if len(unique)==1 else 'unresolved_or_outside_candidate_roster',
                    'observed_at_utc':captures[0]['retrieved_at_utc'],'source_published_at_utc':None,
                    'report_season':report['season'],'report_week':report['week']})
        except Exception as e:parse_error=str(e)
    depth_audit=None
    if captures[1]['ok']:
        try:
            d=pd.read_csv(captures[1]['file']);ts=pd.to_datetime(d.dt,utc=True,errors='coerce')
            depth_audit=dict(rows=len(d),source_min=str(ts.min()),source_max=str(ts.max()),
                gsis_present=int(d.gsis_id.notna().sum()),future_source_rows=int((ts>pd.Timestamp(captures[1]['retrieved_at_utc'])).sum()),
                note='Latest update is not proof of actual starter; collection time also gates forward eligibility')
        except Exception as e:depth_audit=dict(error=str(e))
    result=dict(captures=captures,parse_error=parse_error,mapped=sum(r['aid'] is not None for r in rows),
        rows=len(rows),depth_audit=depth_audit,rows_mapped=rows,
        limits='Existing collection-only NFL text-news pipeline is inventoried separately in news_inventory files. Blank injury status or missing row is not healthy.')
    path=DEST/output_name
    if path.exists():raise FileExistsError(path)
    path.write_text(json.dumps(result,indent=2))
    return {k:v for k,v in result.items() if k!='rows_mapped'}

def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/'results.json').exists():raise FileExistsError('Create only')
    (DEST/'manifest.json').write_text(json.dumps(dict(started=stamp(),rule_sha256=digest(Path(__file__).with_name('FEED_RULE.md').read_bytes()),
        code_sha256=digest(Path(__file__).read_bytes()),source_player_sha256=digest((OUT/'players.parquet').read_bytes())),indent=2))
    audits,reports=audit_history();(DEST/'source_audit.json').write_text(json.dumps(audits,indent=2))
    p=pd.read_parquet(OUT/'players.parquet');p=p[p.season.between(2020,2024)&p.app.notna()&p.actual_team_att.notna()].copy().reset_index(drop=True)
    p=temporal_join(p,reports);p.to_parquet(DEST/'joined_player_reports.parquet',index=False)
    teams=pd.read_parquet(OUT/'teams.parquet');out=[];appearance=[]
    for year in range(2021,2025):
        train=p[p.season<year];z=p[p.season==year].copy().reset_index(drop=True)
        baseline=app_model(train)
        tx=ColumnTransformer([('numeric',StandardScaler(),C.APP_FEATURES),('reports',OneHotEncoder(handle_unknown='ignore'),EXTRA)])
        challenger=make_pipeline(tx,LogisticRegression(C=1,max_iter=1000)).fit(train[C.APP_FEATURES+EXTRA],train.app.astype(int))
        pb=np.clip(baseline.predict_proba(z[C.APP_FEATURES])[:,1],.001,.999)
        pc=np.clip(challenger.predict_proba(z[C.APP_FEATURES+EXTRA])[:,1],.001,.999)
        appearance.append(dict(season=year,n=len(z),baseline_logloss=log_loss(z.app,pb),challenger_logloss=log_loss(z.app,pc),
            listed_rows=int((z.report_status!='UNKNOWN_NO_ELIGIBLE_ROW').sum()),team_report_evidence=int(z.team_report_evidence.sum())))
        ttr=teams[(teams.season>=2018)&(teams.season<year)&teams.actual_team_att.notna()&(teams.actual_team_att>0)]
        te=teams[teams.season==year].reset_index(drop=True)
        vm=model('volume').fit(ttr[C.VOLUME_FEATURES],ttr.actual_team_att)
        dispersion=C.fit_nb(ttr.actual_team_att,np.clip(vm.predict(ttr[C.VOLUME_FEATURES]),5,70))
        vpm=C.nb_pmf(np.clip(vm.predict(te[C.VOLUME_FEATURES]),5,70),dispersion,100)
        vid={(r.game_id,r.team):i for i,r in enumerate(te.itertuples())}
        original=pd.read_parquet(OUT/'players.parquet');original=original[(original.season>=2018)&(original.season<year)&(original.app==1)&original.actual_team_att.notna()]
        pri=make_priors(original)
        for stat in ('attempts','receptions'):
            mask=(z.position=='QB') if stat=='attempts' else z.position.isin(['WR','TE','RB','FB'])
            zz=z[mask].reset_index(drop=True)
            tr=original[(original.position=='QB') if stat=='attempts' else original.position.isin(['WR','TE','RB','FB'])]
            concentration=C.fit_concentration(tr[stat],tr.actual_team_att,C.rates(tr,pri,stat))
            volume_idx=np.array([vid[(r.game_id,r.team)] for r in zz.itertuples()])
            limit=100 if stat=='attempts' else 40;clip=60 if stat=='attempts' else 20
            rate=C.rates(zz,pri,stat)
            bpa=pb[mask];cpa=pc[mask]
            for start in range(0,len(zz),800):
                sl=slice(start,start+800);x=zz.iloc[sl]
                cond=C.allocation_pmf(vpm[volume_idx[sl]],rate[sl],concentration,limit)
                bp=cond*bpa[sl,None];bp[:,0]+=1-bpa[sl]
                cp=cond*cpa[sl,None];cp[:,0]+=1-cpa[sl]
                rec=x[['game_id','team','aid','season','app','report_status','practice_status']].copy()
                rec['stat']=stat;rec['base_rps']=C.rps(bp,x[stat],clip);rec['candidate_rps']=C.rps(cp,x[stat],clip)
                rec['base_pa']=bpa[sl];rec['candidate_pa']=cpa[sl];out.append(rec)
        print('Feed experiment',year,appearance[-1],flush=True)
    scores=pd.concat(out,ignore_index=True);scores.to_parquet(DEST/'paired_scores.parquet',index=False)
    results={}
    for stat,z in scores.groupby('stat'):
        y=z.groupby('season')[['base_rps','candidate_rps']].mean()
        results[stat]=dict(n=len(z),baseline_rps=float(z.base_rps.mean()),candidate_rps=float(z.candidate_rps.mean()),
            relative_gain=float(1-z.candidate_rps.mean()/z.base_rps.mean()),season_lower=C.season_bound(z.base_rps-z.candidate_rps,z.season),
            seasons_better=int((y.candidate_rps<y.base_rps).sum()),by_season=y.reset_index().to_dict('records'))
    result=dict(appearance=appearance,props=results,live=live_audit(),completed_at=stamp(),deployed=False,
        limitation='Timestamp-screened revised historical injury rows, not original vintages. Four seasons, development evidence. No actual-starter or target-volume redistribution test.')
    (DEST/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(results,indent=2))

if __name__=='__main__':main()
