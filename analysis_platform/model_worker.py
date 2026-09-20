"""Optional Essentia model process. Weights are never downloaded implicitly."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from importlib import metadata

HOP_SEC = 93 * 256 / 16000
PATCH_SEC = 187 * 256 / 16000


def select_instruments(classes, scores, threshold):
    # Filter paired labels AND values, retaining original model output indices.
    return sorted([{'label': label, 'score': float(score)} for label, score in zip(classes, scores)
                   if label != 'voice' and score >= threshold], key=lambda x: -x['score'])


def emotion_points(predictions, duration):
    return [{'start': i * HOP_SEC, 'end': min((i + 1) * HOP_SEC, duration),
             'window_start': i * HOP_SEC, 'window_end': min(i * HOP_SEC + PATCH_SEC, duration),
             'raw_valence': float(v), 'raw_arousal': float(a),
             'valence': max(-1., min(1., (float(v) - 5) / 4)),
             'arousal': max(0., min(1., (float(a) - 1) / 8))}
            for i, (v, a) in enumerate(predictions) if i * HOP_SEC < duration]


def predict(kind, request):
    root = Path(request['config'].get('models_dir', 'data/analysis-platform-models')).resolve()
    names = ['msd-musicnn-1.pb', 'deam-msd-musicnn-2.pb'] if kind == 'emotion' else [
        'discogs-effnet-bs64-1.pb', 'mtg_jamendo_instrument-discogs-effnet-1.pb',
        'mtg_jamendo_instrument-discogs-effnet-1.json']
    if kind == 'genre':
        names = ['discogs-effnet-bs64-1.pb', 'genre_discogs400-discogs-effnet-1.pb', 'genre_discogs400-discogs-effnet-1.json']
    missing = [name for name in names if not (root / name).is_file()]
    if missing:
        return {'status': 'unavailable', 'reason': '未安装可选模型权重：' + ', '.join(missing)}
    import essentia.standard as es
    import numpy as np
    native = os.getenv('ANALYSIS_TF_BACKEND') == 'python'
    if native:
        from .native_audio import load_audio
        audio = load_audio(request['audio'], es.Resample)
    else:
        audio = es.MonoLoader(filename=request['audio'], sampleRate=16000, resampleQuality=4)()
    duration = len(audio) / 16000
    if duration < .5 or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-8:
        raise ValueError('silent, too short or invalid audio')
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
    import essentia
    provenance = {'model_files': hashes, 'license': 'CC-BY-NC-SA-4.0; commercial license separate',
                  'essentia_version': essentia.__version__, 'duration': duration, 'last_patch_mode': 'repeat',
                  'backend': 'essentia-preprocessing-tensorflow-python-cpu' if native else 'essentia-tensorflow'}
    if native:
        from .native_tensorflow import predictors, tf
        embedding, head = predictors(root, kind)
        provenance['tensorflow_version'] = tf.__version__
    if kind == 'emotion':
        if not native:
            embedding = es.TensorflowPredictMusiCNN(graphFilename=str(root / names[0]),
                         output='model/dense/BiasAdd', patchSize=187, patchHopSize=93, lastPatchMode='repeat')
            head = es.TensorflowPredict2D(graphFilename=str(root / names[1]), output='model/Identity')
        from .embedding_cache import audio_sha256
        provenance['audio_sha256'] = audio_sha256(request['audio'])
        points = emotion_points(head(embedding(audio)), duration)
        return {'status': 'ready', 'data': {**provenance, 'points': points,
                'definition': 'DEAM valence/arousal predictions; window support differs from display step',
                'covered_until': points[-1]['window_end'] if points else 0}}
    if not native:
        embedding = es.TensorflowPredictEffnetDiscogs(graphFilename=str(root / names[0]), output='PartitionedCall:1', lastPatchMode='repeat')
        head = es.TensorflowPredict2D(graphFilename=str(root / names[1]),
                    input='serving_default_model_Placeholder' if kind == 'genre' else 'model/Placeholder',
                    output='PartitionedCall:0' if kind == 'genre' else 'model/Sigmoid')
    classes = json.loads((root / names[2]).read_text())['classes']
    if kind == 'genre' and len(classes) != 400:
        raise ValueError('Discogs400 requires 400 metadata classes')
    from .embedding_cache import audio_sha256, cached_embedding, PROTOCOL
    identity = {'audio_sha256': audio_sha256(request['audio']), 'backbone_sha256': hashes[names[0]],
                'backend': provenance['backend'], 'essentia': provenance['essentia_version'],
                'tensorflow': provenance.get('tensorflow_version'), 'protocol': PROTOCOL}
    hits = 0
    windows = []
    segments, all_scores = [], []
    threshold = float(request['config'].get('instrument_threshold', .35))
    for start in range(0, len(audio), 30 * 16000):
        end = min(start + 30 * 16000, len(audio))
        vectors, hit = cached_embedding(request['config'].get('embedding_cache_dir'),
                      {**identity, 'start_sample': start, 'end_sample': end}, lambda: embedding(audio[start:end]))
        hits += int(hit)
        predictions = np.asarray(head(vectors))
        if kind == 'genre':
            windows.append((start / 16000, end / 16000, predictions))
            continue
        scores = predictions.mean(axis=0)
        if len(scores) != len(classes):
            raise ValueError('model metadata class count mismatch')
        all_scores.append(scores)
        segments.append({'start': start / 16000, 'end': min(start / 16000 + 30, duration),
                         'labels': select_instruments(classes, scores, threshold)})
    provenance['embedding_cache'] = {'hits': hits, 'windows': (len(audio)+30*16000-1)//(30*16000), 'protocol': PROTOCOL}
    provenance['audio_sha256'] = identity['audio_sha256']
    if kind == 'genre':
        from .genre import summarize_genre
        return {'status': 'ready', 'data': {**provenance, **summarize_genre(classes, windows)}}
    return {'status': 'ready', 'data': {**provenance, 'segments': segments,
            'labels': select_instruments(classes, np.max(all_scores, axis=0), threshold),
            'definition': '30-second instrument tags; scores are uncalibrated, not note-level events'}}


if __name__ == '__main__':
    try:
        result = predict(sys.argv[1], json.loads(Path(sys.argv[2]).read_text()))
    except ImportError as exc:
        result = {'status': 'unavailable', 'reason': str(exc)}
    except Exception as exc:
        result = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}
    Path(sys.argv[3]).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))
