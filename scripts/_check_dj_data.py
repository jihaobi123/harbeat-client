"""Check DJ Session data for user qqq - diagnose why playlists show no playable songs."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong, Song
from app.modules.users.models import User

db = SessionLocal()

u = db.query(User).filter(User.username == "qqq").first()
if not u:
    print("User qqq not found")
    sys.exit(1)
print(f"User: id={u.id} username={u.username}")

# Check playlists
playlists = db.query(Playlist).filter(Playlist.user_id == u.id).all()
for p in playlists:
    ps_list = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == p.id).all()
    print(f"\nPlaylist: id={p.id} name='{p.name}' songs={len(ps_list)}")
    for ps in ps_list[:3]:
        song = db.get(Song, ps.song_id)
        if song:
            print(f"  Song: id={song.id} title='{song.title}' artist='{song.artist}' audio_url='{song.audio_url}' exists={os.path.isfile(song.audio_url) if song.audio_url else False}")
            # Check LibrarySong link
            lib = db.query(LibrarySong).filter(
                LibrarySong.user_id == u.id,
                LibrarySong.song_id == song.id
            ).first()
            if lib:
                print(f"    LibrarySong: id={lib.id} source_path='{lib.source_path}' exists={os.path.isfile(lib.source_path) if lib.source_path else False}")
            else:
                # Try by title+artist
                lib2 = db.query(LibrarySong).filter(
                    LibrarySong.user_id == u.id,
                    LibrarySong.title == song.title,
                    LibrarySong.artist == song.artist
                ).first()
                if lib2:
                    print(f"    LibrarySong (by title): id={lib2.id} source_path='{lib2.source_path}' exists={os.path.isfile(lib2.source_path) if lib2.source_path else False} song_id={lib2.song_id}")
                else:
                    print(f"    NO LibrarySong found for user {u.id}")

# Check overall LibrarySong stats
total_lib = db.query(LibrarySong).filter(LibrarySong.user_id == u.id).count()
with_path = db.query(LibrarySong).filter(
    LibrarySong.user_id == u.id,
    LibrarySong.source_path.isnot(None),
    LibrarySong.source_path != ""
).all()
exists_count = sum(1 for l in with_path if l.source_path and os.path.isfile(l.source_path))
print(f"\nLibrarySong stats: total={total_lib} with_path={len(with_path)} files_exist={exists_count}")
if with_path and exists_count == 0:
    # show sample paths
    for l in with_path[:5]:
        print(f"  path='{l.source_path}' exists={os.path.isfile(l.source_path) if l.source_path else False}")
