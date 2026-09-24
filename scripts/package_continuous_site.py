#!/usr/bin/env python3
"""Prepare source-bound public metadata and a PRIVATE direct-transfer manifest.

Audio stays byte-identical. The cloud verification step checks every transferred
file before making content-addressed hardlinks; no NAS URL remains in playback.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    path.write_bytes(data)
    path.with_suffix(path.suffix + '.gz').write_bytes(gzip.compress(data, mtime=0))


def checksum(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_bundle(corpus, store, out, source_root, expected=157):
    corpus, store, out, source_root = map(Path, (corpus, store, out, source_root))
    source_root = source_root.resolve()
    index = json.loads((corpus / 'library-index.json').read_text())
    audit_path = corpus / 'corpus-audit.json'
    audit = json.loads(audit_path.read_text()) if audit_path.is_file() else {}
    expected_mix = audit.get('sourceMixReady', expected)
    rows = index['tracks']
    ids = [row['id'] for row in rows]
    if (len(rows) != expected or len(set(ids)) != expected or
            any(not re.fullmatch(r'[a-zA-Z0-9_-]+', i) for i in ids) or
            any(row.get('playStatus') != 'ready' for row in rows) or
            sum(row.get('mixStatus') == 'ready' for row in rows) != expected_mix or audit.get('failures')):
        raise ValueError('complete playable and mix-ready library required')
    assets, records, details, evidence = {}, {}, {}, {}

    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        if not isinstance(value, dict):
            return value
        result = {k: rewrite(v) for k, v in value.items()}
        if {'url', 'sha256', 'bytes', 'duration'} <= value.keys():
            match = re.fullmatch(r'/api/analysis-lab/media/([a-f0-9]{32,64})', value['url'])
            sha = value['sha256']
            if not match or not re.fullmatch(r'[a-f0-9]{64}', sha):
                raise ValueError('unrecognized registered asset or checksum')
            identifier = match[1]
            if identifier not in records:
                record = json.loads((store / 'media' / (identifier + '.json')).read_text())
                source = Path(record['path']).resolve()
                if not source.is_relative_to(source_root) or source.suffix != '.flac':
                    raise ValueError('media path outside allowed source root')
                stat = source.stat()
                if stat.st_size != record['size'] or stat.st_mtime_ns != record['mtime_ns']:
                    raise ValueError('registered media changed')
                records[identifier] = record
            record = records[identifier]
            if value['bytes'] != record['size'] or sha != record['public']['declared_sha256']:
                raise ValueError('asset checksum or byte size differs from registry')
            prior = assets.get(sha)
            if prior and prior['bytes'] != value['bytes']:
                raise ValueError('conflicting checksum metadata')
            assets.setdefault(sha, {'source': str(Path(record['path']).resolve()),
                                    'sha256': sha, 'bytes': value['bytes']})
            result['url'] = '/listen/media/' + sha + '.flac'
        if 'reportSnapshotUrl' in result:
            filename = Path(result['reportSnapshotUrl']).name
            source = corpus / 'evidence' / filename
            if source.is_file():
                evidence[filename] = json.loads(source.read_text())
                result['reportSnapshotUrl'] = '/listen/evidence/' + filename
            else:
                result.pop('reportSnapshotUrl')
        return result

    for row in rows:
        document = json.loads((corpus / 'details' / (row['id'] + '.json')).read_text())
        if document['track']['id'] != row['id']:
            raise ValueError('detail track identity mismatch')
        details[row['id']] = rewrite(document)
        row['detailUrl'] = 'details/' + row['id'] + '.json'
    index['coverage'].update(indexed=expected, playable=expected, mixReady=expected_mix,
                             unavailable=0, mixUnavailable=expected-expected_mix)
    # Validation completes before any public index can be written.
    for identifier, document in details.items():
        write_json(out / 'details' / (identifier + '.json'), document)
    for filename, document in evidence.items():
        write_json(out / 'evidence' / filename, rewrite(document))
    write_json(out / 'library.json', index)
    return {'schema': 'harbeat.cloud-transfer.v1', 'tracks': expected,
            'bytes': sum(v['bytes'] for v in assets.values()),
            'assets': sorted(assets.values(), key=lambda v: v['source'])}


def verify_cloud(manifest, downloaded, media):
    downloaded, media = Path(downloaded).resolve(), Path(media)
    media.mkdir(parents=True, exist_ok=True)
    count = 0
    for asset in manifest['assets']:
        sha = asset['sha256']
        if not re.fullmatch(r'[a-f0-9]{64}', sha):
            raise ValueError('invalid checksum')
        source = (downloaded / asset['source'].lstrip('/')).resolve()
        if not source.is_relative_to(downloaded) or not source.is_file():
            raise ValueError('missing or escaped cloud media source')
        if source.stat().st_size != asset['bytes']:
            raise ValueError('cloud media size mismatch: ' + sha)
        if checksum(source) != sha:
            raise ValueError('cloud media checksum mismatch: ' + sha)
        target = media / (sha + '.flac')
        if target.exists() and not os.path.samefile(source, target):
            if target.stat().st_size!=asset['bytes'] or checksum(target)!=sha:
                raise ValueError('immutable media destination differs: ' + sha)
        if not target.exists():
            os.link(source, target)
        count += 1
        if count % 1000 == 0:
            print('VERIFIED', count, flush=True)
    return {'tracks': manifest['tracks'], 'verifiedAssets': count, 'bytes': manifest['bytes']}


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    package = commands.add_parser('package')
    for name in ('corpus', 'store', 'out', 'source-root', 'manifest'):
        package.add_argument('--' + name, type=Path, required=True)
    package.add_argument('--expected', type=int, default=157)
    verify = commands.add_parser('verify')
    for name in ('manifest', 'downloaded', 'media'):
        verify.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'package':
        if args.manifest.resolve().is_relative_to(args.out.resolve()):
            raise ValueError('private transfer manifest must be outside public directory')
        manifest = build_bundle(args.corpus, args.store, args.out, args.source_root, args.expected)
        args.manifest.write_text(json.dumps(manifest, separators=(',', ':')))
        args.manifest.chmod(0o600)
        files = args.manifest.with_suffix('.files')
        files.write_text(''.join(v['source'].lstrip('/') + '\n' for v in manifest['assets']))
        files.chmod(0o600)
        print(json.dumps({'tracks': manifest['tracks'], 'assets': len(manifest['assets']),
                          'bytes': manifest['bytes']}, ensure_ascii=False), flush=True)
    else:
        manifest = json.loads(args.manifest.read_text())
        print(json.dumps(verify_cloud(manifest, args.downloaded, args.media)), flush=True)


if __name__ == '__main__':
    main()
