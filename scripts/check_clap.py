"""Test CLAP audio embedding on a single file"""
import sys, os
sys.path.insert(0, '/app')
from app.modules.models import LibrarySong, Song
from app.shared.database import SessionLocal

db = SessionLocal()
ls = db.query(LibrarySong).filter(
    LibrarySong.source_path.isnot(None),
    LibrarySong.source_path != ""
).first()

if ls:
    print(f"Song: {ls.title} - {ls.artist}")
    print(f"Path: {ls.source_path}")
    print(f"song_id: {ls.song_id}")
    print(f"Exists: {os.path.isfile(ls.source_path)}")
else:
    print("No library song with source_path found")

# Count how many have valid files
all_ls = db.query(LibrarySong).filter(
    LibrarySong.source_path.isnot(None),
    LibrarySong.source_path != ""
).all()
valid = sum(1 for x in all_ls if os.path.isfile(x.source_path))
print(f"\nTotal with source_path: {len(all_ls)}")
print(f"Valid files on disk: {valid}")
db.close()
