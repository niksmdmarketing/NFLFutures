"""Export frozen v1.1 distributions without reading price files or refitting models.

Receipt-proved snapshots remain byte-equivalent distributions. Missing snapshots
receive explicitly supplementary, cutoff-filtered reconstructions using revised
nflverse vintages and no invented historical injury reports.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,gzip,hashlib,json,subprocess,sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
import nfl_props as B
import nfl_props_v11 as V
import nfl_props_score as S
import nfl_props_receipts as R
import nfl_prop_identity as I

MODEL=V.MODEL_ID
FROZEN=['pipeline/nfl_props.py','pipeline/nfl_props_v11.py','model/nfl_player_props_v1.json']
AS_OF_DEFAULT='2026-11-05T14:56:17Z'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def prior_games(schedule,cut):
    return set(schedule.loc[schedule.kickoff+pd.Timedelta(hours=6)<cut,'game_id'])

def depth_at(depth,team,cut):
    d=depth[depth.team.eq(team)&depth.dt.le(cut)&depth.gsis_id.notna()].copy()
    if d.empty:return d
    d=d[d.dt.eq(d.dt.max())]
    return d.sort_values(['team','pos_abb','pos_rank']).drop_duplicates(['team','gsis_id'])

def aliases(ids):
    out={}
    for aid,z in ids[ids.gsis_id.notna()].groupby('gsis_id'):
        espns={str(x) for x in z.espn_id.dropna() if str(x) not in ('','nan')}
        names=set()
        for c in ('display_name',):
            if c in z:names.update(str(x) for x in z[c].dropna() if str(x))
        for _,r in z.iterrows():
            for c in ('first_name','common_first_name','football_name'):
                if pd.notna(r.get(c)) and pd.notna(r.get('last_name')):
                    names.add(str(r[c])+' '+str(r['last_name'])+(' '+str(r['suffix']) if pd.notna(r.get('suffix')) else ''))
        out[str(aid)]={'espn_id':next(iter(espns)) if len(espns)==1 else '', 'name_aliases':sorted(names)}
    return out

def prepared(data):
    schedule=pd.read_csv(data/'games.csv',usecols=['game_id','season','week','game_type','gameday','gametime','home_team','away_team','home_score','away_score','location'],low_memory=False)
    schedule=B._kickoffs(schedule)
    for c in ('home_team','away_team'):schedule[c]=schedule[c].replace(V.FIX)
    weekly=pd.concat([pd.read_csv(data/f'stats_player_week_{y}.csv',low_memory=False) for y in (2025,2026)],ignore_index=True)
    weekly=weekly[weekly.season_type.eq('REG')].copy()
    weekly['team']=weekly.team.replace(V.FIX);weekly['opponent_team']=weekly.opponent_team.replace(V.FIX)
    ids=pd.read_csv(data/'players.csv',dtype=str,low_memory=False)
    n=ids.dropna(subset=['pfr_id','gsis_id']).groupby('pfr_id').gsis_id.nunique()
    mp=ids[ids.pfr_id.isin(n[n.eq(1)].index)].drop_duplicates('pfr_id').set_index('pfr_id').gsis_id
    snaps=pd.concat([pd.read_csv(data/f'snap_counts_{y}.csv',low_memory=False) for y in (2025,2026)],ignore_index=True)
    snaps=snaps[snaps.game_type.eq('REG')].copy();snaps['aid']=snaps.pfr_player_id.map(mp);snaps=snaps[snaps.aid.notna()]
    snaps['team']=snaps.team.replace(V.FIX)
    depth=pd.read_csv(data/'depth_charts_2026.csv',dtype={'gsis_id':str,'espn_id':str},low_memory=False)
    depth['dt']=pd.to_datetime(depth.dt,utc=True,errors='coerce');depth['team']=depth.team.replace(V.FIX)
    agg=pd.concat([V.team_pbp(data/f'play_by_play_{y}.csv.gz') for y in (2025,2026)],ignore_index=True)
    totals=weekly.groupby(['game_id','team']).attempts.sum().to_dict()
    games=V.load_games(schedule.drop(columns=['kickoff']))
    return schedule,weekly,snaps,depth,ids,agg,totals,games

def reconstruct(target,cut,inputs,feature_cache):
    schedule,weekly,snaps,depth,ids,agg,totals,games=inputs
    known=prior_games(schedule,cut)
    w=weekly[weekly.game_id.isin(known)].copy();s=snaps[snaps.game_id.isin(known)].copy()
    d=pd.concat([depth_at(depth,t,cut) for t in (target.home_team,target.away_team)],ignore_index=True)
    missing=[t for t in (target.home_team,target.away_team) if d[d.team.eq(t)&d.pos_abb.eq('QB')].empty]
    if missing:raise ValueError('No pre-cutoff QB depth chart for '+','.join(missing))
    one=schedule[schedule.game_id.eq(target.game_id)].copy()
    # Isolate the original forecast builder; all probability/availability/allocation functions stay frozen.
    with patch.object(B,'games',return_value=one),patch.object(B,'_latest_depth',return_value=(d,None)),patch.object(B,'_weekly',return_value=(w,[])),patch.object(B,'_snaps',return_value=(s,[])),patch.object(B,'_availability',return_value=([],[])):
        base=B.make_forecast(now=cut)
    if cut not in feature_cache:
        feature_cache[cut]=V.team_features(games,agg,totals,now=cut)
    result=V.make_v11(base,feature_cache[cut])
    result['historical_reconstruction']={'historical_news_available':False,'depth_latest_utc':d.dt.max().isoformat(),
         'latest_completed_input_kickoff_utc':schedule.loc[schedule.game_id.isin(known)&schedule.game_id.isin(w.game_id),'kickoff'].max().isoformat(),
         'depth_times':{t:d[d.team.eq(t)].dt.max().isoformat() for t in (target.home_team,target.away_team)}}
    return result

def export_rows(snapshot,game,meta,id_map):
    out=[]
    for tr in game['teams']:
        for p in tr['players']:
            pmf=p['pmf']
            if any(not np.isfinite(v) or v<0 for v in pmf) or abs(sum(pmf)-1)>1e-8:raise ValueError('Invalid archived/reconstructed distribution')
            identity=id_map.get(str(p['player_id']),{'espn_id':'','name_aliases':[]})
            sources=[R.timestamp(t) for t in p.get('source_times',[]) if t]
            future_source=any(t>R.timestamp(snapshot['generated_utc']) for t in sources)
            row={**meta,'model_id':MODEL,'gsis_id':str(p['player_id']),'espn_id':identity['espn_id'],'name':p['name'],
                 'position':p['position'],'team':tr['team'],'opponent':game['home'] if tr['team']==game['away'] else game['away'],
                 'name_aliases':identity['name_aliases'],'generated_utc':snapshot['generated_utc'],'appearance_probability':p['availability_probability'],
                 'stat':p['stat'],'pmf':pmf,'distribution':'conditional_on_appearance','support_min':0,'tail_pooled_at':len(pmf)-1,
                 'report_status':p.get('report_status'),'source_times':p.get('source_times',[]),'future_source_detected':future_source,
                 'primary_eligible':meta['source_tier']=='receipt_proved' and not future_source}
            out.append(row)
    return out

def run(data,archive,output,as_of):
    data,archive,output=Path(data),Path(archive),Path(output)
    if output.exists():raise FileExistsError('Use a new output directory; preserve previous exports')
    output.mkdir(parents=True)
    now=pd.Timestamp(as_of)
    if now.tzinfo is None:raise ValueError('as_of requires an explicit timezone')
    # This manifest is written BEFORE any distributions are generated.
    frozen={name:sha(ROOT/name) for name in FROZEN}
    expected={name:hashlib.sha256(subprocess.check_output(['git','-C',str(ROOT),'show','370ceb4:'+name])).hexdigest() for name in FROZEN}
    if frozen!=expected:raise ValueError('Frozen model code/parameters differ from preregistered revision')
    manifest={'schema':1,'as_of_utc':now.isoformat(),'model_id':MODEL,'rule_freeze_commit':'9434ed1',
              'frozen_files':frozen,'export_code_sha256':sha(__file__),'identity_code_sha256':sha(Path(__file__).with_name('nfl_prop_identity.py')),
              'prices_read':False,'model_refitted':False,'status':'running',
              'input_files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in data.iterdir() if p.is_file() and not p.name.endswith('.part')},
              'nba_rule_review_ref':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','origin/claude/nba-props-price-test']).decode().strip(),
              'archive_revision':subprocess.check_output(['git','-C',str(archive),'rev-parse','HEAD']).decode().strip()}
    receipt_file=archive/'scores/github_push_activity.json'
    manifest['receipt_evidence_sha256']=sha(receipt_file)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    document=json.loads(receipt_file.read_text(encoding='utf-8'))
    if document.get('repository')!='niksmdmarketing/NFLFutures' or document.get('branch')!='nfl-props-v11-archive':raise ValueError('Wrong receipt evidence')
    selected={h:S.choose(archive,h,document['pushes']) for h in (60,360)}
    inputs=prepared(data)
    schedule=inputs[0]
    targets=schedule[schedule.season.eq(2026)&schedule.game_type.eq('REG')&schedule.kickoff.le(now)].sort_values(['kickoff','game_id'])
    ids=aliases(inputs[4]);cache={};coverage=[];records=[];fixtures=[]
    for i,target in enumerate(targets.itertuples()):
        fixtures.append({'game_id':target.game_id,'home':target.home_team,'away':target.away_team,'kickoff_utc':target.kickoff.isoformat()})
        for horizon in (60,360):
            cut=target.kickoff-pd.Timedelta(minutes=horizon)
            meta={'game_id':target.game_id,'season':2026,'week':int(target.week),'game_type':'REG','kickoff_utc':target.kickoff.isoformat(),
                  'horizon_minutes':horizon,'cutoff_utc':cut.isoformat(),'params_sha256':frozen['model/nfl_player_props_v1.json'],
                  'receipt_utc':None,'snapshot':None,'source_tier':'reconstruction','historical_availability':'not_reconstructed',
                  'source_vintage':'revised_nflverse_files','schedule_match':True}
            archived=selected[horizon].get(target.game_id)
            try:
                if archived:
                    rec,index=archived
                    snapshot=json.loads((archive/index['file']).read_text(encoding='utf-8'))
                    if snapshot.get('model_id')!=MODEL or snapshot.get('v11',{}).get('parameters_sha256')!=frozen['model/nfl_player_props_v1.json']:
                        raise ValueError('Archived model/parameter mismatch; no silent reconstruction substitution')
                    if R.timestamp(index['kickoff_utc'])!=R.timestamp(target.kickoff.isoformat()):raise ValueError('Archived kickoff no longer matches schedule')
                    meta.update(receipt_utc=rec.isoformat(),snapshot=index['file'],snapshot_sha256=index['sha256'],
                                source_tier='receipt_proved',historical_availability='original_archived_inputs',source_vintage='original_forecast_snapshot')
                else:
                    snapshot=reconstruct(target,cut,inputs,cache)
                    meta.update(snapshot['historical_reconstruction'])
                game=next(g for g in snapshot['games'] if g['game_id']==target.game_id)
                rows=export_rows(snapshot,game,meta,ids)
                if not rows:raise ValueError('No forecast players')
                records.extend(rows)
                coverage.append({'game_id':target.game_id,'horizon_minutes':horizon,'status':'exported','source_tier':meta['source_tier'],
                                 'rows':len(rows),'primary_rows':sum(r['primary_eligible'] for r in rows),'reason':''})
            except Exception as exc:
                coverage.append({'game_id':target.game_id,'horizon_minutes':horizon,'status':'excluded','source_tier':meta['source_tier'],'rows':0,'primary_rows':0,'reason':str(exc)})
            # Features for unrelated future cutoffs are not reused. Bound memory to one game.
        cache.clear()
        print(f'{i+1}/{len(targets)} {target.game_id}',flush=True)
    playoffs=schedule[schedule.gameday.astype(str).str.startswith('2026-01')&~schedule.game_type.eq('REG')]
    for target in playoffs.itertuples():
        for h in (60,360):coverage.append({'game_id':target.game_id,'horizon_minutes':h,'status':'unsupported','source_tier':'none','rows':0,'primary_rows':0,'reason':'Frozen model/scorer supports regular-season games only'})
    fields=sorted(set().union(*(r.keys() for r in records))) if records else []
    with gzip.open(output/'probabilities.csv.gz','wt',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in records:writer.writerow({k:json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    with gzip.open(output/'probabilities.jsonl.gz','wt',encoding='utf-8') as f:
        for row in records:f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
    with (output/'coverage.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(coverage[0]));writer.writeheader();writer.writerows(coverage)
    (output/'fixtures.json').write_text(json.dumps(fixtures,indent=2),encoding='utf-8')
    identity_rows=[{k:r.get(k) for k in ('game_id','horizon_minutes','cutoff_utc','stat','team','opponent','name','gsis_id','espn_id','position','name_aliases','source_tier')} for r in records]
    (output/'player_index.json').write_text(json.dumps(identity_rows,separators=(',',':')),encoding='utf-8')
    counts={h:{'games':len(targets),'exported_games':sum(c['status']=='exported' and c['horizon_minutes']==h for c in coverage),
               'receipt_games':sum(c['source_tier']=='receipt_proved' and c['status']=='exported' and c['horizon_minutes']==h for c in coverage),
               'rows':sum(r['horizon_minutes']==h for r in records),'primary_rows':sum(r['horizon_minutes']==h and r['primary_eligible'] for r in records)} for h in (60,360)}
    manifest.update(status='complete',summary=counts,unsupported_january_playoff_games=len(playoffs),
                    output_files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='manifest.json'})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest['summary'],indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--as-of',default=AS_OF_DEFAULT)
    a=p.parse_args();run(a.data,a.archive,a.output,a.as_of)
