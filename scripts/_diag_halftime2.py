"""Diagnostic: analyze onset periodicity for songs with wrong BPM selection."""
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

def analyze_song(path, title, ref_bpm, engine_bpm):
    print(f"\n{'='*70}")
    print(f"  {title}  (ref={ref_bpm}, engine={engine_bpm})")
    print(f"{'='*70}")
    
    y, sr = librosa.load(path, sr=22050, mono=True)
    hop = 512
    fps = sr / hop
    
    # Full-band onset
    onset_full = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    
    # Different low-pass cutoffs
    bands = {'full': onset_full}
    for cutoff in [300, 150, 100, 80]:
        try:
            sos = butter(4, cutoff, btype='low', fs=sr, output='sos')
            y_filt = sosfilt(sos, y.astype(np.float64))
            bands[f'{cutoff}Hz'] = librosa.onset.onset_strength(
                y=y_filt.astype(np.float32), sr=sr, hop_length=hop)
        except Exception as e:
            print(f"  Filter {cutoff}Hz failed: {e}")
    
    # librosa tempo estimates per band
    print(f"\n  librosa.feature.tempo() per band:")
    for bname, env in bands.items():
        try:
            t = librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=hop)
            print(f"    {bname:>8s}: {t[0]:.1f} BPM")
        except:
            print(f"    {bname:>8s}: FAILED")
    
    # Generate candidates 
    candidates = set()
    for ratio in [0.5, 2/3, 1.0, 1.5, 2.0]:
        alt = engine_bpm * ratio
        if 65 <= alt <= 210:
            candidates.add(round(alt, 1))
    candidates.add(float(ref_bpm))
    candidates = sorted(candidates)
    
    print(f"\n  Periodicity scores:")
    print(f"  {'BPM':>8s}", end="")
    for bname in bands:
        print(f"  {bname:>8s}", end="")
    print("   weighted(35/65)")
    
    for c_bpm in candidates:
        lag = int(round(60.0 / c_bpm * fps))
        if lag <= 0 or lag >= len(onset_full) // 4:
            continue
        marker = ""
        if abs(c_bpm - ref_bpm) < 2:
            marker = " <-- REF"
        elif abs(c_bpm - engine_bpm) < 2:
            marker = " <-- ENGINE"
        
        print(f"  {c_bpm:>8.1f}", end="")
        for bname, env in bands.items():
            ac = onset_periodicity(env, lag)
            print(f"  {ac:>8.4f}", end="")
        
        # Compute weighted score (current algorithm: 0.35*full + 0.65*low300)
        ac_full = onset_periodicity(onset_full, lag)
        ac_low = onset_periodicity(bands.get('300Hz', onset_full), lag)
        weighted = 0.35 * ac_full + 0.65 * ac_low
        print(f"   {weighted:>6.4f}{marker}")

songs = [
    ("/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI&Bohan Phoenix&马思唯&J.Mag.mp3",
     "不怪她 - HARIKIRI", 80, 161.8),
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3",
     "One B-Boy - Dj Pablo", 126, 161.8),  # engine raw was ~126, final was 84
]

for path, title, ref, eng in songs:
    if os.path.exists(path):
        try:
            analyze_song(path, title, ref, eng)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
    else:
        print(f"  FILE NOT FOUND: {path}")
