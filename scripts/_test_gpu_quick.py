"""Quick test: verify GPU-optimized BeatNet works correctly on one song."""
import time
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(message)s")

import librosa
from app.modules.library.beat_engine import analyze_beats

test_file = "data/music-files/shared/California Love - 2Pac _ Dr. Dre _ The D.O.C..mp3"

print(f"\n{'='*60}")
print(f"  GPU Optimization Quick Test")
print(f"{'='*60}\n")

print("Loading audio with librosa...")
y, sr = librosa.load(test_file, sr=22050, mono=True)
duration = len(y) / sr
print(f"Audio loaded: {len(y)} samples, {duration:.1f}s, sr={sr}")

t0 = time.time()
result = analyze_beats(test_file, y, sr, duration)
dt = time.time() - t0

print(f"\nResult: BPM={result.bpm:.1f}  confidence={result.confidence:.3f}")
print(f"Engines: {result.engines_used}")
print(f"Beat count: {len(result.beat_points)}")
print(f"Needs review: {result.needs_review}")
print(f"Analysis time: {dt:.1f}s")
print(f"\nRaw engine results:")
for eng, res in result.raw_results.items():
    if "bpm" in res:
        print(f"  {eng}: BPM={res['bpm']}")
    if "_sub_bpms" in res:
        print(f"  {eng} sub-models: {res['_sub_bpms']}")
