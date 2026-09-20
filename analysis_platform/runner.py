"""Each extension is an independent, bounded subprocess; no core mutation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from importlib import metadata

from . import VERSION
from .report import canonical, digest

MODULES = ('dj_signals', 'core_features', 'roughness', 'repeat', 'instruments', 'genre', 'chords', 'measurements', 'emotion', 'emotion_summary')


class Unavailable(RuntimeError):
    pass


def run_worker(name, audio, base, config):
    with tempfile.TemporaryDirectory(prefix='harbeat-extension-') as tmp:
        request = Path(tmp) / 'request.json'
        output = Path(tmp) / 'output.json'
        request.write_bytes(canonical({'audio': str(audio.resolve()), 'base': base, 'config': config}))
        executable = (config.get('model_python') or sys.executable) if name in ('emotion', 'instruments', 'genre') else (config.get('chord_python') or sys.executable) if name == 'chords' else sys.executable
        env = {**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
        root = str(Path(__file__).resolve().parent.parent)
        env['PYTHONPATH'] = root + os.pathsep + env.get('PYTHONPATH', '')
        worker = 'analysis_platform.model_worker' if name in ('emotion', 'instruments', 'genre') else 'analysis_platform.chords' if name == 'chords' else 'analysis_platform.features'
        try:
            result = subprocess.run([executable, '-m', worker, name, str(request), str(output)],
                                    capture_output=True, text=True, timeout=config.get('timeout_sec', 300), env=env)
        except subprocess.TimeoutExpired:
            # Killing the interpreter wrapper alone does not stop a Docker container.
            from .container_runtime import cleanup
            cleanup(Path(tmp) / 'container.cid')
            raise
        if not output.is_file():
            raise RuntimeError((result.stderr or 'worker exited without output')[-1500:])
        payload = json.loads(output.read_text())
        if payload.get('status') == 'unavailable':
            raise Unavailable(payload.get('reason', 'dependency unavailable'))
        if payload.get('status') != 'ready':
            raise RuntimeError(payload.get('reason', 'worker failed'))
        return payload['data']


def run_modules(audio: Path, base: dict, config: dict, implementations=None, progress=None, on_result=None, modules=None):
    from .emotion_summary import derive
    base = {**base, 'extensions':dict(base.get('extensions', {}))}
    implementations = implementations if implementations is not None else {
        name: derive if name == 'emotion_summary' else (lambda audio, base, config, name=name: run_worker(name, audio, base, config)) for name in (modules or MODULES)}
    output = {}
    for name, fn in implementations.items():
        started = time.monotonic()
        if progress:
            progress(name)
        item = {'module': name, 'version': VERSION, 'parameters': {k: v for k, v in config.items() if k not in ('model_python', 'chord_python')},
                'validation': 'experimental', 'config_sha256': digest(config), 'data': None}
        try:
            item.update(status='ready', data=fn(audio, base, config))
            canonical(item)
        except (Unavailable, ImportError, FileNotFoundError) as exc:
            item.update(status='unavailable', reason=str(exc), data=None)
        except Exception as exc:
            item.update(status='failed', reason=f'{type(exc).__name__}: {exc}', data=None)
        item['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        output[name] = item
        base['extensions'][name] = item
        if on_result:
            on_result(name, item)
    return output
