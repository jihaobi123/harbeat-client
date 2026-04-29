"""Test half-time detection via beat-strength alternation pattern.
If beats show strong-weak-strong-weak pattern, it's half-time."""
import sys, os
sys.path.insert(0, '/app')
import numpy as np
import librosa
from scipy.signal import butter, sosfilt

def halftime_evidence(onset_env, fast_bpm, sr, hop_length=512):
    """Check if onset pattern shows every-other-beat accentuation.
    Returns ratio of strong/weak beat strengths."""
    fps = sr / hop_length
    fast_period = 60.0 / fast_bpm * fps
    
    n_beats = int(len(onset_env) / fast_period)
    if n_beats < 8:
        return 1.0, []
    
    strengths = []
    for i in range(n_beats):
        frame = int(round(i * fast_period))
        if frame < len(onset_env):
            w = max(1, int(fast_period * 0.15))
            s = max(0, frame - w)
            e = min(len(onset_env), frame + w + 1)
            strengths.append(float(np.max(onset_env[s:e])))
    
    if len(strengths) < 8:
        return 1.0, strengths
    
    s = np.array(strengths)
    even = s[0::2]
    odd = s[1::2]
    
    min_len = min(len(even), len(odd))
    even = even[:min_len]
    odd = odd[:min_len]
    
    e_mean = np.mean(even)
    o_mean = np.mean(odd)
    
    if min(e_mean, o_mean) < 1e-6:
        return 999.0, strengths
    
    ratio = max(e_mean, o_mean) / min(e_mean, o_mean)
    return ratio, strengths

def analyze(path, title, ref_bpm):
    print(f"\n{'='*70}")
    print(f"  {title}  (ref={ref_bpm})")
    print(f"{'='*70}")
    
    y, sr = librosa.load(path, sr=22050, mono=True)
    hop = 512
    
    # Full-band onset 
    onset_full = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    
    # Sub-bass (<100Hz) onset
    try:
        sos = butter(4, 100, btype='low', fs=sr, output='sos')
        y_low = sosfilt(sos, y.astype(np.float64))
        onset_low = librosa.onset.onset_strength(y=y_low.astype(np.float32), sr=sr, hop_length=hop)
    except:
        onset_low = onset_full
    
    # Get engine BPM
    from app.modules.library.beat_engine import analyze_beats
    result = analyze_beats(path, y, sr, len(y)/sr)
    engine_bpm = result.bpm
    print(f"  Engine BPM: {engine_bpm}")
    
    # Check half-time evidence at engine BPM
    print(f"\n  Half-time alternation analysis at engine BPM ({engine_bpm}):")
    for band_name, env in [("full-band", onset_full), ("sub-100Hz", onset_low)]:
        ratio, strengths = halftime_evidence(env, engine_bpm, sr, hop)
        print(f"    {band_name:>12s}: strong/weak ratio = {ratio:.3f}  "
              f"(>{1.3:.1f} suggests half-time)  "
              f"n_beats={len(strengths)}")
        if len(strengths) >= 8:
            s = np.array(strengths)
            even_mean = np.mean(s[0::2][:len(s)//2])
            odd_mean = np.mean(s[1::2][:len(s)//2])
            print(f"              even_mean={even_mean:.3f}, odd_mean={odd_mean:.3f}")
    
    # Also check at double engine BPM if applicable
    double_bpm = engine_bpm * 2
    half_bpm = engine_bpm / 2
    if half_bpm >= 65:
        print(f"\n  At half-BPM ({half_bpm:.1f}):")
        for band_name, env in [("full-band", onset_full), ("sub-100Hz", onset_low)]:
            ratio, strengths = halftime_evidence(env, half_bpm, sr, hop)
            print(f"    {band_name:>12s}: ratio = {ratio:.3f}, n_beats={len(strengths)}")

songs = [
    # SHOULD detect as half-time
    ("/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI&Bohan Phoenix&马思唯&J.Mag.mp3",
     "不怪她 (ref=80, should halve from ~162)", 80),
    ("/app/data/music-files/shared/God&#039;s Plan - Drake.mp3",
     "God's Plan (ref=77, should halve from ~153)", 77),
    
    # Should NOT change (correct tempo detected)
    ("/app/data/music-files/shared/Hypnotize - The Notorious B.I.G..mp3",
     "Hypnotize (ref=94, should stay ~94)", 94),
    ("/app/data/music-files/shared/Hip Hop Hooray - Naughty by Nature.mp3",
     "Hip Hop Hooray (ref=99, should stay ~99)", 99),
    ("/app/data/music-files/shared/Hip Hop - Mos Def.mp3",
     "Hip Hop - Mos Def (ref=90, should stay ~92)", 90),
    
    # Should NOT change (126 is correct)
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3",
     "One B-Boy (ref=126, engine=84 wrong)", 126),
]

for path, title, ref in songs:
    if os.path.exists(path):
        try:
            analyze(path, title, ref)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
    else:
        print(f"  FILE NOT FOUND: {path}")
