"""Check boundary artifacts at segment boundaries in demucs output."""
import numpy as np
import soundfile as sf
import os

stem_base = '/app/data/music-files/stems/htdemucs/Hot-n-Fun - N.E.R.D'
vocals, sr = sf.read(os.path.join(stem_base, 'vocals.wav'))
print(f'SR={sr}, shape={vocals.shape}')

# Check energy around segment boundaries (4s = 4*sr samples)
seg_len = 4 * sr
window = sr // 10  # 100ms window

print("\n--- Boundary energy check (100ms windows) ---")
for i in range(1, 10):
    boundary = i * seg_len
    if boundary + window >= len(vocals):
        break
    before = vocals[boundary-window:boundary]
    at = vocals[boundary:boundary+window]
    rms_before = np.sqrt(np.mean(before**2))
    rms_at = np.sqrt(np.mean(at**2))
    ratio = rms_at / rms_before if rms_before > 0.001 else -1
    print(f'  {i*4:3d}s: before={rms_before:.6f} after={rms_at:.6f} ratio={ratio:.3f}')

# Check max sample values near boundaries for clipping
print("\n--- Max abs values near boundaries ---")
for i in range(1, 10):
    boundary = i * seg_len
    if boundary + window >= len(vocals):
        break
    region = vocals[boundary-window:boundary+window]
    max_abs = np.max(np.abs(region))
    print(f'  {i*4:3d}s: max_abs={max_abs:.6f}')

# Overall quality metrics
all_stems = None
for s in ["vocals", "drums", "bass", "other"]:
    data, _ = sf.read(os.path.join(stem_base, s + '.wav'))
    if all_stems is None:
        all_stems = data.copy()
    else:
        all_stems += data

# Check for clipping in sum
clipped = np.sum(np.abs(all_stems) > 0.99)
total_samples = all_stems.size
print(f"\n--- Sum clipping check ---")
print(f"  Samples near clipping (>0.99): {clipped}/{total_samples} ({100*clipped/total_samples:.4f}%)")
print(f"  Max abs in sum: {np.max(np.abs(all_stems)):.6f}")
print(f"  Max abs vocals: {np.max(np.abs(vocals)):.6f}")
