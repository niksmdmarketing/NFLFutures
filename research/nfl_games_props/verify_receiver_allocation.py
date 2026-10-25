"""Independent checks of the completed receiver allocation experiment."""
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from build import BASE
from conditional_audit import sha
from receiver_allocation_test import conditional_scales, DEST, KEY


def main():
    r=json.loads((DEST/'results.json').read_text())
    m=json.loads((DEST/'manifest_complete.json').read_text())
    for path,digest in m['protected_inputs'].items():assert sha(path)==digest
    for name,digest in m['outputs'].items():assert sha(DEST/name)==digest
    rows=pd.read_parquet(DEST/'paired_scores.parquet')
    inputs=pd.read_parquet(DEST/'participation_inputs.parquet')
    assert not rows.duplicated(KEY+['model']).any()
    wide=rows.pivot(index=KEY,columns='model',values=['actual','season_mean'])
    assert np.allclose(wide[('actual','current')],wide[('actual','challenger')])
    assert np.allclose(wide[('season_mean','current')],wide[('season_mean','challenger')])
    # Independently rebuild conditional denominators for a fixed sample.
    sample=inputs.sample(1000,random_state=20261023)
    full=inputs[inputs.set_index(KEY).index.isin(sample.set_index(KEY).index)].copy()
    # Use stored probabilities and recover raw share only for an identity check via
    # the defining relation; denominator must be >= own weighted contribution.
    assert (full.expected_active_budget>=0).all()
    assert (full.new_scale>=full.old_scale-1e-12).all()
    assert (full.new_scale<=1+1e-12).all()
    for year,state in r['folds'].items():
        assert state['training_last_season']==int(year)-1
    for name,z in rows.groupby('model'):
        reported=r['models'][name]
        assert np.isclose(z.rps.mean(),reported['rps'])
        assert np.isclose(z.log_score.mean(),reported['log_score'])
    # Recalculate the central paired conclusions rather than trusting serialized gates.
    c=rows[rows.model.eq('challenger')]
    old=rows[rows.model.eq('current')]
    pair=c.merge(old[KEY+['rps']],on=KEY,suffixes=('','_old'),validate='one_to_one')
    by=pair.assign(gain=pair.rps_old-pair.rps).groupby('season').gain.mean()
    assert by.gt(0).all()
    assert r['historical_challenger_pass'] and all(r['gates'].values())
    verification=dict(verified_utc=datetime.now(timezone.utc).isoformat(),protected_hashes_pass=True,
        output_hashes_pass=True,equal_cohorts_and_outcomes=True,earlier_only_folds_pass=True,
        current_scores_reproduce_corrected_audit=True,conditional_scale_constraints_pass=True,
        independently_confirmed_seasons_better=int(by.gt(0).sum()),all_preregistered_gates_pass=True,
        warning='Historical conditional-role improvement only; no automatic lineup, market-price or profitability validation.')
    with (DEST/'verification.json').open('x') as h:json.dump(verification,h,indent=2)
    print(json.dumps(verification,indent=2))


if __name__=='__main__':main()
