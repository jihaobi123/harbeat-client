"""Batch BPM test: 10 random songs."""
import sys, os, time
sys.path.insert(0, '/app')
import librosa
import numpy as np
from app.modules.library.beat_engine import analyze_beats

songs = [
    ("Hypnotize", "The Notorious B.I.G.", "/app/data/music-files/shared/Hypnotize - The Notorious B.I.G..mp3"),
    ("One B-Boy", "Dj Pablo", "/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3"),
    ("Hip Hop Hooray", "Naughty by Nature", "/app/data/music-files/shared/Hip Hop Hooray - Naughty by Nature.mp3"),
    ("It's Been A Long Time", "Rakim", "/app/data/music-files/shared/It's Been A Long Time - Rakim.mp3"),
    ("So Many Ways", "Warren G", "/app/data/music-files/shared/So Many Ways - Warren G.mp3"),
    ("Deadly Combination", "Miqu / 2Pac", "/app/data/music-files/shared/Deadly Combination (Miqu Remix) - Miqu _ 2Pac.mp3"),
    ("Hip Hop", "Mos Def", "/app/data/music-files/shared/Hip Hop - Mos Def.mp3"),
    ("God's Plan", "Drake", "/app/data/music-files/shared/God&#039;s Plan - Drake.mp3"),
    ("不怪她 (Blame)", "HARIKIRI", "/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI&Bohan Phoenix&马思唯&J.Mag.mp3"),
    ("P-Poppin'", "Ludacris", "/app/data/music-files/shared/P-Poppin' - Ludacris _ Shawnna _ Lil Fate.mp3"),
]

print("=" * 80)
print("BATCH BPM ANALYSIS - 10 SONGS")
print("=" * 80)

results = []
for title, artist, path in songs:
    print(f"\n--- {title} - {artist} ---")
    
    if not os.path.exists(path):
        print(f"  FILE NOT FOUND: {path}")
        results.append((title, artist, None, None, None, "NOT FOUND"))
        continue
    
    t0 = time.time()
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)
        result = analyze_beats(path, y, sr, duration)
        elapsed = time.time() - t0
        
        bpm = result.bpm
        conf = result.confidence
        engines = result.engines_used
        raw = result.raw_results
        review = result.needs_review
        
        print(f"  BPM={bpm} | Conf={conf} | Engines={engines} | Review={review}")
        print(f"  Raw: {raw} | Time: {elapsed:.1f}s")
        results.append((title, artist, bpm, conf, raw, "OK"))
    except Exception as ex:
        elapsed = time.time() - t0
        print(f"  ERROR: {ex} ({elapsed:.1f}s)")
        results.append((title, artist, None, None, None, str(ex)))

print(f"\n{'='*80}")
print("RESULTS TABLE")
print(f"{'='*80}")
print(f"{'Song':<30} {'BPM':>6} {'Conf':>5} {'Raw BPMs':<50}")
for title, artist, bpm, conf, raw, status in results:
    if status == "OK":
        raw_str = ", ".join(f"{k}={v.get('bpm',0)}" for k,v in raw.items())
        print(f"{title:<30} {bpm:>6.1f} {conf:>5.3f} {raw_str:<50}")
    else:
        print(f"{title:<30} {'ERR':>6} {'':>5} {status:<50}")
