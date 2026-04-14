"""Full integration test for HarBeat API + Frontend."""
import urllib.request, json, sys

BASE = 'http://localhost:8000'

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    headers = {'Content-Type': 'application/json'} if body else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code

print('=== 1. Health Check ===')
r, s = api('GET', '/health')
code = r.get('code')
print(f'  Status: {s}, code: {code}')

print('=== 2. Vibe Search (Spotify + CLAP rerank) ===')
r, s = api('POST', '/api/recommendations/vibe-search', {'query': '90s old school hip hop'})
d = r.get('data', {})
sq = d.get('search_query', '')
print(f'  Status: {s}, search_query: {sq}')
songs = d.get('songs', [])
print(f'  Songs count: {len(songs)}')
for i, song in enumerate(songs[:5]):
    src = song.get('source', '?')
    dist = song.get('distance', 0)
    art = 'Y' if song.get('album_art') else 'N'
    spot = 'Y' if song.get('spotify_url') else 'N'
    prev = 'Y' if song.get('preview_url') else 'N'
    title = song.get('title', '')[:40]
    print(f'    [{i+1}] {title} | src={src} dist={dist:.3f} art={art} spotify={spot} preview={prev}')

print('=== 3. Library Songs ===')
r, s = api('GET', '/api/library/songs')
lib_songs = r.get('data', {}).get('songs', [])
print(f'  Status: {s}, count: {len(lib_songs)}')

print('=== 4. Frontend Serving ===')
req = urllib.request.Request(BASE + '/')
resp = urllib.request.urlopen(req, timeout=10)
html = resp.read().decode()
has_js = 'index-CIdY3-QV.js' in html
print(f'  index.html: {resp.status}, correct JS: {has_js}')

req2 = urllib.request.Request(BASE + '/assets/index-CIdY3-QV.js')
resp2 = urllib.request.urlopen(req2, timeout=10)
js = resp2.read().decode(errors='replace')
print(f'  JS size: {len(js)} bytes')
has_spotify = 'spotify' in js.lower()
has_album = 'album_art' in js
has_vibe = 'vibe' in js.lower()
print(f'  JS refs - spotify: {has_spotify}, album_art: {has_album}, vibe: {has_vibe}')

print('=== 5. Schema Consistency ===')
r, s = api('POST', '/api/recommendations/vibe-search', {'query': 'jazz night'})
d = r.get('data', {})
data_fields = ['query', 'vibe_description', 'search_query', 'genres', 'songs']
missing_d = [f for f in data_fields if f not in d]
print(f'  VibeSearchData missing: {missing_d or "none"}')
if d.get('songs'):
    song = d['songs'][0]
    song_fields = ['title', 'artist', 'distance', 'spotify_id', 'album_art', 'spotify_url', 'source', 'song_id']
    missing_s = [f for f in song_fields if f not in song]
    print(f'  SongItem missing: {missing_s or "none"}')
    sid = song.get('spotify_id', '')
    print(f'  Sample: {song.get("title")} | src={song.get("source")} | id={sid[:12]}')
else:
    print('  No songs for schema check')

print()
print('=== ALL TESTS DONE ===')
