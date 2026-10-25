"""Freeze conditional workload parameters and editable assumptions; no news logic."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import core as C
from build import OUT,BASE,locate

DEST=BASE/'outputs/nfl_conditional_props_20261024'
def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def first_qb_samples(year):
    sp=locate(f'stats_player_week_{year}.csv');bp=locate(f'play_by_play_{year}.csv.gz')
    s=pd.read_csv(sp,usecols=['game_id','team','season_type','player_id','position','attempts'])
    s=s[s.season_type=='REG'].rename(columns={'player_id':'aid'});s.team=s.team.replace(C.FIX)
    total=s.groupby(['game_id','team']).attempts.sum().rename('team_attempts')
    q=s[s.position=='QB'].copy();ids=set(q.aid.dropna())
    cols={'game_id','posteam','play_id','qb_dropback','passer_player_id','rusher_player_id','play_type'}
    b=pd.read_csv(bp,usecols=lambda c:c in cols,low_memory=False)
    b['aid']=b.passer_player_id.fillna(b.rusher_player_id)
    b=b[(b.qb_dropback==1)&b.aid.isin(ids)&b.play_type.isin(['pass','run'])].copy();b.posteam=b.posteam.replace(C.FIX)
    first=b.sort_values(['game_id','play_id']).drop_duplicates(['game_id','posteam'])[['game_id','posteam','aid']].rename(columns={'posteam':'team'})
    z=first.merge(q[['game_id','team','aid','attempts']],on=['game_id','team','aid'],validate='one_to_one').merge(total,on=['game_id','team'],validate='many_to_one')
    z=z[(z.team_attempts>0)&(z.attempts<=z.team_attempts)].copy();z['season']=year
    return z,{str(sp):sha(sp),str(bp):sha(bp)}

def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/'build_manifest.json').exists():raise FileExistsError('Create-only build')
    src=Path(__file__).parent;manifest=dict(started=now(),rule_sha256=sha(src/'CONDITIONAL_RULE.md'),
        code_sha256={n:sha(src/n) for n in ['conditional_engine.py','conditional_build.py']},inputs={})
    (DEST/'build_manifest.json').write_text(json.dumps(manifest,indent=2))
    samples=[]
    for year in range(2020,2026):
        z,used=first_qb_samples(year);samples.append(z);manifest['inputs'].update(used)
        print('Starting-role workload labels',year,len(z),flush=True)
    samples=pd.concat(samples,ignore_index=True);samples.to_parquet(DEST/'starting_role_training.parquet',index=False)
    share=float((samples.attempts.sum()+100*.95)/(samples.team_attempts.sum()+100))
    state=dict(share=share,concentration=C.fit_concentration(samples.attempts,samples.team_attempts,np.full(len(samples),share)),
        samples=len(samples),early_exit_proxy_share=float((samples.attempts<.5*samples.team_attempts).mean()),
        label='first identifiable QB dropback; not official announced-starter ground truth')
    fpath=OUT/'frozen_2026.json';f=json.loads(fpath.read_text());manifest['inputs'][str(fpath)]=sha(fpath)
    frozen=dict(model_id='nfl-conditional-props-v1-experimental',created_at=now(),training_last_season=2025,
        starting_role=state,volume=f['volume'],volume_dispersion=f['volume_dispersion'],receiving=f['props']['receptions'],
        market_inputs=False,automatic_availability=False,
        limits=['Assumptions, not confirmed lineups','No automatic injury or news adjustment','QB selection does not alter team volume',
            'Marginal distributions, not joint team simulation','No market edge established','Unseen receiver role uses position-prior fallback'])
    with (DEST/'model.json').open('x') as h:json.dump(frozen,h,indent=2)
    # Identity/roster context only. Do not read injury rows or eliminate Out players.
    audit=json.loads((OUT/'feed_extension/live_feed_audit_network_verified.json').read_text());dp=Path(audit['captures'][1]['file'])
    d=pd.read_csv(dp,dtype={'gsis_id':str});d.team=d.team.replace(C.FIX);d['updated']=pd.to_datetime(d.dt,utc=True)
    asof=pd.Timestamp.now(tz='UTC');d=d[d.updated<=asof];d=d[d.updated==d.groupby('team').updated.transform('max')]
    d=d[d.gsis_id.notna()].sort_values('pos_rank').drop_duplicates(['team','gsis_id'])
    p=pd.read_parquet(OUT/'players.parquet');g=pd.read_parquet(OUT/'games.parquet')
    g=g[(g.tip>asof)&(g.tip<asof+pd.Timedelta(days=8))].sort_values('tip')
    assumptions=dict(model_id=frozen['model_id'],created_at=now(),lineup_policy='ALL listed players assumed participating; NO injury check. Review before use.',games=[])
    for game in g.itertuples():
        entry=dict(game_id=game.game_id,kickoff_utc=str(game.tip),teams=[])
        for t in (game.away,game.home):
            roster=d[d.team==t];q=roster[roster.pos_abb=='QB']
            qb=None if q.empty else dict(aid=q.iloc[0].gsis_id,name=q.iloc[0].player_name,role='assumed_starting_QB_NOT_confirmed')
            receivers=[];hist=p[(p.game_id==game.game_id)&(p.team==t)].drop_duplicates('aid').set_index('aid')
            listed=roster[roster.pos_abb.isin(['WR','TE','RB','FB'])]
            for r in listed.itertuples():
                h=hist.loc[r.gsis_id] if r.gsis_id in hist.index else None
                pri=frozen['receiving']['position_priors'];pos=r.pos_abb
                targetprior=pri['target_share'].get(pos,.08);catchprior=pri['catch'].get(pos,.65)
                target=float((h.h_targets+20*targetprior)/(h.h_team_att+20)) if h is not None else float(targetprior)
                catch=float((h.h_receptions+8*catchprior)/(h.h_targets+8)) if h is not None else float(catchprior)
                receivers.append(dict(aid=r.gsis_id,name=r.player_name,position=pos,assumed_playing=True,include_projection=h is not None,
                    default_target_share=float(np.clip(target,0,1)),catch_probability=float(np.clip(catch,0,1)),target_share_override=None,
                    history_status='recent_team_history' if h is not None else 'POSITION_PRIOR_ONLY_REVIEW_ROLE'))
            entry['teams'].append(dict(team=t,qb=qb,qb_alternatives=[dict(aid=r.gsis_id,name=r.player_name) for r in q.itertuples()],
                receivers=receivers,assumption_note='Depth rank is a convenience default, not starter confirmation. All receivers assumed active.'))
        assumptions['games'].append(entry)
    with (DEST/'assumptions.json').open('x') as h:json.dump(assumptions,h,indent=2)
    for path in [dp,OUT/'players.parquet',OUT/'games.parquet',OUT/'teams.parquet']:
        manifest['inputs'][str(path)]=sha(path)
    manifest['finished']=now();manifest['starting_role']=state
    (DEST/'build_manifest_complete.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(dict(model=str(DEST/'model.json'),assumptions=str(DEST/'assumptions.json'),games=len(g),starting_role=state),indent=2))

if __name__=='__main__':main()
