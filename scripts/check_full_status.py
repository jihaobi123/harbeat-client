"""Quick status check: stem separation + ChromaDB."""
import os
import sys

sys.path.insert(0, "/app")

from app.shared.database import SessionLocal
from app.modules.models import *  # noqa: register all models
from app.modules.library.models import LibrarySong

db = SessionLocal()
all_songs = db.query(LibrarySong).filter(
    LibrarySong.source_path.isnot(None),
    LibrarySong.source_path != ""
).all()

total = 0
has_stems = 0
no_stems = 0
missing_file = 0

for s in all_songs:
    if not os.path.isfile(s.source_path):
        missing_file += 1
        continue
    total += 1
    if s.stems and all(os.path.isfile(v) for v in s.stems.values()):
        has_stems += 1
    else:
        no_stems += 1

print(f"=== Stem Separation ===")
print(f"Total songs (with file): {total}")
print(f"Stems done: {has_stems}")
print(f"Stems pending: {no_stems}")
print(f"File missing: {missing_file}")

# BPM/Key analysis status
no_bpm = db.query(LibrarySong).filter(
    LibrarySong.source_path.isnot(None),
    LibrarySong.source_path != "",
    LibrarySong.bpm.is_(None),
).count()
print(f"BPM pending: {no_bpm}")

print()
print("=== ChromaDB ===")
try:
    import chromadb
    client = chromadb.PersistentClient(path="./data/chroma_db")
    cols = client.list_collections()
    if cols:
        for col in cols:
            c = client.get_collection(col.name)
            print(f"  {col.name}: {c.count()} items")
    else:
        print("  No collections (not initialized)")
except Exception as e:
    print(f"  Error: {e}")

db.close()
