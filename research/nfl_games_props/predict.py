"""Reproducible private preview from frozen parameters and lagged feature tables."""
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from build import OUT
from freeze import linear
import core as C


def main():
    dest=OUT/'frozen_preview.json'
    if dest.exists():raise FileExistsError('Preview already exists')
    f=json.loads((OUT/'frozen_2026.json').read_text());now=pd.Timestamp.now(tz='UTC')
    g=pd.read_parquet(OUT/'games.parquet');g=g[(g.tip>now)&(g.tip<now+pd.Timedelta(days=8))].copy()
    t=pd.read_parquet(OUT/'teams.parquet');t=t[t.game_id.isin(g.game_id)].copy().reset_index(drop=True)
    p=pd.read_parquet(OUT/'players.parquet');p=p[p.game_id.isin(g.game_id)].copy()
    gm=linear(g,f['game_margin']);gt=linear(g,f['game_total']);wp=1/(1+np.exp(-linear(g,f['game_win'])))
    margin=C.empirical_pmf(gm,f['margin_residuals'],-70,70);total=C.empirical_pmf(gt,f['total_residuals'],0,120)
    games=[dict(game_id=r.game_id,home=r.home,away=r.away,tip=str(r.tip),home_win_probability=float(wp[i]),
        elo_home_win_probability=float(r.elo_p),margin_mean=float(gm[i]),total_mean=float(gt[i]),
        margin_support_start=-70,margin_pmf=margin[i].tolist(),total_pmf=total[i].tolist()) for i,r in enumerate(g.itertuples())]
    mu=np.clip(np.exp(linear(t,f['volume'])),5,70);v=C.nb_pmf(mu,f['volume_dispersion'],100)
    idx={(r.game_id,r.team):i for i,r in enumerate(t.itertuples())}
    players=[]
    for stat in ('attempts','receptions'):
        z=p[(p.position=='QB') if stat=='attempts' else p.position.isin(['WR','TE','RB','FB'])].copy().reset_index(drop=True)
        pp=f['props'][stat];pa=np.clip(1/(1+np.exp(-linear(z,f['appearance']))),1e-3,1-1e-3)
        rate=C.rates(z,pp['position_priors'],stat);limit=100 if stat=='attempts' else 40
        vi=np.array([idx[(r.game_id,r.team)] for r in z.itertuples()])
        cond=C.allocation_pmf(v[vi],rate,pp['concentration'],limit)
        for i,r in enumerate(z.itertuples()):
            unc=pa[i]*cond[i];unc[0]+=1-pa[i]
            players.append(dict(game_id=r.game_id,team=r.team,aid=r.aid,name=r.name,stat=stat,
                offensive_involvement_probability=float(pa[i]),conditional_mean=float(cond[i]@np.arange(limit+1)),
                conditional_pmf=cond[i].tolist(),including_dnp_zero_pmf=unc.tolist()))
    audit=json.loads((OUT/'data_validation.json').read_text())
    record=dict(model_id=f['model_id'],generated_utc=datetime.now(timezone.utc).isoformat(),research_only=True,
        latest_input_game=audit['latest_player_target_game'],games=games,players=players,limits=f['limits'],
        forward_test_eligible=False,reason='Not independently pre-cutoff archived; prototype failed/passed screens must be reviewed separately')
    with dest.open('x') as h:json.dump(record,h)
    print(json.dumps(dict(path=str(dest),games=len(games),player_props=len(players),research_only=True)))


if __name__=='__main__':main()
