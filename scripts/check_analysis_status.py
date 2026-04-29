"""Check analysis completion status for all library songs."""
import os, sys
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong

db = SessionLocal()
all_songs = db.query(LibrarySong).all()
total = len(all_songs)

has_bpm = sum(1 for s in all_songs if s.bpm is not None)
has_key = sum(1 for s in all_songs if s.key is not None)
has_stems = sum(1 for s in all_songs if s.stems)
has_file = sum(1 for s in all_songs if s.source_path and os.path.isfile(s.source_path))
completed = sum(1 for s in all_songs if s.analysis_status == "completed")
error = sum(1 for s in all_songs if s.analysis_status == "error")
pending = sum(1 for s in all_songs if s.analysis_status in ("pending", "none", "analyzing"))

stem_names = ["vocals", "drums", "bass", "other"]
stems_on_disk = 0
missing_stems = []
for s in all_songs:
    if not s.source_path:
        continue
    base = os.path.splitext(os.path.basename(s.source_path))[0]
    stems_dir = os.path.abspath(os.path.join(os.path.dirname(s.source_path), "..", "stems", "htdemucs", base))
    if all(os.path.isfile(os.path.join(stems_dir, f"{sn}.wav")) for sn in stem_names):
        stems_on_disk += 1
    else:
        missing_stems.append(f"{s.title} - {s.artist}")

print(f"=== Analysis Status ===")
print(f"Total songs:      {total}")
print(f"Has source file:  {has_file}")
print(f"Has BPM:          {has_bpm}")
print(f"Has Key:          {has_key}")
print(f"Has stems (DB):   {has_stems}")
print(f"Stems on disk:    {stems_on_disk}")
print(f"Status completed: {completed}")
print(f"Status error:     {error}")
print(f"Status pending:   {pending}")
if missing_stems:
    print(f"\n=== {len(missing_stems)} songs missing stems ===")
    for t in missing_stems:
        print(f"  {t}")
no_analysis = [f"{s.title} - {s.artist} (status={s.analysis_status})" for s in all_songs if s.bpm is None]
if no_analysis:
    print(f"\n=== {len(no_analysis)} songs without BPM ===")
    for t in no_analysis:
        print(f"  {t}")
db.close()
