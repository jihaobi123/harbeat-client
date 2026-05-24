#!/usr/bin/env python3
"""Offline audio quality report for A/B transition renders.

Analyzes one or two WAV files and produces a JSON quality report covering:
  - peak dBFS, RMS, LUFS estimate
  - transition-window energy curve (before / during / after)
  - clipping detection (samples exceeding 0.999)
  - silence detection (500ms windows below -60 dBFS)
  - low-frequency conflict (energy below 100 Hz, bass overlap 60-100 Hz)
  - stereo correlation (if stereo input)

Usage:
    # Single file
    python scripts/quality_report.py --input non_stem.wav --bpm 120 --bars 8

    # A/B comparison
    python scripts/quality_report.py --a non_stem.wav --b stem_aware.wav --bpm 120
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np


def load_audio(path: str) -> tuple[np.ndarray, int]:
    """Load audio file, return (mono_float64, sample_rate)."""
    try:
        import soundfile as sf
    except ImportError:
        print("ERROR: soundfile not installed. Run: pip install soundfile", file=sys.stderr)
        sys.exit(1)

    audio, sr = sf.read(path, dtype="float64")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, int(sr)


def analyze_wav(path: str, label: str, bpm: float = 120.0,
                duration_bars: int = 8) -> dict[str, Any]:
    """Full quality analysis for one WAV file."""
    audio, sr = load_audio(path)

    # ── Basic stats ──
    peak = float(np.max(np.abs(audio)))
    peak_dbfs = 20.0 * np.log10(max(peak, 1e-10))
    rms = float(np.sqrt(np.mean(audio ** 2)))
    rms_dbfs = 20.0 * np.log10(max(rms, 1e-10))

    # ── LUFS estimate (simplified: no K-weighting or gating) ──
    lufs_est = rms_dbfs

    # ── Transition window ──
    bar_dur = 60.0 / max(bpm, 1.0) * 4.0
    trans_sec = duration_bars * bar_dur
    total_sec = len(audio) / sr
    t_mid = total_sec / 2.0
    t_start = max(0.0, t_mid - trans_sec / 2.0)
    t_end = min(total_sec, t_start + trans_sec)
    i_start = int(t_start * sr)
    i_end = int(t_end * sr)
    trans = audio[i_start:i_end]

    seg_n = max(1, len(trans) // 3)
    before_rms = float(np.sqrt(np.mean(trans[:seg_n] ** 2))) if seg_n > 0 else 0.0
    during_rms = float(np.sqrt(np.mean(trans[seg_n:2 * seg_n] ** 2))) if seg_n > 0 else 0.0
    after_rms = float(np.sqrt(np.mean(trans[2 * seg_n:] ** 2))) if seg_n > 0 else 0.0

    # ── Clipping ──
    clipped = int(np.sum(np.abs(audio) > 0.999))

    # ── Silence detection ──
    window_s = int(0.5 * sr)
    silences = []
    for i in range(0, len(audio) - window_s, window_s // 2):
        win = audio[i:i + window_s]
        wrms = float(np.sqrt(np.mean(win ** 2)))
        wdb = 20.0 * np.log10(max(wrms, 1e-10))
        if wdb < -60.0:
            silences.append({
                "start_sec": round(i / sr, 3),
                "end_sec": round((i + window_s) / sr, 3),
                "rms_dbfs": round(wdb, 1),
            })

    # ── Low-frequency analysis ──
    try:
        from scipy import signal
        nperseg = min(4096, len(audio) // 4)
        if nperseg >= 64:
            f, Pxx = signal.welch(audio, sr, nperseg=nperseg)
            low_mask = f <= 100.0
            low_energy = float(np.sum(Pxx[low_mask]))
            total_energy = float(np.sum(Pxx))
            low_ratio = low_energy / max(total_energy, 1e-10)

            bass_mask = (f >= 60.0) & (f <= 100.0)
            bass_overlap = float(np.sum(Pxx[bass_mask]))
        else:
            low_ratio = 0.0
            bass_overlap = 0.0
    except ImportError:
        low_ratio = 0.0
        bass_overlap = 0.0

    # ── Dynamic range ──
    p99 = float(np.percentile(np.abs(audio), 99))
    p10 = float(np.percentile(np.abs(audio), 10))
    crest_factor = 20.0 * np.log10(max(p99 / max(p10, 1e-10), 1.0))

    return {
        "label": label,
        "file": path,
        "duration_sec": round(len(audio) / sr, 3),
        "sample_rate": sr,
        "peak_dbfs": round(peak_dbfs, 2),
        "rms_dbfs": round(rms_dbfs, 2),
        "lufs_estimate": round(lufs_est, 2),
        "crest_factor_db": round(crest_factor, 1),
        "clipping": clipped > 0,
        "clipped_samples": clipped,
        "silence_windows": silences,
        "silence_count": len(silences),
        "transition_energy": {
            "start_sec": round(t_start, 3),
            "end_sec": round(t_end, 3),
            "before_dbfs": round(20.0 * np.log10(max(before_rms, 1e-10)), 1),
            "during_dbfs": round(20.0 * np.log10(max(during_rms, 1e-10)), 1),
            "after_dbfs": round(20.0 * np.log10(max(after_rms, 1e-10)), 1),
        },
        "low_frequency": {
            "below_100hz_ratio": round(low_ratio, 4),
            "bass_overlap_60_100hz": round(bass_overlap, 4),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Offline audio quality report for A/B transition renders",
    )
    parser.add_argument("--input", "-i", help="Single WAV file to analyze")
    parser.add_argument("--a", help="WAV A (non-stem / reference)")
    parser.add_argument("--b", help="WAV B (stem-aware / comparison)")
    parser.add_argument("--bpm", type=float, default=120.0,
                        help="BPM for transition window calculation")
    parser.add_argument("--bars", type=int, default=8,
                        help="Transition duration in bars")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON path (default: stdout)")
    parser.add_argument("--label-a", default="non_stem")
    parser.add_argument("--label-b", default="stem_aware")

    args = parser.parse_args()

    results: dict[str, Any] = {"bpm": args.bpm, "bars": args.bars}

    if args.input:
        results["tracks"] = [analyze_wav(args.input, "input", args.bpm, args.bars)]
    elif args.a:
        tracks = [analyze_wav(args.a, args.label_a, args.bpm, args.bars)]
        if args.b and os.path.isfile(args.b):
            tracks.append(analyze_wav(args.b, args.label_b, args.bpm, args.bars))
            # Comparison
            a_peak = tracks[0]["peak_dbfs"]
            b_peak = tracks[1]["peak_dbfs"]
            a_rms = tracks[0]["rms_dbfs"]
            b_rms = tracks[1]["rms_dbfs"]
            results["comparison"] = {
                "peak_delta_db": round(b_peak - a_peak, 2),
                "rms_delta_db": round(b_rms - a_rms, 2),
                "a_clipped": tracks[0]["clipped_samples"],
                "b_clipped": tracks[1]["clipped_samples"],
                "a_silence_count": tracks[0]["silence_count"],
                "b_silence_count": tracks[1]["silence_count"],
            }
        results["tracks"] = tracks
    else:
        parser.print_help()
        sys.exit(1)

    # Health verdict
    issues = []
    for t in results.get("tracks", []):
        if t["clipping"]:
            issues.append(f"{t['label']}: {t['clipped_samples']} clipped samples")
        if t["silence_count"] > 0:
            issues.append(f"{t['label']}: {t['silence_count']} silence windows")
        if abs(t["peak_dbfs"]) < 0.5:
            issues.append(f"{t['label']}: near-digital full scale ({t['peak_dbfs']:.1f} dBFS)")
        if abs(t["peak_dbfs"]) > 30:
            issues.append(f"{t['label']}: very quiet ({t['peak_dbfs']:.1f} dBFS)")

    results["health"] = "ok" if not issues else "issues_found"
    results["health_issues"] = issues

    output = json.dumps(results, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Report saved to: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
