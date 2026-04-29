"""Check analysis status of recently added songs."""
import sys
sys.path.insert(0, '/app')

from app.shared.database import SessionLocal
from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Song, SongTag

db = SessionLocal()

songs = db.query(LibrarySong).order_by(LibrarySong.id.desc()).limit(15).all()
for s in songs:
    tag = db.query(SongTag).filter(SongTag.song_id == s.song_id).first() if s.song_id else None
    print(f"ID={s.id} | song_id={s.song_id} | {s.title} - {s.artist}")
    print(f"  status={s.analysis_status} | bpm={s.bpm} | key={s.key} | energy={s.energy}")
    has_file = bool(s.source_path)
    print(f"  file={'YES' if has_file else 'NO'} ({s.source_path}) | size={s.file_size}")
    print(f"  stems={bool(s.stems)} | beats={bool(s.beat_points)} | cues={bool(s.cue_points)}")
    if tag:
        print(f"  tag: style={tag.style} energy={tag.energy} groove={tag.groove_tag} bpm={tag.bpm}")
    print()

# CLAP stats
from app.modules.recommendations.vector_store import get_clap_collection
clap = get_clap_collection()
print(f"CLAP vector store count: {clap.count()}")

db.close()
