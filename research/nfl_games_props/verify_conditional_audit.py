"""Independent artifact/chronology checks; never writes model inputs."""
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from build import OUT, player_inputs
from conditional_audit import DEST, KEY, appearances, sha


def main():
    result = json.loads((DEST/'results.json').read_text())
    manifest = json.loads((DEST/'manifest_complete.json').read_text())
    for file, digest in manifest['protected_inputs'].items():
        assert sha(file) == digest
    for file, digest in manifest['outputs'].items():
        assert sha(DEST/file) == digest
    p = pd.read_parquet(DEST/'paired_scores.parquet')
    assert not p.duplicated(KEY+['stat','model']).any()
    for stat, z in p.groupby('stat'):
        pivot = z.pivot(index=KEY, columns='model', values='actual')
        assert not pivot.isna().any().any()
        assert (pivot.max(axis=1) == pivot.min(axis=1)).all()
        for model, x in z.groupby('model'):
            assert np.isclose(x.rps.mean(), result['results'][stat]['models'][model]['rps'])
    original = json.loads((OUT/'results.json').read_text())
    for year, state in result['folds'].items():
        assert state['training_last_season'] == int(year)-1
        assert np.isclose(state['receiver_concentration'],original['props']['frozen'][year]['receptions']['concentration'])
    g = pd.read_parquet(OUT/'games.parquet')
    st, sn, _, _ = player_inputs(g)
    history = appearances(st,sn,g)
    controls = pd.read_parquet(DEST/'receiver_controls.parquet')
    assert ((pd.to_datetime(controls.latest_history_tip,utc=True)+pd.Timedelta(hours=6)) < (controls.tip-pd.Timedelta(hours=1))).all()
    sample = controls[controls.season.between(2021,2025)].sample(100,random_state=17)
    verified = 0
    for r in sample.itertuples():
        h = history[(history.aid == r.aid)&(history.tip+pd.Timedelta(hours=6) < r.tip-pd.Timedelta(hours=1))].sort_values('tip')
        assert len(h) == r.earlier_appearances
        if len(h):
            assert np.isclose(h.tail(10).receptions.mean(),r.recent_mean)
            current = h[h.season == r.season]
            previous = h[h.season == r.season-1]
            season = current if len(current) else previous
            if len(season):
                assert np.isclose(season.receptions.mean(),r.season_mean)
            verified += 1
    qb = pd.read_parquet(DEST/'qb_controls.parquet')
    qhist = pd.read_parquet(DEST/'first_role_history.parquet')
    qb_verified = 0
    for r in qb[qb.season.between(2021,2025)].sample(100,random_state=17).itertuples():
        h = qhist[(qhist.aid == r.aid)&(qhist.tip+pd.Timedelta(hours=6)<r.tip-pd.Timedelta(hours=1))].sort_values('tip')
        assert len(h) == r.earlier_appearances
        if len(h):
            assert np.isclose(h.tail(10).attempts.mean(),r.recent_mean)
            qb_verified += 1
    for year, c in result['coverage'].items():
        assert c['receiver_appearances']+c['receiver_unseen_appearances']==c['actual_receiver_appearances']
        assert c['scored_qb_roles']+c['qb_unseen_or_not_appearing']==c['first_role_labels']
        assert c['first_role_labels']+c['first_role_label_gaps']==c['team_games_expected']
    # Exploratory attribution only, not a new model or an alternative scored test.
    z = p[(p.stat=='receptions')&(p.model=='candidate')]
    exploratory = {str(y):dict(predicted_mean=float(x['mean'].mean()),actual_mean=float(x.actual.mean()),
        pre_budget_linear_mean_approximation=float((x['mean']/x.budget_scale).mean()),
        mean_budget_multiplier=float(x.budget_scale.mean())) for y,x in z.groupby('season')}
    checks = dict(verified_utc=datetime.now(timezone.utc).isoformat(), verifier_sha256=sha(__file__),
        protected_artifact_hashes_pass=True, output_hashes_pass=True, equal_model_cohorts_and_labels=True,
        earlier_only_fold_markers_pass=True, original_receiver_concentration_reproduced=True,
        receiver_history_timestamps_checked=len(controls), independently_recomputed_receiver_samples=verified,
        independently_recomputed_qb_samples=qb_verified, coverage_reconciles=True,
        exploratory_budget_diagnostic=exploratory,
        diagnostic_warning='Post-result exploratory mean attribution; not a refitted or scored candidate. Overflow makes the linear mean approximation inexact at extreme counts.')
    with (DEST/'verification.json').open('x') as h:
        json.dump(checks,h,indent=2)
    print(json.dumps(checks,indent=2))


if __name__=='__main__':
    main()
