"""Clear stale analysis lock and re-separate one test song."""
import redis
import os
import sys
import subprocess
import gc
import ctypes

# Clear stale lock
r = redis.Redis(host='harbeat-redis')
r.delete('harbeat:analysis_lock')
print("Cleared stale analysis lock")

# Re-separate just one song as test
STEMS_BASE = "/app/data/music-files/stems"
test_song = "Hot-n-Fun - N.E.R.D"
stem_dir = os.path.join(STEMS_BASE, "htdemucs", test_song)
source = None
for ext in [".mp3", ".flac", ".wav", ".m4a"]:
    p = os.path.join("/app/data/music-files/shared", test_song + ext)
    if os.path.isfile(p):
        source = p
        break

if not source:
    print(f"ERROR: no source file for {test_song}")
    sys.exit(1)

print(f"Source: {source}")
print(f"Stems dir: {stem_dir}")

# Delete old stems
import shutil
if os.path.isdir(stem_dir):
    shutil.rmtree(stem_dir)
    print("Deleted old stems")

# Run demucs with --segment 7
print("Running demucs --segment 7 ...")
result = subprocess.run(
    [sys.executable, "-m", "demucs", "-n", "htdemucs", "--segment", "7",
     "-o", STEMS_BASE, source],
    capture_output=True,
    text=True,
    timeout=1800,
)

if result.returncode != 0:
    print(f"FAILED: {result.stderr[-500:]}")
    sys.exit(1)

print("Done! Checking stems...")
for s in ["vocals", "drums", "bass", "other"]:
    p = os.path.join(stem_dir, s + ".wav")
    if os.path.isfile(p):
        size = os.path.getsize(p) / 1024 / 1024
        print(f"  {s}.wav: {size:.1f} MB")
    else:
        print(f"  {s}.wav: MISSING")

# Compare quality
import soundfile as sf
import numpy as np
import librosa

y_orig, sr_orig = librosa.load(source, sr=None, mono=False)
all_stems = None
for s in ["vocals", "drums", "bass", "other"]:
    data, sr = sf.read(os.path.join(stem_dir, s + ".wav"))
    if all_stems is None:
        all_stems = data.copy()
    else:
        all_stems += data

y_at_sr = librosa.load(source, sr=sr, mono=False)[0]
if y_at_sr.ndim == 1:
    y_at_sr = y_at_sr.reshape(1, -1)
y_at_sr = y_at_sr.T

min_len = min(len(all_stems), len(y_at_sr))
diff = all_stems[:min_len] - y_at_sr[:min_len]
rms_diff = np.sqrt(np.mean(diff**2))
rms_orig = np.sqrt(np.mean(y_at_sr[:min_len]**2))
ratio = rms_diff / rms_orig

print(f"\nQuality comparison (segment=7):")
print(f"  RMS diff: {rms_diff:.6f}")
print(f"  RMS orig: {rms_orig:.6f}")
print(f"  Ratio: {ratio:.4f} ({ratio*100:.2f}%)")
print(f"  (Previous segment=4 ratio was ~0.0272 = 2.72%)")
