"""Diagnostic: comb filter periodicity + ultra-low-band analysis."""
import sys, os
sys.path.insert(0, '/app')
import librosa
import numpy as np
from scipy.signal import butter, sosfilt

def ac(env, lag):
    n = len(env) - lag
    if n <= lag:
        return 0.0
    x1, x2 = env[:n], env[lag:lag+n]
    m1, m2 = np.mean(x1), np.mean(x2)
    s1, s2 = np.std(x1), np.std(x2)
    if s1 * s2 < 1e-9:
        return 0.0
    return float(np.mean((x1 - m1) * (x2 - m2)) / (s1 * s2))

def comb_score(env, lag, n_harmonics=4):
    """Autocorrelation at lag and its integer multiples (comb filter)."""
    total, weights = 0.0, 0.0
    for h in range(1, n_harmonics + 1):
        sub_lag = lag * h
        if sub_lag >= len(env) // 2:
            break
        w = 1.0 / h
        total += ac(env, sub_lag) * w
        weights += w
    return total / weights if weights > 0 else 0.0

songs = [
    ("Fired Up", "/app/data/music-files/shared/Fired Up - Various Artists.mp3", 128.4),
    ("Terrapin", "/app/data/music-files/shared/Terrapin - The Quantic Soul Orchestra.mp3", 120.1),
    ("Show Me", "/app/data/music-files/shared/Show Me - Dogg Master.mp3", 98.2),
    ("Dear Mama", "/app/data/music-files/shared/Dear Mama - 2Pac.mp3", 93.8),
]

for name, path, engine_bpm in songs:
    print(f"\n{'='*60}")
    print(f"{name} (engine BPM: {engine_bpm})")
    print(f"{'='*60}")
    
    y, sr = librosa.load(path, sr=22050, mono=True)
    fps = sr / 512
    onset_full = librosa.onset.onset_strength(y=y, sr=sr)
    
    # Different low-pass cutoffs
    bands = {}
    for cutoff in [300, 200, 100]:
        sos = butter(4, cutoff, btype='low', fs=sr, output='sos')
        y_f = sosfilt(sos, y.astype(np.float64))
        bands[cutoff] = librosa.onset.onset_strength(y=y_f.astype(np.float32), sr=sr)
    
    candidates = {round(engine_bpm, 1)}
    for ratio in [2/3, 0.5, 1.5, 2.0]:
        alt = engine_bpm * ratio
        if 75 <= alt <= 200:
            candidates.add(round(alt, 1))
    
    print(f"\n  Single-lag AC vs Comb filter (4 harmonics):")
    print(f"  {'BPM':>7} | {'AC_full':>8} | {'AC_100':>8} | {'Comb_full':>10} | {'Comb_100':>10} | {'Comb_200':>10} | {'Mixed':>10}")
    
    for c_bpm in sorted(candidates):
        lag = int(round(60.0 / c_bpm * fps))
        
        ac_f = ac(onset_full, lag)
        ac_100 = ac(bands[100], lag)
        
        comb_f = comb_score(onset_full, lag)
        comb_100 = comb_score(bands[100], lag)
        comb_200 = comb_score(bands[200], lag)
        
        # Mixed: comb with sub-bass emphasis
        mixed = 0.3 * comb_f + 0.7 * comb_100
        
        is_engine = abs(c_bpm - engine_bpm) / engine_bpm < 0.02
        marker = " <--" if is_engine else ""
        
        print(f"  {c_bpm:7.1f} | {ac_f:8.4f} | {ac_100:8.4f} | {comb_f:10.4f} | {comb_100:10.4f} | {comb_200:10.4f} | {mixed:10.4f}{marker}")
    
    # Also show the individual harmonic ACs for debugging
    print(f"\n  Harmonic breakdown (full band):")
    for c_bpm in sorted(candidates):
        lag = int(round(60.0 / c_bpm * fps))
        harmonics = []
        for h in range(1, 5):
            sub_lag = lag * h
            if sub_lag < len(onset_full) // 2:
                harmonics.append(f"h{h}={ac(onset_full, sub_lag):.3f}")
        is_engine = abs(c_bpm - engine_bpm) / engine_bpm < 0.02
        print(f"    {c_bpm:7.1f}: {', '.join(harmonics)} {'<--' if is_engine else ''}")
    
    print(f"\n  Harmonic breakdown (100 Hz low-band):")
    for c_bpm in sorted(candidates):
        lag = int(round(60.0 / c_bpm * fps))
        harmonics = []
        for h in range(1, 5):
            sub_lag = lag * h
            if sub_lag < len(bands[100]) // 2:
                harmonics.append(f"h{h}={ac(bands[100], sub_lag):.3f}")
        is_engine = abs(c_bpm - engine_bpm) / engine_bpm < 0.02
        print(f"    {c_bpm:7.1f}: {', '.join(harmonics)} {'<--' if is_engine else ''}")
