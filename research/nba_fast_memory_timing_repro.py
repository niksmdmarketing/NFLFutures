"""Offline regression from actual archived boxes; NEVER a forward forecast."""
import gzip,hashlib,io,json
from pathlib import Path
import numpy as np
import pandas as pd
import nba_minutes_test as M
import nba_fast_memory_live as L
from nba_props_archive_audit import GitArchive
from test_nba_fast_memory_live import LiveTests

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/nba_props_repair_20261023/timing_fix_20261024'

def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'offline_repro.json').exists():raise FileExistsError('Create-only evidence')
    a=GitArchive(Path(__file__).resolve().parents[1],'origin/forecast-archive')
    path='nba/props_forward/2026-10-23/401909095_60_20261023T214601761036Z.json.gz'
    primary=a.read(path)
    h=primary['inputs']['player_box'][0]
    paths=a.git('ls-tree','-r','--name-only',a.ref,'nba/props_forward/inputs').decode().splitlines()
    boxpath=next(p for p in paths if Path(p).name.startswith(h+'.'))
    raw=a.git('show',a.ref+':'+boxpath)
    assert hashlib.sha256(raw).hexdigest()==h
    p=pd.read_csv(io.BytesIO(raw),compression='gzip',usecols=['game_id','season','season_type','game_date_time','athlete_id',
        'athlete_display_name','team_abbreviation','team_display_name','minutes','starter','athlete_position_abbreviation'])
    # Only current-season boxes are needed to reproduce the row-shape bug.
    p=p[(p.season==2027)&(p.season_type==2)].copy()
    # Match the primary run's preprocessing of raw DNP/blank minutes.
    p['minutes']=pd.to_numeric(p.minutes,errors='coerce').fillna(0.)
    p['tip']=pd.to_datetime(p.game_date_time,utc=True);p=p[p.tip<pd.Timestamp(primary['forecast_finished_utc'])]
    p['grp']=p.athlete_position_abbreviation.map(M.GROUP).fillna('W')
    p['starter']=p.starter.astype(str).str.lower().eq('true')
    source_tips=p.tip.copy();tip=pd.Timestamp(primary['cutoff_utc'])+pd.Timedelta(hours=1)
    extra=[]
    for t in primary['coverage']:
        extra.append(dict(game_id=primary['game_id'],season=2027,season_type=2,game_date_time=tip.isoformat(),
            athlete_id=-1,athlete_display_name='',team_abbreviation=t,team_display_name=t,minutes=0.,starter=False,
            athlete_position_abbreviation='',tip=tip,grp='W'))
    p=pd.concat([p,pd.DataFrame(extra)],ignore_index=True).sort_values(['tip','game_id'])
    empty=pd.DataFrame(columns=['team','season','pkey','player','game_date','report','status','rtime'])
    empty['rtime']=pd.to_datetime(empty.rtime,utc=True)
    M.load_box=lambda:p
    M.load_reports=lambda src:empty.copy()
    M.ROWS=str(OUT/'reconstructed_feature_rows_preprocessed.csv.gz')
    M.build(str(OUT))
    history=pd.read_csv(M.ROWS,low_memory=False)
    primary_time=pd.Timestamp(primary['forecast_finished_utc'])
    history['tip']=pd.to_datetime(history.tip,utc=True)
    future=history.tip>primary_time
    assert future.any() and (history.loc[future,'minutes']==0).all()
    # Actual future rows recreate the failure without manufacturing their schema.
    r,z,_,f,params=LiveTests().fixture()
    before=history[['season','aid','tip','minutes']].copy();before['observed_at_utc']=r['forecast_finished_utc']
    old_failure=False
    try:L.S.make_shadow(z,before,f,params,r['cutoff_utc'],'2026-10-23T21:31:00Z',replay=False)
    except ValueError as error:
        assert str(error)=='Invalid observed-history timing';old_failure=True
    assert old_failure
    result=L.build_record(r,z,history,f,params,'2026-10-23T21:31:00Z')
    baseline=L.build_record(r,z,history[history.minutes>0],f,params,'2026-10-23T21:31:00Z')
    assert result['players']==baseline['players']
    evidence=dict(actual_primary_path=path,actual_box_path=boxpath,box_sha256=h,source_box_rows=len(source_tips),
        reconstructed_rows=len(history),future_placeholder_rows=int(future.sum()),future_positive_rows=int((future&(history.minutes>0)).sum()),
        original_failure_reproduced=old_failure,fixed_build_passed=True,positive_history_forecasts_identical=True,
        filter=result['history_filter'],forward_eligible=False,
        limits='Actual archived boxes and primary-builder row schema, empty injury reports for reconstruction; synthetic single-player forecast fixture. Not a full reproduction of the archived forecast and never a live record.')
    (OUT/'offline_repro.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence,indent=2))

if __name__=='__main__':main()
