"""Attach source-bound acoustic evidence without replacing any V3 music assets."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--v3', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.v3.read_text())
    evidence = {t['id']: t for t in json.loads(args.evidence.read_text())['tracks']}
    for track in base['tracks']:
        aligned = evidence[track['id']]
        assert track['native'] == aligned['native'], 'native asset changed'
        for key in ('masterSha256', 'reportSha256', 'vocalSha256'):
            assert track['provenance'][key] == aligned['alignment']['source'][key], key
        track['alignment'] = aligned['alignment']
    base['schema'] = 'harbeat.v30-small-tuning.v1'
    base['inputs'] = {p: hashlib.sha256(getattr(args, p).read_bytes()).hexdigest()
                      for p in ('v3', 'evidence', 'cases')}
    args.output.mkdir(parents=True, exist_ok=True)
    data = json.dumps(base, ensure_ascii=False, separators=(',', ':')).encode()
    (args.output / 'catalog.json').write_bytes(data)
    (args.output / 'catalog.json.gz').write_bytes(gzip.compress(data))
    cases = json.loads(args.cases.read_text())
    cases['cases'] = [{**c, 'group': 'original20'} for c in cases['cases']]
    (args.output / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False))
    print(json.dumps({'tracks': len(base['tracks']), 'windows': sum(len(t['windows']) for t in base['tracks']), 'gzipBytes': len(gzip.compress(data))}))


if __name__ == '__main__':
    main()
