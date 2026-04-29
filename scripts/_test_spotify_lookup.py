"""Test online BPM lookup (songbpm.com + Spotify search) for the same 10 songs.

Usage: PYTHONPATH=. python scripts/_test_spotify_lookup.py
"""
import json
import os
import sys
import time

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from app.modules.library.bpm_lookup import lookup_track_info, normalize_bpm

# Same 10 songs from _test_bpm10.py — extracted title/artist from filenames
SONGS = [
    {"file": "California Love - 2Pac _ Dr. Dre _ The D.O.C..mp3", "title": "California Love", "artist": "2Pac"},
    {"file": "C.R.E.A.M. - Wu-Tang Clan.mp3", "title": "C.R.E.A.M.", "artist": "Wu-Tang Clan"},
    {"file": "Cheshire - ITZY.mp3", "title": "Cheshire", "artist": "ITZY"},
    {"file": "10 MINUTES - 李孝利.mp3", "title": "10 Minutes", "artist": "Lee Hyori"},
    {"file": "3055 - Ólafur Arnalds.mp3", "title": "3055", "artist": "Ólafur Arnalds"},
    {"file": "Could Heaven Ever Be Like This - Alice Russell.mp3", "title": "Could Heaven Ever Be Like This", "artist": "Alice Russell"},
    {"file": "Deep Cover - Dr. Dre.mp3", "title": "Deep Cover", "artist": "Dr. Dre"},
    {"file": "ATLiens - OutKast.mp3", "title": "ATLiens", "artist": "OutKast"},
    {"file": "Adventure (Battle Edit) - DJ_Beat老果.mp3", "title": "Adventure Battle Edit", "artist": "DJ Beat"},
    {"file": "On & On - Erykah Badu.mp3", "title": "On & On", "artist": "Erykah Badu"},
]

# Local analysis results for comparison
LOCAL_RESULTS = {
    "California Love": 92.7,
    "C.R.E.A.M.": 91.4,
    "Cheshire": 98.9,
    "10 MINUTES": 96.2,
    "3055": 166.8,
    "Could Heaven Ever Be Like This": 76.0,
    "Deep Cover": 123.0,
    "ATLiens": 105.0,
}

print("=" * 70)
print("  Online BPM Lookup Test (songbpm.com) — 10 Songs")
print("=" * 70)
print()

results = []
success = 0
total_time = 0.0

for i, song in enumerate(SONGS, 1):
    print(f"[{i}/10] {song['title']} - {song['artist']} ...", end=" ", flush=True)

    t0 = time.time()
    info = lookup_track_info(song["title"], song["artist"])
    elapsed = time.time() - t0
    total_time += elapsed

    if info:
        success += 1
        raw_bpm = info["bpm"]
        bpm = normalize_bpm(raw_bpm, info.get("alt_bpm"))
        local_bpm = LOCAL_RESULTS.get(song["title"], "N/A")
        bpm_match = ""
        if isinstance(local_bpm, (int, float)):
            diff = abs(bpm - local_bpm)
            pct = diff / local_bpm * 100
            if pct < 2:
                bpm_match = "✅"
            elif pct < 5:
                bpm_match = "⚠️"
            else:
                bpm_match = f"❌({pct:.0f}%)"

        matched = info.get('matched_name') or 'N/A'
        key_display = info.get('key') or 'N/A'
        camelot_display = info.get('camelot_key') or 'N/A'
        src_display = info.get('source') or 'N/A'
        bpm_display = f"{bpm}" if bpm == raw_bpm else f"{bpm}({raw_bpm})"
        print(f"BPM={bpm_display:<12} key={key_display:<12} "
              f"camelot={camelot_display:<4} "
              f"src={src_display:<8} "
              f"matched='{matched}' "
              f"[{elapsed:.1f}s] {bpm_match}")

        results.append({
            "title": song["title"],
            "artist": song["artist"],
            "online_bpm": bpm,
            "raw_bpm": raw_bpm,
            "online_key": info.get("key"),
            "online_camelot": info.get("camelot_key"),
            "source": info.get("source"),
            "local_bpm": local_bpm,
            "lookup_time": round(elapsed, 2),
            "matched": matched,
        })
    else:
        print(f"NOT FOUND [{elapsed:.1f}s]")
        results.append({
            "title": song["title"],
            "artist": song["artist"],
            "online_bpm": None,
            "local_bpm": LOCAL_RESULTS.get(song["title"], "N/A"),
            "lookup_time": round(elapsed, 2),
        })

print()
print("=" * 70)
print(f"  Found: {success}/10 ({success * 10}%)")
print(f"  Avg lookup time: {total_time / len(SONGS):.1f}s")
print(f"  Total time: {total_time:.1f}s")
print("=" * 70)

# Write results
with open("/tmp/spotify_lookup_results.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nResults saved to /tmp/spotify_lookup_results.json")
