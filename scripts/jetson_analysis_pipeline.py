#!/usr/bin/env python3
"""
Jetson Analysis Pipeline — GrooveEngine-style audio analysis on Jetson.

Analyzes raw WAV files → produces TrackContext-compatible dicts →
feeds directly into stem_automix scoring and optimal preset selection.

Usage:
    python3 scripts/jetson_analysis_pipeline.py [--tracks-dir data/tracks]
"""

import json
import os
import sys
import time
import numpy as np
import librosa
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.library.analysis import (
    MAX_ANALYSIS_DURATION,
    _analyze_key,
    _analyze_dancefloor_profile,
    _analyze_loudness,
    _attach_phrase_energy,
    _build_bpm_curve,
    _build_energy_curve,
    _build_transition_windows,
    _compute_groove_score,
    _detect_downbeats_with_meter,
    _detect_time_signature,
    _generate_dj_hot_cues,
    _recommend_transition_techniques,
    _score_section_intensity,
    _summarize_beatgrid,
)
from app.modules.library.genre_classifier import classify_genre

# ── Camelot wheel ────────────────────────────────────────────────

CAMELOT_MAJOR = {0:'8B',1:'3B',2:'10B',3:'5B',4:'12B',5:'7B',6:'2B',7:'9B',8:'4B',9:'11B',10:'6B',11:'1B'}
CAMELOT_MINOR = {0:'5A',1:'12A',2:'7A',3:'2A',4:'9A',5:'4A',6:'11A',7:'6A',8:'1A',9:'8A',10:'3A',11:'10A'}
KEY_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']


def analyze_track(filepath, track_id):
    """Full audio analysis. Returns TrackContext-compatible dict."""

    t0 = time.time()
    try:
        real_duration = float(sf.info(filepath).duration)
    except Exception:
        real_duration = None
    y, sr = librosa.load(filepath, sr=None, mono=False, duration=MAX_ANALYSIS_DURATION)
    if y.ndim == 2:
        y_mono = np.mean(y, axis=0)
    else:
        y_mono = y
    analysis_duration = float(len(y_mono) / sr)
    duration = real_duration if real_duration is not None else analysis_duration

    # ── BPM + Beats ──
    onset_env = librosa.onset.onset_strength(y=y_mono, sr=sr)
    bpm_raw, beats_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    bpm = float(bpm_raw[0]) if isinstance(bpm_raw, np.ndarray) else float(bpm_raw)
    beat_times = librosa.frames_to_time(beats_frames, sr=sr).tolist()
    bpm_curve, tempo_stability = _build_bpm_curve(beat_times)
    beatgrid_summary = _summarize_beatgrid(beat_times, bpm_curve, tempo_stability)

    # ── Downbeats ──
    downbeats, time_signature = _detect_downbeats_with_meter(
        y_mono,
        sr,
        np.asarray(beat_times),
    )

    # ── Key / Camelot ──
    key_result = _analyze_key(y_mono, sr)
    key_name, mode = key_result["key"].split(" ", 1)
    camelot = key_result["camelot_key"]

    # ── Energy ──
    rms = librosa.feature.rms(y=y_mono)[0]
    rms_norm = rms / (np.max(rms) + 1e-8)
    mean_energy = float(np.mean(rms_norm))
    energy_label = "low" if mean_energy < 0.12 else ("medium" if mean_energy < 0.22 else "high")
    energy_curve = _build_energy_curve(y_mono, sr)
    loudness_profile = _analyze_loudness(y_mono, sr)

    # ── Vocal density ──
    mfcc = librosa.feature.mfcc(y=y_mono, sr=sr, n_mfcc=13)
    ve = float(np.mean(np.abs(mfcc[1:4, :])))
    te = float(np.mean(np.abs(mfcc[1:, :])))
    vocal_ratio = ve / (te + 1e-8)
    vocal_density = float(np.clip((vocal_ratio - 1.8) / 1.2, 0.0, 1.0))

    # ── Bass energy ──
    S = np.abs(librosa.stft(y_mono))
    freqs = librosa.fft_frequencies(sr=sr)
    bass_mask = freqs < 150
    bass_e = float(np.mean(S[bass_mask, :]) / (np.mean(S) + 1e-8))
    bass_energy = float(np.clip(bass_e / (bass_e + 15.0), 0.0, 1.0))

    # ── Spectral centroid ──
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y_mono, sr=sr)))

    # ── Phrase map ──
    phrase_map = _segment_phrases(y_mono, sr, analysis_duration)
    phrase_map = _attach_phrase_energy(phrase_map, energy_curve)
    # ── Extended analysis ──────────────────────────────────────────
    phrase_map = _score_section_intensity(phrase_map, energy_curve, y_mono, sr)
    groove = _compute_groove_score(beat_times, downbeats, bpm_curve, tempo_stability)
    transition_windows = _build_transition_windows(phrase_map)
    dancefloor_profile = _analyze_dancefloor_profile(
        bpm=bpm,
        energy=mean_energy,
        groove=groove,
        spectral_centroid=centroid,
        phrase_map=phrase_map,
    )
    dj_hot_cues = _generate_dj_hot_cues(phrase_map, transition_windows, energy_curve, duration)
    transition_recommendations = _recommend_transition_techniques(phrase_map, transition_windows)
    genre_profile = classify_genre(
        bpm=bpm,
        groove_profile=groove,
        dj_features={"spectral_centroid": centroid},
        energy=mean_energy,
    )

    elapsed = time.time() - t0
    print(f"  [{track_id}] BPM={bpm:.1f} Key={camelot} Energy={energy_label} "
          f"Dur={duration:.0f}s Beats={len(beat_times)} Phrases={len(phrase_map)} "
          f"Groove={groove['score']:.2f}({groove['label']}) "
          f"({elapsed:.1f}s)")

    return {
        "song_id": f"rk{track_id}",
        "title": f"Track {track_id}",
        "bpm": round(bpm, 1),
        "key": key_result["key"],
        "camelot_key": camelot,
        "mode": mode,
        "key_profile": {
            "tonal_clarity": key_result["tonal_clarity"],
            "relative_ambiguity": key_result["relative_ambiguity"],
            "candidates": key_result["candidates"],
            "method": key_result["method"],
        },
        "energy": energy_label,
        "energy_rms": round(mean_energy, 4),
        "duration_sec": round(duration, 1),
        "analysis_duration_sec": round(analysis_duration, 1),
        "beat_points": [round(t, 3) for t in beat_times[:2000]],
        "bpm_curve": bpm_curve,
        "tempo_stability": tempo_stability,
        **beatgrid_summary,
        "energy_curve": energy_curve,
        "loudness_profile": loudness_profile,
        "time_signature": time_signature,
        "groove": groove,
        "danceability_score": dancefloor_profile["danceability_score"],
        "dancefloor_profile": dancefloor_profile,
        "genre_profile": genre_profile,
        "dj_hot_cues": dj_hot_cues,
        "transition_windows": transition_windows,
        "transition_recommendations": transition_recommendations,
        "downbeats": [round(d, 3) for d in downbeats[:1000]],
        "phrase_map": phrase_map,
        "has_stems": False,
        "stem_quality_score": 0.0,
        "stem_quality_profile": {"method": "not_available", "completeness": 0.0},
        "vocal_density": round(vocal_density, 2),
        "bass_energy": round(bass_energy, 2),
        "intro_is_clean": bool(transition_windows and transition_windows[0]["clean_candidate"]),
        "outro_is_clean": bool(transition_windows and transition_windows[-1]["clean_candidate"]),
        "intro_clean_score": 0.0,
        "outro_clean_score": 0.0,
        "has_drum_loop": tempo_stability >= 0.85,
        "spectral_centroid": round(centroid, 0),
    }


def _segment_phrases(y_mono, sr, duration):
    """Structural segmentation via spectral novelty peak-picking."""
    S = np.abs(librosa.stft(y_mono))
    novelty = librosa.onset.onset_strength(S=np.log1p(S), sr=sr)
    peak_frames = librosa.util.peak_pick(
        novelty, pre_max=3, post_max=3, pre_avg=5, post_avg=5,
        delta=0.1, wait=10,
    )
    novelty_times = librosa.frames_to_time(np.arange(len(novelty)), sr=sr)
    peak_times = novelty_times[peak_frames]

    boundaries = [0.0]
    last = 0.0
    for t in peak_times:
        if t - last >= 8.0:
            boundaries.append(float(t))
            last = t
    boundaries.append(duration)

    labels = ["intro","verse","bridge","drop","verse","bridge","drop","outro"]
    phrase_map = []
    for i in range(len(boundaries) - 1):
        label = labels[i % len(labels)]
        phrase_map.append({
            "label": label,
            "start": round(boundaries[i], 2),
            "end": round(boundaries[i+1], 2),
        })
    if len(phrase_map) < 2:
        phrase_map = [
            {"label":"intro","start":0.0,"end":duration*0.25},
            {"label":"drop","start":duration*0.25,"end":duration*0.75},
            {"label":"outro","start":duration*0.75,"end":duration},
        ]
    return phrase_map


# ══════════════════════════════════════════════════════════════════

def run_pipeline(tracks_dir="data/tracks", output_path="data/jetson_analysis.json"):
    track_ids = ["100","101","102","103","106","107","108"]
    results = {}

    print("=" * 65)
    print("  JETSON ANALYSIS PIPELINE")
    print("  librosa → TrackContext → stem_automix ready")
    print("=" * 65)

    t0 = time.time()
    for tid in track_ids:
        path = os.path.join(tracks_dir, f"{tid}.wav")
        if not os.path.exists(path):
            print(f"  [{tid}] SKIP: file not found at {path}")
            continue
        results[tid] = analyze_track(path, tid)

    elapsed = time.time() - t0

    # Save
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n  Total: {len(results)} tracks in {elapsed:.1f}s → {output_path}")

    # ── Summary Table ──
    print(f"\n{'─'*80}")
    print(f"  {'Track':>6}  {'BPM':>6}  {'Key':>8}  {'Energy':>8}  {'Dur':>5}  {'Groove':>7}  {'TimeSig':>8}  {'Phrases':>8}")
    print(f"  {'─'*80}")
    for tid in track_ids:
        t = results.get(tid)
        if t:
            groove = t.get("groove", {})
            groove_label = groove.get("label", "?") if groove else "?"
            ts = t.get("time_signature", {})
            ts_str = f"{ts.get('numerator',4)}/{ts.get('denominator',4)}" if ts else "4/4"
            print(f"  {tid:>6}  {t['bpm']:>5.1f}   {t['camelot_key']:>8}  {t['energy']:>8}  {t['duration_sec']:>4.0f}s  {groove_label:>7}  {ts_str:>8}  {len(t['phrase_map']):>8}")
    print()

    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks-dir", default="data/tracks")
    ap.add_argument("--output", default="data/jetson_analysis.json")
    args = ap.parse_args()
    run_pipeline(args.tracks_dir, args.output)
