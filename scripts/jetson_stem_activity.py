#!/usr/bin/env python3
"""
Generate stem_activity_windows from full mix using spectral analysis.

For each song, split into ~2s windows and estimate per-window:
  - vocals: harmonic energy in 300-3000Hz
  - bass: energy below 150Hz
  - drums: percussive/transient energy
  - other: remaining harmonic energy above 3000Hz

This feeds directly into RK3588's strategy_selector to enable
differentiated stem-aware preset selection.
"""

import json
import os
import sys
import numpy as np
import librosa


def compute_stem_activity(y_mono, sr, window_sec=2.0):
    """
    Split audio into windows, estimate per-stem activity per window.

    Returns list[dict] with {start, end, vocals, drums, bass, other}.
    """
    # Harmonic-percussive separation
    y_harm, y_perc = librosa.effects.hpss(y_mono)

    hop = int(sr * window_sec)
    total_samples = len(y_mono)
    windows = []

    for start_sample in range(0, total_samples, hop):
        end_sample = min(start_sample + hop, total_samples)
        if end_sample - start_sample < sr * 0.5:
            break

        h_seg = y_harm[start_sample:end_sample]
        p_seg = y_perc[start_sample:end_sample]
        full_seg = y_mono[start_sample:end_sample]

        # FFT for frequency analysis
        n_fft = min(2048, len(full_seg))
        if n_fft < 128:
            continue

        D = np.abs(librosa.stft(full_seg, n_fft=n_fft))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        total_energy = np.sum(D) + 1e-10

        # Bass: < 150Hz
        bass_energy = np.sum(D[freqs < 150, :]) / total_energy

        # Drums: percussive component energy (broadband transients)
        p_energy = np.sum(np.abs(p_seg)) / (np.sum(np.abs(full_seg)) + 1e-10)

        # Vocals: harmonic energy in 300-3000Hz
        vocal_mask = (freqs >= 300) & (freqs <= 3000)
        vocal_energy = np.sum(D[vocal_mask, :]) / total_energy * 0.7  # scale

        # Other: harmonic energy above 3000Hz
        other_mask = freqs > 3000
        other_energy = np.sum(D[other_mask, :]) / total_energy * 1.5

        # Normalize to 0-1 range per window
        total_stem = max(bass_energy + p_energy + vocal_energy + other_energy, 0.01)

        windows.append({
            "start": round(float(start_sample / sr), 2),
            "end": round(float(end_sample / sr), 2),
            "vocals": round(float(min(1.0, vocal_energy / total_stem * 2.5)), 2),
            "drums": round(float(min(1.0, p_energy / total_stem * 3.0)), 2),
            "bass": round(float(min(1.0, bass_energy / total_stem * 3.0)), 2),
            "other": round(float(min(1.0, other_energy / total_stem * 2.0)), 2),
        })

    return windows


def compute_global_stem_activity(windows):
    """Aggregate per-window activity into global averages."""
    if not windows:
        return {"vocals": 0.5, "drums": 0.5, "bass": 0.5, "other": 0.5}
    n = len(windows)
    return {
        "vocals": round(sum(w["vocals"] for w in windows) / n, 2),
        "drums": round(sum(w["drums"] for w in windows) / n, 2),
        "bass": round(sum(w["bass"] for w in windows) / n, 2),
        "other": round(sum(w["other"] for w in windows) / n, 2),
    }


def enrich_analysis(input_path, output_path):
    """Load Jetson analysis, add stem_activity_windows."""
    with open(input_path) as f:
        analysis = json.load(f)

    tracks_dir = os.path.join(os.path.dirname(input_path), "tracks")

    for tid, info in analysis.items():
        wav_path = os.path.join(tracks_dir, f"{tid}.wav")
        if not os.path.exists(wav_path):
            print(f"  [{tid}] SKIP: no WAV at {wav_path}")
            continue

        print(f"  [{tid}] Computing stem activity windows...", end=" ", flush=True)

        y, sr = librosa.load(wav_path, sr=None, mono=False)
        if y.ndim == 2:
            y_mono = np.mean(y, axis=0)
        else:
            y_mono = y

        windows = compute_stem_activity(y_mono, sr)
        global_act = compute_global_stem_activity(windows)

        info["stem_activity_windows"] = windows
        info["stem_activity"] = global_act
        info["vocal_density"] = global_act["vocals"]
        info["bass_energy"] = global_act["bass"]

        print(f"{len(windows)} windows, "
              f"V={global_act['vocals']:.2f} D={global_act['drums']:.2f} "
              f"B={global_act['bass']:.2f} O={global_act['other']:.2f}")

    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved → {output_path}")
    return analysis


if __name__ == "__main__":
    enrich_analysis("data/jetson_analysis.json", "data/jetson_analysis_enriched.json")
