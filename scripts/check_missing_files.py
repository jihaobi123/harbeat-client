"""Check which songs have missing files."""
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong
import os

db = SessionLocal()
songs = db.query(LibrarySong).filter(
    LibrarySong.analysis_status == "completed",
).all()

bad_cue = [s for s in songs if len(s.cue_points or []) <= 1]
print(f"Songs with <=1 cue: {len(bad_cue)}")
for s in bad_cue:
    exists = os.path.isfile(s.source_path) if s.source_path else False
    print(f"  [{s.id[:8]}] user={s.user_id} {s.title[:30]:30s} file_exists={exists} path={s.source_path}")
db.close()
