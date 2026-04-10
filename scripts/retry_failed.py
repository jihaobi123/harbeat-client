"""Try harder to download the 4+1 failed songs."""
import sys, os, asyncio
sys.path.insert(0, "/app")

from app.modules.fangpi.service import _kuwo_search, download_fangpi_song
from app.shared.database import SessionLocal
from app.modules.playlists.models import Song
from app.modules.library.models import LibrarySong

DEST = "/app/data/music-files/shared"

async def try_download(title, artist, alt_queries=None):
    queries = [f"{title} {artist}"]
    if alt_queries:
        queries.extend(alt_queries)
    
    for q in queries:
        print(f"  Trying search: '{q}'")
        results = await _kuwo_search(q)
        if results:
            for r in results[:3]:
                print(f"    [{r.get('id')}] {r.get('title')} - {r.get('artist')}")
            # Try downloading the first result with an ID
            for r in results:
                if r.get("id"):
                    print(f"  -> Downloading rid={r['id']}")
                    try:
                        result = await download_fangpi_song(
                            music_id=r["id"], title=title, artist=artist,
                            dest_dir=DEST, source="kuwo"
                        )
                        if result:
                            print(f"  OK: {result['file_size']/1024:.0f} KB -> {result['file_path']}")
                            return result
                    except Exception as e:
                        print(f"  Download failed: {e}")
                    break
        else:
            print("    No results")
    return None

async def main():
    db = SessionLocal()
    
    songs = [
        ("Not Shy", "ITZY", ["Not Shy ITZY", "낫 샤이"]),
        ("Cheshire", "ITZY", ["Cheshire ITZY", "있지 Cheshire"]),
        ("一路向北", "周杰伦", ["一路向北"]),
        ("C.R.E.A.M.", "Wu-Tang Clan", ["CREAM Wu-Tang", "C.R.E.A.M"]),
        ("Ms. Fat Booty", "Mos Def", ["Ms Fat Booty", "Fat Booty Mos Def"]),
    ]
    
    db = SessionLocal()
    
    for title, artist, alts in songs:
        print(f"\n=== {title} - {artist} ===")
        result = await try_download(title, artist, alts)
        
        if result:
            # Update DB for all copies
            all_copies = db.query(LibrarySong).filter(
                LibrarySong.title == title,
                LibrarySong.artist == artist,
            ).all()
            for copy in all_copies:
                copy.source_path = result["file_path"]
                copy.file_size = result["file_size"]
                if len(copy.cue_points or []) <= 1:
                    copy.analysis_status = "pending"
            db.commit()
            print(f"  Updated {len(all_copies)} DB records")
        else:
            print(f"  FAILED - song not available on Kuwo")
    
    db.close()

asyncio.run(main())
