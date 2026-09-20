"""Import exact existing results and optionally enrich matching local audio."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .report import build_report
from .runner import run_modules
from .store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--track-key', help='key in a batch JSON; omit for a single analysis')
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--attach', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('data/analysis-platform'))
    parser.add_argument('--models-dir', type=Path, default=Path('data/analysis-platform-models'))
    parser.add_argument('--model-python')
    parser.add_argument('--enrich', action='store_true')
    args = parser.parse_args()
    value = json.loads(args.source.read_text())
    core = value[args.track_key] if args.track_key else value
    docs = {'core': core}
    for path in args.attach:
        if path.name in docs:
            parser.error('duplicate attachment name')
        docs[path.name] = json.loads(path.read_text())
    store = Store(args.output)
    audio = {}
    if args.audio:
        import soundfile as sf
        hasher = hashlib.sha256()
        with args.audio.open('rb') as source_audio:
            for chunk in iter(lambda: source_audio.read(1024*1024), b''):
                hasher.update(chunk)
        sha = hasher.hexdigest()
        info = sf.info(args.audio)
        base = build_report(docs)
        declared = base['summary']['duration']
        if declared and abs(declared-info.duration) > 2:
            raise ValueError('audio duration does not match analysis')
        audio = {'name': args.audio.name, 'sha256': sha, 'duration': info.duration,
                 'binding': 'user_associated_duration_checked', 'source_file': args.source.name,
                 'source_track_key': args.track_key}
        target = store.path('audio', sha, '.audio')
        if not target.exists():
            shutil.copyfile(args.audio, target)
    report = build_report(docs, {}, audio)
    store.save_report(report)
    if args.enrich:
        if not args.audio:
            parser.error('--enrich requires --audio')
        config = {'models_dir': str(args.models_dir.resolve()), 'model_python': args.model_python,
                  'timeout_sec': 300, 'repeat_threshold': .5, 'instrument_threshold': .35}
        extensions = run_modules(args.audio, {'sections': report['timeline']['sections']}, config,
                                 progress=lambda name: print('running', name, flush=True))
        report = build_report(docs, extensions, audio)
        store.save_report(report)
    print(json.dumps({'report': str(store.path('reports', report['id'])),
                      'modules': {k: v['status'] for k, v in report['extensions'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
