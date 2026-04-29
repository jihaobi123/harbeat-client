#!/usr/bin/env python3
"""Test BeatNet+ BPM detection on songs from NAS.

Run on Jetson:
    cd ~/harbeat && /home/mark/venvs/harbeat/bin/python scripts/_test_bpm10.py

Results are written to /tmp/bpm_test_results.txt
"""
import os
import sys
import time
import json
import io

# Unbuffered stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import librosa

from app.modules.library.beat_engine import analyze_beats

MUSIC_DIR = os.path.expanduser("~/harbeat/data/music-files/shared")
RESULT_FILE = "/tmp/bpm_test_results.txt"

# Pick 10 diverse songs (different genres/BPM ranges)
TARGET_SONGS = [
    "California Love - 2Pac _ Dr. Dre _ The D.O.C..mp3",       # Hip-hop classic
    "C.R.E.A.M. - Wu-Tang Clan.mp3",                            # East coast hip-hop
    "Cheshire - ITZY.mp3",                                       # K-pop
    "10 MINUTES - 李孝利.mp3",                                   # K-pop dance
    "3055 - Ólafur Arnalds.mp3",                                 # Ambient/classical
    "Could Heaven Ever Be Like This - Alice Russell.mp3",        # Soul/funk
    "Deep Cover - Dr. Dre.mp3",                                  # G-funk
    "ATLiens - OutKast.mp3",                                     # Southern hip-hop
    "Adventure (Battle Edit) - DJ_Beat老果.mp3",                 # DJ battle edit
    "Boom - Royce Da 5'9_.mp3",                                  # Hip-hop
]


def test_song(filepath: str) -> dict:
    """Analyze one song and return results."""
    name = os.path.basename(filepath)
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")

    t0 = time.time()

    # Load audio
    y, sr = librosa.load(filepath, sr=22050, mono=True)
    duration = len(y) / sr
    load_time = time.time() - t0

    # Run analysis
    t1 = time.time()
    result = analyze_beats(filepath, y, sr, duration)
    analysis_time = time.time() - t1

    total_time = time.time() - t0

    # Extract sub-model BPMs if available
    sub_bpms = {}
    if "beatnet" in result.raw_results:
        sub_bpms = result.raw_results["beatnet"].get("sub_bpms", {})

    # Per-engine BPMs
    engine_bpms = {}
    for eng, res in result.raw_results.items():
        if "bpm" in res:
            engine_bpms[eng] = res["bpm"]
        if "percival_bpm" in res:
            engine_bpms[f"{eng}_percival"] = res["percival_bpm"]
        if "bpm_beat_track" in res:
            engine_bpms[f"{eng}_beat_track"] = res["bpm_beat_track"]
        if "bpm_tempogram" in res:
            engine_bpms[f"{eng}_tempogram"] = res["bpm_tempogram"]

    print(f"  Duration:    {duration:.1f}s")
    print(f"  Final BPM:   {result.bpm:.2f}")
    print(f"  Confidence:  {result.confidence:.3f}")
    print(f"  Engines:     {', '.join(result.engines_used)}")
    print(f"  Needs review: {result.needs_review}")
    print()
    print(f"  Per-engine BPMs:")
    for eng, bpm in sorted(engine_bpms.items()):
        print(f"    {eng:25s}: {bpm:.2f}")
    if sub_bpms:
        print(f"  BeatNet+ sub-model BPMs:")
        for key, bpm in sorted(sub_bpms.items()):
            print(f"    {key:25s}: {bpm:.2f}")
    print()
    print(f"  Beat count:  {len(result.beat_points)}")
    print(f"  Downbeats:   {len(result.downbeats)}")
    print(f"  Grid offset: {result.grid_offset:.4f}s")
    print(f"  Load time:   {load_time:.1f}s")
    print(f"  Analysis:    {analysis_time:.1f}s")
    print(f"  Total:       {total_time:.1f}s")

    return {
        "name": name,
        "bpm": result.bpm,
        "confidence": result.confidence,
        "engines": result.engines_used,
        "needs_review": result.needs_review,
        "engine_bpms": engine_bpms,
        "sub_bpms": sub_bpms,
        "beat_count": len(result.beat_points),
        "analysis_time": round(analysis_time, 1),
    }


def out(msg, f=None):
    print(msg)
    sys.stdout.flush()
    if f:
        f.write(msg + "\n")
        f.flush()


def main():
    f = open(RESULT_FILE, "w")
    out("=" * 70, f)
    out("  BeatNet+ BPM Detection Test — 10 Songs", f)
    out("=" * 70, f)

    # Verify music dir
    if not os.path.isdir(MUSIC_DIR):
        out(f"ERROR: Music directory not found: {MUSIC_DIR}", f)
        sys.exit(1)

    # Filter to existing files
    songs = []
    for name in TARGET_SONGS:
        path = os.path.join(MUSIC_DIR, name)
        if os.path.isfile(path):
            songs.append(path)
        else:
            out(f"  SKIP (not found): {name}", f)

    if not songs:
        out("ERROR: No songs found!", f)
        sys.exit(1)

    out(f"\n  Testing {len(songs)} songs...\n", f)

    results = []
    t_total = time.time()

    for i, filepath in enumerate(songs):
        out(f"[{i+1}/{len(songs)}] Starting: {os.path.basename(filepath)}", f)
        try:
            r = test_song(filepath)
            results.append(r)
            # Write per-song result to file immediately
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            out(f"[{i+1}/{len(songs)}] Done: BPM={r['bpm']:.2f} conf={r['confidence']:.3f}", f)
        except Exception as e:
            out(f"\n  ERROR: {os.path.basename(filepath)}: {e}", f)
            import traceback
            traceback.print_exc()

    elapsed = time.time() - t_total

    # Summary table
    out("\n" + "=" * 70, f)
    out("  SUMMARY", f)
    out("=" * 70, f)
    out(f"  {'Song':<45} {'BPM':>7} {'Conf':>6} {'Time':>6} {'Engines'}", f)
    out(f"  {'-'*45} {'-'*7} {'-'*6} {'-'*6} {'-'*20}", f)
    for r in results:
        flag = " !" if r["needs_review"] else ""
        out(f"  {r['name'][:44]:<45} {r['bpm']:>7.2f} {r['confidence']:>6.3f} {r['analysis_time']:>5.1f}s {','.join(r['engines'])}{flag}", f)

    avg_conf = np.mean([r["confidence"] for r in results]) if results else 0
    avg_time = np.mean([r["analysis_time"] for r in results]) if results else 0

    out(f"\n  Average confidence: {avg_conf:.3f}", f)
    out(f"  Average analysis time: {avg_time:.1f}s", f)
    out(f"  Total elapsed: {elapsed:.1f}s", f)
    out(f"  Songs tested: {len(results)}/{len(songs)}", f)
    f.close()
    out(f"\nResults saved to {RESULT_FILE}")


if __name__ == "__main__":
    main()
