"""Verify candidate transitions on Jetson against the device-execution sources."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

from .transition_arrangement import ROLES, candidate_curves
from .transition_policy import select_transition

SR = 44100


def canonical_cue(candidate):
    plan = dict(candidate)
    for key in ('aStart', 'aExit', 'bStart'):
        plan[key] = round(plan[key] * SR) / SR
    n = round((plan['aExit'] - plan['aStart']) * SR)
    plan['rate'] = round(n * plan['rate']) / n
    return plan


def stage_source(track, job, root):
    from metric_mix.prepare import source_assets

    paths, proof = source_assets(track, Path('/mnt/nas/harbeat/preprocess'),
                                 Path('/mnt/nas/harbeat/data/analysis-platform/reports'))
    manifest = json.loads((root / 'tracks' / (track['id'] + '.json')).read_bytes())
    provenance = track['provenance']
    if (manifest['manifestSha256'] != proof['manifestSha256'] or
            manifest['reportSha256'] != provenance['reportSha256'] or
            manifest['sourceSha256'] != provenance['masterSha256'] or
            manifest['runId'] != provenance['runId'] or
            any(manifest['stems'][r]['sourceSha256'] != proof['assets'][r]['sha256'] for r in ROLES)):
        raise ValueError('device manifest does not match the reviewed recording')
    binding = {key: provenance[key] for key in ('masterSha256', 'reportSha256', 'runId', 'vocalSha256')}
    return paths, dict(binding, trackId=track['id'], originalSha256=job['item']['input_sha256'],
                       manifestSha256=manifest['manifestSha256'], profileSha256=manifest['profile']['sha256'],
                       stemSha256={role: manifest['stems'][role]['sourceSha256'] for role in ROLES})


def extract(source, start, frames, target):
    offset = round(start * SR)
    audio = subprocess.check_output(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(source), '-af',
                                     f'aresample=44100,atrim=start_sample={offset}:end_sample={offset + frames}',
                                     '-ac', '2', '-f', 'f32le', 'pipe:1'], timeout=90)
    if len(audio) != 8 * frames or not np.isfinite(np.frombuffer(audio, '<f4')).all():
        raise ValueError('decoded source does not cover the reviewed sample interval')
    target.write_bytes(audio)


def review(a_job, b_job, proposal, root, evaluator):
    jobs = {'a': a_job, 'b': b_job}
    tracks = {s: jobs[s]['job']['track'] for s in jobs}
    if (proposal['from'], proposal['to']) != (tracks['a']['id'], tracks['b']['id']):
        raise ValueError('proposed cue references a different track pair')
    if not proposal['candidates']:
        return {'producer': 'jetson', 'status': 'fallback', 'results': [],
                'winner': {'method': 'original-player-fallback'}, 'reason': proposal.get('reason')}
    if any(proposal['sources'][s] != tracks[s]['provenance'] for s in jobs):
        raise ValueError('proposed cue references a different analysis run')
    sources = {s: stage_source(tracks[s], jobs[s], root) for s in jobs}
    results, accepted = [], []
    for item in proposal['candidates']:
        if item['method'] not in ('intro-beatmix', 'intro-tail-handover'):
            continue
        cue = canonical_cue(item)
        curves = list(candidate_curves(cue, tracks['b']))
        if not curves:
            continue
        n = round((cue['aExit'] - cue['aStart']) * SR)
        starts = {'a': cue['aStart'], 'b': cue['bStart']}
        with TemporaryDirectory(prefix='harbeat-policy-review-', dir='/dev/shm') as temp:
            work = Path(temp)
            files, bindings = {}, {}
            for side, (paths, proof) in sources.items():
                files[side] = {}
                frames = n if side == 'a' else round(n * cue['rate']) + (0 if cue['rate'] == 1 else round(.35 * SR))
                for role in ('master', *ROLES):
                    path = work / f'{side}-{role}.f32'
                    extract(paths[role], starts[side], frames, path)
                    files[side][role] = str(path)
                bindings[side] = dict(proof, sourceStart=starts[side])
            payload = work / 'review.json'
            payload.write_text(json.dumps(dict(files=files, bindings=bindings, duration=curves[0]['duration'],
                                               bpm=tracks['a']['bpm'], rate=cue['rate'], timelines=curves,
                                               sources=dict(**tracks, cue=cue))))
            result = json.loads(subprocess.check_output(['node', str(evaluator), str(payload)], timeout=90))
        results.append({'cue': cue, 'review': result})
        if result['approvals']:
            best = max(result['approvals'], key=lambda v: (v['evidence']['improvement'], v['evidence']['minimumLevelDbfs']))
            accepted.append(dict(method=cue['method'], verified=True, recipe=best))
    winner = select_transition(accepted, {'method': 'original-player-fallback'})
    return {'producer': 'jetson', 'status': 'approved' if 'recipe' in winner else 'fallback',
            'winner': winner, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('a_job', 'b_job', 'proposal', 'root', 'evaluator'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    docs = [json.loads(path.read_bytes()) for path in (args.a_job, args.b_job, args.proposal)]
    print(json.dumps(review(*docs, args.root, args.evaluator), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
