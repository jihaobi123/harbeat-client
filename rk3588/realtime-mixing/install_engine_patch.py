"""Guarded installation of the tested engine file on RK, with exact backup.

Does NOT restart services; operator verifies idle state separately.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil

BASE=Path('/home/cat/harbeat-mixing-v1')
LIVE=Path('/home/cat/cypher/audio-engine/engine.py')
OLD='0b9cae7c1edf504b705bd7bea23bc3340db53f5639d6152027603ccc7b812df1'
BACKUP=BASE/'engine-patch/engine.before-rt-cache.py'
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

p=argparse.ArgumentParser()
p.add_argument('--rollback',action='store_true')
args=p.parse_args()
candidate=BASE/'engine-patch/engine.py'
if args.rollback:
    assert digest(LIVE)==digest(candidate), 'Live engine changed; refuse rollback overwrite'
    assert digest(BACKUP)==OLD, 'Invalid backup'
    source=BACKUP
else:
    if digest(LIVE)==digest(candidate):
        print('already installed')
        raise SystemExit(0)
    assert digest(LIVE)==OLD, 'Live engine changed; refuse overwrite'
    if BACKUP.exists():
        assert digest(BACKUP)==OLD, 'Backup conflict'
    else:
        shutil.copy2(LIVE,BACKUP)
    source=candidate
stage=LIVE.with_name('engine.py.rt-cache-staged')
shutil.copy2(source,stage)
os.replace(stage,LIVE)
print('installed',digest(LIVE),'backup',str(BACKUP))
