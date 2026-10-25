"""Current projected starter scenarios from saved, dated facts; not confirmations."""
import json
from pathlib import Path
import pandas as pd
from starter_test import DEST,OUT,now,sha

def main():
    dest=DEST/'CURRENT_STARTER_SCENARIOS.json'
    if dest.exists():raise FileExistsError(dest)
    source=OUT/'feed_extension/current_player_context_verified.json';ctx=json.loads(source.read_text())
    age=(pd.Timestamp.now(tz='UTC')-pd.Timestamp(ctx['created_at'])).total_seconds()/3600
    rows=[]
    for q in ctx['qb_context']:
        available=sorted(q['players'],key=lambda x:x['depth_rank'])
        cutoff=pd.Timestamp(q['cutoff']);observed=pd.Timestamp(q['depth_observed'])
        eligible=observed<cutoff and age<=24
        alternatives=[p for p in available if not(q['official_report_week_matches'] and p.get('game_status')=='Out')]
        unique=alternatives and sum(p['depth_rank']==alternatives[0]['depth_rank'] for p in alternatives)==1
        projected=alternatives[0] if unique and eligible else None
        rows.append(dict(team=q['team'],game_id=q['game_id'],cutoff=q['cutoff'],
            depth_observed=q['depth_observed'],official_report_week_matches=q['official_report_week_matches'],
            projected_primary_id=projected['aid'] if projected else None,projected_primary_name=projected['name'] if projected else None,
            classification='depth_plus_explicit_out_elimination_ASSUMPTION_NOT_CONFIRMATION' if projected else 'unresolved',
            uncertain=bool(projected is None or projected.get('game_status') in ('Questionable','Doubtful')),
            source_status=projected.get('game_status') if projected else None,
            newly_covered_qbs=[p for p in available if not p['existing_candidate']],
            all_qb_alternatives=available,
            note='Blank/missing status is not confirmed active. Doubtful remains uncertain, not automatically removed. No numeric probabilities adopted.'))
    result=dict(created_at=now(),source_context_sha256=sha(source),source_context_created=ctx['created_at'],
        source_context_age_hours=age,teams=rows,live_model_changed=False,independent_forward_eligible=False,
        limits='Reused earlier captured bytes, not a fresh source check. Depth plus Out elimination is an explicit scenario assumption, not validated historical starter confirmation.')
    with dest.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(teams=len(rows),projected=sum(r['projected_primary_id'] is not None for r in rows),
        newly_covered_qb_rows=sum(len(r['newly_covered_qbs']) for r in rows),source_context_age_hours=age)))

if __name__=='__main__':main()
