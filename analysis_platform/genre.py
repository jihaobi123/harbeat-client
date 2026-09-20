"""Discogs label presentation, retaining every raw sigmoid output."""
import numpy as np


def ranked(classes, scores):
    return sorted([{'label': label, 'parent': label.split('---')[0],
                    'style': label.split('---', 1)[-1], 'score': float(score)}
                   for label, score in zip(classes, scores)], key=lambda item: -item['score'])


def summarize_genre(classes, windows):
    if not classes or len(set(classes)) != len(classes):
        raise ValueError('missing or duplicated genre labels')
    total = np.zeros(len(classes), dtype=np.float64)
    count, segments = 0, []
    for start, end, predictions in windows:
        p = np.asarray(predictions, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] != len(classes) or not len(p):
            raise ValueError('genre model metadata class count mismatch or empty predictions')
        if not np.isfinite(p).all() or np.min(p) < 0 or np.max(p) > 1:
            raise ValueError('invalid genre sigmoid scores')
        total += p.sum(axis=0)
        count += len(p)
        mean = p.mean(axis=0)
        segments.append({'start': start, 'end': end, 'patch_count': len(p),
                         'top': ranked(classes, mean)[:5], 'raw_scores': mean.tolist()})
    if not count: raise ValueError('no genre windows')
    means = total / count
    scores = [{'label': label, 'score': float(score)} for label, score in zip(classes, means)]
    parents = {}
    for label, score in zip(classes, means):
        parent = label.split('---')[0]
        parents[parent] = max(parents.get(parent, 0), float(score))
    return {'classes': classes, 'scores': scores, 'top': ranked(classes, means)[:5],
            'parents': sorted([{'label': label, 'score': score} for label, score in parents.items()], key=lambda x:-x['score']),
            'segments': segments, 'patch_count': count,
            'aggregation': 'mean over all valid patches; 30-second independent windows; parent=max child; no normalization',
            'definition': '400 raw multi-label sigmoid scores; uncalibrated model candidates, not accuracy or mix compatibility',
            'selection_enabled': False}
