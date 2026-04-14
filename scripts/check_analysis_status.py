import sys, os
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song

db = SessionLocal()
songs = db.query(LibrarySong).all()
status_counts = {}
for s in songs:
    status_counts[s.analysis_status] = status_counts.get(s.analysis_status, 0) + 1
print("Status counts:", status_counts)
pending = [s for s in songs if s.analysis_status in ("pending", "analyzing", "none")]
for s in pending[:15]:
    print("  %s: %s (bpm=%s, key=%s)" % (s.analysis_status, s.title, s.bpm, s.key))
db.close()
