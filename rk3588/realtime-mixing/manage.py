#!/usr/bin/env python3
"""Isolated RK deployment wrapper. Does not send commands to the live player."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('/home/cat/harbeat-mixing-v1')
RELEASE = BASE / 'releases/harbeat_mixing_algorithm_vocal_v4_20260913'
ROOT = BASE / 'data/edm_8_bundle'
INDEX = 'published/indexes/edm_8_handoff_v1.json'
VOCAL_INDEX = 'published/indexes/edm_8_vocal_activity_v1.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def resolve(key):
    p = Path(key)
    require(bool(key) and not p.is_absolute() and '..' not in p.parts, f'Unsafe key: {key}')
    result = (ROOT / p).resolve()
    require(ROOT.resolve() in result.parents, f'Escaped root: {key}')
    return result


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def validate():
    sys.path.insert(0, str(RELEASE))
    from harbeat import read_track_preprocess_from_manifest_key
    index = read(ROOT / INDEX)
    vocal_index = read(ROOT / VOCAL_INDEX)
    items = index['items']
    require(len(items) == index['total_tracks'] == 8, 'Expected exactly eight EDM tracks')
    ids = {i['track_id'] for i in items}
    require(len(ids) == 8, 'Duplicate tracks')
    vocal = {i['track_id']: i for i in vocal_index['items']}
    require(len(vocal_index['items']) == len(vocal) == 8 and set(vocal) == ids, 'Vocal index mismatch')
    report = {'status': 'validating', 'root': str(ROOT), 'validated_at': datetime.now(timezone.utc).isoformat(),
              'index_sha256': digest(ROOT / INDEX), 'vocal_index_sha256': digest(ROOT / VOCAL_INDEX),
              'tracks': [], 'audio_assets': 0, 'audio_bytes': 0, 'accuracy_evaluated': False}
    for item in items:
        tid, run = item['track_id'], item['analysis_run_id']
        require('EDM' in item['style_labels'], f'Not EDM: {tid}')
        bundle = read_track_preprocess_from_manifest_key(item['manifest_storage_key'], root=ROOT,
            expected_track_id=tid, expected_analysis_run_id=run, style='EDM', allow_degraded=True, verify_assets=True)
        manifest = bundle.manifest
        manifest_hash = digest(resolve(item['manifest_storage_key']))
        pointer = read(resolve(f'published/tracks/{tid}/latest.json'))
        for key, value in [('track_id', tid), ('analysis_run_id', run),
                           ('manifest_storage_key', item['manifest_storage_key']), ('manifest_sha256', manifest_hash)]:
            require(pointer.get(key) == value, f'Pointer mismatch: {tid} {key}')
        assets = manifest['assets']
        audio = {'master': assets['master']}
        audio.update({f'stem_{k}': assets['stems'][k] for k in ('vocals', 'drums', 'bass', 'other')})
        audio.update({f'drum_{k}': assets['drum_stems'][k] for k in ('kick', 'snare', 'hihat', 'tom', 'cymbal')})
        paths = {}
        for role, asset in audio.items():
            path = resolve(asset['storage_key'])
            require(path.stat().st_size == asset['size_bytes'] and digest(path) == asset['sha256'], f'Bad asset: {tid} {role}')
            paths[role] = str(path)
            report['audio_assets'] += 1
            report['audio_bytes'] += path.stat().st_size
        vi = vocal[tid]
        require(vi['status'] == 'ready' and vi['analysis_run_id'] == run, f'Vocal not ready: {tid}')
        require(vi['manifest_storage_key'] == item['manifest_storage_key'] and vi['manifest_sha256'] == manifest_hash, f'Vocal base mismatch: {tid}')
        va = assets['stems']['vocals']
        require(vi['vocal_storage_key'] == va['storage_key'] and vi['vocal_sha256'] == va['sha256'], f'Vocal audio mismatch: {tid}')
        path = resolve(vi['vocal_activity_storage_key'])
        require(digest(path) == vi['vocal_activity_sha256'], f'Bad vocal report: {tid}')
        vr = read(path)
        vs = read(path.parent / '_SUCCESS.json')
        require(vs.get('vocal_activity_sha256') == vi['vocal_activity_sha256'], f'Vocal success hash mismatch: {tid}')
        require(vr['status'] == 'ready' and vr['unit'] == 'ms' and vr['time_origin'] == 'master_audio_start', f'Vocal format mismatch: {tid}')
        for field in ('track_id', 'analysis_run_id', 'manifest_storage_key', 'manifest_sha256', 'vocal_storage_key', 'vocal_sha256'):
            require(vr['source'].get(field) == vi[field], f'Vocal report binding mismatch: {tid} {field}')
        require(vr['duration_ms'] == manifest['source']['duration_ms'], f'Vocal duration mismatch: {tid}')
        end = 0
        for span in vr['intervals']:
            require(0 <= end <= span['start_ms'] < span['end_ms'] <= vr['duration_ms'], f'Invalid vocal interval: {tid}')
            end = span['end_ms']
        report['tracks'].append({'track_id': tid, 'title': item['title'], 'analysis_run_id': run,
            'manifest_path': str(resolve(item['manifest_storage_key'])), 'manifest_sha256': manifest_hash,
            'vocal_activity_path': str(path), 'vocal_intervals': len(vr['intervals']),
            'quality_flags': list(bundle.quality_flags), 'status': manifest['status'], 'audio_paths': paths})
        print(f'VALIDATED {item["title"]}: 10 audio assets + vocal report', flush=True)
    require(report['audio_assets'] == 80, 'Expected 80 audio assets')
    report['status'] = 'ready'
    save(BASE / 'reports/data_validation.json', report)
    return report


def render():
    validate()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = BASE / f'reports/render_{stamp}.json'
    log_path = BASE / f'reports/render_{stamp}.log'
    output_root = BASE / 'outputs' / f'rk_v1_{stamp}'
    cmd = [sys.executable, str(RELEASE / 'scripts/render_edm_bundle_smooth_v3.py'),
           '--root', str(ROOT), '--vocal-root', str(ROOT), '--output-root', str(output_root), '--verify-assets']
    report = {'status': 'running', 'deployment_version': 'rk-mixing-v1', 'algorithm_version': 'vocal_v4',
              'started_at': datetime.now(timezone.utc).isoformat(), 'command': cmd, 'log': str(log_path)}
    save(report_path, report)
    started = time.monotonic()
    with log_path.open('w') as log:
        result = subprocess.run(cmd, cwd=RELEASE, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    if result.returncode:
        report.update(status='failed', returncode=result.returncode, render_seconds=elapsed)
        save(report_path, report)
        raise RuntimeError(f'Render failed: {log_path}')
    plans = list(output_root.glob('*/mix_plan.json'))
    require(len(plans) == 1, 'Expected one render plan')
    plan = read(plans[0])
    require(len(plan['tracks']) == 8 and len(plan['transitions']) == 7, 'Incomplete mix')
    wav = Path(plan['outputs']['mixtape_wav'])
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(wav), '-f', 'null', '-'], check=True)
    report.update(status='ready', finished_at=datetime.now(timezone.utc).isoformat(),
                  plan=str(plans[0]), mixtape=str(wav), sha256=digest(wav),
                  duration_seconds=plan['outputs']['duration_seconds'], tracks=8, transitions=7,
                  render_seconds=round(elapsed, 3),
                  playback_tested=False, wearable_control_integrated=False)
    save(report_path, report)
    save(BASE / 'reports/latest_render.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def audit():
    archive = BASE / 'downloads/harbeat_mixing_algorithm_vocal_v4_20260913_packaged.zip'
    expected = '8238bf1520ed4f4477d939c92664a7ee955f13089bb75796faac6d036a403bcf'
    require(digest(archive) == expected, 'Algorithm archive hash mismatch')
    verified = []
    # Sender stored UTF-8 filenames without the ZIP UTF-8 flag.
    with zipfile.ZipFile(archive, metadata_encoding='utf-8') as z:
        for item in z.infolist():
            if item.is_dir():
                continue
            rel = Path(item.filename)
            require(rel.parts[0] == RELEASE.name and '..' not in rel.parts, 'Bad source archive path')
            path = RELEASE.parent / rel
            expected_member = hashlib.sha256(z.read(item)).hexdigest()
            require(digest(path) == expected_member, f'Algorithm source changed: {rel}')
            verified.append({'path': str(path.relative_to(RELEASE)), 'sha256': expected_member})
    log = BASE / 'reports/unit_tests.log'
    with log.open('w') as out:
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                                cwd=RELEASE, stdout=out, stderr=subprocess.STDOUT)
    report = {'source_archive_sha256': expected, 'algorithm_source_modified': False,
              'verified_files': verified, 'tests_exit_code': result.returncode, 'tests_log': str(log),
              'python': sys.version, 'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]}
    save(BASE / 'reports/source_audit.json', report)
    print(log.read_text())
    require(result.returncode == 0, 'Source unit tests failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['validate', 'render', 'audit'])
    args = parser.parse_args()
    try:
        {'validate': validate, 'render': render, 'audit': audit}[args.action]()
    except Exception as exc:
        print(f'FAILED: {exc}', file=sys.stderr)
        raise
