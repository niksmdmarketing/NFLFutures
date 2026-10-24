"""Separate live archive hook. Primary record is already saved before this runs."""
import copy, gzip, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import nba_props_live_core as C
import nba_props_simple_test as P
import nba_props_repair as R
import nba_props_shadow as S

HERE=Path(__file__).resolve().parent


def build_record(primary,z,history,frozen,params,captured):
    before=copy.deepcopy(primary)
    now=pd.Timestamp(captured)
    if now<pd.Timestamp(params['activation_utc']): return None
    # History comes from the already retrieved primary box inputs. This is an
    # availability upper bound, not a fabricated exact per-row retrieval time.
    h=history[['season','aid','tip','minutes']].copy()
    h['minutes']=pd.to_numeric(h['minutes'],errors='raise')
    if not np.isfinite(h['minutes'].to_numpy(float)).all() or (h['minutes']<0).any():
        raise ValueError('Invalid minutes in primary history')
    input_rows=len(h)
    # The primary feature builder also emits zero-minute target/candidate rows.
    # They are NOT observations of future games. fast_inputs already ignores
    # all non-appearances, so remove only these before validating provenance.
    # Do not filter positive rows by date: the strict guard must still reject
    # any claimed appearance that occurs after the observation/capture time.
    h=h[h['minutes']>0].copy()
    h['observed_at_utc']=primary['forecast_finished_utc']
    shadow=S.make_shadow(z,h,frozen,params,primary['cutoff_utc'],str(now),replay=False)
    base,_=C.q_m2(z,frozen['m2'],True)
    pmap={(p['team'],p['aid']):p for p in primary['players']}
    means=base@np.arange(1,54)
    baseline_dists={}
    for stat in ('reb','ast'):
        rate,disp=C.prop_rate(z,stat,frozen['props'])
        baseline_dists[stat]=P.mixture_pmf(rate,base,disp,P.SUP_FULL[stat])
    for i,row in enumerate(z.itertuples()):
        p=shadow['players'][i]; old=pmap[(row.team,int(row.aid))]
        if abs(p['p_appear']-old['p_appear'])>5.1e-7:
            raise ValueError('Primary appearance mismatch')
        if np.max(np.abs(base[i]-old['minutes_v3']))>5.1e-7:
            raise ValueError('Primary M2b minutes mismatch')
        p.update(name=old.get('name',''),status=old.get('status',''),baseline_minutes=base[i].tolist(),
            baseline_expected_minutes=float(means[i]),start10=float(row.start10),
            bench=bool(row.start10<=.2 and means[i]<=20),
            established=bool(row.start10>=.8 and means[i]>=25),
            risk=bool(base[i,:14].sum()>=.2))
        for stat in ('reb','ast'):
            cond=baseline_dists[stat][i]
            unc=cond*p['p_appear']; unc[0]+=1-p['p_appear']
            if np.max(np.abs(unc-old[stat+'_v3']))>1e-6:
                raise ValueError('Primary M2b prop mismatch')
            p['baseline_'+stat+'_given_appearing']=cond.tolist()
            p['baseline_'+stat+'_including_dnp_zero']=unc.tolist()
            mean=(getattr(row,stat+'_cur')/row.n_cur if row.n_cur>0 else
                getattr(row,stat+'_prv')/row.n_prv if row.n_prv>0 else params['group_game_mean'][stat][row.grp])
            p[stat+'_calibration_line']=float(np.floor(max(mean,.01))+.5)
    if primary!=before: raise ValueError('Primary mutated')
    shadow.update(archive_schema_version=1,horizon_min=primary['horizon_min'],
        primary_code_commit=primary['code_commit'],params_id=primary['params_id'],
        report=copy.deepcopy(primary.get('report')),report_diagnostics=copy.deepcopy(primary.get('report_diagnostics')),
        coverage=copy.deepcopy(primary.get('coverage')),github=copy.deepcopy(primary.get('github')),
        activation_utc=params['activation_utc'],pair_check={'same_players':set(pmap)=={(p['team'],p['aid']) for p in shadow['players']}},
        history_provenance='Primary archived box/row history, available by primary completion; no new data request',
        history_filter=dict(input_rows=input_rows,positive_appearances=len(h),
                            nonappearance_rows_removed=input_rows-len(h)),
        challenger_eligibility='requires_independent_push_receipt_and_valid_primary',
        warning='Separate fast-memory test, not M2/M2b adoption population; not evidence of profit.')
    return shadow


def _store_blob(archive,data,ext):
    h=hashlib.sha256(data).hexdigest()
    path=Path(archive)/'nba/props_forward/inputs'/(h+'.'+ext)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data: raise ValueError('Corrupt immutable challenger input')
    else:
        with path.open('xb') as f: f.write(data)
    return h


def archive_challenger(archive,primary_path,primary,z,history,frozen):
    """No network, fitting, primary edits, retroactive replays or forced games."""
    path=HERE/'nba_fast_memory_params_2027.json'
    params=json.loads(path.read_bytes())
    now=datetime.now(timezone.utc)
    if pd.Timestamp(now)<pd.Timestamp(params['activation_utc']): return None
    fpath=HERE.parent/'model/nba_props_live_params_2027b.json'
    canonical=fpath.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(canonical).hexdigest()!=params['primary_parameter_sha256']:
        raise ValueError('Frozen primary parameters changed')
    shadow=build_record(primary,z,history,frozen,params,now)
    if shadow is None: return None
    parameter_hash=_store_blob(archive,path.read_bytes(),'json')
    rule=HERE/'NBA_FAST_MEMORY_FORWARD_RULE.md'
    rule_hash=_store_blob(archive,rule.read_bytes(),'md')
    code_hashes={}
    for name in ('nba_fast_memory_live.py','nba_props_repair.py','nba_props_shadow.py'):
        code_hashes[name]=_store_blob(archive,(HERE/name).read_bytes(),'py')
    shadow.update(primary_path=Path(primary_path).relative_to(archive).as_posix(),
        primary_sha256=hashlib.sha256(Path(primary_path).read_bytes()).hexdigest(),
        primary_inputs=copy.deepcopy(primary['inputs']),
        parameters_sha256=parameter_hash,rule_sha256=rule_hash,code_sha256=code_hashes,
        forecast_finished_utc=datetime.now(timezone.utc).isoformat())
    shadow['locally_on_time']=pd.Timestamp(shadow['forecast_finished_utc'])<=pd.Timestamp(primary['cutoff_utc'])
    day=Path(primary_path).parent.name
    dest=Path(archive)/'nba/props_forward/challengers'/R.MODEL_ID/day/Path(primary_path).name
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as g:
            g.write(json.dumps(shadow,allow_nan=False).encode())
    return str(dest)
