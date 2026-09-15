#!/usr/bin/env python3
"""Extract verified data archives without overwriting any existing file."""
import hashlib
import stat
import zipfile
from pathlib import Path

BASE = Path('/home/cat/harbeat-mixing-v1')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def extract(archive, target, expected):
    if sha(archive) != expected:
        raise ValueError(f'Archive checksum failed: {archive}')
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            rel = Path(item.filename)
            dest = (target / rel).resolve()
            if rel.is_absolute() or '..' in rel.parts or target.resolve() not in dest.parents or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError(f'Unsafe archive entry: {rel}')
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            if dest.exists():
                # Resume only when the existing member is byte-identical.
                with z.open(item) as src:
                    h = hashlib.sha256()
                    for block in iter(lambda: src.read(1024 * 1024), b''):
                        h.update(block)
                if dest.stat().st_size != item.file_size or sha(dest) != h.hexdigest():
                    raise ValueError(f'Existing file differs; refusing overwrite: {dest}')
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as src, dest.open('xb') as out:
                for block in iter(lambda: src.read(1024 * 1024), b''):
                    out.write(block)
    print(f'EXTRACTED {archive.name}', flush=True)


if __name__ == '__main__':
    extract(BASE / 'downloads/edm_8_bundle_20260911_193431.zip', BASE / 'data',
            '312f0e996b7b47eade1021685487d0e908b91167555ab892df65eb3bb3db53be')
    extract(BASE / 'edm_8_vocal_activity_20260913_v1.zip', BASE / 'data/edm_8_bundle',
            '93f9cc996e9556b2c057c4f823e835a08aa8d88cb9923d28b338d22160f55a37')
