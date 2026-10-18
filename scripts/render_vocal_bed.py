"""Render immutable, phase-shared master/bass/vocal clips for one controlled trial."""
import argparse, hashlib, json, pathlib
from render_melody_overlap import checked_source, sha, write_asset, stretch_layers, SR

def render(selection, nas, reports, output):
    raw = selection.read_bytes()
    data = json.loads(raw)
    output.mkdir(parents=True, exist_ok=True)
    sources, evidence, expected = {}, {}, {}
    for case in data['cases']:
        for side, track_id in [('a', case['plan']['from']), ('b', case['plan']['to'])]:
            expected[track_id] = case['sourceVerification'][side]
    for track in data['tracks']:
        provenance = track['provenance']
        report = reports / (track['reportId'] + '.json')
        if sha(report) != provenance['reportSha256']:
            raise ValueError('frozen report changed: ' + track['id'])
        manifest = nas / 'published/tracks' / track['id'] / 'runs' / provenance['runId'] / 'manifest.json'
        doc = json.loads(manifest.read_text())
        success = json.loads((manifest.parent / '_SUCCESS.json').read_text())
        assets = doc['assets']
        if (doc['track_id'] != track['id'] or doc['analysis_run_id'] != provenance['runId']
                or sha(manifest) != success['manifest_sha256']
                or assets['master']['sha256'] != provenance['masterSha256']
                or assets['stems']['vocals']['sha256'] != provenance['vocalSha256']
                or assets['stems']['bass']['sha256'] != expected[track['id']]['bassSha256']
                or sha(manifest) != expected[track['id']]['manifestSha256']):
            raise ValueError('source identity mismatch')
        entries = [assets['master'], assets['stems']['bass'], assets['stems']['vocals']]
        if any(x['channels'] != 2 for x in entries):
            raise ValueError('stereo sources required')
        sources[track['id']] = [checked_source(nas, x) for x in entries]
        evidence[track['id']] = dict(provenance, manifestSha256=sha(manifest), bassSha256=entries[1]['sha256'])
        print('verified', track['title'], flush=True)
    cases = []
    for case in data['cases']:
        plan, assets = case['plan'], {}
        for part, track_id, start, duration, rate in [
            ('a', plan['from'], plan['start']-case['pre'], case['pre']+plan['duration'], 1),
            ('bEntry', plan['to'], plan['window']['start'], plan['duration'], plan['rate']),
            ('bBody', plan['to'], plan['window']['end'], case['post'], 1),
        ]:
            pcm = stretch_layers(sources[track_id], start, duration, rate)
            for j, name in enumerate(['Master', 'Bass', 'Vocal']):
                key = part + name
                asset = write_asset(output / (case['id']+'-'+key+'.flac'), pcm[:, 2*j:2*j+2])
                asset['url'] = '/vocal-bed-audio/' + pathlib.Path(asset['url']).name
                assets[key] = asset
        cases.append(dict(case, assets=assets, sourceVerification={'a': evidence[plan['from']], 'b': evidence[plan['to']]}))
    pack = dict(schema='harbeat.vocal-bed-pack.v1', selectionSha256=hashlib.sha256(raw).hexdigest(), cases=cases,
                audit=data['audit'], rendering='Six-channel master/bass/vocal joint WSOLA on both sides; original native B takeover.',
                limitation='Detected activity endpoints do not certify complete lyrics. Both arms share new clips and original EQ/bass. No per-arm normalization; separation bleed and source offset require listening.')
    (output/'vocal-bed-data.json').write_text(json.dumps(pack, ensure_ascii=False, indent=2)+'\n')
    print('finished', len(cases), 'cases', sum(x['bytes'] for c in cases for x in c['assets'].values()), 'bytes', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['selection', 'nas', 'reports', 'output']:
        parser.add_argument('--'+name, type=pathlib.Path, required=True)
    args = parser.parse_args()
    render(args.selection, args.nas, args.reports, args.output)
