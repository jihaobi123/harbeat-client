"""Check breaking playlist and re-analyze all songs."""
import sys, os, gc, ctypes, subprocess, shutil
sys.path.insert(0, "/app")

from app.shared.config import get_settings
from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong

db = SessionLocal()

# Find breaking playlist
playlists = db.query(Playlist).filter(Playlist.name.ilike("%breaking%")).all()
if not playlists:
    print("No breaking playlist found!")
    sys.exit(1)

pl = playlists[0]
print(f"Playlist: {pl.name} (id={pl.id})")

items = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == pl.id).order_by(PlaylistSong.position).all()
song_ids = [item.song_id for item in items]
songs = db.query(LibrarySong).filter(LibrarySong.id.in_(song_ids)).all()

print(f"Total songs: {len(songs)}\n")

for song in songs:
    has_src = bool(song.source_path and os.path.isfile(song.source_path))
    has_stems = bool(song.stems)
    stems_disk = False
    if has_stems:
        stems_disk = all(os.path.isfile(v) for v in song.stems.values())
    status = song.analysis_status or "none"
    print(f"  [{status:10s}] {song.title[:45]:45s} src={has_src} stems={has_stems}/{stems_disk} bpm={song.bpm}")

db.close()
