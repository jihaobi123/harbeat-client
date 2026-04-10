"""End-to-end test: simulate full playlist import flow (search -> audio URL -> download)."""
import asyncio
import json
import os
import re
import sys
import tempfile

import httpx

_UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_UA_MOBILE = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36"
_UA_DOWNLOAD = "okhttp/3.10.0"
_FANGPI_BASE = "https://www.fangpi.net"
_MIN_REAL_FILE_SIZE = 200_000


def _clean_html(s):
    return (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&apos;", "'")
             .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
             .replace("\\u0026", "&").replace("\\\\u0026", "&").replace("&#039;", "'"))


# ---- Step 1: Fangpi search (fixed) ----
async def fangpi_search(query):
    clean_query = re.sub(r'[./"\\]', ' ', query.strip())
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()
    if not clean_query:
        return []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            r1 = await client.post(f"{_FANGPI_BASE}/api/s", data={"keyword": clean_query},
                headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"})
            if r1.status_code >= 500:
                return []
            search_path = None
            try:
                body = r1.json()
                if body.get("code") == 1 and body.get("data", {}).get("u"):
                    search_path = body["data"]["u"]
            except:
                pass
            if search_path:
                search_url = f"{_FANGPI_BASE}{search_path}"
            else:
                from urllib.parse import quote
                search_url = f"{_FANGPI_BASE}/s/{quote(clean_query, safe='')}"
            resp = await client.get(search_url, headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"})
            if resp.status_code >= 400:
                return []
    except Exception as e:
        print(f"    [fangpi search error] {e}")
        return []
    results = []
    seen = set()
    for m in re.finditer(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', resp.text, re.DOTALL):
        mid = m.group(1)
        if mid in seen: continue
        seen.add(mid)
        full_title = _clean_html(m.group(2)).strip()
        parts = full_title.split(" - ", 1)
        results.append({"id": mid, "title": parts[0].strip(), "artist": parts[1].strip() if len(parts)>1 else "", "source": "fangpi"})
    return results


# ---- Step 2: Kuwo search ----
async def kuwo_search(query):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get("https://search.kuwo.cn/r.s",
                params={"ft": "music", "rformat": "json", "encoding": "utf8", "rn": "20", "pn": "0", "all": query},
                headers={"User-Agent": _UA_MOBILE, "Referer": "https://m.kuwo.cn/"})
        ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", resp.text)
        names = re.findall(r"['\"]NAME['\"]\s*:\s*['\"]([^'\"]*)['\"]", resp.text)
        artists = re.findall(r"['\"]ARTIST['\"]\s*:\s*['\"]([^'\"]*)['\"]", resp.text)
        return [{"id": ids[i], "title": _clean_html(names[i] if i<len(names) else ""), 
                 "artist": _clean_html(artists[i] if i<len(artists) else ""), "source": "kuwo"} for i in range(len(ids))]
    except Exception as e:
        print(f"    [kuwo search error] {e}")
        return []


# ---- Step 3: Get fangpi audio URL ----
async def fangpi_get_audio_url(music_id):
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        resp = await client.get(f"{_FANGPI_BASE}/music/{music_id}",
            headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/"})
        print(f"    [fangpi page] status={resp.status_code}")
        if resp.status_code >= 400:
            raise ValueError(f"fangpi page status {resp.status_code}")
        
        m = re.search(r"window\.appData\s*=\s*JSON\.parse\('(.+?)'\)", resp.text)
        if not m:
            # Try alternative pattern
            m2 = re.search(r"window\.appData\s*=\s*(\{.+?\})\s*;", resp.text)
            if m2:
                print(f"    [fangpi] found appData via alt pattern")
            else:
                # Show what we actually got
                snippets = [resp.text[max(0,i-30):i+50] for i in [m.start() for m in re.finditer(r'window\.', resp.text)]]
                print(f"    [fangpi] window.* patterns found: {len(snippets)}")
                for s in snippets[:3]:
                    print(f"      {s[:80]}")
                raise ValueError("cannot find window.appData")
        
        raw = m.group(1).encode("utf-8").decode("unicode_escape")
        data = json.loads(raw)
        play_id = data.get("play_id", "")
        print(f"    [fangpi] play_id={play_id}")
        if not play_id:
            raise ValueError("play_id is empty")
        
        r2 = await client.post(f"{_FANGPI_BASE}/api/play-url", data={"id": play_id},
            headers={"User-Agent": _UA_BROWSER, "Referer": f"{_FANGPI_BASE}/music/{music_id}"})
        print(f"    [fangpi play-url] status={r2.status_code}, body={r2.text[:200]}")
        body = r2.json()
        if body.get("code") == 1 and body.get("data", {}).get("url"):
            return body["data"]["url"]
        raise ValueError(f"play-url failed: {r2.text[:200]}")


# ---- Step 4: Get kuwo audio URL ----
async def kuwo_get_audio_url(music_id):
    async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
        resp = await client.get(
            f"https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid={music_id}&format=mp3&response=url",
            headers={"User-Agent": _UA_DOWNLOAD})
        print(f"    [kuwo audio] status={resp.status_code}, body={resp.text[:200]}")
        try:
            body = resp.json()
            url = body.get("url", "")
            if url:
                return url
        except:
            url = resp.text.strip()
            if url.startswith("http"):
                return url
    raise ValueError("kuwo: no audio URL")


# ---- Step 5: Download file ----
async def download_file(audio_url):
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        resp = await client.get(audio_url, headers={"User-Agent": _UA_DOWNLOAD})
        print(f"    [download] status={resp.status_code}, content_length={len(resp.content)}, content_type={resp.headers.get('content-type','?')}")
        if len(resp.content) < _MIN_REAL_FILE_SIZE:
            raise ValueError(f"file too small: {len(resp.content)} bytes")
        return len(resp.content)


# ---- Title matching ----
def _normalize_title(t):
    t = t.lower().strip()
    t = re.sub(r"[\uff08(].*?[)\uff09]", "", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()

def title_matches(candidate, target):
    a, b = _normalize_title(candidate), _normalize_title(target)
    if not a or not b: return False
    if a == b or a in b or b in a: return True
    overlap = len(set(a.split()) & set(b.split())) / max(len(set(b.split())), 1)
    return overlap >= 0.5


# ---- Full flow ----
async def test_song(title, artist):
    print(f"\n{'='*60}")
    print(f"SONG: {title} - {artist}")
    print(f"{'='*60}")
    
    # Search
    query = f"{title} {artist}"
    print(f"  [1] Searching: {query[:50]}")
    fangpi_results = await fangpi_search(query)
    kuwo_results = await kuwo_search(query)
    
    # If first search empty, try title only
    if not fangpi_results:
        fangpi_results = await fangpi_search(title)
    if not kuwo_results:
        kuwo_results = await kuwo_search(title)
    
    # Combine + filter
    all_results = fangpi_results + kuwo_results
    matched = [r for r in all_results if title_matches(r["title"], title)]
    print(f"  [2] Results: fangpi={len(fangpi_results)}, kuwo={len(kuwo_results)}, matched={len(matched)}")
    
    if not matched:
        print(f"  RESULT: FAIL - no matching search results")
        if all_results:
            print(f"    Unmatched results: {[(r['title'][:30], r['source']) for r in all_results[:5]]}")
        return False
    
    best = matched[0]
    print(f"  [3] Best match: {best['title'][:40]} (id={best['id']}, source={best['source']})")
    
    # Get audio URL
    audio_url = None
    print(f"  [4] Getting audio URL from {best['source']}...")
    try:
        if best["source"] == "fangpi":
            audio_url = await fangpi_get_audio_url(best["id"])
        else:
            audio_url = await kuwo_get_audio_url(best["id"])
    except Exception as e:
        print(f"    Primary source failed: {e}")
    
    # Fallback: try kuwo by searching
    if not audio_url:
        print(f"  [5] Fallback: searching kuwo for audio...")
        kuwo_fallback = await kuwo_search(f"{title} {artist}")
        kuwo_matched = [r for r in kuwo_fallback if title_matches(r["title"], title)]
        if not kuwo_matched and kuwo_fallback:
            kuwo_matched = kuwo_fallback[:1]
        for candidate in kuwo_matched[:3]:
            try:
                audio_url = await kuwo_get_audio_url(candidate["id"])
                print(f"    Kuwo fallback succeeded with id={candidate['id']}")
                break
            except Exception as e:
                print(f"    Kuwo fallback failed for {candidate['id']}: {e}")
    
    if not audio_url:
        print(f"  RESULT: FAIL - no audio URL from any source")
        return False
    
    print(f"  [6] Audio URL: {audio_url[:80]}...")
    
    # Download
    try:
        size = await download_file(audio_url)
        print(f"  RESULT: SUCCESS ({size//1024} KB)")
        return True
    except Exception as e:
        print(f"  RESULT: FAIL - download error: {e}")
        return False


async def main():
    songs = [
        ("Nuthin' But A \"G\" Thang", "Dr. Dre / Snoop Dogg"),
        ("Juicy", "The Notorious B.I.G."),
        ("Elevate", "Jigmastas"),
        ("My Block (Nitty Remix)", "2Pac"),
        ("Shook Ones Part II (Instrumental)", "Mobb Deep"),
    ]
    
    results = []
    for title, artist in songs:
        ok = await test_song(title, artist)
        results.append((title, ok))
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for title, ok in results:
        print(f"  {'OK' if ok else 'FAIL'}: {title}")
    print(f"\nTotal: {sum(1 for _,ok in results if ok)}/{len(results)} succeeded")

asyncio.run(main())
