"""Check duplicate songs across users."""
import sys, os
sys.path.insert(0, "/app")
from collections import Counter
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong

db = SessionLocal()
all_songs = db.query(LibrarySong).all()

# Group by song_id
by_song_id = {}
for s in all_songs:
    key = s.song_id or f"NO_SONGID_{s.id}"
    by_song_id.setdefault(key, []).append(s)

# Group by source_path (file-level dedup)
by_path = {}
for s in all_songs:
    if s.source_path:
        by_path.setdefault(s.source_path, []).append(s)

print(f"=== Overview ===")
print(f"Total LibrarySong rows: {len(all_songs)}")
print(f"Unique song_id:         {len([k for k in by_song_id if not str(k).startswith('NO_SONGID')])}")
print(f"Unique source_path:     {len(by_path)}")

# Show user distribution
users = Counter(s.user_id for s in all_songs)
print(f"\nUsers: {dict(users)}")

# Show duplicates (same song_id, multiple users)
dups = {k: v for k, v in by_song_id.items() if len(v) > 1}
if dups:
    print(f"\n=== {len(dups)} songs shared across users ===")
    for sid, entries in sorted(dups.items(), key=lambda x: -len(x[1])):
        title = entries[0].title
        artist = entries[0].artist
        user_ids = [e.user_id for e in entries]
        paths = set(e.source_path for e in entries)
        same_file = len(paths) == 1
        print(f"  {title} - {artist} | users={user_ids} | same_file={same_file}")
        if not same_file:
            for e in entries:
                print(f"    user={e.user_id} path={e.source_path}")

# Check files stored more than once on disk
dup_files = {k: v for k, v in by_path.items() if len(v) > 1}
print(f"\n=== File-level sharing ===")
print(f"Files shared by >1 LibrarySong: {len(dup_files)}")
print(f"Files used by only 1 entry:     {len(by_path) - len(dup_files)}")

db.close()
