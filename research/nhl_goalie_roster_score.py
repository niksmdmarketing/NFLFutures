import sys,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import argparse
parser=argparse.ArgumentParser(description="Score the registered paired NHL goalie roster check")
parser.add_argument("baseline")
parser.add_argument("variant")
parser.add_argument("--out",required=True)
args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parent));import nhl_holdout as H
base=Path(args.baseline);variant=Path(args.variant)
expected={2015,2016,2017,2018,2021,2022,2023,2024,2025}
keys=['season','week','date','team'];counts={};hashed={}
for path in [base,variant]:
 years={int(p.stem.split('_')[1]) for p in path.glob('nhl_*.csv')};assert years==expected,(path,years)
 for y in sorted(expected):
  p=path/f'nhl_{y}.csv';raw=p.read_bytes();hashed[str(Path(path.name)/p.name)]=hashlib.sha256(raw).hexdigest()
for y in sorted(expected):
 a=pd.read_csv(base/f'nhl_{y}.csv').sort_values(keys).reset_index(drop=True);b=pd.read_csv(variant/f'nhl_{y}.csv').sort_values(keys).reset_index(drop=True)
 assert not a.duplicated(keys).any() and not b.duplicated(keys).any()
 pd.testing.assert_frame_equal(a[keys],b[keys]);counts[y]={'rows':len(a),'checkpoints':int(a.week.nunique()),'teams':int(a.team.nunique())}
 for market,(pc,yc) in H.MK.items():
  for d in [a,b]:
   assert np.isfinite(d[[pc,yc]].to_numpy()).all()
   assert d[pc].between(0,1).all() and d[yc].isin([0,1]).all()
  np.testing.assert_array_equal(a[yc],b[yc])
assert json.loads((base/'rating_identities.json').read_text())==json.loads((variant/'rating_identities.json').read_text())
L=H.per_season(str(base));V=H.per_season(str(variant));D=L-V
markets={m:dict(zip(['mean_gain','lower_90','upper_90'],H.boot(D[m]))) for m in H.MK}
combined=dict(zip(['mean_gain','lower_90','upper_90'],H.boot(D[list(H.MK)].mean(axis=1))))
gates={'combined_lower_above_zero':combined['lower_90']>0,'no_market_mean_below_minus_0005':all(r['mean_gain']>=-0.0005 for r in markets.values())}
result={'rule':'research/NHL_GOALIE_ROSTER_RULE.md','scale':0.438,'simulations':2000,'seasons':sorted(expected),'excluded_2014':'No earlier RAPM shift data; exclusion committed before replay','matched_rows':counts,'identical_player_ratings':True,'baseline_scores':L.to_dict(orient='index'),'variant_scores':V.to_dict(orient='index'),'markets':markets,'combined':combined,'gates':gates,'pass':all(gates.values()),'seasons_better':int((D.mean(axis=1)>0).sum()),'per_season_gain':D.to_dict(orient='index'),'output_hashes':hashed}
Path(args.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:result[k] for k in ['markets','combined','gates','pass','seasons_better']},indent=2))
H.main([str(base),str(variant)])
