"""Re-analyze cue points for songs that only have 1 Intro cue.

Uses the updated _detect_structure() with energy fallback.
Only updates cue_points field - does NOT re-run full analysis or stem separation.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__) if os.path.dirname(__file__) else ".")

from app.shared.database import SessionLocal
from app.modules.models import *  # noqa
from app.modules.library.models import LibrarySong

db = SessionLocal()

songs = db.query(LibrarySong).filter(
    LibrarySong.analysis_status == "completed",
    LibrarySong.bpm.isnot(None),
).all()

bad_songs = [s for s in songs if len(s.cue_points or []) <= 1 and s.source_path and os.path.isfile(s.source_path)]
print(f"Total completed songs: {len(songs)}")
print(f"Songs needing cue re-analysis: {len(bad_songs)}")

if not bad_songs:
    print("Nothing to do!")
    db.close()
    sys.exit(0)

# Import analysis function
from app.modules.library.analysis import _detect_structure
import librosa
import numpy as np

success = 0
failed = 0

for i, song in enumerate(bad_songs):
    try:
        print(f"\n[{i+1}/{len(bad_songs)}] {song.title} ({song.id[:8]}...) dur={song.duration:.0f}s")
        y, sr = librosa.load(song.source_path, sr=22050)
        duration = float(librosa.get_duration(y=y, sr=sr))

        new_cues = _detect_structure(y, sr, duration)
        # Add IDs
        song.cue_points = [
            {"id": f"cue-{song.id}-{j}", "time": c["time"], "label": c["label"], "color": c["color"]}
            for j, c in enumerate(new_cues)
        ]
        db.commit()
        labels = [f"{c['label']}@{c['time']:.0f}s" for c in new_cues]
        print(f"  -> {len(new_cues)} cues: {', '.join(labels)}")
        success += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        failed += 1

print(f"\nDone! Success={success}, Failed={failed}")
db.close()
