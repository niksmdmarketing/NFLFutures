"""Current ID-mapped depth and official-report context, not a starter oracle."""
import json,sys
from pathlib import Path
import pandas as pd
from feed_test import DEST,OUT,stamp,norm,team,digest

def main():
    dest=DEST/'current_player_context_verified.json'
    if dest.exists():raise FileExistsError(dest)
    live=json.loads((DEST/'live_feed_audit_network_verified.json').read_text())
    injury,depth=live['captures'];assert injury['ok'] and depth['ok']
    d=pd.read_csv(depth['file'],dtype={'gsis_id':str,'espn_id':str})
    d['team']=d.team.map(team);d['updated']=pd.to_datetime(d.dt,utc=True)
    d=d[d.updated<=pd.Timestamp(depth['retrieved_at_utc'])]
    d=d[d.updated==d.groupby('team').updated.transform('max')].copy()
    ps=pd.read_csv(OUT/'raw_fresh/players.csv',dtype=str)
    aliases={}
    for r in ps.itertuples():
        for name in (r.display_name,str(r.first_name)+' '+str(r.last_name),str(r.football_name)+' '+str(r.last_name)):
            if isinstance(name,str):aliases.setdefault(norm(name),set()).add(r.gsis_id)
    for r in d[d.gsis_id.notna()].itertuples():aliases.setdefault(norm(r.player_name),set()).add(r.gsis_id)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'pipeline'))
    import nfl_injuries
    report=nfl_injuries.parse_report(Path(injury['file']).read_bytes().decode('utf-8',errors='replace'))
    inventory=json.loads((DEST/'news_inventory_network_verified.json').read_text())
    snapshot=json.loads(Path(inventory['captures'][0]['file']).read_text())
    authoritative={}
    expected_game=f"{report['season']} week {report['week']}"
    for r in snapshot['records']:
        sid=str(r.get('player_id') or '')
        if sid.startswith('gsis:') and r.get('affected_game')==expected_game and not r.get('stale'):
            aid=sid[5:]
            if aid in set(ps.gsis_id.dropna()):authoritative.setdefault((team(r.get('team')),norm(r.get('player'))),set()).add(aid)
    mapped=[]
    for r in report['rows']:
        ids=aliases.get(norm(r['player']),set());pool=d[(d.team==team(r['team']))&d.gsis_id.isin(ids)]
        # Position must agree for offensive props; broader defensive labels are left unresolved.
        pool=pool[pool.pos_abb==r['position']];unique=pool.gsis_id.dropna().unique()
        direct=authoritative.get((team(r['team']),norm(r['player'])),set())
        direct=direct if len(direct)==1 else set()
        conflict=bool(direct and len(unique)==1 and str(unique[0]) not in direct)
        aid=next(iter(direct)) if direct and not conflict else str(unique[0]) if len(unique)==1 and not conflict else None
        mapped.append({**r,'gsis_id':aid,
            'mapping':'same_week_nflverse_unique_name_team_gsis' if direct and not conflict else 'unique_alias_current_team_exact_position' if aid else 'unresolved_or_conflict',
            'source_modified_at_utc':None,'observed_at_utc':injury['retrieved_at_utc'],
            'report_season':report['season'],'report_week':report['week']})
    lookup={(r['team'],r['gsis_id']):r for r in mapped if r['gsis_id']}
    games=pd.read_parquet(OUT/'games.parquet');now=pd.Timestamp(depth['retrieved_at_utc'])
    games=games[games.tip>now].sort_values('tip')
    candidates=pd.read_parquet(OUT/'players.parquet')
    qbs=[]
    for t,z in d[d.pos_abb=='QB'].groupby('team'):
        future=games[(games.home==t)|(games.away==t)]
        if future.empty:continue
        game=future.iloc[0];rows=[]
        for r in z.sort_values('pos_rank').itertuples():
            inj=lookup.get((t,r.gsis_id))
            valid=report['season']==int(game.season) and report['week']==int(game.week)
            active=inj if valid else None
            rows.append(dict(aid=r.gsis_id if pd.notna(r.gsis_id) else None,name=r.player_name,depth_rank=int(r.pos_rank),
                game_status=active.get('game_status') if active else None,
                status_meaning='listed_status' if active and active.get('game_status') else 'unknown_or_no_designation_NOT_confirmed_active',
                existing_candidate=bool(((candidates.game_id==game.game_id)&(candidates.aid==r.gsis_id)&(candidates.team==t)).any())))
        qbs.append(dict(team=t,game_id=game.game_id,kickoff=str(game.tip),cutoff=str(game.tip-pd.Timedelta(hours=1)),
            depth_source_updated=str(z.updated.max()),depth_observed=depth['retrieved_at_utc'],
            official_report_week_matches=bool(valid),players=rows,
            starter_status='depth_order_only_not_confirmed',
            scenario='If rank-one is confirmed out, evaluate next available QB; do not transfer old attempts unchanged.'))
    result=dict(created_at=stamp(),research_only=True,injury_rows=mapped,mapped=int(sum(r['gsis_id'] is not None for r in mapped)),
        unresolved=int(sum(r['gsis_id'] is None for r in mapped)),latest_depth_rows=len(d),qb_context=qbs,
        sources=[{k:v for k,v in x.items() if k in ('source_url','retrieved_at_utc','sha256','file')} for x in (injury,depth,inventory['captures'][0])],
        limits='No numeric override. Exact position mapping is intentionally conservative; unresolved rows are not healthy. Current snapshots cannot be backdated. Forecasts need an explicit starter/usage scenario and new-starter fallback.')
    dest.write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(mapped=result['mapped'],unresolved=result['unresolved'],teams=len(qbs),
        depth_QBs_missing_candidates=sum(not r['existing_candidate'] for q in qbs for r in q['players'])),indent=2))

if __name__=='__main__':main()
