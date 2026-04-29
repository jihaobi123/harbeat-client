"""Check song files and analysis status in detail."""
import sys, os
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song

db = SessionLocal()
pending = db.query(LibrarySong).filter(
    LibrarySong.analysis_status.in_(["pending", "none", "analyzing"])
).all()

print(f"Found {len(pending)} non-completed songs:\n")
for s in pending:
    has_file = os.path.isfile(s.source_path) if s.source_path else False
    print(f"  [{s.analysis_status}] {s.title} - {s.artist}")
    print(f"    source_path: {s.source_path}")
    print(f"    file_exists: {has_file}")
    print(f"    bpm={s.bpm}, key={s.key}, song_id={s.song_id}")
    print()
db.close()
