"""Offline test (Oct 2026): does NBL/AFL roster continuity improve preseason forecasts? Run: python pipeline/roster_continuity_test.py nbl|afl
Result: no. NBL every variant worse out of sample (RMSE 5.18 -> 5.25-5.29); AFL best 14.28 -> 14.24, not significant. Not adopted (TypeSafe 97%).
"""
import json,glob,re,numpy as np,pandas as pd,sys
sp=sys.argv[1]
val='eff' if sp=='nbl' else 'supercoach_points_pg'
use='mins' if sp=='nbl' else 'games'
P=[]
for f in glob.glob(f'build/{sp}_site/players_20*.json'):
    if f.endswith('p.json'): continue
    y=int(re.findall(r'(\d{4})',f)[-1]); d=json.load(open(f)); cols=['name','team']+[c['k'] for c in d['cols']]
    x=pd.DataFrame(d['rows'],columns=cols); x['season']=y
    if sp=='afl': x['v']=x[val]*x['games']
    else: x['v']=x[val]
    x['u']=x[use]; P.append(x[['season','name','team','u','v']])
P=pd.concat(P); P['key']=P.name.str.lower().str.replace(r'[^a-z]','',regex=True)
S=pd.read_csv(f'data/research/snapshots_{sp}.csv.gz'); S=S[S.checkpoint==1.0][['season','team','pd_pg','wp','gp']]
rows=[]
for y in sorted(P.season.unique()):
    if y-1 not in set(P.season): continue
    prev=P[P.season==y-1]; cur=P[P.season==y]
    for t in cur.team.unique():
        on=set(cur[cur.team==t].key)
        pt=prev[prev.team==t]
        if pt.u.sum()==0: continue
        cont=pt[pt.key.isin(on)].u.sum()/pt.u.sum()
        vcont=pt[pt.key.isin(on)].v.sum()/max(pt.v.sum(),1e-9)
        inc=prev[(prev.team!=t)&prev.key.isin(on)]
        rows.append(dict(season=y,team=t,cont=cont,vcont=vcont,inc_v=inc.v.sum()/max(prev.groupby('team').v.sum().mean(),1e-9)))
C=pd.DataFrame(rows)
M=S.merge(S.assign(season=S.season+1).rename(columns={'pd_pg':'pd1','wp':'wp1'})[['season','team','pd1','wp1']],on=['season','team']).merge(C,on=['season','team'])
M=M.dropna(); M=M[M.gp>=(20 if sp=='nbl' else 15)]; print(sp,'team-seasons',len(M),'seasons',M.season.min(),'-',M.season.max()); print(M[['pd_pg','pd1','cont','vcont','inc_v']].corr().round(2).iloc[:,:2])
def feats(D,v):
    c=D.cont-0.6; vc=D.vcont-0.6
    X={'base':[D.pd1],'cont':[D.pd1,D.pd1*c,c],'vcont':[D.pd1,D.pd1*vc,vc],'vcont_inc':[D.pd1,D.pd1*vc,vc,D.inc_v]}[v]
    return np.column_stack(X)
out={}
for v in ('base','cont','vcont','vcont_inc'):
    errs=[]
    for y in sorted(M.season.unique()):
        tr=M[M.season<y]
        if tr.season.nunique()<4: continue
        te=M[M.season==y]
        b=np.linalg.lstsq(feats(tr,v),tr.pd_pg,rcond=None)[0]
        errs+=list(te.pd_pg-feats(te,v)@b)
    e=np.array(errs); out[v]=e
    print(v,'n',len(e),'rmse',round(float(np.sqrt((e**2).mean())),3))
for v in ('cont','vcont','vcont_inc'):
    d=out[v]**2-out['base']**2; print(v,'vs base: mean diff',round(float(d.mean()),3),'t',round(float(d.mean()/(d.std()/np.sqrt(len(d)))),2))
