"""Compare original audio vs demucs stems: sample rate, duration, channels."""
import os, sys
sys.path.insert(0, "/app")
import soundfile as sf
import librosa

# Pick a song that has stems
stem_base = "/app/data/music-files/stems/htdemucs"
shared = "/app/data/music-files/shared"

# Find a song with both original and stems
for d in os.listdir(stem_base):
    stem_dir = os.path.join(stem_base, d)
    if not os.path.isdir(stem_dir):
        continue
    # Find matching source
    for ext in [".mp3", ".flac", ".wav"]:
        src = os.path.join(shared, d + ext)
        if os.path.isfile(src):
            break
    else:
        continue

    print(f"=== {d} ===")
    y_orig, sr_orig = librosa.load(src, sr=None, mono=False)
    dur_orig = y_orig.shape[-1] / sr_orig
    print(f"  Original: sr={sr_orig} channels={y_orig.shape[0] if y_orig.ndim > 1 else 1} duration={dur_orig:.2f}s")

    for s in ["vocals", "drums", "bass", "other"]:
        p = os.path.join(stem_dir, s + ".wav")
        if os.path.isfile(p):
            data, sr = sf.read(p)
            dur = data.shape[0] / sr
            ch = data.shape[1] if data.ndim > 1 else 1
            print(f"  {s:8s}: sr={sr} channels={ch} duration={dur:.2f}s diff={dur - dur_orig:+.3f}s")
        else:
            print(f"  {s:8s}: MISSING")

    # Check if sum of stems matches original
    import numpy as np
    stems_sum = None
    for s in ["vocals", "drums", "bass", "other"]:
        p = os.path.join(stem_dir, s + ".wav")
        data, sr = sf.read(p)
        if stems_sum is None:
            stems_sum = data.copy()
        else:
            stems_sum += data

    # Load original at stem sample rate for comparison
    y_at_stem_sr, _ = librosa.load(src, sr=sr, mono=False)
    if y_at_stem_sr.ndim == 1:
        y_at_stem_sr = y_at_stem_sr.reshape(1, -1)
    y_at_stem_sr = y_at_stem_sr.T  # (samples, channels)

    min_len = min(len(stems_sum), len(y_at_stem_sr))
    diff = stems_sum[:min_len] - y_at_stem_sr[:min_len]
    rms_diff = np.sqrt(np.mean(diff**2))
    rms_orig = np.sqrt(np.mean(y_at_stem_sr[:min_len]**2))
    print(f"  Sum check: RMS_diff={rms_diff:.6f} RMS_orig={rms_orig:.6f} ratio={rms_diff/rms_orig:.4f}")
    print(f"  Length: stems={len(stems_sum)} orig={len(y_at_stem_sr)} diff={len(stems_sum)-len(y_at_stem_sr)}")
    print()

    # Only check first 2 songs
    if d.startswith("H"):
        break
