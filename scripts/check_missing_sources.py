import sys, os
sys.path.insert(0, '/app')
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong

db = SessionLocal()
songs = db.query(LibrarySong).all()
missing = []
corrupt = []
ok = []
for s in songs:
    if not s.source_path:
        missing.append(s)
    elif not os.path.isfile(s.source_path):
        missing.append(s)
    elif os.path.getsize(s.source_path) < 1024:  # < 1KB likely corrupt
        corrupt.append(s)
    else:
        ok.append(s)

print(f"=== Total: {len(songs)}, OK: {len(ok)}, Missing/No source: {len(missing)}, Corrupt(<1KB): {len(corrupt)} ===\n")

if missing:
    print("--- Missing / No source file ---")
    for s in missing:
        print(f"  {s.title[:45]:45s} | {(s.artist or '')[:20]:20s} | path={s.source_path}")

if corrupt:
    print("\n--- Corrupt (< 1KB) ---")
    for s in corrupt:
        sz = os.path.getsize(s.source_path)
        print(f"  {s.title[:45]:45s} | {(s.artist or '')[:20]:20s} | size={sz}B | path={s.source_path}")

db.close()
