"""Test new scoring formula: penalize BPMs that only appear in high frequencies.
Formula: score = (1+alpha)*low_80Hz - alpha*full
This rewards BPMs present in sub-bass, penalizes hi-hat-only periodicity."""
import sys, os
sys.path.insert(0, '/app')
import numpy as np
import librosa
from scipy.signal import butter, sosfilt

def onset_periodicity(env, lag):
    n = len(env) - lag
    if n <= lag:
        return 0.0
    x1 = env[:n]
    x2 = env[lag:lag + n]
    m1, m2 = float(np.mean(x1)), float(np.mean(x2))
    s1, s2 = float(np.std(x1)), float(np.std(x2))
    if s1 * s2 < 1e-9:
        return 0.0
    return float(np.mean((x1 - m1) * (x2 - m2)) / (s1 * s2))

def test_formula(path, title, ref_bpm):
    print(f"\n{'='*70}")
    print(f"  {title}  (ref={ref_bpm})")
    print(f"{'='*70}")
    
    y, sr = librosa.load(path, sr=22050, mono=True)
    hop = 512
    fps = sr / hop
    
    onset_full = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    
    # Sub-bass 80Hz
    sos = butter(4, 80, btype='low', fs=sr, output='sos')
    y_low = sosfilt(sos, y.astype(np.float64))
    onset_80 = librosa.onset.onset_strength(y=y_low.astype(np.float32), sr=sr, hop_length=hop)
    
    # Get engine BPM (without perceptual correction - use _correct_octave_bpm directly)
    from app.modules.library.beat_engine import _correct_octave_bpm, _run_essentia
    from app.modules.library.beat_engine import _run_librosa_tempogram
    
    # Gather raw BPMs
    raw_bpms = []
    try:
        ess = _run_essentia(path)
        raw_bpms.extend([ess['bpm'], ess.get('percival_bpm', 0)])
        print(f"  Essentia: {ess['bpm']}")
    except Exception as e:
        print(f"  Essentia failed: {e}")
    
    try:
        from app.modules.library.beat_engine import _run_madmom
        mad = _run_madmom(path)
        raw_bpms.append(mad['bpm'])
        print(f"  Madmom: {mad['bpm']}")
    except Exception as e:
        print(f"  Madmom failed: {e}")
    
    try:
        lib_res = _run_librosa_tempogram(y, sr)
        raw_bpms.extend([lib_res.get('bpm', 0), lib_res.get('bpm_beat_track', 0),
                         lib_res.get('bpm_tempogram', 0), lib_res.get('bpm_low_prior', 0)])
        print(f"  Librosa: {lib_res.get('bpm', 0)}")
    except Exception as e:
        print(f"  Librosa failed: {e}")
    
    raw_bpms = [b for b in raw_bpms if b and b > 0]
    consensus_bpm = _correct_octave_bpm(raw_bpms)
    print(f"  Consensus BPM (pre-perceptual): {consensus_bpm}")
    
    # Generate candidates (×1/2 and ×2 only, NO 2/3 or 3/2)
    candidates = {round(consensus_bpm, 1)}
    for ratio in [0.5, 2.0]:
        alt = consensus_bpm * ratio
        if 70 <= alt <= 200:
            candidates.add(round(alt, 1))
    
    candidates = sorted(candidates)
    print(f"  Candidates: {candidates}")
    
    # Test different scoring formulas
    ALPHA = 0.5
    ENGINE_BIAS = 0.02
    SWITCH_THRESH = 0.02
    
    print(f"\n  {'BPM':>8s}  {'full':>8s}  {'80Hz':>8s}  {'OLD(35/65)':>10s}  {'NEW(sub-prom)':>13s}")
    
    old_scores = {}
    new_scores = {}
    
    for c_bpm in candidates:
        lag = int(round(60.0 / c_bpm * fps))
        if lag <= 0 or lag >= len(onset_full) // 4:
            continue
        
        ac_full = onset_periodicity(onset_full, lag)
        ac_80 = onset_periodicity(onset_80, lag)
        
        # Old formula: 0.35*full + 0.65*low300
        # Approximate with 80Hz: 0.35*full + 0.65*80Hz
        old_score = 0.35 * ac_full + 0.65 * ac_80
        
        # New formula: (1+alpha)*low - alpha*full
        new_score = (1 + ALPHA) * ac_80 - ALPHA * ac_full
        
        # Engine bias
        is_engine = abs(c_bpm - consensus_bpm) / consensus_bpm < 0.02
        if is_engine:
            old_score += 0.05  # old engine bias
            new_score += ENGINE_BIAS
        
        old_scores[c_bpm] = old_score
        new_scores[c_bpm] = new_score
        
        marker = " <-- ENGINE" if is_engine else (" <-- REF" if abs(c_bpm - ref_bpm) < 3 else "")
        print(f"  {c_bpm:>8.1f}  {ac_full:>8.4f}  {ac_80:>8.4f}  {old_score:>10.4f}  {new_score:>13.4f}{marker}")
    
    # Determine winners
    if old_scores:
        old_best = max(old_scores, key=old_scores.get)
        new_best = max(new_scores, key=new_scores.get)
        
        old_switch = old_best != round(consensus_bpm, 1) and old_scores[old_best] - old_scores.get(round(consensus_bpm, 1), 0) >= SWITCH_THRESH
        new_switch = new_best != round(consensus_bpm, 1) and new_scores[new_best] - new_scores.get(round(consensus_bpm, 1), 0) >= SWITCH_THRESH
        
        old_final = old_best if old_switch else consensus_bpm
        new_final = new_best if new_switch else consensus_bpm
        
        correct_old = abs(old_final - ref_bpm) < 5 or abs(old_final - ref_bpm * 2) < 5
        correct_new = abs(new_final - ref_bpm) < 5 or abs(new_final - ref_bpm * 2) < 5
        
        print(f"\n  OLD result: {old_final:.1f} {'✓' if correct_old else '✗'}")
        print(f"  NEW result: {new_final:.1f} {'✓' if correct_new else '✗'}")
        print(f"  Reference:  {ref_bpm}")

songs = [
    # Should detect as half-time
    ("/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI&Bohan Phoenix&马思唯&J.Mag.mp3",
     "不怪她", 80),
    ("/app/data/music-files/shared/God&#039;s Plan - Drake.mp3",
     "God's Plan", 77),
    # Should NOT change
    ("/app/data/music-files/shared/Hypnotize - The Notorious B.I.G..mp3",
     "Hypnotize", 94),
    ("/app/data/music-files/shared/Hip Hop Hooray - Naughty by Nature.mp3",
     "Hip Hop Hooray", 99),
    ("/app/data/music-files/shared/Hip Hop - Mos Def.mp3",
     "Hip Hop - Mos Def", 90),
    # Was wrongly corrected to 84 (should stay 126)
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3",
     "One B-Boy", 126),
    # Previous test songs
    ("/app/data/music-files/shared/Terrapin - Bonobo.mp3",
     "Terrapin", 120),
    ("/app/data/music-files/shared/Show Me - Kid Ink.mp3",
     "Show Me", 99),
    ("/app/data/music-files/shared/Fired Up - Various Artists.mp3",
     "Fired Up", 86),
]

for path, title, ref in songs:
    if os.path.exists(path):
        try:
            test_formula(path, title, ref)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
    else:
        print(f"  FILE NOT FOUND: {path}")
