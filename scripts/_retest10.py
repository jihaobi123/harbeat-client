"""Re-test all 10 songs with updated _select_perceptual_tempo algorithm."""
import sys, os, time
sys.path.insert(0, '/app')
import numpy as np
import librosa

from app.modules.library.beat_engine import analyze_beats

songs = [
    ("/app/data/music-files/shared/Hypnotize - The Notorious B.I.G..mp3", "Hypnotize", "The Notorious B.I.G.", 94),
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3", "One B-Boy", "Dj Pablo", 126),
    ("/app/data/music-files/shared/Hip Hop Hooray - Naughty by Nature.mp3", "Hip Hop Hooray", "Naughty by Nature", 99),
    ("/app/data/music-files/shared/It's Been A Long Time - Rakim.mp3", "It's Been A Long Time", "Rakim", 89),
    ("/app/data/music-files/shared/So Many Ways - Warren G.mp3", "So Many Ways", "Warren G", 95),
    ("/app/data/music-files/shared/Deadly Combination (Miqu Remix) - Miqu _ 2Pac _ Biggie Smalls.mp3", "Deadly Combination", "Miqu/2Pac", None),
    ("/app/data/music-files/shared/Hip Hop - Mos Def.mp3", "Hip Hop", "Mos Def", 90),
    ("/app/data/music-files/shared/God&#039;s Plan - Drake.mp3", "God's Plan", "Drake", 77),
    ("/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI&Bohan Phoenix&马思唯&J.Mag.mp3", "不怪她", "HARIKIRI", 80),
    ("/app/data/music-files/shared/P-Poppin' - Ludacris _ Shawnna _ Lil Fate.mp3", "P-Poppin'", "Ludacris", 150),
]

print("="*80)
print("BATCH BPM RE-TEST (New Algorithm: sub-bass prominence, no 3:2)")
print("="*80)

results = []
for path, title, artist, ref in songs:
    if not os.path.exists(path):
        print(f"\n  FILE NOT FOUND: {path}")
        continue
    
    t0 = time.time()
    y, sr = librosa.load(path, sr=22050, mono=True)
    duration = len(y) / sr
    result = analyze_beats(path, y, sr, duration)
    elapsed = time.time() - t0
    
    raw_bpms = {k: round(v.get('bpm', 0), 2) for k, v in result.raw_results.items() if isinstance(v, dict)}
    
    ref_str = str(ref) if ref else "?"
    diff_str = ""
    status = ""
    if ref:
        diff = result.bpm - ref
        diff_str = f"{diff:+.1f}"
        if abs(diff) <= 3:
            status = "✓"
        elif abs(diff) <= 8:
            status = "~"
        else:
            status = "✗"
    
    results.append((title, result.bpm, ref, diff_str, status, raw_bpms, result.confidence, elapsed))
    
    print(f"\n--- {title} - {artist} ---")
    print(f"  BPM={result.bpm} | Ref={ref_str} | Diff={diff_str} {status}")
    print(f"  Conf={result.confidence:.3f} | Raw: {raw_bpms} | Time: {elapsed:.1f}s")

print("\n" + "="*80)
print("SUMMARY TABLE")
print("="*80)
print(f"{'Song':<30s} {'BPM':>6s} {'Ref':>5s} {'Diff':>6s} {'OK':>3s} Raw BPMs")
for title, bpm, ref, diff, status, raw, conf, _ in results:
    ref_str = str(ref) if ref else "?"
    raw_str = ", ".join(f"{k}={v}" for k, v in raw.items())
    print(f"{title:<30s} {bpm:>6.1f} {ref_str:>5s} {diff:>6s} {status:>3s} {raw_str}")

# Stats
tested_with_ref = [(t, b, r, d, s) for t, b, r, d, s, _, _, _ in results if r]
exact = sum(1 for _, _, _, _, s in tested_with_ref if s == "✓")
close = sum(1 for _, _, _, _, s in tested_with_ref if s in ("✓", "~"))
total = len(tested_with_ref)
print(f"\nAccuracy: {exact}/{total} exact (≤3 BPM), {close}/{total} close (≤8 BPM)")
