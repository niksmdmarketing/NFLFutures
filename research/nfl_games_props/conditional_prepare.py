"""Normalise the default role budget once, before any user scenario edits."""
import json
import conditional_engine as E
from conditional_build import DEST,now,sha

def main():
    ap=DEST/'assumptions_ready.json';rp=DEST/'roster_model_features_ready.json'
    if ap.exists() or rp.exists():raise FileExistsError('Create only')
    source=DEST/'assumptions.json';a=json.loads(source.read_text())
    for g in a['games']:
        for t in g['teams']:
            enabled,budget=E.target_budget(t['receivers']);shares={r['aid']:r['effective_target_share'] for r in enabled}
            t['initial_role_budget']=budget
            for r in t['receivers']:
                if r['aid'] in shares:r['default_target_share']=shares[r['aid']]
    a['role_budget_policy']='Default shares normalised once. Disabling a receiver leaves remaining shares unchanged. New roles require an explicit share.'
    with ap.open('x') as f:json.dump(a,f,indent=2)
    record=dict(model_id=a['model_id'],created_at=now(),source_assumptions_sha256=sha(source),games=a['games'])
    with rp.open('x') as f:json.dump(record,f,indent=2)
    print(str(ap))

if __name__=='__main__':main()
