"""Test the fixed search+match logic."""
import asyncio
import re
import httpx

_UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_UA_MOBILE = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36"
_UA_DOWNLOAD = "okhttp/3.10.0"

def _clean_html(s):
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')

def _normalize_title(t):
    t = t.lower().strip()
    t = re.sub(r"[\uff08(].*?[)\uff09]", "", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()

def _title_matches(candidate_title, target_title):
    a = _normalize_title(candidate_title)
    b = _normalize_title(target_title)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    a_words = set(a.split())
    b_words = set(b.split())
    if not b_words:
        return False
    overlap = len(a_words & b_words) / len(b_words)
    return overlap >= 0.5

async def kuwo_search(query):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get("https://search.kuwo.cn/r.s",
                params={"ft": "music", "rformat": "json", "encoding": "utf8", "rn": "20", "pn": "0", "all": query},
                headers={"User-Agent": _UA_MOBILE, "Referer": "https://m.kuwo.cn/"})
        ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", resp.text)
        names = re.findall(r"['\"]NAME['\"]\s*:\s*['\"]([^'\"]*)['\"]", resp.text)
        artists = re.findall(r"['\"]ARTIST['\"]\s*:\s*['\"]([^'\"]*)['\"]", resp.text)
        return [{"id": ids[i], "title": _clean_html(names[i] if i < len(names) else ""), "artist": _clean_html(artists[i] if i < len(artists) else ""), "source": "kuwo"} for i in range(len(ids))]
    except:
        return []

async def smart_search(title, artist):
    for q in [f"{title} {artist}".strip(), title.strip(), re.sub(r"[\uff08(].*?[)\uff09]", "", title).strip()]:
        if not q:
            continue
        results = await kuwo_search(q)
        matched = [r for r in results if _title_matches(r["title"], title)]
        if matched:
            return matched
    return []

async def main():
    songs = [
        ("Nuthin' But A \"G\" Thang", "Dr. Dre / Snoop Dogg"),
        ("Pieces Of A (Black) Man (Explicit)", "AZ"),
        ("Elevate", "Jigmastas"),
        ("My Block (Nitty Remix)", "2Pac"),
        ("Juicy", "The Notorious B.I.G."),
        ("Shook Ones Part II (Instrumental)", "Mobb Deep"),
    ]
    
    found = 0
    for title, artist in songs:
        results = await smart_search(title, artist)
        if results:
            best = results[0]
            found += 1
            # Try to get audio URL
            async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
                resp = await client.get(
                    f"https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid={best['id']}&format=mp3&response=url",
                    headers={"User-Agent": _UA_DOWNLOAD})
                try:
                    body = resp.json()
                    has_url = bool(body.get("url"))
                except:
                    has_url = resp.text.strip().startswith("http")
            print(f"  OK: {title[:40]} => {best['title'][:30]} (id={best['id']}, audio={'YES' if has_url else 'NO'})")
        else:
            print(f"  MISS: {title[:40]} => no match")
    
    print(f"\nMatch rate: {found}/{len(songs)}")

asyncio.run(main())
