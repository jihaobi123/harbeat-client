import sys, os
sys.path.insert(0, "/app")
from app.shared.database import SessionLocal
from app.modules.models import *
from app.modules.library.models import LibrarySong

db = SessionLocal()

# Check CLAP in ChromaDB
try:
    from app.modules.recommendations.vector_store import get_collection_stats, COLLECTION_CLAP, COLLECTION_TEXT
    stats_clap = get_collection_stats(COLLECTION_CLAP)
    print(f"ChromaDB CLAP audio: {stats_clap}")
except Exception as e:
    print(f"CLAP stats error: {e}")

try:
    stats_text = get_collection_stats(COLLECTION_TEXT)
    print(f"ChromaDB text:       {stats_text}")
except Exception as e:
    print(f"Text stats error: {e}")

# Check which songs are missing from ChromaDB
try:
    from app.modules.recommendations.vector_store import get_clap_collection
    col = get_clap_collection()
    clap_ids = set(col.get()["ids"])
    all_lib = db.query(LibrarySong).all()
    missing_clap = []
    for s in all_lib:
        if s.song_id and str(s.song_id) not in clap_ids:
            missing_clap.append(f"{s.title} - {s.artist} (song_id={s.song_id})")
        elif not s.song_id:
            missing_clap.append(f"{s.title} - {s.artist} (NO song_id)")
    if missing_clap:
        print(f"\n=== {len(missing_clap)} songs missing from CLAP ChromaDB ===")
        for t in missing_clap:
            print(f"  {t}")
    else:
        print("\nAll songs have CLAP embeddings")
except Exception as e:
    print(f"CLAP check error: {e}")

# Song without stems in DB
no_stems = [s for s in db.query(LibrarySong).all() if not s.stems]
if no_stems:
    print(f"\nSongs without stems in DB ({len(no_stems)}):")
    for s in no_stems:
        base = os.path.splitext(os.path.basename(s.source_path))[0] if s.source_path else "?"
        stems_dir = os.path.abspath(os.path.join(os.path.dirname(s.source_path), "..", "stems", "htdemucs", base)) if s.source_path else "?"
        on_disk = all(os.path.isfile(os.path.join(stems_dir, f"{sn}.wav")) for sn in ["vocals","drums","bass","other"]) if s.source_path else False
        print(f"  {s.title} - {s.artist} | status={s.analysis_status} | stems_on_disk={on_disk}")
else:
    print("\nAll songs have stems in DB")
db.close()
