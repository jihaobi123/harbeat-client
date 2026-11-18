"""Bounded Jetson read-through cache for the approved execution sources."""
import fcntl
import json
from pathlib import Path
import re
import shutil
import tempfile

from metric_mix.prepare import sha

CACHE = Path('/dev/shm/harbeat-approved-execution-sources')
MAX_BYTES = 6 * 1024**3
MIN_FREE_BYTES = 4 * 1024**3
IDENTITY = re.compile(r'[A-Za-z0-9_-]{1,160}')
STEMS = ('bass', 'drums', 'vocals', 'other')


def cache_run(track, entry, nas, cache=CACHE):
    """Copy only the exact approved run. The caller still verifies every asset."""
    tid, run = track['id'], track['provenance']['runId']
    if not IDENTITY.fullmatch(tid) or not IDENTITY.fullmatch(run):
        raise ValueError('invalid cache source identity')
    relative = Path('published/tracks') / tid / 'runs' / run
    target = cache / relative
    if (target / '_SUCCESS.json').is_file():
        return cache
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (cache / '.stage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (target / '_SUCCESS.json').is_file():
            return cache
        source = (nas / relative).resolve()
        manifest = source / 'manifest.json'
        success = source / '_SUCCESS.json'
        if (nas.resolve() not in source.parents or manifest.stat().st_size > 8 * 1024**2
                or success.stat().st_size > 64 * 1024):
            raise ValueError('invalid cache manifest location')
        proof = sha(manifest)
        if proof != entry['manifestSha256'] or proof != json.loads(success.read_bytes())['manifest_sha256']:
            raise ValueError('unapproved cache manifest')
        assets = json.loads(manifest.read_bytes())['assets']
        files = [(manifest, Path('manifest.json')), (success, Path('_SUCCESS.json'))]
        for asset in [assets['master'], *(assets['stems'][name] for name in STEMS)]:
            name = Path(asset['storage_key']).relative_to(relative)
            file = (source / name).resolve()
            if source not in file.parents or not file.is_file():
                raise ValueError('cache source path escaped the approved run')
            files.append((file, name))
        needed = sum(p.stat().st_size for p, _ in files)
        used = sum(p.stat().st_size for p in (cache / 'published').rglob('*') if p.is_file())
        if used + needed > MAX_BYTES or shutil.disk_usage(cache).free < MIN_FREE_BYTES + needed:
            return nas
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.source-', dir=target.parent) as temp:
            stage = Path(temp) / 'run'
            stage.mkdir()
            for file, name in files:
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, destination)
            stage.rename(target)
        return cache
