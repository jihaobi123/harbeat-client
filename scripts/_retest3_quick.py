import sys
import os

sys.path.insert(0, '/app')

import librosa
from app.modules.library.beat_engine import analyze_beats

songs = [
    ("/app/data/music-files/shared/Hypnotize - The Notorious B.I.G..mp3", "Hypnotize", 94),
    ("/app/data/music-files/shared/God&#039;s Plan - Drake.mp3", "God's Plan", 77),
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3", "One B-Boy", 126),
]

print("=" * 78)
print("BPM RETEST (3 songs)")
print("=" * 78)

for path, title, ref in songs:
    if not os.path.exists(path):
        print(f"{title}: FILE NOT FOUND -> {path}")
        continue

    y, sr = librosa.load(path, sr=22050, mono=True)
    result = analyze_beats(path, y, sr, len(y) / sr)

    diff = result.bpm - ref
    if abs(diff) <= 3:
        mark = "OK"
    elif abs(diff) <= 8:
        mark = "CLOSE"
    else:
        mark = "OFF"

    raw = {
        k: round(v.get("bpm", v.get("bpm_beat_track", 0)), 2)
        for k, v in result.raw_results.items()
        if isinstance(v, dict)
    }

    print(f"\n{title}")
    print(f"  final={result.bpm:.1f}, ref={ref}, diff={diff:+.1f}, conf={result.confidence:.3f}, {mark}")
    print(f"  raw={raw}")

print("\nDone.")
