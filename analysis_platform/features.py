"""CPU descriptors, independent of HarBeat's beat/section/model decisions."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import find_peaks
from scipy.cluster.hierarchy import linkage, fcluster

from .report import intervals
from .runner import Unavailable


def load_audio(path):
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True)
    if len(y) < sr // 2 or not np.isfinite(y).all():
        raise ValueError('audio is too short or contains invalid samples')
    if len(y) > sr * 7200:
        raise ValueError('maximum audio duration is 2 hours')
    return y, sr


def roughness_points(y, sr):
    # Pairwise spectral-peak roughness, Sethares-style critical-band curve.
    # This is not Essentia's exact implementation, nor a harmony correctness score.
    frame, hop = 2048, max(1, round(sr * .25))
    result = []
    for start in range(0, len(y), hop):
        part = y[start:start + frame]
        rms = float(np.sqrt(np.mean(part**2)))
        value = None
        if len(part) > 64 and rms > 1e-7:
            magnitude = np.abs(np.fft.rfft(part * np.hanning(len(part)), n=frame))
            frequencies = np.fft.rfftfreq(frame, 1 / sr)
            peaks, _ = find_peaks(magnitude, height=magnitude.max() * .02)
            peaks = peaks[(frequencies[peaks] >= 30) & (frequencies[peaks] <= 8000)]
            peaks = np.sort(peaks[np.argsort(magnitude[peaks])[-60:]])
            f, a = frequencies[peaks], magnitude[peaks]
            if len(a):
                a = a / a.sum()
                i, j = np.triu_indices(len(f), 1)
                s = .24 / (.0207 * f[i] + 18.96)
                x = s * (f[j] - f[i])
                value = float(np.sum(a[i] * a[j] * (np.exp(-3.5*x) - np.exp(-5.75*x))))
        result.append({'start': start / sr, 'end': min((start + hop) / sr, len(y) / sr),
                       'window_end': min((start + frame) / sr, len(y) / sr),
                       'value': value, 'rms_dbfs': float(20*np.log10(rms)) if rms > 0 else None})
    return result


def roughness(path, base, config):
    y, sr = load_audio(path)
    points = roughness_points(y, sr)
    values = [p['value'] for p in points if p['value'] is not None]
    return {'method': 'spectral_peak_pair_roughness_v1', 'sample_rate': sr, 'points': points,
            'mean': float(np.mean(values)) if values else None,
            'definition': 'gain-normalized spectral roughness; not harmonic tension or aesthetic quality',
            'parameters': {'frame_samples': 2048, 'hop_sec': .25, 'max_peaks': 60},
            'limitations': ['mono analysis', 'noise/distortion affect this measure', 'no listener calibration']}


def repeat_sections(path, base, config):
    import librosa
    y, sr = load_audio(path)
    duration = len(y) / sr
    segments = intervals(base.get('sections', base.get('phrase_map', [])))
    if not segments:
        segments = [{'start': s, 'end': min(s+8, duration), 'label': 'analysis_window'} for s in np.arange(0, duration, 8)]
        origin = 'fixed_8s_windows_without_section_claim'
    else:
        origin = 'existing_sections_unchanged'
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=2048, hop_length=512)
    vectors, energy, valid, output = [], [], [], []
    for index, seg in enumerate(segments):
        start, end = max(0., seg['start']), min(duration, seg['end'])
        if end <= start:
            continue
        output.append({**seg, 'start': start, 'end': end, 'cluster': None})
        part = y[int(start*sr):int(end*sr)]
        rms = float(np.sqrt(np.mean(part**2))) if len(part) else 0
        if rms < 1e-7 or end - start < .5:
            continue
        lo, hi = int(start*sr/512), max(int(start*sr/512)+1, int(end*sr/512))
        v = chroma[:, lo:hi].mean(axis=1)
        vectors.append(v / (np.linalg.norm(v) + 1e-10))
        energy.append(20 * np.log10(rms))
        valid.append(len(output)-1)
    if vectors:
        e = np.asarray(energy)
        e = (e-e.mean()) / (e.std() if e.std() > 1e-8 else 1)
        x = np.column_stack([vectors, e * .25])
        labels = fcluster(linkage(x, method='average', metric='euclidean'),
                          t=float(config.get('repeat_threshold', .5)), criterion='distance') if len(x) > 1 else [1]
        for index, label in zip(valid, labels):
            output[index]['cluster'] = f'R{int(label)}'
    return {'method': 'chroma_rms_average_linkage_v1', 'boundary_source': origin,
            'segments': output, 'definition': 'similarity groups; no verse/chorus inference',
            'limitations': ['similar chords may group different musical roles', 'threshold is not listener calibrated']}


if __name__ == '__main__':
    try:
        request = json.loads(Path(sys.argv[2]).read_text())
        from .measurements import core_features, measure
        from .dj_signals import analyze
        fn = {'dj_signals':analyze,'roughness': roughness, 'repeat': repeat_sections, 'core_features': core_features, 'measurements': measure}[sys.argv[1]]
        result = {'status': 'ready', 'data': fn(request['audio'], request['base'], request['config'])}
    except (ImportError, Unavailable) as exc:
        result = {'status': 'unavailable', 'reason': str(exc)}
    except Exception as exc:
        result = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}
    Path(sys.argv[3]).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))
