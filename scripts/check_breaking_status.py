import sys
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import PlaylistSong, Song

db = SessionLocal()
ps_list = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == 8).all()
song_ids = [ps.song_id for ps in ps_list]
songs = db.query(Song).filter(Song.id.in_(song_ids)).all()
sm = {s.id: s for s in songs}
ls_list = db.query(LibrarySong).filter(LibrarySong.song_id.in_(song_ids)).all()
c = 0
for ls in ls_list:
    s = sm.get(ls.song_id)
    t = s.title[:35] if s else "?"
    st = ls.analysis_status or "none"
    if st == "completed": c += 1
    print(f"{st:12s} bpm={str(ls.bpm):>6s} stems={bool(ls.stems)} {t}")
print(f"\nDone: {c}/{len(ls_list)}")
db.close()
