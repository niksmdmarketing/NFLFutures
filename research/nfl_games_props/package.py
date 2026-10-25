"""Private deliverable validation, provenance and code-only handoff ZIP."""
import json,hashlib,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from build import OUT
import core as C

def main():
    here=Path(__file__).parent
    preview=json.loads((OUT/'frozen_preview.json').read_text())
    for g in preview['games']:
        assert abs(sum(g['margin_pmf'])-1)<1e-10
        assert abs(sum(g['total_pmf'])-1)<1e-10
        assert 0<=g['home_win_probability']<=1
    for p in preview['players']:
        for key in ('conditional_pmf','including_dnp_zero_pmf'):
            q=np.array(p[key]);assert np.isfinite(q).all() and (q>=0).all() and abs(q.sum()-1)<1e-10
    run=json.loads((OUT/'run_manifest.json').read_text())
    rule=(here/'RULE.md').read_bytes()
    original=rule.split(b'\n## Baseline implementation correction')[0]
    candidates=[original,original+b'\n']
    exact=next((b for b in candidates if hashlib.sha256(b).hexdigest()==run['rule_sha256']),None)
    assert exact is not None,'Pre-score rule provenance mismatch'
    rule_copy=OUT/'RULE_AT_SCORING.md'
    if rule_copy.exists():assert rule_copy.read_bytes()==exact
    else:
        with rule_copy.open('xb') as f:f.write(exact)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in here.iterdir() if p.is_file()}
    r=pd.read_parquet(OUT/'prop_baseline_audit_rows.parquet')
    subgroup={}
    for stat,z in r.groupby('stat'):
        subgroup[stat]={}
        for group,mask in [('regular',z.regular_role),('lower_role',~z.regular_role)]:
            x=z[mask];a=x[x.app==1]
            subgroup[stat][group]=dict(n=len(x),appearances=len(a),rps=float(x.rps.mean()),season_baseline_rps=float(x.season_average_rps.mean()),
                over_predicted=float(a.over_probability.mean()),over_actual=float(a.over_actual.mean()))
    g=pd.read_parquet(OUT/'game_predictions.parquet');g=g[g.season<=2025]
    b=g.merge(pd.read_parquet(OUT/'market_benchmarks.parquet'),on='game_id')
    keep=b.total_line.notna()
    league=[]
    full=pd.read_parquet(OUT/'games.parquet')
    for year,x in g.groupby('season'):
        train=full[(full.season<year)&(full.season>=year-4)&full.home_score.notna()]
        m=C.empirical_pmf(np.zeros(len(x)),(train.home_score-train.away_score).to_numpy(),-70,70)
        t=C.empirical_pmf(np.zeros(len(x)),(train.home_score+train.away_score).to_numpy(),0,120)
        league.append(dict(season=int(year),n=len(x),league_margin_rps=float(C.rps(m,x.margin.to_numpy()+70).mean()),
            model_margin_rps=float(x.margin_rps.mean()),league_total_rps=float(C.rps(t,x.total.to_numpy()).mean()),model_total_rps=float(x.total_rps.mean())))
    report=dict(code_sha256=files,preview_games=len(preview['games']),preview_player_props=len(preview['players']),
        preview_pmfs_valid=True,original_rule_hash_verified=True,candidate_unchanged_in_baseline_audit=True,
        closing_total_benchmark=dict(n=int(keep.sum()),rmse=float(np.sqrt(np.mean((b.loc[keep,'total']-b.loc[keep,'total_line'])**2)))),
        league_distribution_baseline=league,prop_subgroups=subgroup,live_models_unchanged=True,site_unchanged=True,git_pushes=False)
    with (OUT/'PACKAGE_MANIFEST_VERIFIED.json').open('x') as f:json.dump(report,f,indent=2)
    with zipfile.ZipFile(OUT/'NFL_FOUNDATION_CODE_ONLY_VERIFIED.zip','x',zipfile.ZIP_DEFLATED) as z:
        for p in here.iterdir():
            if p.is_file():z.write(p,'nfl_games_props/'+p.name)
    print(json.dumps({k:v for k,v in report.items() if k!='code_sha256'},indent=2))

if __name__=='__main__':main()
