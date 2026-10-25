"""Audit the existing collection-only news archive, separately from model scoring."""
import json
from pathlib import Path
import pandas as pd
from feed_test import DEST,OUT,OLD,fetch,digest,stamp,norm,team

def main(filename='news_inventory.json'):
    path=DEST/filename
    if path.exists():raise FileExistsError(path)
    captures=[]
    for label,suffix in [('availability_latest','availability/nfl/latest.json'),('availability_sources','availability/sources.json'),
                         ('availability_changes','availability/nfl/changes.jsonl')]:
        captures.append(fetch('https://raw.githubusercontent.com/niksmdmarketing/NFLFutures/injury-monitor/'+suffix,label))
    captures.append(fetch('https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries','espn_nfl_injuries'))
    names=pd.read_csv(OUT/'raw_fresh/players.csv',dtype=str)
    ids=names.dropna(subset=['espn_id','gsis_id']).groupby('espn_id').gsis_id.agg(lambda x:sorted(set(x)))
    players=pd.read_parquet(OUT/'players.parquet');now=pd.Timestamp.now(tz='UTC')
    roster=players[(players.tip>now)&(players.tip<now+pd.Timedelta(days=8))][['aid','team','name','position']].drop_duplicates()
    matched=[];summary={}
    if captures[0]['ok']:
        latest=json.loads(Path(captures[0]['file']).read_bytes())
        records=latest.get('records',[])
        for r in records:
            sid=str(r.get('player_id') or '');aid=None;method='unresolved'
            if sid.startswith('gsis:'):aid=sid.split(':',1)[1];method='source_gsis_id'
            elif sid.startswith('espn:') and sid[5:] in ids and len(ids[sid[5:]])==1:
                aid=ids[sid[5:]][0];method='espn_to_gsis_unique_id'
            if aid is None and r.get('player') and r.get('team'):
                pool=roster[(roster.team==team(r['team']))&(roster.name.map(norm)==norm(r['player']))]
                unique=pool.aid.unique()
                if len(unique)==1:aid=str(unique[0]);method='unique_name_and_candidate_team_no_position_in_source'
            matched.append({**r,'mapped_gsis_id':aid,'mapping_method':method,
                'local_retrieved_at_utc':captures[0]['retrieved_at_utc'],
                'version_available_no_earlier_than':r.get('collected_utc') or latest.get('collected_utc')})
        summary=dict(archive_collected_at=latest.get('collected_utc'),records=len(records),mapped=sum(x['mapped_gsis_id'] is not None for x in matched),
            stale=sum(bool(x.get('stale')) for x in records),sources=sorted(set(str(x.get('source')) for x in records)),
            context_rows=sum(x.get('layer')=='reported' for x in records))
        (DEST/'mapped_existing_news.json').write_text(json.dumps(matched,indent=2))
    history={}
    if captures[2]['ok']:
        changes=[json.loads(x) for x in Path(captures[2]['file']).read_text().splitlines() if x.strip()]
        times=[r.get('collected_utc') for r in changes if r.get('collected_utc')]
        history=dict(changes=len(changes),first_change=min(times) if times else None,last_change=max(times) if times else None)
    local=[]
    root=OLD.parents[0]/'outputs/multisport-availability-collector'
    if root.exists():
        for p in root.rglob('latest.json'):
            if 'nfl' not in str(p):continue
            b=p.read_bytes();local.append(dict(path=str(p),sha256=digest(b),bytes=len(b)))
    correction='Existing pipeline/avail_collect.py DOES include NFL/ESPN injury feeds, ESPN transactions/news, Rapoport and Pelissero context. It is collection-only. Any earlier no-news-parser note from the narrow injury audit is superseded by this inventory.'
    result=dict(captures=captures,summary=summary,history=history,local_archives=local,correction=correction,
        timing='Preserve published_utc, first_seen_utc and collected_utc separately. First_seen belongs to an entity/key and can precede a changed status: use the change version collection time, not old first_seen, for replay eligibility. A present-day fetch cannot establish earlier observation.',
        next='News can inform a scenario, not automatic numeric usage changes. Need timestamped starter confirmation and eligible rosters; unknown mappings remain unknown.',completed_at=stamp())
    path.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
