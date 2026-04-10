"""Quick test: playlist URL parsing + audio URL resolution."""
import asyncio
import sys
sys.path.insert(0, ".")

async def main():
    from app.modules.fangpi.playlist_parser import detect_platform, parse_playlist_url
    
    # Test 1: URL detection
    urls = [
        "https://music.163.com/playlist?id=25672837&uct2=U2FsdGVkX19q8S2WpfhZLBMuacPb8OPHVvXQMhLo/9A=",
        "https://c6.y.qq.com/base/fcgi-bin/u?__=BLW6bHdztqbb",
    ]
    for u in urls:
        platform, pid = detect_platform(u)
        print(f"[detect] {u[:60]}... => platform={platform}, id={pid[:40] if pid else 'NONE'}")
    
    # Test 2: Parse netease
    print("\n--- NetEase parse ---")
    try:
        result = await parse_playlist_url(urls[0])
        print(f"Name: {result['name']}, Tracks: {len(result['tracks'])}")
        if result['tracks']:
            for t in result['tracks'][:3]:
                print(f"  {t['title']} - {t['artist']}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Test 3: Parse QQ
    print("\n--- QQ Music parse ---")
    try:
        result = await parse_playlist_url(urls[1])
        print(f"Name: {result['name']}, Tracks: {len(result['tracks'])}")
        if result['tracks']:
            for t in result['tracks'][:3]:
                print(f"  {t['title']} - {t['artist']}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Test 4: Try downloading one song via fangpi/kuwo
    print("\n--- Audio URL test ---")
    from app.modules.fangpi.service import search_fangpi, _get_audio_url
    results = await search_fangpi("Dr. Dre Nuthin But A G Thang")
    if results:
        r = results[0]
        print(f"Search result: {r['title']} - {r['artist']} (id={r['id']}, source={r['source']})")
        try:
            url = await _get_audio_url(r['id'], r['source'], title=r['title'], artist=r['artist'])
            print(f"Audio URL: {url[:80]}...")
        except Exception as e:
            print(f"Audio URL ERROR: {e}")
    else:
        print("No search results")

asyncio.run(main())
