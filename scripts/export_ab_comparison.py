#!/usr/bin/env python3
"""Export A/B comparison: non-stem vs stem-aware transition for the same track pair.

Usage:
    python scripts/export_ab_comparison.py \
        --song-a /path/to/song_a.wav \
        --song-b /path/to/song_b.wav \
        --stems-a /path/to/stems_a/ \
        --stems-b /path/to/stems_b/ \
        --output-dir ./ab_output/

Outputs:
    {output_dir}/non_stem.wav      — Non-stem Automix version
    {output_dir}/stem_aware.wav    — Stem-aware Automix version
    {output_dir}/plan_comparison.json  — Both transition plans for inspection
    {output_dir}/scores.json       — Scoring breakdown

Without stems:
    {output_dir}/non_stem.wav      — Non-stem Automix (same as stem_aware fallback)
    {output_dir}/plan_comparison.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def main():
    parser = argparse.ArgumentParser(
        description="A/B compare non-stem vs stem-aware Automix transitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--song-a", required=True, help="Path to track A (original WAV)")
    parser.add_argument("--song-b", required=True, help="Path to track B (original WAV)")
    parser.add_argument("--stems-a", default=None, help="Directory with A stems (vocals/drums/bass/other.wav)")
    parser.add_argument("--stems-b", default=None, help="Directory with B stems (vocals/drums/bass/other.wav)")
    parser.add_argument("--bpm-a", type=float, default=None, help="BPM of track A")
    parser.add_argument("--bpm-b", type=float, default=None, help="BPM of track B")
    parser.add_argument("--key-a", default=None, help="Camelot key of track A (e.g. 8A)")
    parser.add_argument("--key-b", default=None, help="Camelot key of track B (e.g. 9A)")
    parser.add_argument("--output-dir", "-o", default="./ab_output", help="Output directory")
    parser.add_argument("--duration-bars", type=int, default=8, help="Transition duration in bars")
    parser.add_argument("--force-preset", default=None, help="Force a specific preset (bypass auto-selection)")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Output sample rate")

    args = parser.parse_args()

    # Validate inputs
    if not os.path.isfile(args.song_a):
        print(f"Error: song-a not found: {args.song_a}")
        sys.exit(1)
    if not os.path.isfile(args.song_b):
        print(f"Error: song-b not found: {args.song_b}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # Add project to path
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Resolve stems
    def find_stems(stems_dir: str | None) -> dict[str, str] | None:
        if not stems_dir or not os.path.isdir(stems_dir):
            return None
        stems = {}
        for name in ("vocals", "drums", "bass", "other"):
            path = os.path.join(stems_dir, f"{name}.wav")
            if os.path.isfile(path):
                stems[name] = path
        return stems if len(stems) >= 2 else None

    stems_a = find_stems(args.stems_a)
    stems_b = find_stems(args.stems_b)

    # Estimate BPM if not provided
    def estimate_bpm(path: str) -> float | None:
        try:
            import librosa
            y, sr = librosa.load(path, sr=22050, mono=True, duration=60)
            bpm, _ = librosa.beat.beat_track(y=y, sr=sr)
            return float(bpm) if bpm else None
        except Exception:
            return None

    bpm_a = args.bpm_a or estimate_bpm(args.song_a) or 120.0
    bpm_b = args.bpm_b or estimate_bpm(args.song_b) or 120.0

    # Build track contexts
    from app.modules.playlists.stem_automix import (
        TrackContext,
        TransitionPreset,
        generate_plan,
        score_transition_candidates,
        render_transition_plan,
    )

    ctx_a = TrackContext(
        song_id="A",
        bpm=bpm_a,
        camelot_key=args.key_a,
        duration_sec=float(sf.info(args.song_a).duration),
        has_stems=stems_a is not None,
        stem_quality_score=0.8 if stems_a else 0.0,
        vocal_density=0.5,
        bass_energy=0.5,
        intro_is_clean=stems_b is not None,
        outro_is_clean=stems_a is not None,
        has_drum_loop=stems_a is not None,
    )

    ctx_b = TrackContext(
        song_id="B",
        bpm=bpm_b,
        camelot_key=args.key_b,
        duration_sec=float(sf.info(args.song_b).duration),
        has_stems=stems_b is not None,
        stem_quality_score=0.8 if stems_b else 0.0,
        vocal_density=0.5,
        bass_energy=0.5,
        intro_is_clean=True,
        outro_is_clean=True,
        has_drum_loop=False,
    )

    force_preset = TransitionPreset(args.force_preset) if args.force_preset else None

    # Score
    scores = score_transition_candidates(ctx_a, ctx_b)
    print("\n=== Transition Scoring ===")
    for k, v in scores.to_dict().items():
        print(f"  {k}: {v:.3f}")

    # ---- Non-stem version ----
    ctx_a_ns = TrackContext(
        song_id="A", bpm=bpm_a, camelot_key=args.key_a,
        duration_sec=ctx_a.duration_sec,
        has_stems=False, stem_quality_score=0.0,
        vocal_density=0.5, bass_energy=0.5,
        intro_is_clean=True, outro_is_clean=True, has_drum_loop=False,
    )
    ctx_b_ns = TrackContext(
        song_id="B", bpm=bpm_b, camelot_key=args.key_b,
        duration_sec=ctx_b.duration_sec,
        has_stems=False, stem_quality_score=0.0,
        vocal_density=0.5, bass_energy=0.5,
        intro_is_clean=True, outro_is_clean=True, has_drum_loop=False,
    )

    plan_non_stem = generate_plan(
        ctx_a_ns, ctx_b_ns,
        force_preset or TransitionPreset.fallback_crossfade,
        duration_bars=args.duration_bars,
    )
    print(f"\n=== Non-Stem Plan ===")
    print(f"  Mode: {plan_non_stem.mode.value}")
    print(f"  Preset: {plan_non_stem.preset.value}")
    print(f"  Curves: {len(plan_non_stem.curves)}")

    wav_non_stem = render_transition_plan(
        plan_non_stem,
        args.song_a, args.song_b,
        from_stems=None, to_stems=None,
        sample_rate=args.sample_rate,
    )
    out_non_stem = os.path.join(args.output_dir, "non_stem.wav")
    sf.write(out_non_stem, wav_non_stem, args.sample_rate, subtype="PCM_16")
    print(f"  Output: {out_non_stem} ({wav_non_stem.shape[0] / args.sample_rate:.1f}s)")

    # ---- Stem-aware version ----
    plan_stem = generate_plan(
        ctx_a, ctx_b,
        force_preset or TransitionPreset.bass_swap,
        duration_bars=args.duration_bars,
    )
    print(f"\n=== Stem-Aware Plan ===")
    print(f"  Mode: {plan_stem.mode.value}")
    print(f"  Preset: {plan_stem.preset.value}")
    print(f"  Curves: {len(plan_stem.curves)}")

    wav_stem = render_transition_plan(
        plan_stem,
        args.song_a, args.song_b,
        from_stems=stems_a, to_stems=stems_b,
        sample_rate=args.sample_rate,
    )
    out_stem = os.path.join(args.output_dir, "stem_aware.wav")
    sf.write(out_stem, wav_stem, args.sample_rate, subtype="PCM_16")
    print(f"  Output: {out_stem} ({wav_stem.shape[0] / args.sample_rate:.1f}s)")

    # ---- Export plans for inspection ----
    comparison = {
        "scores": scores.to_dict(),
        "non_stem_plan": plan_non_stem.to_dict(),
        "stem_aware_plan": plan_stem.to_dict(),
    }
    out_json = os.path.join(args.output_dir, "plan_comparison.json")
    with open(out_json, "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"\n=== Plans exported to: {out_json} ===")

    # ---- Export scores ----
    out_scores = os.path.join(args.output_dir, "scores.json")
    with open(out_scores, "w") as f:
        json.dump(scores.to_dict(), f, indent=2)
    print(f"Scores exported to: {out_scores}")

    print("\nDone. A/B compare:")
    print(f"  Non-stem:    {out_non_stem}")
    print(f"  Stem-aware:  {out_stem}")


if __name__ == "__main__":
    main()
