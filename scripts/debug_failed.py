"""Try to debug the 4 failed downloads."""
import sys, os, asyncio
sys.path.insert(0, "/app")

from app.modules.fangpi.service import _kuwo_search

async def main():
    songs = [
        ("Not Shy", "ITZY"),
        ("Cheshire", "ITZY"),
        ("一路向北", "周杰伦"),
        ("C.R.E.A.M.", "Wu-Tang Clan"),
        ("Ms. Fat Booty", "Mos Def"),
    ]
    for title, artist in songs:
        query = f"{title} {artist}"
        print(f"\n=== Searching: {query} ===")
        try:
            results = await _kuwo_search(query)
            if results:
                for r in results[:3]:
                    print(f"  rid={r.get('rid')} | {r.get('name')} - {r.get('artist')} | pay={r.get('isListenFee', '?')}")
            else:
                print("  No results")
        except Exception as e:
            print(f"  Error: {e}")

asyncio.run(main())
