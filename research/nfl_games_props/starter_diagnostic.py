"""Separate outcome first passer from primary passer; no forecast changes."""
import json
import pandas as pd
from starter_test import DEST,OUT,locate,sha,now

def main():
    dest=DEST/'FIRST_PASSER_DIAGNOSTIC.json'
    if dest.exists():raise FileExistsError(dest)
    path=locate('play_by_play_2025.csv.gz')
    keep={'game_id','posteam','play_id','qb_dropback','passer_player_id','play_type'}
    pb=pd.read_csv(path,usecols=lambda c:c in keep,low_memory=False)
    qbids=set(pd.read_parquet(DEST/'expanded_features.parquet').aid)
    pb=pb[(pb.qb_dropback==1)&pb.passer_player_id.isin(qbids)&pb.play_type.isin(['pass','run'])].sort_values(['game_id','play_id'])
    first=pb.drop_duplicates(['game_id','posteam'])[['game_id','posteam','passer_player_id']].rename(columns={'posteam':'team','passer_player_id':'first_observed_passer'})
    paired=pd.read_parquet(DEST/'paired_scores.parquet')
    a=paired[(paired.app==1)&(paired.actual_primary==1)&(paired.last_was_primary==0)].merge(first,on=['game_id','team'],how='left',validate='many_to_one')
    a['first_passer_is_primary']=a.first_observed_passer==a.aid
    def stats(z):
        return dict(n=len(z),baseline=float(z.baseline_cond_rps.mean()),candidate=float(z.candidate_cond_rps.mean()),
            depth_rank_one=int((z.depth_signal==1).sum()),depth_lower_rank=int((z.depth_signal==-1).sum()),
            relative_gain=float(1-z.candidate_cond_rps.mean()/z.baseline_cond_rps.mean()))
    result=dict(created=now(),pbp_path=str(path),pbp_sha256=sha(path),
        note='Outcome-only first observed passing QB, not verified announced starter. Never used as a feature. Candidate-ID filter can miss an earlier unlisted QB; unknowns cannot establish in-game injury.',
        groups={str(k):stats(z) for k,z in a.groupby('first_passer_is_primary')},
        new_primary_depth_signals=a.depth_signal.value_counts().to_dict())
    with dest.open('x') as f:json.dump(result,f,indent=2)
    a.to_parquet(DEST/'first_passer_diagnostic_rows.parquet',index=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
