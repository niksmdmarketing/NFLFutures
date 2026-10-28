"""Frozen scorer for NBA_AWARD_EARLY_SHRINK_RULE.md; no fitting or threshold selection."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

SEED=20261028
DRAWS=10000
FLOOR=.002
KEYS=['season','award','ck']
AWARDS={'MVP','DPOY','ROY','6MOY'}


def score(rows,expected_seasons=None):
    required=set(KEYS+['method','frac','L','team_games','p_winner','fav','fav_won'])
    if not required.issubset(rows):raise ValueError('Missing exact checkpoint/probability fields')
    x=rows[(rows.ck>=0)&rows.method.isin(['sim','shrink'])].copy()
    if x.duplicated(KEYS+['method']).any():raise ValueError('Duplicate paired row')
    if not np.isfinite(x[['frac','L','team_games','p_winner','fav','fav_won']].to_numpy(float)).all():raise ValueError('Non-finite score input')
    if ((x.p_winner<0)|(x.p_winner>1)|(x.fav<0)|(x.fav>1)).any():raise ValueError('Invalid probability')
    if not np.allclose(x.frac*x.L,x.team_games,rtol=0,atol=1e-9):raise ValueError('Rounded frac disagrees with raw team games')
    if 'probability_mass' in x and not np.allclose(x.probability_mass,1,rtol=0,atol=1e-10):raise ValueError('Invalid probability mass')
    pair=x.pivot(index=KEYS,columns='method',values='p_winner')
    if set(pair.columns)!={'sim','shrink'} or pair.isna().any().any():raise ValueError('Unpaired forecasts')
    meta=x.groupby(KEYS)[['L','team_games']].nunique()
    if (meta>1).any().any():raise ValueError('Arms disagree on checkpoint')
    x=x[x.team_games<20].copy()
    if x.empty:raise ValueError('No eligible rows')
    if expected_seasons is not None:
        expected={(y,a,k) for y in expected_seasons for a in AWARDS for k in range(5)}
        # All registered opening checkpoints must exist, including any excluded at 20+.
        actual=set(map(tuple,pair.index))
        if actual!=expected:raise ValueError('Missing/unexpected registered season-award-checkpoint cells')
    x['score']=-np.log(x.p_winner.clip(lower=FLOOR))
    p=x.pivot(index=KEYS,columns='method',values='score')
    if p.isna().any().any():raise ValueError('Eligibility filtering broke pairing')
    p['gain']=p['sim']-p['shrink']
    # Registered mean over all award/checkpoint rows, paired. Resample whole seasons.
    totals=p.groupby('season')['gain'].agg(['sum','count'])
    rng=np.random.default_rng(SEED)
    draws=rng.integers(0,len(totals),size=(DRAWS,len(totals)))
    boot=totals['sum'].to_numpy()[draws].sum(axis=1)/totals['count'].to_numpy()[draws].sum(axis=1)
    interval=np.quantile(boot,[.05,.95])
    award=p.groupby('award')[['sim','shrink','gain']].mean()
    seasons=p.groupby('season')[['sim','shrink','gain']].mean()
    share=float((seasons.gain>=0).mean())
    gain=float(p.gain.mean())
    gates={
        'G1':{'pass':bool(gain>0 and interval[0]>0),'gain':gain,'central_90_ci':[float(v) for v in interval]},
        'G2':{'pass':bool((award.gain>=-.05).all()),'minimum_award_gain':float(award.gain.min()),'maximum_allowed_loss':.05},
        'G3':{'pass':bool(share>=.60),'better_or_equal_seasons':int((seasons.gain>=0).sum()),'seasons':len(seasons),'share':share,'required_share':.60},
    }
    calibration=[]
    for (a,k,m),g in x.groupby(['award','ck','method']):
        calibration.append({'award':a,'ck':int(k),'day':(3,7,14,21,28)[int(k)],'method':m,'n':len(g),'favourite_said':float(g.fav.mean()),'favourite_won':float(g.fav_won.mean())})
    def records(frame,index):return [{index:str(i),**{k:float(v) for k,v in r.items()}} for i,r in frame.iterrows()]
    return {'verdict':'pass' if all(g['pass'] for g in gates.values()) else 'fail','gates':gates,
            'mean_nll':{m:float(p[m].mean()) for m in ('sim','shrink')},'gain':gain,'paired_cells':len(p),'seasons':len(seasons),
            'bootstrap':{'seed':SEED,'draws':DRAWS,'unit':'whole season','interval':'central 90% (5th, 95th percentiles)'},'floor':FLOOR,
            'per_award':records(award,'award'),'per_season':records(seasons,'season'),'favourite_said_won':calibration,
            'floor_hits':{m:int((x[x.method==m].p_winner<=FLOOR).sum()) for m in ('sim','shrink')},
            'diagnostics':{'invalid_simulation_draws':int(x[x.method=='sim'].get('invalid_draws',pd.Series(dtype=float)).sum()),
                           'validation':'paired cells; exact raw counts; finite probabilities; unit mass'},
            'interpretation':'Retrospective LOSO on repaired research sim; not a live-site adoption or profitability result.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('input',nargs='?',default='model/replay/nba_awards_early_shrink.csv');ap.add_argument('--output',default='research/nba_award_early_shrink_results.json');a=ap.parse_args()
    path=Path(a.input);result=score(pd.read_csv(path),range(2010,2027));result['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'verdict':result['verdict'],'mean_nll':result['mean_nll'],'gates':result['gates']},indent=2))
if __name__=='__main__':main()
