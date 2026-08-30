"""DJ-oriented analysis for separated vocals, drums, bass, and other stems."""
from __future__ import annotations

import os
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from app.modules.library.drum_analysis import analyze_drum_stem, empty_drum_analysis
from app.modules.library.feature_model_adapters import collect_mature_model_evidence
from app.modules.library.high_frequency_feature_analysis import (
    analyze_high_frequency_features,
    empty_high_frequency_features,
    summarize_feature_validation,
)
from app.modules.library.feature_calibration import apply_feature_calibration
from app.modules.library.style_feature_evidence import make_feature_evidence

STEM_NAMES = ("vocals", "drums", "bass", "other")


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    try:
        audio, sr = sf.read(path, dtype="float32", always_2d=True)
        return np.mean(audio, axis=1), int(sr)
    except sf.SoundFileError:
        # Some otherwise valid MP3 streams fail in libsndfile.  Audioread/
        # ffmpeg remains able to decode them, so keep reconstruction scoring
        # available instead of failing the complete feature-analysis job.
        audio, sr = librosa.load(path, sr=None, mono=True)
        return np.asarray(audio, dtype=np.float32), int(sr)


def _rms(audio: np.ndarray) -> float:
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _activity_curve(audio: np.ndarray, window_samples: int, count: int) -> list[float]:
    raw = []
    for index in range(count):
        start = index * window_samples
        end = min(start + window_samples, len(audio))
        raw.append(_rms(audio[start:end]))
    reference = float(np.percentile(raw, 95)) if raw else 0.0
    if reference <= 1e-8:
        return [0.0] * count
    return [round(float(np.clip(value / reference, 0.0, 1.0)), 4) for value in raw]


def _reconstruction_score(
    stems: dict[str, np.ndarray],
    original_path: str | None,
    expected_sr: int,
    length: int,
) -> tuple[float | None, str]:
    if not original_path or not os.path.isfile(original_path):
        return None, "original_audio_unavailable"
    original, sr = _load_mono(original_path)
    if sr != expected_sr or len(original) == 0:
        return None, "original_audio_incompatible"
    length = min(length, len(original))
    reconstructed = sum(audio[:length] for audio in stems.values())
    reference = _rms(original[:length]) + 1e-8
    error = _rms(reconstructed - original[:length]) / reference
    return float(np.clip(1.0 - error, 0.0, 1.0)), "waveform_reconstruction"


def _drum_loop_repetition(
    drums: np.ndarray | None,
    sr: int,
    *,
    bpm: float | None,
    beat_points: list[float] | None,
    downbeats: list[float] | None,
) -> dict[str, Any]:
    """Measure adjacent bar repetition instead of drum activity duration."""
    if drums is None or sr <= 0 or len(drums) < sr:
        return {"status": "unavailable", "score": 0.0, "bar_count": 0, "similarities": []}
    bars = np.asarray([] if downbeats is None else downbeats, dtype=float)
    bars = np.sort(bars[np.isfinite(bars) & (bars >= 0)])
    if len(bars) < 3:
        beats = np.asarray([] if beat_points is None else beat_points, dtype=float)
        beats = np.sort(beats[np.isfinite(beats) & (beats >= 0)])
        if len(beats) >= 12:
            bars = beats[::4]
        elif bpm and np.isfinite(bpm) and bpm > 0:
            bars = np.arange(0.0, len(drums) / sr, 240.0 / bpm)
    if len(bars) < 3:
        return {"status": "unavailable", "score": 0.0, "bar_count": 0, "similarities": []}

    vectors = []
    used_ranges = []
    for start, end in list(zip(bars[:-1], bars[1:]))[:96]:
        clip = np.asarray(drums[int(start * sr):int(end * sr)], dtype=float)
        if len(clip) < int(0.5 * sr):
            continue
        mel = librosa.feature.melspectrogram(
            y=clip, sr=sr, n_fft=min(2048, max(512, 2 ** int(np.floor(np.log2(len(clip)))))),
            hop_length=256, n_mels=24, power=2.0,
        )
        log_mel = librosa.power_to_db(mel + 1e-12, ref=np.max)
        target = np.linspace(0.0, 1.0, 16)
        source = np.linspace(0.0, 1.0, log_mel.shape[1])
        resized = np.vstack([np.interp(target, source, row) for row in log_mel])
        vector = resized.ravel()
        vector -= float(np.mean(vector))
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-8:
            continue
        vectors.append(vector / norm)
        used_ranges.append({"start": round(float(start), 4), "end": round(float(end), 4)})
    similarities = [
        float(np.clip(np.dot(left, right), -1.0, 1.0))
        for left, right in zip(vectors[:-1], vectors[1:])
    ]
    if len(similarities) < 2:
        return {"status": "unavailable", "score": 0.0, "bar_count": len(vectors), "similarities": []}
    normalized = np.clip((np.asarray(similarities) - 0.45) / 0.50, 0.0, 1.0)
    repeated_fraction = float(np.mean(np.asarray(similarities) >= 0.82))
    score = float(np.clip(0.65 * np.mean(normalized) + 0.35 * repeated_fraction, 0.0, 1.0))
    return {
        "status": "ready",
        "method": "bar_aligned_log_mel_self_similarity_v1",
        "score": round(score, 4),
        "bar_count": len(vectors),
        "adjacent_pair_count": len(similarities),
        "repeated_pair_fraction": round(repeated_fraction, 4),
        "similarities": [round(value, 4) for value in similarities[:95]],
        "time_ranges": used_ranges[:48],
    }


def analyze_stem_files(
    stem_paths: dict[str, str] | None,
    *,
    original_path: str | None = None,
    window_sec: float = 2.0,
    bpm: float | None = None,
    beat_points: list[float] | None = None,
    downbeats: list[float] | None = None,
    key_profile: dict | None = None,
) -> dict[str, Any]:
    """Analyze real separated stems into planner-ready activity metadata."""
    available = {
        name: path for name, path in (stem_paths or {}).items()
        if name in STEM_NAMES and path and os.path.isfile(path)
    }
    loaded: dict[str, np.ndarray] = {}
    sample_rate = 0
    for name in STEM_NAMES:
        path = available.get(name)
        if not path:
            continue
        audio, sr = _load_mono(path)
        if sample_rate and sr != sample_rate:
            continue
        sample_rate = sample_rate or sr
        loaded[name] = audio

    completeness = len(loaded) / len(STEM_NAMES)
    if not loaded or sample_rate <= 0:
        return {
            "has_complete_stems": False,
            "stem_quality_score": 0.0,
            "stem_quality_method": "completeness_reconstruction_proxy",
            "stem_quality_profile": {
                "method": "reconstruction_completeness_proxy_v2",
                "completeness": 0.0,
                "reconstruction_score": 0.0,
                "reconstruction_quality": None,
                "reconstruction_method": "unavailable",
                "separation_reliability": None,
                "leakage_risk": None,
                "source_quality_proxy": 0.0,
                "quality_status": "unavailable",
            },
            "stem_activity": {name: 0.0 for name in STEM_NAMES},
            "stem_activity_windows": [],
            "intro_is_clean": False,
            "outro_is_clean": False,
            "intro_clean_score": 0.0,
            "outro_clean_score": 0.0,
            "has_drum_loop": False,
            "drum_analysis": empty_drum_analysis(),
            "feature_analysis": empty_high_frequency_features(),
            "model_evidence": {"status": "unavailable", "routes": {}},
        }

    length = min(len(audio) for audio in loaded.values())
    window_samples = max(1, int(sample_rate * window_sec))
    count = max(1, int(np.ceil(length / window_samples)))
    curves = {
        name: _activity_curve(loaded.get(name, np.zeros(length)), window_samples, count)
        for name in STEM_NAMES
    }

    windows = []
    for index in range(count):
        windows.append({
            "start": round(index * window_samples / sample_rate, 3),
            "end": round(min((index + 1) * window_samples, length) / sample_rate, 3),
            **{name: curves[name][index] for name in STEM_NAMES},
        })

    activity = {
        name: round(float(np.mean(curves[name])), 4) if curves[name] else 0.0
        for name in STEM_NAMES
    }
    reconstruction, reconstruction_method = _reconstruction_score(
        loaded, original_path, sample_rate, length
    )
    # Keep the historical score stable for automix consumers, but no longer
    # present it as separation purity.  Missing reconstruction evidence uses
    # the previous neutral component only for this compatibility alias.
    reconstruction_component = 0.75 if reconstruction is None else reconstruction
    quality = completeness * (0.75 + 0.25 * reconstruction_component)
    source_quality_proxy = min(0.85, quality)
    vocals = curves["vocals"]
    drums = curves["drums"]
    bass = curves["bass"]
    intro_clean_score = float(np.clip(
        1.0 - (0.8 * vocals[0]) - (0.2 * bass[0]),
        0.0,
        1.0,
    )) if completeness == 1.0 and vocals and bass else 0.0
    outro_clean_score = float(np.clip(
        1.0 - (0.8 * vocals[-1]) - (0.2 * bass[-1]),
        0.0,
        1.0,
    )) if completeness == 1.0 and vocals and bass else 0.0
    model_evidence = collect_mature_model_evidence(
        available,
        original_path=original_path,
    )
    loop_analysis = _drum_loop_repetition(
        loaded.get("drums"), sample_rate, bpm=bpm,
        beat_points=beat_points, downbeats=downbeats,
    )
    drum_analysis = analyze_drum_stem(
        loaded.get("drums"),
        sample_rate,
        bpm=bpm,
        beat_points=beat_points,
        downbeats=downbeats,
        separation_quality=quality,
        density_window_sec=window_sec,
        model_route=(model_evidence.get("routes") or {}).get("drum_transcription"),
    )
    feature_analysis = analyze_high_frequency_features(
        loaded,
        sample_rate,
        bpm=bpm,
        beat_points=beat_points,
        downbeats=downbeats,
        drum_analysis=drum_analysis,
        key_profile=key_profile,
        # Reconstruct from already-loaded stems inside the analyzer.  Avoid a
        # second full-song decode and keep memory bounded in background jobs.
        original_audio=None,
        model_evidence=model_evidence,
    )
    production = (feature_analysis.get("feature_groups") or {}).get("production")
    if isinstance(production, dict):
        production["sampled_loop_tendency"] = apply_feature_calibration(
            make_feature_evidence(
                float(loop_analysis.get("score", 0.0)),
                threshold=0.62,
                confidence=float(np.clip(source_quality_proxy, 0.0, 1.0)),
                measurement_confidence=float(np.clip(source_quality_proxy, 0.0, 1.0)),
                source_quality=float(np.clip(source_quality_proxy, 0.0, 1.0)),
                estimator_quality=0.72,
                sources=["drums_stem", "bar_grid"],
                analysis_method="bar_aligned_log_mel_self_similarity_v1",
                time_ranges=list(loop_analysis.get("time_ranges") or []),
                evidence={
                    **loop_analysis,
                    "semantic_limitation": "bar repetition is not proof that a copyrighted sample was used",
                },
            ),
            group="production",
            name="sampled_loop_tendency",
        )
        feature_analysis["validation_summary"] = summarize_feature_validation(
            feature_analysis.get("feature_groups") or {},
        )
    feature_analysis.setdefault("music_context", {})["drum_loop_analysis"] = loop_analysis

    return {
        "has_complete_stems": completeness == 1.0,
        "stem_quality_score": round(float(np.clip(quality, 0.0, 1.0)), 4),
        "stem_quality_method": "completeness_reconstruction_proxy",
        "stem_quality_profile": {
            "method": "reconstruction_completeness_proxy_v2",
            "completeness": round(completeness, 4),
            # Compatibility alias.  New consumers should use the nullable,
            # explicitly measured reconstruction_quality field below.
            "reconstruction_score": round(reconstruction_component, 4),
            "reconstruction_quality": (
                round(reconstruction, 4) if reconstruction is not None else None
            ),
            "reconstruction_method": reconstruction_method,
            "separation_reliability": None,
            "leakage_risk": None,
            "source_quality_proxy": round(source_quality_proxy, 4),
            "quality_status": "reconstruction_only",
        },
        "stem_activity": activity,
        "stem_activity_windows": windows,
        "intro_is_clean": bool(completeness == 1.0 and vocals and vocals[0] < 0.25),
        "outro_is_clean": bool(completeness == 1.0 and vocals and vocals[-1] < 0.25),
        "intro_clean_score": round(intro_clean_score, 4),
        "outro_clean_score": round(outro_clean_score, 4),
        "has_drum_loop": bool(loop_analysis.get("score", 0.0) >= 0.62),
        "drum_loop_analysis": loop_analysis,
        "drum_analysis": drum_analysis,
        "feature_analysis": feature_analysis,
        "model_evidence": model_evidence,
    }
