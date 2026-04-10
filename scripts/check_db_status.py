"""Check DB status + retrigger pending analysis."""
import os, sys
sys.path.insert(0, "/app")
from app.modules.models import *  # noqa
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong

db = SessionLocal()
songs = db.query(LibrarySong).all()
print(f"Total songs: {len(songs)}")

counts = {}
for s in songs:
    st = s.analysis_status or "none"
    counts[st] = counts.get(st, 0) + 1
print(f"Status distribution: {counts}")

# Show first few unanalyzed
need_analysis = [s for s in songs if s.bpm is None and s.source_path and os.path.isfile(s.source_path)]
print(f"\nNeed analysis (bpm=None, file exists): {len(need_analysis)}")
for s in need_analysis[:5]:
    print(f"  {s.title} - {s.artist} | status={s.analysis_status} | path={s.source_path}")

# Reset stuck 'error'/'analyzing' back to 'none' so startup scheduler picks them up
reset_count = 0
for s in songs:
    if s.analysis_status in ("error", "analyzing") and s.source_path and os.path.isfile(s.source_path):
        s.analysis_status = "none"
        reset_count += 1
if reset_count > 0:
    db.commit()
    print(f"\nReset {reset_count} stuck songs back to 'none'")

db.close()
print("\nDone!")
