"""Re-analyze cue points for pending songs (after re-download).

These songs already have BPM/key/beats from before. We just need to
re-detect structure/cues using the new audio files, then set status back to completed.
"""
import sys, os
sys.path.insert(0, "/app")

from app.shared.database import SessionLocal
from app.modules.models import *  # noqa
from app.modules.library.models import LibrarySong
from app.modules.library.analysis import _detect_structure
import librosa

db = SessionLocal()
pending = db.query(LibrarySong).filter(
    LibrarySong.analysis_status == "pending",
).all()

# Filter to songs with files
pending_with_files = [s for s in pending if s.source_path and os.path.isfile(s.source_path)]
print(f"Pending songs: {len(pending)}, with files: {len(pending_with_files)}")

success = 0
failed = 0

for i, song in enumerate(pending_with_files):
    try:
        print(f"\n[{i+1}/{len(pending_with_files)}] {song.title} - {song.artist}")
        y, sr = librosa.load(song.source_path, sr=22050)
        duration = float(librosa.get_duration(y=y, sr=sr))

        new_cues = _detect_structure(y, sr, duration)
        song.cue_points = [
            {"id": f"cue-{song.id}-{j}", "time": c["time"], "label": c["label"], "color": c["color"]}
            for j, c in enumerate(new_cues)
        ]
        song.analysis_status = "completed"
        if not song.duration or abs(song.duration - duration) > 1:
            song.duration = duration
        db.commit()

        labels = [f"{c['label']}@{c['time']:.0f}s" for c in new_cues]
        print(f"  -> {len(new_cues)} cues: {', '.join(labels)}")
        success += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        song.analysis_status = "error"
        db.commit()
        failed += 1

print(f"\nDone! Success={success}, Failed={failed}")
db.close()
