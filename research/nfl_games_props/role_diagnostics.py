"""Outcome-defined role changes: diagnostics only, never predictor selection."""
import json,hashlib
import pandas as pd
from role_test import DEST,utc

def main():
    target=DEST/'OUTCOME_ROLE_DIAGNOSTIC.json'
    if target.exists():raise FileExistsError(target)
    p=pd.read_parquet(DEST/'role_features.parquet')
    s=pd.read_parquet(DEST/'paired_scores.parquet');s=s[(s.stat=='attempts')&(s.app==1)]
    z=s.merge(p[['game_id','team','aid','actual_primary','last_was_primary']],on=['game_id','team','aid'],validate='one_to_one')
    z['actual_new_primary']=(z.actual_primary==1)&(z.last_was_primary==0)
    result=dict(created=utc(),label='Outcome-defined diagnostic only; not a pregame group, selection rule or adoption gate',groups={})
    for flag,x in z.groupby('actual_new_primary'):
        result['groups'][str(flag)]=dict(n=len(x),baseline=float(x.baseline_cond_rps.mean()),candidate=float(x.candidate_cond_rps.mean()),
            relative_gain=float(1-x.candidate_cond_rps.mean()/x.baseline_cond_rps.mean()),
            by_season=x.groupby('season')[['baseline_cond_rps','candidate_cond_rps']].mean().reset_index().to_dict('records'))
    result['coverage']=json.loads((DEST/'results.json').read_text())['coverage']
    result['coverage_denominator']='Team-games already having at least one historical QB candidate; excludes completely uncovered team-games'
    result['script_sha256']=hashlib.sha256(__file__.encode()).hexdigest() if False else hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest()
    with target.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
