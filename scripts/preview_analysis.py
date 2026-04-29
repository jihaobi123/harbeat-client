import sys, os
sys.path.insert(0, '/app')
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong
db = SessionLocal()
songs = db.query(LibrarySong).filter(LibrarySong.source_path.isnot(None)).all()
todo = 0
done = 0
for s in songs:
    has_src = bool(s.source_path and os.path.isfile(s.source_path))
    if not has_src:
        continue
    ok = (s.analysis_status == 'completed' and s.bpm and s.stems
          and all(os.path.isfile(v) for v in (s.stems or {}).values()))
    if ok:
        done += 1
    else:
        todo += 1
        print(f'TODO: {s.title[:40]:40s} status={s.analysis_status} bpm={s.bpm} stems={bool(s.stems)}')
print(f'\nDone: {done}, TODO: {todo}')
db.close()
