from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.playlists.models import Playlist, PlaylistSong

db = SessionLocal()
ps = db.query(Playlist).all()
print(f"Total playlists: {len(ps)}")
for p in ps:
    count = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == p.id).count()
    print(f"  id={p.id} user={p.user_id} name={p.playlist_name} songs={count}")
db.close()
