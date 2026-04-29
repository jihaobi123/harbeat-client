"""Batch BPM test: run analyze_beats on 20 songs, output compact results."""
import sys, os, json, time, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)  # suppress all logging noise

sys.path.insert(0, '/app')

# Redirect stderr to suppress BeatNet noise during imports and execution
import io
_real_stderr = sys.stderr

import numpy as np
import librosa
from app.modules.library.beat_engine import analyze_beats

with open("/tmp/_songs20.json") as f:
    songs = json.load(f)

print(f"BATCH BPM TEST — {len(songs)} songs", flush=True)
print("=" * 80, flush=True)

results = []
for i, s in enumerate(songs, 1):
    path = s["path"]
    title = s["title"][:30]
    db_bpm = s.get("db_bpm")

    if not os.path.exists(path):
        print(f"[{i:2d}] {title}: FILE NOT FOUND", flush=True)
        continue

    t0 = time.time()
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        # Suppress stderr during analyze_beats (BeatNet noise)
        sys.stderr = io.StringIO()
        result = analyze_beats(path, y, sr, len(y) / sr)
        sys.stderr = _real_stderr
        elapsed = time.time() - t0

        raw = {}
        for k, v in result.raw_results.items():
            if isinstance(v, dict):
                raw[k] = round(v.get("bpm", v.get("bpm_beat_track", 0)), 1)

        results.append({
            "title": title,
            "artist": s["artist"][:16],
            "final": result.bpm,
            "conf": result.confidence,
            "raw": raw,
            "db_bpm": db_bpm,
            "time": round(elapsed, 1),
        })
        print(f"[{i:2d}] {title}: {result.bpm:.1f} BPM (conf={result.confidence:.3f}) [{elapsed:.0f}s]", flush=True)
    except Exception as e:
        sys.stderr = _real_stderr
        print(f"[{i:2d}] {title}: ERROR — {e}", flush=True)

print("\n" + "=" * 80, flush=True)
print("RESULTS TABLE", flush=True)
print(f"{'#':>2s} {'Song':<32s} {'Final':>6s} {'Conf':>5s} {'Ess':>6s} {'Mad':>6s} {'Lib':>6s} {'Time':>5s}", flush=True)
print("-" * 80, flush=True)

for i, r in enumerate(results, 1):
    ess = r["raw"].get("essentia", 0)
    mad = r["raw"].get("madmom", 0)
    lib = r["raw"].get("librosa", 0)
    ess_s = f"{ess:.1f}" if ess else "—"
    mad_s = f"{mad:.1f}" if mad else "—"
    lib_s = f"{lib:.1f}" if lib else "—"
    print(f"{i:2d} {r['title']:<32s} {r['final']:>6.1f} {r['conf']:>5.3f} {ess_s:>6s} {mad_s:>6s} {lib_s:>6s} {r['time']:>5.1f}", flush=True)

avg_conf = np.mean([r["conf"] for r in results]) if results else 0
low_conf = sum(1 for r in results if r["conf"] < 0.70)
print(f"\nAvg confidence: {avg_conf:.3f}")
print(f"Low confidence (< 0.70): {low_conf}/{len(results)}")

# Save results for reference
with open("/tmp/_results20.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\nResults saved to /tmp/_results20.json")
