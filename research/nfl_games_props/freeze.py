"""Freeze the same 2026 fits for deterministic local inference; no new tuning."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import core as C
from build import OUT
from run import model,app_model


def pack(pipe,features):
    scale,fit=pipe.steps[0][1],pipe.steps[1][1]
    return dict(features=features,mean=scale.mean_.tolist(),scale=scale.scale_.tolist(),
        coef=np.asarray(fit.coef_).tolist(),intercept=np.asarray(fit.intercept_).tolist())


def linear(z,p):
    x=(z[p['features']].to_numpy(float)-np.asarray(p['mean']))/np.asarray(p['scale'])
    coef=np.asarray(p['coef']);v=x@coef.T+np.asarray(p['intercept'])
    return np.asarray(v).reshape(-1)


def main():
    if (OUT/'frozen_2026.json').exists():raise FileExistsError('Frozen prototype already exists')
    result=json.loads((OUT/'results.json').read_text())
    g=pd.read_parquet(OUT/'games.parquet');g=g[(g.season>=2010)&(g.season<2026)&g.home_score.notna()].copy()
    g['margin']=g.home_score-g.away_score;g['total']=g.home_score+g.away_score
    x=g[C.GAME_FEATURES];y=g.margin
    win=model('win').fit(x[y!=0],(y[y!=0]>0).astype(int))
    margin=model('score').fit(x,g.margin);total=model('score').fit(x,g.total)
    t=pd.read_parquet(OUT/'teams.parquet');t=t[(t.season>=2018)&(t.season<2026)&t.actual_team_att.notna()&(t.actual_team_att>0)]
    volume=model('volume').fit(t[C.VOLUME_FEATURES],t.actual_team_att)
    p=pd.read_parquet(OUT/'players.parquet');p=p[(p.season>=2018)&(p.season<2026)&p.actual_team_att.notna()&p.app.notna()]
    ap=app_model(p)
    predictions=pd.read_parquet(OUT/'game_predictions.parquet');cal=predictions[(predictions.season>=2022)&(predictions.season<=2025)]
    frozen=dict(model_id='nfl-independent-foundation-dev1',season=2026,training_last_season=2025,
        game_win=pack(win,C.GAME_FEATURES),game_margin=pack(margin,C.GAME_FEATURES),game_total=pack(total,C.GAME_FEATURES),
        volume=pack(volume,C.VOLUME_FEATURES),appearance=pack(ap,C.APP_FEATURES),
        volume_dispersion=C.fit_nb(t.actual_team_att,np.clip(volume.predict(t[C.VOLUME_FEATURES]),5,70)),
        props=result['props']['frozen']['2026'],
        margin_residuals=(cal.margin-cal.margin_mean).tolist(),total_residuals=(cal.total-cal.total_mean).tolist(),
        limits=['Experimental; no market edge or deployment','Unseen/debut candidates excluded','No replay-validated injury/expected-starter news',
            'Per-player conditional marginals, NOT a jointly reconciled roster/target simulator','Separate margin and total forecasts, not joint scores',
            'DNP-zero mixture is not a bookmaker settlement convention'])
    # Check serialization reproduces estimator predictions, including Poisson/logit links.
    assert np.allclose(linear(g,frozen['game_margin']),margin.predict(x))
    w=1/(1+np.exp(-linear(g,frozen['game_win'])))
    assert np.allclose(w,win.predict_proba(x)[:,1])
    assert np.allclose(np.exp(linear(t,frozen['volume'])),volume.predict(t[C.VOLUME_FEATURES]))
    with (OUT/'frozen_2026.json').open('x') as f:json.dump(frozen,f,indent=2)
    print(json.dumps(dict(frozen=str(OUT/'frozen_2026.json'),serialization_verified=True,sha256=hashlib.sha256((OUT/'frozen_2026.json').read_bytes()).hexdigest())))


if __name__=='__main__':main()
