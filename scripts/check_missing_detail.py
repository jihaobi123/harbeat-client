"""Check details of songs with missing source files."""
import sys
sys.path.insert(0, "/app")

from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong
import os

db = SessionLocal()
missing = db.query(LibrarySong).filter(
    (LibrarySong.source_path == None) | (LibrarySong.source_path == "")
).all()

# Also check for files that don't exist on disk
all_songs = db.query(LibrarySong).filter(
    LibrarySong.source_path != None, LibrarySong.source_path != ""
).all()
for s in all_songs:
    if not os.path.isfile(s.source_path):
        missing.append(s)

print(f"=== {len(missing)} songs with missing/nonexistent source ===")
for s in missing:
    print(f"id={s.id}")
    print(f"  title={s.title}")
    print(f"  artist={s.artist}")
    print(f"  platform_id={s.platform_id}")
    print(f"  source_type={s.source_type}")
    print(f"  source_path={repr(s.source_path)}")
    exists = os.path.isfile(s.source_path) if s.source_path else False
    print(f"  file_exists={exists}")
    print()

# Summary
total = db.query(LibrarySong).count()
ok = total - len(missing)
print(f"=== Total: {total}, OK: {ok}, Missing: {len(missing)} ===")
db.close()
