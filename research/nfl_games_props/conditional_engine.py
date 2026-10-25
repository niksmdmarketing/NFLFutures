"""Projection engine conditional on explicit participation and role assumptions."""
import numpy as np
import core as C

def line_probabilities(p,line):
    p=np.asarray(p,float);k=np.arange(len(p));line=float(line)
    if not np.isfinite(line) or line<0 or line>=len(p)-1:raise ValueError('Line outside exact support')
    return dict(line=line,over=float(p[k>line].sum()),under=float(p[k<line].sum()),push=float(p[k==line].sum()))

def describe(p):
    p=np.asarray(p,float)
    if np.any(p<0) or not np.isclose(p.sum(),1):raise ValueError('Invalid count PMF')
    k=np.arange(len(p));cdf=p.cumsum();mean=float(p@k)
    return dict(mean=mean,median=int(np.searchsorted(cdf,.5)),interval80=[int(np.searchsorted(cdf,.1)),int(np.searchsorted(cdf,.9))],
        zero_probability=float(p[0]),illustrative_line=line_probabilities(p,min(np.floor(mean)+.5,len(p)-1.5)),pmf=p.tolist(),
        support_start=0,upper_endpoint_is_overflow=True)

def starting_qb(volume,state):
    """A starting-role workload, including variability/early exits in training."""
    return C.allocation_pmf(np.asarray(volume,float).reshape(1,-1),np.array([state['share']]),state['concentration'],100)[0]

def target_budget(rows):
    enabled=[dict(r) for r in rows if r.get('assumed_playing',True) and r.get('include_projection',True)]
    ids=[r['aid'] for r in enabled]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate receiver IDs')
    fixed=0.;free=0.
    for r in enabled:
        value=r.get('target_share_override')
        r['explicit_share']=value is not None
        share=r['default_target_share'] if value is None else float(value)
        if not np.isfinite(share) or not 0<=share<=1:raise ValueError('Invalid target share')
        r['effective_target_share']=share
        if r['explicit_share']:fixed+=share
        else:free+=share
    if fixed>1+1e-10:raise ValueError('Explicit target shares exceed team budget')
    scale=min(1.,max(0.,1-fixed)/free) if free else 1.
    for r in enabled:
        if not r['explicit_share']:r['effective_target_share']*=scale
    total=sum(r['effective_target_share'] for r in enabled)
    if total>1+1e-9:raise ValueError('Target budget exceeded')
    return enabled,dict(default_share_scale=scale,explicit_share_total=fixed,unallocated_target_share=max(0.,1-total))

def receiving(volume,target_share,catch_probability,concentration):
    if not 0<=target_share<=1 or not 0<=catch_probability<=1:raise ValueError('Invalid production rate')
    return C.allocation_pmf(np.asarray(volume,float).reshape(1,-1),np.array([target_share*catch_probability]),concentration,40)[0]
