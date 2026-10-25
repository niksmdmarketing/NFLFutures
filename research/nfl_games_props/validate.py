import json
import pandas as pd
import numpy as np
from build import OUT
import core as C

def main():
    g=pd.read_parquet(OUT/'games.parquet');t=pd.read_parquet(OUT/'teams.parquet');p=pd.read_parquet(OUT/'players.parquet')
    assert not g.duplicated('game_id').any()
    assert not t.duplicated(['game_id','team']).any()
    assert not p.duplicated(['game_id','team','aid']).any()
    assert np.isfinite(g[C.GAME_FEATURES].to_numpy()).all()
    assert np.isfinite(t[C.VOLUME_FEATURES].to_numpy()).all()
    assert np.isfinite(p[C.APP_FEATURES].to_numpy()).all()
    assert (p.receptions<=p.targets).all()
    known=p[p.actual_team_att.notna()]
    assert (known.attempts<=known.actual_team_att).all()
    assert (known.receptions<=known.actual_team_att).all()
    contradiction=known[(known.app==0)&((known.attempts>0)|(known.targets>0))]
    report=dict(games=len(g),team_rows=len(t),players=len(p),
        appearance_contradictions=len(contradiction),
        unknown_played_candidates=int(p[p.game_id.isin(g[g.home_score.notna()].game_id)].app.isna().sum()),
        latest_completed_schedule_game=str(g[g.home_score.notna()].tip.max()),
        latest_player_target_game=str(p[p.actual_team_att.notna()].tip.max()))
    (OUT/'data_validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if len(contradiction):raise ValueError('Appearance labels contradict known production; inspect before scoring')

if __name__=='__main__':main()
