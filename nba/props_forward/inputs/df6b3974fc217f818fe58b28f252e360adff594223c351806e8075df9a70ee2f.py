"""Explicit local shadow command; no scheduler, primary archive or site changes.

Use prepared pre-game feature rows (NBA_PROPS_DUMP), observed historical minutes,
the exact frozen primary parameters and fast_minutes_2027_dev1.json. Historical
inputs require --replay and never count as prospective evidence.
"""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import nba_props_repair as R
import nba_props_live_core as C
import nba_props_simple_test as P


def make_shadow(z, history, frozen, candidate, cutoff, captured, replay=False):
    cutoff=pd.Timestamp(cutoff); captured=pd.Timestamp(captured)
    if cutoff.tzinfo is None or captured.tzinfo is None:
        raise ValueError('Timestamps need timezone')
    if not replay and not cutoff-pd.Timedelta(minutes=45)<=captured<=cutoff:
        raise ValueError('Not in genuine pre-cutoff capture window; use explicitly labelled replay')
    if z.game_id.nunique()!=1 or z.season.nunique()!=1 or z.duplicated(['team','aid']).any():
        raise ValueError('One unique game and player identities required')
    if int(z.season.iloc[0])!=int(candidate['season']) or int(frozen['season'])!=int(candidate['season']):
        raise ValueError('Parameter season mismatch')
    h=history.copy(); h['tip']=pd.to_datetime(h.tip,utc=True)
    if not replay:
        if 'observed_at_utc' not in h:
            raise ValueError('Live history requires per-row observed-at provenance')
        h['observed_at_utc']=pd.to_datetime(h.observed_at_utc,utc=True)
        if (h.observed_at_utc>captured).any() or (h.observed_at_utc<h.tip).any():
            raise ValueError('Invalid observed-history timing')
    z=R.fast_inputs(z,h)
    q=R.fast_minutes(z,frozen,candidate)
    pa=np.clip(z.pa1.to_numpy(),1e-3,1-1e-3)
    players=[dict(aid=int(x.aid),team=x.team,p_appear=float(pa[i]),
        fast_used=bool(x.fast_used),minutes_given_appearing=q[i].tolist()) for i,x in enumerate(z.itertuples())]
    for st in ('reb','ast'):
        rate,disp=C.prop_rate(z,st,frozen['props'])
        cond=P.mixture_pmf(rate,q,disp,P.SUP_FULL[st])
        unc=cond*pa[:,None]; unc[:,0]+=1-pa
        for i,p in enumerate(players):
            p[st+'_given_appearing']=cond[i].tolist()
            p[st+'_including_dnp_zero']=unc[i].tolist()
    return dict(model_id=R.MODEL_ID,game_id=int(z.game_id.iloc[0]),cutoff_utc=str(cutoff),
        captured_at_utc=str(captured),replay=bool(replay),eligible_for_primary_test=False,
        status='separate_experimental_shadow_not_adopted',players=players,
        settlement_warning='DNP-zero is a statistical mixture, not a verified contract settlement rule.',
        original_failed_gate=candidate.get('failed_original_gate'),
        warning='No independent upload receipt; not part of M2/M2b adoption test.')


def main():
    a=argparse.ArgumentParser(description=__doc__)
    for name in ('features','history','frozen','candidate','cutoff','output'): a.add_argument('--'+name,required=True)
    a.add_argument('--replay',action='store_true'); args=a.parse_args()
    b=Path(args.frozen).read_bytes(); candidate=json.loads(Path(args.candidate).read_bytes())
    if hashlib.sha256(b).hexdigest()!=candidate['primary_parameter_sha256']:
        raise ValueError('Challenger must use the exact frozen primary parameter bytes')
    z=pd.read_csv(args.features); h=pd.read_csv(args.history)
    out=make_shadow(z,h,json.loads(b),candidate,args.cutoff,datetime.now(timezone.utc).isoformat(),args.replay)
    out['input_sha256']={key:hashlib.sha256(Path(getattr(args,key)).read_bytes()).hexdigest() for key in ('features','history','frozen','candidate')}
    out['code_sha256']={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
        for name in ('nba_props_shadow.py','nba_props_repair.py','nba_props_live_core.py','nba_props_simple_test.py')}
    R.write_immutable(args.output,out)
    print(json.dumps(dict(path=args.output,players=len(out['players']),replay=out['replay'])))


if __name__=='__main__':main()
