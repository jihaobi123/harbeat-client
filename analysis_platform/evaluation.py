"""Metrics only compare the same audio and explicitly supplied human annotations."""
from __future__ import annotations

import math


def event_metrics(predicted, reference, tolerance=.07):
    if tolerance <= 0 or not all(math.isfinite(v) and v >= 0 for v in [*predicted, *reference]):
        raise ValueError('invalid events or tolerance')
    pred, ref = sorted(predicted), sorted(reference)
    i = j = matches = 0
    while i < len(pred) and j < len(ref):
        if abs(pred[i] - ref[j]) <= tolerance:
            matches += 1
            i += 1
            j += 1
        elif pred[i] < ref[j]:
            i += 1
        else:
            j += 1
    precision = matches / len(pred) if pred else 0
    recall = matches / len(ref) if ref else None
    return {'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if recall and precision else (0 if ref else None),
            'matched': matches, 'predicted': len(pred), 'reference': len(ref), 'tolerance_sec': tolerance}


def compare_annotations(report, annotations):
    sha = report.get('audio', {}).get('sha256')
    if not sha or sha != annotations.get('audio_sha256'):
        raise ValueError('annotations must refer to the same audio SHA256')
    results = {}
    for name in ['beats', 'downbeats']:
        if name in annotations:
            results[name] = event_metrics(report['timeline'].get(name, []), annotations[name])
    if 'section_boundaries' in annotations:
        results['section_boundaries'] = event_metrics(
            [s['start'] for s in report['timeline']['sections'] if s['start'] > 0],
            annotations['section_boundaries'], .5)
    if 'instruments' in annotations:
        module = report.get('extensions', {}).get('instruments', {})
        if module.get('status') == 'ready':
            pred = {i['label'] for i in module['data'].get('labels', [])}
            ref = set(annotations['instruments'])
            tp = len(pred & ref)
            results['instruments'] = {'precision': tp / len(pred) if pred else 0,
                                      'recall': tp / len(ref) if ref else None,
                                      'predicted': len(pred), 'reference': len(ref)}
    if 'emotion' in annotations:
        points = (report.get('extensions', {}).get('emotion', {}).get('data') or {}).get('points', [])
        pairs = [(p, a) for a in annotations['emotion'] for p in points if p['start'] <= a['time'] < p['end']]
        if pairs:
            results['emotion'] = {k + '_mae': sum(abs(p[k] - a[k]) for p, a in pairs) / len(pairs)
                                  for k in ['valence', 'arousal']}
            results['emotion']['matched_samples'] = len(pairs)
    return {'status': 'evaluated' if results else 'not_evaluated', 'metrics': results,
            'audio_sha256': sha, 'annotation_id': annotations.get('annotation_id'),
            'scope': 'only this audio and the provided annotations; no general accuracy claim'}
