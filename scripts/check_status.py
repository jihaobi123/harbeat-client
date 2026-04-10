"""Quick check of song status after re-download."""
import os, sys
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.models import *  # noqa: load all models
from app.modules.library.models import LibrarySong

db = SessionLocal()
all_songs = db.query(LibrarySong).all()

# Count by status
statuses = {}
for s in all_songs:
    statuses[s.analysis_status] = statuses.get(s.analysis_status, 0) + 1
print("=== Status counts ===")
for k, v in sorted(statuses.items()):
    print(f"  {k}: {v}")

# Check pending songs
pending = [s for s in all_songs if s.analysis_status == "pending"]
print(f"\n=== Pending re-analysis ({len(pending)}) ===")
for s in pending:
    has_file = os.path.isfile(s.source_path) if s.source_path else False
    cues = len(s.cue_points or [])
    print(f"  [{s.id}] {s.title} - {s.artist} | file={has_file} | cues={cues}")

# Check still-missing files
missing = [s for s in all_songs if not s.source_path or not os.path.isfile(s.source_path)]
print(f"\n=== Still missing files ({len(missing)}) ===")
for s in missing:
    print(f"  [{s.id}] {s.title} - {s.artist} | status={s.analysis_status}")

db.close()
