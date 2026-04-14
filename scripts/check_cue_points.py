"""Check cue_points data in database."""
from app.shared.database import SessionLocal
from app.modules.models import *  # noqa: load all models
from app.modules.library.models import LibrarySong

db = SessionLocal()
songs = db.query(LibrarySong).filter(LibrarySong.analysis_status == "completed").all()

print(f"Total completed songs: {len(songs)}\n")

# Categorize
good, bad, empty = [], [], []
for s in songs:
    cues = s.cue_points or []
    if len(cues) == 0:
        empty.append(s)
    elif len(cues) <= 1:
        bad.append(s)
    else:
        good.append(s)

print(f"Good cue points (2+ sections): {len(good)}")
print(f"Bad cue points (only 1 Intro): {len(bad)}")
print(f"Empty cue points: {len(empty)}")
print()

print("=== BAD (1 cue point only) ===")
for s in bad:
    print(f"  [{s.id[:8]}] {s.title[:35]:35s} BPM={s.bpm} dur={s.duration:.0f}s cues={s.cue_points}")

print()
print("=== EMPTY ===")
for s in empty:
    print(f"  [{s.id[:8]}] {s.title[:35]:35s} BPM={s.bpm} dur={s.duration:.0f}s")

print()
print("=== GOOD examples ===")
for s in good[:5]:
    cues = s.cue_points
    labels = [f"{c['label']}@{c['time']:.0f}s" for c in cues]
    print(f"  [{s.id[:8]}] {s.title[:35]:35s} BPM={s.bpm} -> {', '.join(labels)}")

# Check: any with time=0 only that have integer times (SSM) vs float times (energy fallback)
print()
print("=== CUE POINT TIME PATTERNS ===")
for s in good[:10]:
    cues = s.cue_points
    times = [c['time'] for c in cues]
    all_int = all(t == int(t) for t in times)
    print(f"  {s.title[:30]:30s} times={times} {'(all int - SSM)' if all_int else '(has floats - energy fallback)'}")

db.close()
