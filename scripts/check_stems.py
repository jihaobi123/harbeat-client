"""Check stems status for all songs."""
import sys, os
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song  # needed for FK resolution

db = SessionLocal()
all_songs = db.query(LibrarySong).all()
total = len(all_songs)
no_stems = [s for s in all_songs if not s.stems]
completed = [s for s in all_songs if s.analysis_status == "completed"]
pending = [s for s in all_songs if s.analysis_status in ("pending", "none")]
analyzing = [s for s in all_songs if s.analysis_status == "analyzing"]
error = [s for s in all_songs if s.analysis_status == "error"]

print(f"Total: {total}")
print(f"Completed: {len(completed)}")
print(f"Pending: {len(pending)}")
print(f"Analyzing: {len(analyzing)}")
print(f"Error: {len(error)}")
print(f"No stems: {len(no_stems)}")
print()

print("=== Songs without stems ===")
for s in no_stems:
    has_file = "FILE_OK" if s.source_path and os.path.isfile(s.source_path) else "NO_FILE"
    # Check if stem files actually exist on disk
    stem_dir = ""
    stems_exist = False
    if s.source_path and os.path.isfile(s.source_path):
        base = os.path.splitext(os.path.basename(s.source_path))[0]
        stem_dir = os.path.join(os.path.dirname(os.path.abspath(s.source_path)), "..", "stems", "htdemucs", base)
        stem_dir = os.path.abspath(stem_dir)
        stems_exist = all(os.path.isfile(os.path.join(stem_dir, f"{n}.wav")) for n in ["vocals","drums","bass","other"])
    print(f"  [{s.analysis_status:10s}] {s.title[:40]:40s} | {has_file} | disk_stems={'YES' if stems_exist else 'NO'}")

print()
print("=== Songs WITH stems in DB but check disk ===")
with_stems = [s for s in all_songs if s.stems]
missing_disk = 0
for s in with_stems:
    if s.stems:
        all_ok = all(os.path.isfile(p) for p in s.stems.values())
        if not all_ok:
            missing_disk += 1
            print(f"  [{s.analysis_status}] {s.title[:40]} | stems in DB but files MISSING on disk")
if missing_disk == 0:
    print(f"  All {len(with_stems)} songs with stems have files on disk OK")

db.close()
