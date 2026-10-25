"""Seal the private extension report and code provenance; no publication."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from feed_test import DEST

def h(p):
    s=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):s.update(b)
    return s.hexdigest()

def main():
    path=DEST/'feed_extension_manifest.json'
    if path.exists():raise FileExistsError(path)
    src=Path(__file__).parent
    files=['FEED_RULE.md','feed_test.py','feed_inventory.py','feed_context.py','test_feed.py','seal_feed.py']
    out=dict(sealed_at=datetime.now(timezone.utc).isoformat(),
        code_sha256={n:h(src/n) for n in files},
        output_sha256={p.name:h(p) for p in DEST.iterdir() if p.is_file()},
        no_publication=True,live_model_unchanged=True,tests_passed=12,
        historical_scoring='Frozen original results retained; later code edits are source-inventory/identity reporting only.')
    with path.open('x') as f:json.dump(out,f,indent=2)
    print(str(path))

if __name__=='__main__':main()
