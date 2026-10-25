"""Correct specified season-average control; candidate forecasts unchanged."""
import json
import numpy as np
import pandas as pd
import core as C
from build import OUT,load_games,player_inputs,make_player_features

def main():
    dest=OUT/'baseline_audit.json'
    if dest.exists():raise FileExistsError('Audit already exists')
    g=load_games();st,sn,complete,identity=player_inputs(g)
    fresh,_=make_player_features(g,st,sn,complete,pd.read_parquet(OUT/'teams.parquet'))
    original=pd.read_parquet(OUT/'players.parquet')
    pd.testing.assert_frame_equal(original,fresh[original.columns],check_dtype=False,check_exact=False,atol=1e-12,rtol=0)
    fresh.to_parquet(OUT/'players_with_season_baseline.parquet',index=False)
    r=pd.read_parquet(OUT/'prop_predictions.parquet')
    key=['game_id','team','aid','season']
    r=r.merge(fresh[key+['season_attempts','season_receptions']],on=key,validate='many_to_one')
    pieces=[]
    for (year,stat),z in r.groupby(['season','stat']):
        train=fresh[(fresh.season>=2018)&(fresh.season<year)&(fresh.app==1)]
        train=train[(train.position=='QB') if stat=='attempts' else train.position.isin(['WR','TE','RB','FB'])]
        disp=C.fit_nb(train[stat],np.maximum(train['season_'+stat],.01))
        limit=100 if stat=='attempts' else 40;clip=60 if stat=='attempts' else 20
        q=C.nb_pmf(np.maximum(z['season_'+stat],.01),disp,limit)
        q*=z.pa.to_numpy()[:,None];q[:,0]+=1-z.pa.to_numpy()
        z=z.copy();z['season_average_rps']=C.rps(q,z.actual.to_numpy(),clip);pieces.append(z)
    r=pd.concat(pieces,ignore_index=True)
    r.to_parquet(OUT/'prop_baseline_audit_rows.parquet',index=False)
    out={}
    for stat,z in r.groupby('stat'):
        gain=z.season_average_rps-z.rps
        a=z[z.app==1];regular=a[a.regular_role]
        out[stat]=dict(n=len(z),candidate_rps=float(z.rps.mean()),season_average_rps=float(z.season_average_rps.mean()),
            relative_score_reduction=float(1-z.rps.mean()/z.season_average_rps.mean()),
            season_block_lower=C.season_bound(gain.to_numpy(),z.season),
            seasons_better=int(z.groupby('season').apply(lambda x:x.rps.mean()<x.season_average_rps.mean(),include_groups=False).sum()),
            regular_role_rps=float(z[z.regular_role].rps.mean()),regular_role_baseline_rps=float(z[z.regular_role].season_average_rps.mean()),
            regular_role_conditional_pit_deciles=(np.histogram(regular.pit,bins=10,range=(0,1))[0]/len(regular)).tolist(),
            by_season={int(y):dict(candidate=float(x.rps.mean()),season_average=float(x.season_average_rps.mean())) for y,x in z.groupby('season')})
    out['candidate_unchanged']=True
    out['whole_season_average_uses_only_available_prior_games']=True
    with dest.open('x') as f:json.dump(out,f,indent=2)
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
