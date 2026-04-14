"""Quick status check"""
import sys
sys.path.insert(0, '/app')
from app.shared.database import SessionLocal
from app.modules.models import LibrarySong

db = SessionLocal()
total = db.query(LibrarySong).count()
stems_done = db.query(LibrarySong).filter(LibrarySong.stems.isnot(None)).count()
analysis_done = db.query(LibrarySong).filter(LibrarySong.analysis_status == "completed").count()
analysis_pending = db.query(LibrarySong).filter(LibrarySong.analysis_status != "completed").count()
bpm_done = db.query(LibrarySong).filter(LibrarySong.bpm.isnot(None)).count()
print(f"Total library songs: {total}")
print(f"BPM analyzed: {bpm_done}/{total}")
print(f"Stems done: {stems_done}/{total}")
print(f"Analysis completed: {analysis_done}/{total}")
print(f"Analysis pending: {analysis_pending}/{total}")
db.close()
