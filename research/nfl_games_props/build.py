"""Read existing private local inputs and build strictly lagged features."""
import hashlib,json,os
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from core import FIX,EPA,weighted,elo_probability,elo_change

BASE=Path(__file__).resolve().parents[4]
REPO=Path(__file__).resolve().parents[2]
# Historical experiments use local nflverse caches that are intentionally not committed.
# The root is configurable so the research code contains no machine-specific private path.
OLD=Path(os.environ.get('NFL_RESEARCH_DATA_ROOT', str(BASE/'work')))
DATA=Path(os.environ.get('NFL_RESEARCH_NFLVERSE', str(REPO/'data')))
OUT=BASE/'outputs/nfl_games_props_20261023'
SEARCH=[OUT/'raw_fresh',DATA,OLD/'nfl-consistency-test',OLD/'nfl_availability_v5/raw',BASE/'work/nfl-comprehensive/raw']
USED={}


def locate(name):
    for root in SEARCH:
        p=root/name
        if p.exists():
            if name not in USED:
                h=hashlib.sha256()
                with p.open('rb') as f:
                    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
                USED[name]=dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
            return p
    raise FileNotFoundError(name)


def load_games():
    raw=pd.read_csv(locate('games.csv'),low_memory=False)
    bench=[c for c in ['game_id','spread_line','total_line','home_moneyline','away_moneyline'] if c in raw]
    raw[bench].to_parquet(OUT/'market_benchmarks.parquet',index=False)
    keep=['game_id','season','week','game_type','gameday','gametime','home_team','away_team','home_score','away_score','location']
    g=raw[keep].copy();g=g[(g.game_type=='REG')&(g.season>=2009)&(g.season<=2026)]
    for col in ('home_team','away_team'):g[col]=g[col].replace(FIX)
    tm=pd.to_datetime(g.gameday.astype(str)+' '+g.gametime.fillna('13:00').astype(str))
    g['tip']=tm.dt.tz_localize('America/New_York',ambiguous='NaT',nonexistent='shift_forward').dt.tz_convert('UTC')
    return g.sort_values(['tip','game_id']).reset_index(drop=True)


def team_pbp(year):
    cols={'game_id','posteam','defteam','epa','qb_dropback','rush_attempt','qb_scramble','qb_kneel','pass_attempt','sack','two_point_attempt','play_type'}
    p=locate(f'play_by_play_{year}.csv.gz')
    x=pd.read_csv(p,usecols=lambda c:c in cols,low_memory=False)
    x=x[x.posteam.notna()&x.epa.notna()&x.play_type.isin(['pass','run'])].copy()
    if 'two_point_attempt' in x:x=x[x.two_point_attempt!=1]
    x['posteam']=x.posteam.replace(FIX);x['defteam']=x.defteam.replace(FIX)
    x['designed']=(x.rush_attempt==1)&(x.qb_scramble!=1)&(x.qb_kneel!=1)
    frames=[]
    for (gid,team),z in x.groupby(['game_id','posteam']):
        pa=z[z.qb_dropback==1].epa;ru=z[z.designed].epa
        frames.append(dict(game_id=gid,team=team,pass_off=float(pa.mean()) if len(pa) else 0.,rush_off=float(ru.mean()) if len(ru) else 0.,
            plays=len(z),attempts=int(((z.pass_attempt==1)&(z.sack!=1)).sum())))
    a=pd.DataFrame(frames)
    defs=[]
    for (gid,team),z in x.groupby(['game_id','defteam']):
        pa=z[z.qb_dropback==1].epa;ru=z[z.designed].epa
        defs.append(dict(game_id=gid,team=team,pass_def=float(pa.mean()) if len(pa) else 0.,rush_def=float(ru.mean()) if len(ru) else 0.))
    return a.merge(pd.DataFrame(defs),on=['game_id','team'],validate='one_to_one')


def player_inputs(g):
    stats=[];snaps=[]
    players=pd.read_csv(locate('players.csv'),usecols=['gsis_id','pfr_id'],dtype=str).dropna()
    count=players.groupby('pfr_id').gsis_id.nunique();valid=set(count[count==1].index)
    ids=players[players.pfr_id.isin(valid)].drop_duplicates('pfr_id').set_index('pfr_id').gsis_id
    unknown=0
    for year in range(2018,2027):
        z=pd.read_csv(locate(f'stats_player_week_{year}.csv'),usecols=['game_id','season','week','season_type','team','player_id','player_display_name','position','attempts','targets','receptions'])
        z=z[z.season_type=='REG'].rename(columns={'player_id':'aid','player_display_name':'name'})
        z['team']=z.team.replace(FIX);stats.append(z)
        s=pd.read_csv(locate(f'snap_counts_{year}.csv'))
        s=s[s.game_type=='REG'].copy();s['team']=s.team.replace(FIX)
        s['aid']=s.pfr_player_id.map(ids);unknown+=int(s.aid.isna().sum())
        snaps.append(s[['game_id','team','aid','player','position','offense_snaps','offense_pct']])
    st=pd.concat(stats,ignore_index=True).drop_duplicates(['game_id','team','aid'])
    sn=pd.concat(snaps,ignore_index=True)
    completeness=sn.groupby(['game_id','team']).agg(n=('offense_snaps',lambda x:int((x>0).sum())),total=('offense_snaps','sum'),maximum=('offense_snaps','max'))
    completeness['complete']=(completeness.n>=11)&(completeness.total>=.9*11*completeness.maximum)&(completeness.total<=1.2*11*completeness.maximum)
    unmatched=sn.assign(unmapped=sn.aid.isna()&(sn.offense_snaps>0)&sn.position.isin(['QB','RB','FB','WR','TE'])).groupby(['game_id','team']).unmapped.sum()
    completeness['complete'] &= unmatched.eq(0)
    sn=sn[sn.aid.notna()].copy()
    if sn.duplicated(['game_id','team','aid']).any():raise ValueError('Duplicate snap player IDs')
    summary=dict(unmapped_snap_rows=unknown,incomplete_team_snap_files=int((~completeness.complete).sum()),ambiguous_pfr_ids=int((count>1).sum()))
    return st,sn,completeness,summary


def make_game_features(g,agg,stats):
    tg={(r.game_id,r.team):r for r in agg.itertuples()}
    totals=stats.groupby(['game_id','team']).attempts.sum().to_dict()
    history=defaultdict(list);elos=defaultdict(lambda:1500.);seasons={};pending=[];out=[];teams=[]
    def flush(cut):
        nonlocal pending
        remain=[]
        for old in pending:
            if old['ready']>=cut:remain.append(old);continue
            for team,opp,side in [(old['home'],old['away'],'h'),(old['away'],old['home'],'a')]:
                r=tg.get((old['game_id'],team))
                if r:
                    o=tg.get((old['game_id'],opp))
                    history[team].append(dict(season=old['season'],**{k:getattr(r,k) for k in EPA},
                        attempts=totals.get((old['game_id'],team),r.attempts),allowed=totals.get((old['game_id'],opp),getattr(o,'attempts',35)),
                        plays=r.plays,points=old[side+'_points']))
            change=elo_change(old['elo_diff'],old['h_points']-old['a_points'])
            elos[old['home']]+=change;elos[old['away']]-=change
        pending=remain
    def state(team,year):
        h=[r for r in history[team] if r['season']>=year-1][-20:]
        return {k:weighted([r[k] for r in h]) if h else (0. if k in EPA else 35. if k in ('attempts','allowed') else 64. if k=='plays' else 22.)
                for k in [*EPA,'attempts','allowed','plays','points']}
    for row in g.itertuples():
        cut=row.tip-pd.Timedelta(hours=1);flush(cut)
        for team in (row.home_team,row.away_team):
            if team in seasons and seasons[team]!=row.season:elos[team]=1505/3+elos[team]*2/3
            seasons[team]=row.season
        h=state(row.home_team,row.season);a=state(row.away_team,row.season)
        diff=elos[row.home_team]-elos[row.away_team]+(0 if str(row.location).lower()=='neutral' else 65)
        rec=dict(game_id=row.game_id,season=row.season,week=row.week,tip=row.tip,cutoff=cut,home=row.home_team,away=row.away_team,
            home_score=row.home_score,away_score=row.away_score,elo_diff=diff,elo_p=float(elo_probability(diff)),
            form_margin=h['points']-a['points']+1.8,form_total=h['points']+a['points'])
        rec.update({'h_'+k:h[k] for k in EPA});rec.update({'a_'+k:a[k] for k in EPA});out.append(rec)
        for team,opp,s,o,sign in [(row.home_team,row.away_team,h,a,1),(row.away_team,row.home_team,a,h,-1)]:
            teams.append(dict(game_id=row.game_id,team=team,opp=opp,season=row.season,week=row.week,tip=row.tip,cutoff=cut,
                own_att=s['attempts'],opp_att=o['allowed'],own_plays=s['plays'],opp_plays=o['plays'],
                own_pass_off=s['pass_off'],opp_pass_def=o['pass_def'],elo_gap=sign*diff/400,
                actual_team_att=totals.get((row.game_id,team),np.nan)))
        if pd.notna(row.home_score) and pd.notna(row.away_score):
            pending.append(dict(game_id=row.game_id,home=row.home_team,away=row.away_team,season=row.season,
                ready=row.tip+pd.Timedelta(hours=6),h_points=row.home_score,a_points=row.away_score,elo_diff=diff))
    return pd.DataFrame(out),pd.DataFrame(teams)


def make_player_features(g,st,sn,complete,teams):
    stat={(r.game_id,r.team,r.aid):r for r in st.itertuples()}
    snap={(r.game_id,r.team,r.aid):r for r in sn.itertuples()}
    bygame=defaultdict(list)
    produced={(r.game_id,r.team,r.aid) for r in st.itertuples() if r.attempts>0 or r.targets>0}
    for r in sn.itertuples():
        if r.offense_snaps>0 or (r.game_id,r.team,r.aid) in produced:
            bygame[(r.game_id,r.team)].append(r)
    teamfeatures={(r.game_id,r.team):r._asdict() for r in teams.itertuples(index=False)}
    hist=defaultdict(list);allplayer=defaultdict(list);latest={};pending=[];out=[];excluded=0
    def flush(cut):
        nonlocal pending
        remain=[]
        for record in pending:
            if record['ready']>=cut:remain.append(record);continue
            team,gid=record['team'],record['game_id']
            observed={r.aid:r for r in bygame[(gid,team)] if r.position in ('QB','WR','TE','RB','FB')}
            allids=set(observed)|set(hist[team][-1]['players'] if hist[team] else [])
            values={}
            for aid in allids:
                r=observed.get(aid);v=stat.get((gid,team,aid))
                if r:
                    latest[aid]=team
                    values[aid]=dict(aid=aid,position=r.position,name=r.player,app=1.,snap=r.offense_pct,
                        attempts=float(getattr(v,'attempts',0)),targets=float(getattr(v,'targets',0)),receptions=float(getattr(v,'receptions',0)))
                    allplayer[aid].append((record['season'],values[aid].copy()))
                else:
                    prev=next((x['players'][aid] for x in reversed(hist[team]) if aid in x['players']),None)
                    if prev:values[aid]={**prev,'app':0.,'snap':0.,'attempts':0.,'targets':0.,'receptions':0.}
            hist[team].append(dict(season=record['season'],players=values,team_att=record['team_att'],complete=record['complete']))
        pending=remain
    for game in g[g.season>=2018].itertuples():
        cut=game.tip-pd.Timedelta(hours=1);flush(cut)
        for team in (game.home_team,game.away_team):
            th=[x for x in hist[team] if x['season']>=game.season-1][-8:]
            candidates={a for x in th[-4:] for a,p in x['players'].items() if p['app'] and latest.get(a)==team}
            actual_ids={r.aid for r in bygame[(game.game_id,team)] if r.position in ('QB','RB','FB','WR','TE')}
            excluded+=len(actual_ids-candidates)
            key=(game.game_id,team)
            comp=bool(complete.loc[key,'complete']) if key in complete.index else False
            tf=teamfeatures[key]
            for aid in sorted(candidates):
                ph=[(x,x['players'].get(aid)) for x in th]
                seen=[(x,p) for x,p in ph if p and p['app']]
                if not seen:continue
                last=seen[-1][1];weights=.5**(np.arange(len(seen))[::-1]/4)
                full=[p for season,p in allplayer[aid] if season==game.season]
                if not full:full=[p for season,p in allplayer[aid] if season==game.season-1]
                sums={k:float(sum(w*p[k] for w,(x,p) in zip(weights,seen))) for k in ('attempts','targets','receptions')}
                den=float(sum(w*x['team_att'] for w,(x,p) in zip(weights,seen)))
                apps=[float(p['app']) if p else 0. for x,p in ph if x['complete']]
                streak=0
                for x,p in reversed(ph):
                    if p and p['app']:break
                    streak+=1
                r=snap.get((game.game_id,team,aid));v=stat.get((game.game_id,team,aid))
                appearance=1. if (r and r.offense_snaps>0) or (v and (v.attempts>0 or v.targets>0)) else 0. if comp else np.nan
                rec={k:v for k,v in tf.items() if k!='Index'}
                rec.update(aid=aid,name=last['name'],position=last['position'],app=appearance,
                    app_rate=float(np.mean(apps)) if apps else .5,last_snap_share=float(ph[-1][1]['snap']) if ph[-1][1] else 0.,
                    mean_snap_share=weighted([p['snap'] if p else 0. for x,p in ph]),miss_streak=streak,is_qb=int(last['position']=='QB'),
                    h_team_att=den,h_attempts=sums['attempts'],h_targets=sums['targets'],h_receptions=sums['receptions'],
                    avg_attempts=float(np.mean([p['attempts'] for x,p in seen])),avg_receptions=float(np.mean([p['receptions'] for x,p in seen])),
                    recent_attempts=sums['attempts']/weights.sum(),recent_receptions=sums['receptions']/weights.sum(),
                    season_attempts=float(np.mean([p['attempts'] for p in full])) if full else 0.,
                    season_receptions=float(np.mean([p['receptions'] for p in full])) if full else 0.,
                    attempts=float(getattr(v,'attempts',0)),targets=float(getattr(v,'targets',0)),receptions=float(getattr(v,'receptions',0)))
                out.append(rec)
            team_att=tf['actual_team_att']
            if pd.notna(game.home_score) and pd.notna(team_att):
                pending.append(dict(team=team,game_id=game.game_id,season=game.season,ready=game.tip+pd.Timedelta(hours=6),team_att=team_att,complete=comp))
    return pd.DataFrame(out),dict(excluded_actual_first_or_unseen_appearances=excluded)


def main():
    OUT.mkdir(exist_ok=True);cache=OUT/'derived';cache.mkdir(exist_ok=True)
    prior_inputs=json.loads((OUT/'input_audit.json').read_text()).get('inputs',{}) if (OUT/'input_audit.json').exists() else {}
    g=load_games();st,sn,complete,audit=player_inputs(g)
    frames=[]
    for year in range(2009,2027):
        path=cache/f'team_{year}.parquet'
        name=f'play_by_play_{year}.csv.gz';locate(name)
        if path.exists() and prior_inputs.get(name,{}).get('sha256')==USED[name]['sha256']:
            a=pd.read_parquet(path)
        else:
            a=team_pbp(year);a.to_parquet(path,index=False)
        frames.append(a);print('PBP aggregated',year,len(a),flush=True)
    games,teams=make_game_features(g,pd.concat(frames,ignore_index=True),st)
    players,coverage=make_player_features(g,st,sn,complete,teams)
    games.to_parquet(OUT/'games.parquet',index=False);teams.to_parquet(OUT/'teams.parquet',index=False);players.to_parquet(OUT/'players.parquet',index=False)
    audit.update(coverage);audit.update(game_rows=len(games),team_rows=len(teams),player_candidates=len(players),
        appearance_unknown=int(players.app.isna().sum()),inputs=USED,
        historical_vintage='revised files, strict game lag; NOT original publication snapshots')
    (OUT/'input_audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps({k:v for k,v in audit.items() if k!='inputs'},indent=2))


if __name__=='__main__':main()
