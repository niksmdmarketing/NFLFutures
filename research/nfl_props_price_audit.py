"""Audit forecast exports, timing and source-name identity without reading odds or outcomes."""
import argparse,collections,csv,datetime as dt,gzip,hashlib,json,statistics
from pathlib import Path
import nfl_prop_identity as I

def run(export,archive):
    export,archive=Path(export),Path(archive)
    manifest=json.loads((export/'manifest.json').read_text())
    here=Path(__file__).resolve().parent
    for field,file in [('export_code_sha256','nfl_props_price_export.py'),('identity_code_sha256','nfl_prop_identity.py')]:
        assert hashlib.sha256((here/file).read_bytes()).hexdigest()==manifest[field],('code_changed_since_export',file)
    for name,digest in manifest['output_files'].items():
        assert hashlib.sha256((export/name).read_bytes()).hexdigest()==digest,('output_hash',name)
    with gzip.open(export/'probabilities.jsonl.gz','rt',encoding='utf-8') as f:rows=[json.loads(line) for line in f]
    fixtures=json.loads((export/'fixtures.json').read_text())
    for game in fixtures:
        assert I.fixture(I.TEAM_NAMES[game['home']],I.TEAM_NAMES[game['away']],game['kickoff_utc'],fixtures)['game_id']==game['game_id']
    pools=collections.defaultdict(list);unique=set();snapshots={};counts=collections.Counter();windows=collections.Counter();name_counts=collections.Counter()
    for row in rows:
        key=(row['game_id'],row['horizon_minutes'],row['gsis_id'],row['stat'])
        assert key not in unique,('duplicate',key)
        unique.add(key);pools[row['game_id'],row['horizon_minutes']].append(row)
        assert row['model_id']==manifest['model_id']
        assert len(row['pmf'])==(71 if row['stat']=='pass_attempts' else 31)
        I.probabilities(row['pmf'],.5)
        assert 0<=row['appearance_probability']<=1
        cutoff=I.utc(row['cutoff_utc']);generated=I.utc(row['generated_utc']);kickoff=I.utc(row['kickoff_utc'])
        assert cutoff==kickoff-dt.timedelta(minutes=row['horizon_minutes'])
        assert generated<=cutoff
        if row['source_tier']=='receipt_proved':
            assert generated<=I.utc(row['receipt_utc'])<=cutoff
            path=row['snapshot']
            if path not in snapshots:snapshots[path]=json.loads((archive/path).read_text())
            snapshot=snapshots[path]
            game=next(g for g in snapshot['games'] if g['game_id']==row['game_id'])
            player=next(p for team in game['teams'] if team['team']==row['team'] for p in team['players'] if p['player_id']==row['gsis_id'] and p['stat']==row['stat'])
            assert row['pmf']==player['pmf'],('archive_distribution_changed',key)
            assert row['appearance_probability']==player['availability_probability']
        else:
            assert not row['primary_eligible']
            assert row['historical_availability']=='not_reconstructed'
            assert all(I.utc(t)<=cutoff for t in row['depth_times'].values())
            assert I.utc(row['latest_completed_input_kickoff_utc'])+dt.timedelta(hours=6)<cutoff
        counts[row['horizon_minutes'],row['source_tier'],row['stat']]+=1
        windows[row['horizon_minutes'],'A' if row['week']<=4 else 'B',row['source_tier']]+=1
    for row in rows:
        pool=pools[row['game_id'],row['horizon_minutes']]
        for label,name in [('canonical',row['name']),('punctuation_case_variant',row['name'].replace('.','').replace('-',' ').replace("'",'').upper())]:
            matched=I.player(name,row['stat'],pool,team=row['team'])
            if matched['status']=='matched':assert matched['gsis_id']==row['gsis_id'],('false_id',row,matched)
            name_counts[label,matched['status']]+=1
    with (export/'coverage.csv').open(encoding='utf-8') as f:coverage=list(csv.DictReader(f))
    expected={(g['game_id'],h) for g in fixtures for h in (60,360)}
    actual={(c['game_id'],int(c['horizon_minutes'])) for c in coverage if c['status']!='unsupported'}
    assert expected==actual
    assert all(c['status']=='exported' for c in coverage if c['status']!='unsupported')
    report={'status':'pass','games':len(fixtures),'forecast_rows':len(rows),'unique_forecast_keys':len(unique),
            'primary_rows':sum(r['primary_eligible'] for r in rows),'missing_espn_ids':sum(not r.get('espn_id') for r in rows),
            'all_rows_have_gsis_id':all(bool(r.get('gsis_id')) for r in rows),
            'pmf_and_timing_checks':'passed','original_receipt_pmf_equality':'passed',
            'fixture_self_matches':len(fixtures),'name_self_tests':{'|'.join(k):v for k,v in name_counts.items()},
            'row_counts':{'|'.join(map(str,k)):v for k,v in counts.items()},
            'window_counts':{'|'.join(map(str,k)):v for k,v in windows.items()},
            'actual_bookmaker_name_match_rate':None,'actual_bookmaker_name_match_rate_note':'No OddsPapi rows have been read. These are source-name and synthetic mechanics tests, not a measured bookmaker match rate.',
            'price_test_status':'not_run','prices_read':False,
            'audit_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'current_rule_sha256':hashlib.sha256((here/'NFL_PROPS_PRICE_TEST_RULE.md').read_bytes()).hexdigest()}
    ages={}
    for h in (60,360):
        values=[(I.utc(r['cutoff_utc'])-I.utc(r['generated_utc'])).total_seconds()/60 for r in rows if r['horizon_minutes']==h and r['source_tier']=='receipt_proved']
        ages[str(h)]={'min':min(values),'median':statistics.median(values),'max':max(values)} if values else None
    report['receipt_forecast_age_at_cutoff_minutes']=ages
    (export/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--export',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    a=p.parse_args();run(a.export,a.archive)
