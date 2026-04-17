"""Diagnostic: analyze onset periodicity at different frequency bands
for songs with metrical level selection issues."""
import sys, os
sys.path.insert(0, '/app')
import numpy as np
import librosa
from scipy.signal import butter, sosfilt

def onset_periodicity(env, lag):
    n = len(env)
    if lag <= 0 or lag >= n:
        return 0.0
    x1 = env[:n - lag]
    x2 = env[lag:]
    m1, m2 = x1.mean(), x2.mean()
    s1, s2 = x1.std(), x2.std()
    if s1 * s2 < 1e-9:
        return 0.0
    return float(np.mean((x1 - m1) * (x2 - m2)) / (s1 * s2))

def analyze_song(path, title, ref_bpm):
    print(f"\n{'='*70}")
    print(f"  {title}  (ref BPM = {ref_bpm})")
    print(f"{'='*70}")
    
    y, sr = librosa.load(path, sr=22050, mono=True)
    hop = 512
    fps = sr / hop
    
    # Full-band onset
    onset_full = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    
    # Different low-pass cutoffs
    bands = {'full': onset_full}
    for cutoff in [300, 200, 150, 100, 80]:
        try:
            sos = butter(4, cutoff, btype='low', fs=sr, output='sos')
            y_filt = sosfilt(sos, y.astype(np.float64))
            bands[f'{cutoff}Hz'] = librosa.onset.onset_strength(
                y=y_filt.astype(np.float32), sr=sr, hop_length=hop)
        except Exception as e:
            print(f"  Filter {cutoff}Hz failed: {e}")
    
    # Detect librosa tempo on each band
    print(f"\n  librosa.feature.tempo() estimates per band:")
    for bname, env in bands.items():
        try:
            t = librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=hop)
            print(f"    {bname:>8s}: {t[0]:.1f} BPM")
        except:
            print(f"    {bname:>8s}: FAILED")
    
    # Get engine BPM (the detected value)
    from app.modules.library.beat_engine import analyze_beats
    result = analyze_beats(path, y, sr, len(y)/sr)
    engine_bpm = result.bpm
    print(f"\n  Engine final BPM: {engine_bpm}")
    print(f"  Raw results: {result.raw_results}")
    
    # Generate candidates (×1/2, ×2/3, ×1, ×3/2, ×2)
    candidates = set()
    for ratio in [0.5, 2/3, 1.0, 1.5, 2.0]:
        alt = engine_bpm * ratio
        if 65 <= alt <= 210:
            candidates.add(round(alt, 1))
    
    # Also include ref_bpm as a candidate for analysis
    candidates.add(float(ref_bpm))
    candidates = sorted(candidates)
    
    print(f"\n  Onset periodicity scores for candidates: {candidates}")
    print(f"  {'BPM':>8s}", end="")
    for bname in bands:
        print(f"  {bname:>8s}", end="")
    print()
    
    for c_bpm in candidates:
        lag = int(round(60.0 / c_bpm * fps))
        if lag <= 0 or lag >= len(onset_full) // 4:
            continue
        marker = " <-- ref" if abs(c_bpm - ref_bpm) < 2 else (" <-- engine" if abs(c_bpm - engine_bpm) < 2 else "")
        print(f"  {c_bpm:>8.1f}", end="")
        for bname, env in bands.items():
            ac = onset_periodicity(env, lag)
            print(f"  {ac:>8.4f}", end="")
        print(marker)

# Songs with issues
songs = [
    ("/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI.mp3", "不怪她 - HARIKIRI", 80),
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo.mp3", "One B-Boy - Dj Pablo", 126),
    ("/app/data/music-files/shared/It's Been A Long Time - Rakim.mp3", "It's Been A Long Time - Rakim", 89),
    ("/app/data/music-files/shared/So Many Ways - Warren G.mp3", "So Many Ways - Warren G", 95),
]

for path, title, ref in songs:
    if os.path.exists(path):
        try:
            analyze_song(path, title, ref)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
    else:
        print(f"  FILE NOT FOUND: {path}")
