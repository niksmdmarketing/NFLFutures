"""LOSO choice of a late-season logit temperature for the NBA award simulation. Usage: python research/nba_awards_temp_loso.py <dir with nbaawT_a.csv, nbaawT_b.csv from nba_awards_replay.py with AW_TEMPS/AW_LATE_ONLY>"""
import sys, pandas as pd, numpy as np
S=sys.argv[1]
R=pd.concat([pd.read_csv(f"{S}/nbaawT_a.csv"),pd.read_csv(f"{S}/nbaawT_b.csv")])
R=R[R.method.str.startswith("sim")]
for aw,g in R.groupby("award"):
    piv=g.pivot_table(index=["season","ck"],columns="method",values="nll")
    ps=piv.groupby(level=0).mean()
    loso=[]
    for y in ps.index:
        tr=ps.drop(y).mean(); best=tr.idxmin(); loso.append((y,best,ps.loc[y,best]-ps.loc[y,"sim"]))
    gain=-np.mean([d for _,_,d in loso]); better=sum(d<0 for _,_,d in loso)
    favs=g.groupby("method").agg(fav=("fav","mean"),won=("fav_won","mean")).round(2)
    print(aw, ps.mean().round(3).to_dict(), "LOSO gain %.3f better %d/%d picks %s"%(gain,better,len(loso),pd.Series([b for _,b,_ in loso]).value_counts().to_dict()))
    print(favs.T.to_string())
