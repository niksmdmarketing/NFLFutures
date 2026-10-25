"""Small independent pre-game models. No market-price inputs."""
import numpy as np
from scipy.special import gammaln,betaln
from scipy.optimize import minimize_scalar
from scipy.stats import nbinom,poisson,betabinom

FIX={'OAK':'LV','SD':'LAC','STL':'LA','LAR':'LA','JAC':'JAX'}
EPA=['pass_off','rush_off','pass_def','rush_def']
GAME_FEATURES=[side+'_'+v for side in ('h','a') for v in EPA]
VOLUME_FEATURES=['own_att','opp_att','own_plays','opp_plays','own_pass_off','opp_pass_def','elo_gap']
APP_FEATURES=['app_rate','last_snap_share','mean_snap_share','miss_streak','is_qb']


def elo_probability(diff): return 1/(1+10**(-np.asarray(diff)/400))


def elo_change(diff,margin):
    # Adapted FiveThirtyEight algorithm; MIT notice retained in this directory.
    outcome=1 if margin>0 else 0 if margin<0 else .5
    winner_diff=diff if outcome==1 else -diff
    mult=np.log(abs(margin)+1)*2.2/(1 if outcome==.5 else winner_diff*.001+2.2)
    return 20*mult*(outcome-float(elo_probability(diff)))


def weighted(values,half=5):
    v=np.asarray(values,float)
    if not len(v):return np.nan
    w=.5**(np.arange(len(v))[::-1]/half)
    return float(w@v/w.sum())


def nb_pmf(mu,disp,limit):
    mu=np.asarray(mu,float).reshape(-1)
    k=np.arange(limit+1)[None,:]
    if np.isinf(disp): p=poisson.pmf(k,mu[:,None])
    else: p=nbinom.pmf(k,disp,disp/(disp+np.maximum(mu[:,None],1e-9)))
    # Final support point is a documented overflow bucket, never drop tail mass.
    p[:,-1]+=np.maximum(0,1-p.sum(1))
    return p/p.sum(1,keepdims=True)


def fit_nb(y,mu):
    y=np.asarray(y,float);mu=np.maximum(np.asarray(mu,float),1e-6)
    def loss(logr):
        r=np.exp(logr)
        return -np.mean(gammaln(y+r)-gammaln(r)-gammaln(y+1)+r*np.log(r/(r+mu))+y*np.log(mu/(r+mu)))
    res=minimize_scalar(loss,bounds=(np.log(.2),np.log(10000)),method='bounded')
    return float(np.exp(res.x))


def fit_concentration(y,n,p):
    y=np.asarray(y,int);n=np.asarray(n,int);p=np.clip(np.asarray(p,float),1e-5,1-1e-5)
    ok=(n>=y)&(y>=0)&(n>0)
    y,n,p=y[ok],n[ok],p[ok]
    def loss(logk):
        k=np.exp(logk);a=p*k;b=(1-p)*k
        return -np.mean(gammaln(n+1)-gammaln(y+1)-gammaln(n-y+1)+betaln(y+a,n-y+b)-betaln(a,b))
    res=minimize_scalar(loss,bounds=(0,np.log(2000)),method='bounded')
    return float(np.exp(res.x))


def allocation_pmf(volume,p,concentration,limit=None):
    """Mix counts over uncertain team attempts; player count <= team count."""
    volume=np.asarray(volume,float);p=np.clip(np.asarray(p,float),1e-6,1-1e-6)
    limit=volume.shape[1]-1 if limit is None else min(limit,volume.shape[1]-1)
    out=np.zeros((len(volume),limit+1))
    for n in range(volume.shape[1]):
        end=min(n,limit);k=np.arange(end+1)[None,:]
        cond=betabinom.pmf(k,n,(p*concentration)[:,None],((1-p)*concentration)[:,None])
        if n>limit:cond[:,-1]=betabinom.sf(limit-1,n,p*concentration,(1-p)*concentration)
        out[:,:end+1]+=volume[:,n,None]*cond
    return out/out.sum(1,keepdims=True)


def rates(z,priors,stat):
    pos=z.position.map(priors['target_share']).fillna(.08).to_numpy()
    if stat=='attempts':
        prior=z.position.map(priors['attempt_share']).fillna(.5).to_numpy()
        return np.clip((z.h_attempts.to_numpy()+20*prior)/(z.h_team_att.to_numpy()+20),1e-5,1-1e-5)
    target=(z.h_targets.to_numpy()+20*pos)/(z.h_team_att.to_numpy()+20)
    catch=z.position.map(priors['catch']).fillna(.65).to_numpy()
    success=(z.h_receptions.to_numpy()+8*catch)/(z.h_targets.to_numpy()+8)
    return np.clip(target*success,1e-5,1-1e-5)


def rps(p,y,clip=None):
    p=np.asarray(p);end=p.shape[1]-1 if clip is None else min(clip,p.shape[1]-1)
    return ((p.cumsum(1)[:,:end]-(np.asarray(y)[:,None]<=np.arange(end)[None,:]))**2).mean(1)


def pit(p,y,u):
    y=np.clip(np.asarray(y,int),0,p.shape[1]-1);idx=np.arange(len(y));f=p.cumsum(1)
    hi=f[idx,y];lo=np.where(y>0,f[idx,np.maximum(y-1,0)],0)
    return lo+np.asarray(u)*(hi-lo)


def empirical_pmf(means,residuals,lo,hi):
    support=np.arange(lo,hi+1)
    out=np.zeros((len(means),len(support)))
    residuals=np.asarray(residuals,float)
    for i,m in enumerate(means):
        samples=np.clip(np.rint(m+residuals),lo,hi).astype(int)
        out[i]=np.bincount(samples-lo,minlength=len(support))/len(samples)
    return out


def season_bound(gains,seasons,alpha=.05):
    """Season-cluster paired bootstrap; few seasons => limited precision."""
    seasons=np.asarray(seasons);gains=np.asarray(gains)
    unique=np.unique(seasons);s=np.array([gains[seasons==x].sum() for x in unique]);n=np.array([(seasons==x).sum() for x in unique])
    rng=np.random.default_rng(20261023);idx=rng.integers(0,len(unique),(4000,len(unique)))
    values=s[idx].sum(1)/n[idx].sum(1)
    return float(np.quantile(values,alpha))
