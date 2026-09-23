#!/usr/bin/env python3
"""Prepare half-length tails for controlled comparisons; never alter source assets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cases', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--tracks-root', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.cases.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    media = args.output / 'media'
    media.mkdir(exist_ok=True)
    result = {}
    checked = {}
    for i, item in enumerate(manifest['inputs']):
        source = (args.tracks_root / item['sourceTrackId'] / 'runs' / item['runId'] / 'audio/master.mp3').resolve()
        if not source.is_relative_to(args.tracks_root.resolve()):
            raise ValueError('Source outside tracks root')
        checked.setdefault(str(source), sha(source))
        if checked[str(source)] != item['sourceMasterSha256']:
            raise ValueError('Master hash mismatch')
        start, end, rate, duration = (item[k] for k in ('start', 'end', 'rate', 'targetDuration'))
        if not (0 <= start < end and .8 <= rate <= 1.2 and duration > .5 and abs((end-start)/rate-duration)<.01):
            raise ValueError('Invalid source mapping')
        filename = f'case-{i+1:02d}-tail-2.flac'
        target = media / filename
        if target.exists():
            raise FileExistsError(target)
        filt = f'atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
        command = ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source), '-vn', '-af', filt, '-ar', '44100', '-ac', '2', '-c:a', 'flac', '-sample_fmt', 's16', '-frame_size', '4096', str(target)]
        subprocess.run(command, check=True)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(target)]))
        actual = float(probe['format']['duration'])
        if abs(actual-duration) > 1/44100:
            raise ValueError('Output duration mismatch')
        result[item['caseId']] = {**item, 'source': str(source), 'command': command, 'asset': {'url': 'media/'+filename, 'sha256': sha(target), 'duration': actual, 'bytes': target.stat().st_size, 'rate': rate}}
        print(item['caseId'], actual, flush=True)
    (args.output / 'case-length-assets.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'Prepared {len(result)} verified tails')

if __name__ == '__main__':
    main()
