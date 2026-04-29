"""
Batch BPM analysis: run full beat engine on 6 songs and output detailed results.
"""
import sys, os, json, time
sys.path.insert(0, '/app')

import librosa
import numpy as np
from app.modules.library.beat_engine import analyze_beats

songs = [
    ("Terrapin", "The Quantic Soul Orchestra", "/app/data/music-files/shared/Terrapin - The Quantic Soul Orchestra.mp3", 120),
    ("Dear Mama", "2Pac", "/app/data/music-files/shared/Dear Mama - 2Pac.mp3", 84),
    ("The Learning (Burn)", "Big Noyd / Mobb Deep", "/app/data/music-files/shared/The Learning (Burn) - Big Noyd _ Mobb Deep.mp3", 96),
    ("Show Me", "Dogg Master", "/app/data/music-files/shared/Show Me - Dogg Master.mp3", 99),
    ("Hip Hop", "Rakim", "/app/data/music-files/shared/Hip Hop - Rakim.mp3", 88),
    ("Fired Up", "Various Artists", "/app/data/music-files/shared/Fired Up - Various Artists.mp3", 86),
]

print("=" * 80)
print("BATCH BPM ANALYSIS - 5 SONGS")
print("=" * 80)

results = []
for title, artist, path, ref_bpm in songs:
    print(f"\n{'='*60}")
    print(f"Analyzing: {title} - {artist} (ref BPM: {ref_bpm})")
    print(f"{'='*60}")
    
    if not os.path.exists(path):
        print(f"  FILE NOT FOUND: {path}")
        results.append({"title": title, "artist": artist, "error": "file not found", "ref_bpm": ref_bpm})
        continue
    
    t0 = time.time()
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)
        result = analyze_beats(path, y, sr, duration)
        elapsed = time.time() - t0
        
        # BeatResult is a NamedTuple/dataclass - access via attributes
        bpm = getattr(result, 'bpm', None)
        confidence = getattr(result, 'confidence', None)
        engines = getattr(result, 'engines_used', [])
        needs_review = getattr(result, 'needs_review', False)
        grid_offset = getattr(result, 'grid_offset', None)
        grid_interval = getattr(result, 'grid_interval', None)
        
        # Try to get confidence_details
        confidence_details = {}
        for attr in ['confidence_details', 'details']:
            if hasattr(result, attr):
                confidence_details = getattr(result, attr)
                break
        
        raw_results = getattr(result, 'raw_results', {})
        
        print(f"  BPM: {bpm} (ref: {ref_bpm})")
        err = abs(bpm - ref_bpm) if bpm else 999
        print(f"  Error: {err:.1f} BPM ({'OK' if err <= 3 else 'CLOSE' if err <= 8 else 'WRONG'})")
        print(f"  Raw engines: {raw_results}")
        print(f"  Confidence: {confidence}")
        print(f"  Engines: {engines}")
        print(f"  Needs review: {needs_review}")
        print(f"  Time: {elapsed:.1f}s")
        
        results.append({
            "title": title,
            "artist": artist,
            "bpm": bpm,
            "ref_bpm": ref_bpm,
            "error_bpm": round(err, 1),
            "confidence": confidence,
            "engines": engines,
            "needs_review": needs_review,
            "raw": raw_results,
            "time": round(elapsed, 1)
        })
    except Exception as ex:
        elapsed = time.time() - t0
        print(f"  ERROR: {ex}")
        import traceback
        traceback.print_exc()
        results.append({"title": title, "artist": artist, "error": str(ex), "ref_bpm": ref_bpm, "time": round(elapsed, 1)})

print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")
for r in results:
    if "error" in r:
        print(f"  {r['title']}: ERROR - {r['error']}")
    else:
        status = "✓" if r['error_bpm'] <= 3 else "~" if r['error_bpm'] <= 8 else "✗"
        print(f"  {status} {r['title']}: BPM={r['bpm']} (ref={r['ref_bpm']}, err={r['error_bpm']}) | Conf={r['confidence']} | Raw={r['raw']}")

# Overall accuracy
valid = [r for r in results if "error" not in r]
if valid:
    avg_err = sum(r['error_bpm'] for r in valid) / len(valid)
    correct = sum(1 for r in valid if r['error_bpm'] <= 3)
    close = sum(1 for r in valid if r['error_bpm'] <= 8)
    print(f"\nAccuracy: {correct}/{len(valid)} exact (≤3 BPM), {close}/{len(valid)} close (≤8 BPM)")
    print(f"Average error: {avg_err:.1f} BPM")
