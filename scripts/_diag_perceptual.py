"""Diagnostic: print perceptual tempo scores for Fired Up and Terrapin."""
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
    
    onset_full = librosa.onset.onset_strength(y=y, sr=sr)
    
    sos = butter(4, 300, btype='low', fs=sr, output='sos')
    y_low = sosfilt(sos, y.astype(np.float64))
    onset_low = librosa.onset.onset_strength(y=y_low.astype(np.float32), sr=sr)
    
    # Also try 200 Hz cutoff
    sos200 = butter(4, 200, btype='low', fs=sr, output='sos')
    y_low200 = sosfilt(sos200, y.astype(np.float64))
    onset_low200 = librosa.onset.onset_strength(y=y_low200.astype(np.float32), sr=sr)
    
    candidates = {round(engine_bpm, 1)}
    for ratio in [2/3, 0.5, 1.5, 2.0]:
        alt = engine_bpm * ratio
        if 75 <= alt <= 200:
            candidates.add(round(alt, 1))
    
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
    
    print(f"  Candidates: {sorted(candidates)}")
    print(f"  {'BPM':>7} | {'lag':>4} | {'AC_full':>8} | {'AC_300':>8} | {'AC_200':>8} | {'Score35/65':>11} | {'Score25/75':>11} | {'Score20/80':>11}")
    
    for c_bpm in sorted(candidates):
        lag = int(round(60.0 / c_bpm * fps))
        ac_f = ac(onset_full, lag)
        ac_l300 = ac(onset_low, lag)
        ac_l200 = ac(onset_low200, lag)
        
        s_35_65 = 0.35 * ac_f + 0.65 * ac_l300
        s_25_75 = 0.25 * ac_f + 0.75 * ac_l300
        s_20_80 = 0.20 * ac_f + 0.80 * ac_l200
        
        is_engine = abs(c_bpm - engine_bpm) / engine_bpm < 0.02
        marker = " <-- engine" if is_engine else ""
        
        print(f"  {c_bpm:7.1f} | {lag:4d} | {ac_f:8.4f} | {ac_l300:8.4f} | {ac_l200:8.4f} | {s_35_65:11.4f} | {s_25_75:11.4f} | {s_20_80:11.4f}{marker}")
