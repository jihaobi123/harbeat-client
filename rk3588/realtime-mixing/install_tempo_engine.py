"""Guarded engine-v2 install; source-v1 remains an independent rollback."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil

base=Path('/home/cat/harbeat-mixing-v1')
live=Path('/home/cat/cypher/audio-engine/engine.py')
candidate=base/'engine-patch/engine.py'
backup=base/'engine-patch/engine.before-tempo.py'
expected='f70ded3fe5f76d5d64991f74ff19809825fd605097aee4a1406463ae147db66f'
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser()
p.add_argument('--rollback',action='store_true')
args=p.parse_args()
if args.rollback:
    assert digest(live)==digest(candidate), 'Refuse overwrite: deployed source changed'
    assert digest(backup)==expected, 'Wrong backup'
    source=backup
else:
    if digest(live)==digest(candidate):
        print('already installed')
        raise SystemExit(0)
    assert digest(live)==expected, 'Refuse overwrite: unexpected engine version'
    if backup.exists():
        assert digest(backup)==expected, 'Backup conflict'
    else:
        shutil.copy2(live,backup)
    source=candidate
stage=live.with_name('engine.py.tempo-staged')
shutil.copy2(source,stage)
os.replace(stage,live)
print('installed',digest(live),'backup',str(backup))
