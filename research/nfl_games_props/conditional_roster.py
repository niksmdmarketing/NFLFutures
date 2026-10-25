"""Separate immutable player-rate inputs from editable role assumptions."""
import json
from conditional_build import DEST,sha,now

def main():
    target=DEST/'roster_model_features.json'
    if target.exists():raise FileExistsError(target)
    path=DEST/'assumptions.json';a=json.loads(path.read_text())
    result=dict(model_id=a['model_id'],created_at=now(),source_assumptions_sha256=sha(path),games=a['games'])
    with target.open('x') as f:json.dump(result,f,indent=2)
    print(str(target))

if __name__=='__main__':main()
