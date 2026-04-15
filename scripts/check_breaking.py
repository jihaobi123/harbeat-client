"""Check breaking playlist status and list songs needing re-analysis."""
import sys, os
sys.path.insert(0, "/app")
os.environ.setdefault("DATABASE_URL", "")

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong

db = SessionLocal()

# Find breaking playlist
playlists = db.query(Playlist).filter(Playlist.name.ilike("%breaking%")).all()
for pl in playlists:
    print(f"Playlist: {pl.name} (id={pl.id})")
    items = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == pl.id).order_by(PlaylistSong.position).all()
    print(f"  Songs: {len(items)}")
    for item in items:
        song = db.query(LibrarySong).filter(LibrarySong.id == item.song_id).first()
        if song:
            has_src = bool(song.source_path and os.path.isfile(song.source_path))
            has_stems = bool(song.stems)
            stems_exist = False
            if has_stems:
                stems_exist = all(os.path.isfile(v) for v in song.stems.values())
            print(f"  [{song.analysis_status or 'none':10s}] {song.title[:40]:40s} src={has_src} stems_db={has_stems} stems_disk={stems_exist} bpm={song.bpm}")

db.close()
