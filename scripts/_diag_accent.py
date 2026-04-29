"""Diagnostic: beat-level accent pattern analysis for 3:2 detection."""
import sys, os
sys.path.insert(0, '/app')
import librosa
import numpy as np
from scipy.signal import butter, sosfilt

songs = [
    ("Fired Up", "/app/data/music-files/shared/Fired Up - Various Artists.mp3", 128.4),
    ("Terrapin", "/app/data/music-files/shared/Terrapin - The Quantic Soul Orchestra.mp3", 120.1),
    ("Show Me", "/app/data/music-files/shared/Show Me - Dogg Master.mp3", 98.2),
]

for name, path, engine_bpm in songs:
    print(f"\n{'='*60}")
    print(f"{name} (engine BPM: {engine_bpm})")
    print(f"{'='*60}")
    
    y, sr = librosa.load(path, sr=22050, mono=True)
    hop_length = 512
    fps = sr / hop_length
    
    # Low-band onset envelope (<200 Hz) for kick detection
    sos = butter(4, 200, btype='low', fs=sr, output='sos')
    y_low = sosfilt(sos, y.astype(np.float64))
    onset_low = librosa.onset.onset_strength(y=y_low.astype(np.float32), sr=sr)
    
    # Full-band onset
    onset_full = librosa.onset.onset_strength(y=y, sr=sr)
    
    # Get beats from librosa
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    
    print(f"  Detected {len(beat_times)} beats at ~{float(tempo) if not hasattr(tempo, '__len__') else float(tempo[0]):.1f} BPM")
    
    # Get onset strength at each beat in both bands
    beat_strengths_full = []
    beat_strengths_low = []
    for t in beat_times:
        idx = int(round(t * fps))
        if 0 <= idx < len(onset_full):
            start = max(0, idx - 1)
            end = min(len(onset_full), idx + 2)
            beat_strengths_full.append(float(np.max(onset_full[start:end])))
            beat_strengths_low.append(float(np.max(onset_low[start:end])))
        else:
            beat_strengths_full.append(0.0)
            beat_strengths_low.append(0.0)
    
    bs_full = np.array(beat_strengths_full)
    bs_low = np.array(beat_strengths_low)
    
    # Check accent patterns: n=2 (half-time), n=3 (3:2), n=4 (bar-level)
    print(f"\n  Beat-level accent analysis:")
    print(f"  {'n':>3} | {'Pattern/ratio':>14} | {'Full-band ratio':>16} | {'Low-band ratio':>16} | {'Meaning':>30}")
    
    for n in [2, 3, 4]:
        if len(bs_full) < n * 4:
            continue
        
        # Group beat strengths by position in cycle
        cycle_full = [[] for _ in range(n)]
        cycle_low = [[] for _ in range(n)]
        for i in range(len(bs_full)):
            cycle_full[i % n].append(bs_full[i])
            cycle_low[i % n].append(bs_low[i])
        
        avg_full = [np.mean(c) for c in cycle_full]
        avg_low = [np.mean(c) for c in cycle_low]
        
        # Find strongest position
        max_pos_full = np.argmax(avg_full)
        max_pos_low = np.argmax(avg_low)
        
        # Ratio: strongest / average of others
        other_full = np.mean([s for i, s in enumerate(avg_full) if i != max_pos_full])
        other_low = np.mean([s for i, s in enumerate(avg_low) if i != max_pos_low])
        
        ratio_full = avg_full[max_pos_full] / other_full if other_full > 0 else 0
        ratio_low = avg_low[max_pos_low] / other_low if other_low > 0 else 0
        
        if n == 2:
            meaning = "half-time → BPM/2"
        elif n == 3:
            meaning = "3:2 pattern → BPM*2/3"
        else:
            meaning = "bar accent → BPM/4"
        
        print(f"  {n:3d} | pos{max_pos_low}/{n}→{round(engine_bpm/n*max_pos_low + engine_bpm/n,1)} | {ratio_full:16.3f} | {ratio_low:16.3f} | {meaning:>30}")
    
    # Show first 12 beat strengths for visual inspection
    print(f"\n  First 12 beats (low-band strength):")
    for i in range(min(12, len(bs_low))):
        bar = '#' * int(bs_low[i] * 20)
        print(f"    Beat {i+1:2d}: {bs_low[i]:6.3f} |{bar}")
