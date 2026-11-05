"""Reproduce published summaries without rerunning or changing any forecasting model."""
import gzip,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit,logit
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'research'));import nba_nhl_award_eval as E

def glm(X,y,seasons):
 def objective(b):
  z=X@b;return float((np.logaddexp(0,z)-y*z).sum()),X.T@(expit(z)-y)
 fit=minimize(objective,np.zeros(X.shape[1]),jac=True,method='BFGS',options={'gtol':1e-8,'maxiter':1000})
 q=expit(X@fit.x);bread=np.linalg.pinv(X.T@((q*(1-q))[:,None]*X));scores=[]
 for s in np.unique(seasons):
  k=seasons==s;scores.append(X[k].T@(y[k]-q[k]))
 S=np.array(scores);g=len(S);n=len(y);k=X.shape[1];meat=S.T@S;robust=bread@meat@bread*g/(g-1)*(n-1)/(n-k)
 return {'coefficients':fit.x.tolist(),'naive_se':np.sqrt(np.diag(bread)).tolist(),'season_cluster_se':np.sqrt(np.diag(robust)).tolist(),'score_gradient_max':float(abs(objective(fit.x)[1]).max())}

R=pd.concat([pd.read_csv(ROOT/f'model/replay/nba_{y}.csv') for y in range(2013,2027)],ignore_index=True)
assert not R.duplicated(['season','week','team']).any()
pre=R[R.week.eq(0)].set_index(['season','team']);D=R[R.gp_avg.between(5,20)].copy();result={'window':'5 <= league-average games played <= 20','clip':.002,'logit_increase':.7,'markets':{}}
for m,(p,y) in {'title':('p_title','y_title'),'playoff':('p_playoff','y_playoff'),'seed1':('p_seed1','y_seed1'),'finals':('p_conf','y_finals')}.items():
 prior=pre[p].reindex(pd.MultiIndex.from_frame(D[['season','team']])).to_numpy();cur=logit(np.clip(D[p],.002,.998));pr=logit(np.clip(prior,.002,.998));risers=D[cur-pr>.7];X=np.column_stack([np.ones(len(D)),cur,pr]);Y=D[y].to_numpy(float)
 result['markets'][m]={'riser_rows':len(risers),'riser_unique_team_seasons':int(risers[['season','team']].drop_duplicates().shape[0]),'riser_predicted':float(risers[p].mean()),'riser_actual':float(risers[y].mean()),'two_logit_fit':glm(X,Y,D.season.to_numpy()),'slope_fit':glm(X[:,:2],Y,D.season.to_numpy())}
(OUT/'nba_early_diagnostic_reproduced.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('NBA',json.dumps(result,indent=2),flush=True)

R=pd.read_csv(ROOT/'model/replay/nhl_awards_replay.csv');R=R[R.award.eq('Vezina')&R.frac.between(.1,.9)].copy();maxgames={}
for season in R.season.unique():
 snapshots=json.load(gzip.open(ROOT/f'model/replay/nhl_award_snapshots/{season}.json.gz','rt'))
 for ck,(day,snap) in enumerate(sorted(snapshots.items())):maxgames[(int(season),ck)]=max(t['gamesPlayed'] for t in snap['team'])
T=R[R.method.eq('T1.0')].copy();T['production_method']=['T0.6' if maxgames[(int(y),int(c))]>=82*2/3 else 'T1.0' for y,c in zip(T.season,T.ck)];T=T.drop(columns=['p_winner','fav','fav_won','nll','method']).rename(columns={'production_method':'method'}).merge(R[['season','ck','method','p_winner','fav','fav_won','nll']],on=['season','ck','method'],validate='one_to_one');assert len(T)==len(R[R.method.eq('T1.0')]);T['base']=np.where(T.p_winner>0,np.log(10),E.CLIP);T['model']=np.minimum(T.nll,E.CLIP);by=T.groupby(pd.cut(T.frac,[0,1/3,2/3,1.01],labels=['early','mid','late'],right=False),observed=False)[['model','base']].mean();ci=E.boot_ci(T)
res={'scope':'Existing replay rows at production max-team-games trigger; no forecasting rerun','rows':len(T),'late_rows_switched':int(T.method.eq('T0.6').sum()),'log_loss':float(T.model.mean()),'baseline_proxy_log_loss':float(T.base.mean()),'fav_said':float(T.fav.mean()),'fav_won':float(T.fav_won.mean()),'gap_ci90':ci,'by_third':by.to_dict(orient='index'),'passes_original_proxy_gates':bool(T.model.mean()<T.base.mean() and (by.model<by.base).all() and ci[0]<=0)}
(OUT/'vezina_production_method_check.json').write_text(json.dumps(res,indent=2),encoding='utf-8');T.to_csv(OUT/'vezina_hybrid_rows.csv',index=False);print('VEZINA',json.dumps(res,indent=2),flush=True)
