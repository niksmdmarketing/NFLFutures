"""Audit actual NHL voted-award pool counts; no fitting or award probability replay."""
import gzip,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'pipeline'),str(ROOT/'research')]
import nhl,nhl_awards as A,nhl_awards_replay as H
nhl.NHL_OUT=sys.argv[1];out=Path(sys.argv[2]);R=pd.read_csv(ROOT/'model/replay/nhl_awards_replay.csv');R=R[R.method.eq('T1.0')&R.frac.between(.1,.9)&R.award.isin(['Hart','Vezina','Norris','Calder'])]
T={};rows=[];caps={'Hart':26,'Vezina':10,'Norris':12,'Calder':16}
for year in sorted(R.season.unique()):
 for y in [int(year)-1,int(year)]:
  if y not in T:T[y]=A.season_tables(y)
 snaps=json.load(gzip.open(ROOT/f'model/replay/nhl_award_snapshots/{year}.json.gz','rt'));ordered=sorted(snaps.items())
 for ck in sorted(R[R.season.eq(year)].ck.unique()):
  day,snap=ordered[int(ck)];tc={year:H.snapshot_tables(snap,T[year]),year-1:T[year-1]};c,sk,gl,sks,gls,*_=A.sim_pool('Calder',year,tc,None)
  # sim_pool uses the same simulation seed/arrays for every award; only pool() changes.
  sk2=sk.assign(pts=sks['pts'].mean(0),goals=sks['goals'].mean(0),gp=sks['gp'].mean(0)) if len(sk) else sk
  gl2=gl.assign(saa=gls['saa'].mean(0),gp=gls['gp'].mean(0)) if len(gl) else gl
  for award,cap in caps.items():
   candidates=A.pool(award,sk2,gl2);win=A.norm(A.WINNERS[award][year]);known=win in set(candidates.name.map(A.norm));z=R[R.season.eq(year)&R.ck.eq(ck)&R.award.eq(award)].iloc[0]
   rows.append({'season':int(year),'ck':int(ck),'date':day,'award':award,'actual_pool':len(candidates),'assumed_pool':cap,'winner_in_pool_actual':known,'winner_positive_probability':bool(z.p_winner>0)})
d=pd.DataFrame(rows);d.to_csv(out/'nhl_voted_actual_pools.csv',index=False);summary={'rows':len(d),'pool_size_mismatch_rows':int(d.actual_pool.ne(d.assumed_pool).sum()),'membership_vs_positive_probability_mismatch_rows':int(d.winner_in_pool_actual.ne(d.winner_positive_probability).sum()),'by_award':{a:{'actual_sizes':sorted(map(int,z.actual_pool.unique())),'rows':len(z),'size_mismatches':int(z.actual_pool.ne(z.assumed_pool).sum())} for a,z in d.groupby('award')}};(out/'nhl_voted_pool_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))
