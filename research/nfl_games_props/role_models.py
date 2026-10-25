"""Explicit marginal workload states; player conversion rates are separate."""
import bisect
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
import core as C

NUM=C.APP_FEATURES+['history_qb_share','last_qb_share','last_was_primary','prior_primary_out']
CAT=['report_status','practice_status']

def history_features(p,stats,games):
    """Only earlier team games update role. No target labels are read here."""
    p=p.copy();stats=stats.copy();stats=stats[stats.position=='QB']
    stats=stats.merge(games[['game_id','tip']],on='game_id',validate='many_to_one')
    history={}
    for (gid,t),z in stats.groupby(['game_id','team']):
        total=float(z.attempts.sum())
        if total<=0:continue
        primary=z.sort_values(['attempts','aid'],ascending=[False,True]).iloc[0].aid
        history.setdefault(t,[]).append((pd.Timestamp(z.tip.iloc[0]).value+pd.Timedelta(hours=6).value,
            primary,dict(zip(z.aid,z.attempts/total))))
    for t in history:history[t].sort(key=lambda x:x[0])
    timeline={t:[x[0] for x in h] for t,h in history.items()}
    p['history_qb_share']=np.clip(p.h_attempts/np.maximum(p.h_team_att,1),0,1)
    p['last_qb_share']=0.;p['last_was_primary']=0.;p['prior_primary_out']=0.
    for (gid,t),ix in p.groupby(['game_id','team']).groups.items():
        cutoff=pd.Timestamp(p.loc[ix[0],'tip'])-pd.Timedelta(hours=1)
        j=bisect.bisect_left(timeline.get(t,[]),cutoff.value)-1
        if j<0:continue
        _,primary,shares=history[t][j]
        p.loc[ix,'last_qb_share']=p.loc[ix,'aid'].map(shares).fillna(0).to_numpy()
        p.loc[ix,'last_was_primary']=(p.loc[ix,'aid']==primary).astype(float).to_numpy()
        last=p.loc[ix];last=last[last.aid==primary]
        out=len(last)>0 and last.report_status.isin(['Out','Doubtful']).any()
        p.loc[ix,'prior_primary_out']=float(out)
    return p

def primary_labels(p,stats):
    q=stats[(stats.position=='QB')&(stats.attempts>0)].sort_values(['attempts','aid'],ascending=[False,True])
    lead=q.drop_duplicates(['game_id','team'])[['game_id','team','aid']].rename(columns={'aid':'actual_primary_id'})
    z=p.merge(lead,on=['game_id','team'],how='left',validate='many_to_one')
    z['actual_primary']=(z.aid==z.actual_primary_id).astype(int)
    return z

def fit_role(train):
    z=train[(train.position=='QB')&(train.app==1)]
    tx=ColumnTransformer([('numeric',StandardScaler(),NUM),('categorical',OneHotEncoder(handle_unknown='ignore'),CAT)])
    m=make_pipeline(tx,LogisticRegression(C=1,max_iter=1000)).fit(z[NUM+CAT],z.actual_primary)
    states={}
    for name,flag,prior in [('primary',1,.95),('relief',0,.10)]:
        a=z[z.actual_primary==flag]
        share=float((a.attempts.sum()+100*prior)/(a.actual_team_att.sum()+100))
        share=float(np.clip(share,.001,.999))
        k=C.fit_concentration(a.attempts,a.actual_team_att,np.full(len(a),share))
        states[name]=dict(share=share,concentration=k,n=len(a))
    return m,states

def qb_pmf(volume,role_probability,states):
    n=len(volume);w=np.asarray(role_probability,float)
    if w.shape!=(n,) or np.any((w<0)|(w>1)):raise ValueError('Role weights outside [0,1]')
    distributions={name:C.allocation_pmf(volume,np.full(n,s['share']),s['concentration'],100) for name,s in states.items()}
    return w[:,None]*distributions['primary']+(1-w[:,None])*distributions['relief']

def receiving_parts(z,pri):
    target=(z.h_targets.to_numpy()+20*z.position.map(pri['target_share']).fillna(.08).to_numpy())/(z.h_team_att.to_numpy()+20)
    catch=(z.h_receptions.to_numpy()+8*z.position.map(pri['catch']).fillna(.65).to_numpy())/(z.h_targets.to_numpy()+8)
    return np.clip(target,1e-5,.999),np.clip(catch,1e-5,.999)

def missing_others(z,target,pa):
    x=z[['game_id','team']].copy();x['missing']=np.asarray(target)*(1-np.asarray(pa))
    return np.clip(x.groupby(['game_id','team']).missing.transform('sum').to_numpy()-x.missing.to_numpy(),0,.8)

def repair_budget(z,share,pa):
    x=z[['game_id','team']].copy();x['mass']=np.asarray(share)*np.asarray(pa)
    total=x.groupby(['game_id','team']).mass.transform('sum').to_numpy()
    return np.asarray(share)/np.maximum(total,1),total>1

def redistribute(z,share,pa,beta):
    if not 0<=beta<=1:raise ValueError('beta outside prescribed bounds')
    other=missing_others(z,share,pa)
    raw=np.clip(np.asarray(share)/(1-beta*other),1e-5,.999)
    repaired,changed=repair_budget(z,raw,pa)
    return repaired,other,changed

def fit_redistribution(z,share,pa):
    active=(z.app==1).to_numpy();n=z.actual_team_att.to_numpy()[active];y=z.targets.to_numpy()[active]
    def loss(beta):
        pred,_,_=redistribute(z,share,pa,float(beta));p=np.clip(pred[active],1e-6,1-1e-6)
        return float(-np.sum(y*np.log(p)+(n-y)*np.log1p(-p))+beta**2/(2*.5**2))
    fit=minimize_scalar(loss,bounds=(0,1),method='bounded')
    return float(fit.x)

def serial_logistic(m):
    tx=m[0];num=tx.named_transformers_['numeric'];cat=tx.named_transformers_['categorical']
    return dict(numeric=NUM,categorical=CAT,mean=num.mean_.tolist(),scale=num.scale_.tolist(),
        categories=[x.tolist() for x in cat.categories_],coef=m[-1].coef_[0].tolist(),intercept=float(m[-1].intercept_[0]))
