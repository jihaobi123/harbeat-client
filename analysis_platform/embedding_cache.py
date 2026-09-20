"""Shared EffNet embeddings; content/protocol keyed, validated, atomically stored."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import numpy as np

PROTOCOL = 'effnet16k-mono-frame512-hop256-patch128-hop62-repeat-batchsame-window30-v1'


def audio_sha256(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): sha.update(block)
    return sha.hexdigest()


def valid(values):
    return values.ndim == 2 and 0 < len(values) <= 128 and values.shape[1] == 1280 and np.isfinite(values).all()


def cached_embedding(root, identity, compute):
    path = None
    if root:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        path = root / (key + '.npy')
        try:
            value = np.load(path, allow_pickle=False)
            if valid(value): return value, True
        except (OSError, ValueError, EOFError): pass
    value = np.asarray(compute(), dtype=np.float32)
    if not valid(value): raise ValueError('invalid EffNet embeddings')
    if path:
        fd, temp = tempfile.mkstemp(dir=root, prefix='.embedding-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                np.save(stream, value, allow_pickle=False)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    return value, False
