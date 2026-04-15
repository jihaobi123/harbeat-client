import sys, os
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong

db = SessionLocal()
s = db.query(LibrarySong).filter(LibrarySong.title == "Not Shy", LibrarySong.artist == "ITZY").first()
if s and s.source_path:
    base = os.path.splitext(os.path.basename(s.source_path))[0]
    sd = os.path.abspath(os.path.join(os.path.dirname(s.source_path), "..", "stems", "htdemucs", base))
    stems = {n: os.path.join(sd, n + ".wav") for n in ["vocals", "drums", "bass", "other"]}
    if all(os.path.isfile(v) for v in stems.values()):
        s.stems = stems
        db.commit()
        print(f"Fixed: Not Shy stems updated in DB -> {sd}")
    else:
        print("Stems files not found on disk")
else:
    print("Song not found or no source_path")
db.close()
