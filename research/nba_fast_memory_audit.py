"""Independent archive timing/input validation for the separate challenger."""
import argparse,gzip,hashlib,json,math
from pathlib import Path
from datetime import datetime,timezone
from nba_props_archive_audit import GitArchive,utc,pmf_errors


def timing_errors(record,receipt,primary,raw_primary):
    errors=[]
    if record.get('model_id')!='fast-minutes-hl2-dev1' or record.get('replay'):
        errors.append('wrong_model_or_replay')
    if not primary or primary.get('errors'):errors.append('invalid_primary')
    if primary and (any(record.get(k)!=primary.get(k) for k in ('game_id','horizon_min')) or utc(record['cutoff_utc'])!=utc(primary['cutoff_utc'])):
        errors.append('primary_game_or_cutoff_mismatch')
    if hashlib.sha256(raw_primary).hexdigest()!=record.get('primary_sha256'):errors.append('primary_bytes_mismatch')
    try:
        capture=utc(record['captured_at_utc']); finish=utc(record['forecast_finished_utc']); cutoff=utc(record['cutoff_utc'])
        from datetime import timedelta
        if not cutoff-timedelta(minutes=45)<=capture<=finish<=cutoff:errors.append('outside_capture_window')
        if capture<utc(record['activation_utc']):errors.append('before_activation')
        if receipt is None or not finish<=utc(receipt)<=cutoff:errors.append('no_on_time_independent_receipt')
    except (KeyError,ValueError,TypeError):errors.append('invalid_timing')
    if not record.get('pair_check',{}).get('same_players'):errors.append('unpaired')
    players=record.get('players',[])
    if not players or len({(p['team'],p['aid']) for p in players})!=len(players):errors.append('empty_or_duplicate_players')
    for p in players:
        if not 0<=p['p_appear']<=1:errors.append('invalid_appearance')
        for key in ('minutes_given_appearing','baseline_minutes','reb_given_appearing','ast_given_appearing',
                    'reb_including_dnp_zero','ast_including_dnp_zero','baseline_reb_given_appearing','baseline_ast_given_appearing'):
            errors += [key+':'+e for e in pmf_errors(p.get(key,[]))]
    return sorted(set(errors))


def audit(repo,ref):
    a=GitArchive(repo,ref)
    prefix='nba/props_forward/challengers/fast-minutes-hl2-dev1'
    paths=a.git('ls-tree','-r','--name-only',ref,prefix).decode().splitlines()
    paths=[p for p in paths if p.endswith('.json.gz')]
    if not paths:return dict(checked_utc=datetime.now(timezone.utc).isoformat(),snapshots=0,eligible_game_horizons=0,records=[])
    pri=a.audit(); primaries={r['path']:r for r in pri['snapshots']}
    timings=a.git('ls-tree','-r','--name-only',ref,'nba/props_forward/timing').decode().splitlines()
    pushes={(p['timestamp'],p['after']) for t in timings for p in a.read(t).get('pushes',[]) if p.get('timestamp') and p.get('after')}
    ancestors={h:set(a.git('rev-list',h).decode().splitlines()) for _,h in pushes}
    inputs=a.git('ls-tree','-r','--name-only',ref,'nba/props_forward/inputs').decode().splitlines()
    byhash={Path(p).name.split('.')[0]:p for p in inputs}; verified=set()
    records=[]; selected={}
    expected=hashlib.sha256(a.git('show','HEAD:research/nba_fast_memory_params_2027.json')).hexdigest()
    for path in paths:
        r=a.read(path)
        additions=a.git('log','--diff-filter=A','--format=%H',ref,'--',path).decode().splitlines()
        commits=a.git('log','--format=%H',ref,'--',path).decode().splitlines()
        receipts=[s for s,h in pushes if additions and additions[-1] in ancestors[h]]
        receipt=min(receipts,key=utc) if receipts else None
        primary=primaries.get(r['primary_path'])
        raw=a.git('show',ref+':'+r['primary_path'])
        errors=timing_errors(r,receipt,primary,raw)
        if len(commits)!=1:errors.append('modified_record')
        if r['parameters_sha256']!=expected:errors.append('wrong_frozen_candidate')
        source=a.read(r['primary_path'])
        if {(p['team'],p['aid']) for p in source['players']}!={(p['team'],p['aid']) for p in r['players']}:errors.append('player_set_mismatch')
        if r.get('primary_inputs')!=source.get('inputs'):errors.append('primary_input_set_mismatch')
        hashes=[r['parameters_sha256'],r['rule_sha256'],*r['code_sha256'].values()]
        hashes += [h for values in r['primary_inputs'].values() for h in values]
        for h in hashes:
            if h in verified:continue
            if h not in byhash or hashlib.sha256(a.git('show',ref+':'+byhash[h])).hexdigest()!=h:
                errors.append('missing_or_corrupt_input:'+h)
            else:verified.add(h)
        record=dict(path=path,game_id=r['game_id'],horizon_min=r['horizon_min'],receipt_utc=receipt,
            cutoff_utc=r['cutoff_utc'],captured_at_utc=r['captured_at_utc'],players=len(r['players']),errors=errors,
            primary_warnings=(primary or {}).get('warnings',[]))
        records.append(record);key=(r['game_id'],r['horizon_min'])
        if not errors and (key not in selected or utc(r['captured_at_utc'])>utc(selected[key]['captured_at_utc'])):selected[key]=record
    return dict(checked_utc=datetime.now(timezone.utc).isoformat(),source_commit=a.git('rev-parse',ref).decode().strip(),
        snapshots=len(records),eligible_game_horizons=len(selected),verified_input_blobs=len(verified),selected=list(selected.values()),records=records)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ref',default='origin/forecast-archive');p.add_argument('--output',required=True);args=p.parse_args()
    result=audit(Path(__file__).resolve().parents[1],args.ref)
    Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('records','selected')},indent=2))
