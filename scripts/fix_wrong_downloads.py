"""Fix wrongly downloaded songs and analyze correctly downloaded ones."""
import sys, os, asyncio
sys.path.insert(0, "/app")

from app.shared.database import SessionLocal
from app.modules.playlists.models import Song
from app.modules.library.models import LibrarySong

db = SessionLocal()

# 1. Revert the 3 wrong downloads
wrong_songs = [
    ("Not Shy", "ITZY"),
    ("Cheshire", "ITZY"),
    ("C.R.E.A.M.", "Wu-Tang Clan"),
]

print("=== Reverting wrong downloads ===")
for title, artist in wrong_songs:
    copies = db.query(LibrarySong).filter(
        LibrarySong.title == title,
        LibrarySong.artist == artist,
    ).all()
    for c in copies:
        # Delete wrong file if exists
        if c.source_path and os.path.isfile(c.source_path):
            print(f"  Deleting wrong file: {c.source_path}")
            os.remove(c.source_path)
        c.source_path = ""
        c.file_size = 0
        # Keep analysis_status as completed (the analysis data from before is correct)
        if c.analysis_status == "pending":
            c.analysis_status = "completed"
    print(f"  Reverted {len(copies)} records for {title} - {artist}")
db.commit()

# 2. Analyze newly correctly downloaded songs
print("\n=== Analyzing correctly downloaded songs ===")
correct_songs = [
    ("一路向北", "周杰伦"),
    ("Ms. Fat Booty", "Mos Def"),
]

from app.modules.library.analysis import _detect_structure
import librosa

for title, artist in correct_songs:
    copies = db.query(LibrarySong).filter(
        LibrarySong.title == title,
        LibrarySong.artist == artist,
    ).all()
    for c in copies:
        if not c.source_path or not os.path.isfile(c.source_path):
            print(f"  {title} - no file, skip")
            continue
        if len(c.cue_points or []) > 1 and c.analysis_status == "completed":
            print(f"  {title} ({c.id[:8]}) - already has {len(c.cue_points)} cues, skip")
            continue
        try:
            print(f"  Analyzing {title} ({c.id[:8]})...")
            y, sr = librosa.load(c.source_path, sr=22050)
            duration = float(librosa.get_duration(y=y, sr=sr))
            new_cues = _detect_structure(y, sr, duration)
            c.cue_points = [
                {"id": f"cue-{c.id}-{j}", "time": cu["time"], "label": cu["label"], "color": cu["color"]}
                for j, cu in enumerate(new_cues)
            ]
            c.analysis_status = "completed"
            if not c.duration or abs(c.duration - duration) > 1:
                c.duration = duration
            db.commit()
            labels = [f"{cu['label']}@{cu['time']:.0f}s" for cu in new_cues]
            print(f"    -> {len(new_cues)} cues: {', '.join(labels)}")
        except Exception as e:
            print(f"    -> FAILED: {e}")

db.close()
print("\nDone!")
