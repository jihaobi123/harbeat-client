"""Batch BPM test: run analyze_beats on 20 songs, output compact results."""
import sys, os, json, time
sys.path.insert(0, '/app')
import numpy as np
import librosa
from app.modules.library.beat_engine import analyze_beats

with open("/tmp/_songs20.json") as f:
    songs = json.load(f)

print("=" * 90)
print(f"BATCH BPM TEST — {len(songs)} songs")
print("=" * 90)

results = []
for i, s in enumerate(songs, 1):
    path = s["path"]
    title = s["title"][:28]
    db_bpm = s.get("db_bpm")

    if not os.path.exists(path):
        print(f"[{i:2d}] {title}: FILE NOT FOUND")
        continue

    t0 = time.time()
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        result = analyze_beats(path, y, sr, len(y) / sr)
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
        print(f"[{i:2d}] {title}: {result.bpm:.1f} BPM, conf={result.confidence:.3f}, {elapsed:.0f}s")
    except Exception as e:
        print(f"[{i:2d}] {title}: ERROR — {e}")

print("\n" + "=" * 90)
print("RESULTS TABLE")
print("=" * 90)
print(f"{'#':>2s} {'Song':<30s} {'Final':>6s} {'Conf':>5s} {'Essentia':>9s} {'Madmom':>7s} {'Librosa':>8s}")
print("-" * 90)

for i, r in enumerate(results, 1):
    ess = r["raw"].get("essentia", "—")
    mad = r["raw"].get("madmom", "—")
    lib = r["raw"].get("librosa", "—")
    print(f"{i:2d} {r['title']:<30s} {r['final']:>6.1f} {r['conf']:>5.3f} {str(ess):>9s} {str(mad):>7s} {str(lib):>8s}")

# Engine agreement stats
agreements = []
for r in results:
    raw_vals = [v for v in r["raw"].values() if isinstance(v, (int, float)) and v > 0]
    if len(raw_vals) >= 2:
        # Normalize to same metrical level
        ref = r["final"]
        norm = []
        for b in raw_vals:
            best = b
            for ratio in [0.5, 2/3, 1.0, 1.5, 2.0]:
                v = b * ratio
                if abs(v - ref) < abs(best - ref):
                    best = v
            norm.append(best)
        spread = max(norm) - min(norm)
        agreements.append(spread)

if agreements:
    print(f"\nEngine spread (after normalization): mean={np.mean(agreements):.1f}, median={np.median(agreements):.1f}, max={np.max(agreements):.1f} BPM")

avg_conf = np.mean([r["conf"] for r in results])
print(f"Average confidence: {avg_conf:.3f}")
print(f"Songs needing review (conf<0.70): {sum(1 for r in results if r['conf'] < 0.70)}/{len(results)}")
