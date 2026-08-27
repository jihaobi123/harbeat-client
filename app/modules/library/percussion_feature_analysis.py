"""Time-frequency analysis of drum and percussion timbre families.

The output deliberately prefers acoustically defensible families over exact
instrument names.  For example, a noisy wide-band transient can support the
``wide_clap`` family while ``clap`` remains only a candidate label.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import librosa
import numpy as np

from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


PERCUSSION_FEATURE_VERSION = "percussion_timbre_features_v1"
PERCUSSION_FAMILIES = (
    "full_snare",
    "wide_clap",
    "short_rim_snap",
    "short_metallic",
    "sustained_metallic",
    "low_pitched_drum",
    "mid_pitched_drum",
    "hand_drum_family",
    "continuous_high_percussion",
    "tonal_percussion",
    "repeated_tonal_motif",
)


def _clamp(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def _events(drum_analysis: dict | None) -> list[dict[str, Any]]:
    normalized = []
    for event_class, values in (((drum_analysis or {}).get("events") or {}).items()):
        if not isinstance(values, list):
            continue
        for value in values:
            item = value if isinstance(value, dict) else {"time": value}
            try:
                timestamp = float(item["time"])
            except (KeyError, TypeError, ValueError):
                continue
            normalized.append({
                "time": timestamp,
                "input_class": str(event_class).lower(),
                "input_confidence": _clamp(item.get("confidence", 0.75)),
            })
    return sorted(normalized, key=lambda item: item["time"])


def _onsets(audio: np.ndarray, sr: int) -> np.ndarray:
    envelope = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=256)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope, sr=sr, hop_length=256, units="frames"
    )
    return np.unique(librosa.frames_to_time(frames, sr=sr, hop_length=256))


def _descriptor(audio: np.ndarray, sr: int, event: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = float(event["time"])
    start = max(0, int((timestamp - 0.008) * sr))
    end = min(len(audio), start + int(0.62 * sr))
    clip = np.asarray(audio[start:end], dtype=float)
    if len(clip) < int(0.06 * sr):
        return None
    attack_length = min(len(clip), int(0.10 * sr))
    attack = clip[:attack_length] * np.hanning(attack_length)
    magnitude = np.abs(np.fft.rfft(attack)) + 1e-12
    power = magnitude ** 2
    frequencies = np.fft.rfftfreq(len(attack), 1.0 / sr)
    total = float(np.sum(power)) + 1e-12
    centroid = float(np.sum(frequencies * power) / total)
    spread = float(np.sqrt(np.sum(((frequencies - centroid) ** 2) * power) / total))
    flatness = float(np.exp(np.mean(np.log(magnitude))) / np.mean(magnitude))
    dominant_index = int(np.argmax(power))
    dominant = float(frequencies[dominant_index])
    prominence = float(np.max(magnitude) / (np.mean(magnitude) + 1e-12))

    frame_length = min(512, len(clip))
    rms = librosa.feature.rms(y=clip, frame_length=frame_length, hop_length=64, center=False)[0]
    peak = float(np.max(rms)) if len(rms) else 0.0
    active = np.where(rms >= peak * 0.18)[0] if peak > 0 else np.asarray([])
    decay = float((active[-1] + 1) * 64 / sr) if len(active) else 0.0
    late_start = min(len(clip), int(0.12 * sr))
    late_end = min(len(clip), int(0.45 * sr))
    late_rms = float(np.sqrt(np.mean(np.square(clip[late_start:late_end])))) if late_end > late_start else 0.0
    early_rms = float(np.sqrt(np.mean(np.square(clip[:max(1, int(0.05 * sr))])))) + 1e-10

    def ratio(low: float, high: float) -> float:
        mask = (frequencies >= low) & (frequencies < high)
        return float(np.sum(power[mask]) / total)

    return {
        **event,
        "spectral_centroid_hz": round(centroid, 3),
        "spectral_spread_hz": round(spread, 3),
        "spectral_flatness": round(flatness, 5),
        "dominant_frequency_hz": round(dominant, 3),
        "spectral_prominence": round(prominence, 3),
        "decay_sec": round(decay, 4),
        "late_early_ratio": round(late_rms / early_rms, 4),
        "low_ratio_45_250_hz": round(ratio(45.0, 250.0), 4),
        "mid_ratio_250_4000_hz": round(ratio(250.0, 4000.0), 4),
        "high_ratio_4000_hz_plus": round(ratio(4000.0, sr / 2.0 + 1.0), 4),
    }


def _range(item: dict[str, Any]) -> dict[str, float]:
    return {"start": round(item["time"], 4), "end": round(item["time"] + min(0.5, item["decay_sec"]), 4)}


def _fraction(items: list[dict[str, Any]], predicate, target_fraction: float) -> float:
    if not items:
        return 0.0
    return _clamp(sum(bool(predicate(item)) for item in items) / max(len(items) * target_fraction, 1.0))


def analyze_percussion_features(
    drums: np.ndarray | None,
    sr: int,
    *,
    drum_analysis: dict | None = None,
) -> dict[str, Any]:
    method = "percussion_stft_event_families_v1"
    if drums is None or sr <= 0 or len(drums) < sr:
        return {
            "version": PERCUSSION_FEATURE_VERSION,
            "status": "unavailable",
            "features": {
                name: unavailable_feature(
                    "drums_stem_unavailable", sources=["drums_stem"], analysis_method=method
                ) for name in PERCUSSION_FAMILIES
            },
            "events": [],
            "confidence": 0.0,
            "quality_flags": ["drums_stem_unavailable"],
        }

    drums = np.asarray(drums, dtype=float)
    duration = len(drums) / sr
    input_events = _events(drum_analysis)
    flags = []
    if not input_events:
        flags.append("drum_transcription_unavailable_using_onsets")
        input_events = [
            {"time": float(value), "input_class": "unassigned", "input_confidence": 0.45}
            for value in _onsets(drums, sr)[:1600]
        ]
    descriptors = [
        descriptor for item in input_events[:1600]
        if (descriptor := _descriptor(drums, sr, item)) is not None
    ]
    snare = [item for item in descriptors if item["input_class"] in {"snare", "clap", "rim", "rimshot"}]
    high = [item for item in descriptors if item["input_class"] in {"hihat", "cymbal", "ride", "crash"}]
    low_mid = [item for item in descriptors if item["input_class"] in {"kick", "tom", "percussion", "unassigned"}]

    predicates = {
        "full_snare": lambda x: 700 <= x["spectral_centroid_hz"] <= 4200 and x["decay_sec"] >= 0.075 and x["mid_ratio_250_4000_hz"] >= 0.35,
        "wide_clap": lambda x: x["spectral_spread_hz"] >= 1500 and x["spectral_flatness"] >= 0.11 and x["high_ratio_4000_hz_plus"] >= 0.08 and x["decay_sec"] <= 0.30,
        "short_rim_snap": lambda x: x["decay_sec"] <= 0.095 and x["spectral_prominence"] >= 7.0 and 900 <= x["dominant_frequency_hz"] <= 5000,
        "short_metallic": lambda x: x["spectral_centroid_hz"] >= 2500 and x["high_ratio_4000_hz_plus"] >= 0.12 and x["decay_sec"] < 0.16,
        "sustained_metallic": lambda x: x["spectral_centroid_hz"] >= 2500 and (x["decay_sec"] >= 0.16 or x["late_early_ratio"] >= 0.18),
        "low_pitched_drum": lambda x: 55 <= x["dominant_frequency_hz"] < 220 and x["spectral_prominence"] >= 5.0 and x["decay_sec"] >= 0.06,
        "mid_pitched_drum": lambda x: 220 <= x["dominant_frequency_hz"] < 900 and x["spectral_prominence"] >= 6.0 and x["decay_sec"] >= 0.055,
        "hand_drum_family": lambda x: 140 <= x["dominant_frequency_hz"] < 1200 and x["spectral_prominence"] >= 5.0 and 0.06 <= x["decay_sec"] <= 0.34 and x["mid_ratio_250_4000_hz"] >= 0.22,
        "tonal_percussion": lambda x: 180 <= x["dominant_frequency_hz"] <= 3200 and x["spectral_prominence"] >= 9.0 and x["spectral_flatness"] <= 0.18,
    }
    comparison = {
        "full_snare": snare,
        "wide_clap": snare,
        "short_rim_snap": snare,
        "short_metallic": high,
        "sustained_metallic": high,
        "low_pitched_drum": low_mid,
        "mid_pitched_drum": low_mid,
        "hand_drum_family": low_mid,
        "tonal_percussion": descriptors,
    }
    matches = {
        name: [item for item in comparison[name] if predicate(item)]
        for name, predicate in predicates.items()
    }

    high_times = np.asarray([item["time"] for item in high], dtype=float)
    high_rate = len(high_times) / max(duration, 1.0)
    intervals = np.diff(high_times)
    continuity = _clamp(high_rate / 5.5)
    if len(intervals) >= 4:
        continuity *= _clamp(1.0 - float(np.std(intervals)) / max(float(np.mean(intervals)), 1e-6))

    tonal = matches["tonal_percussion"]
    pitch_bins = [int(round(12 * np.log2(item["dominant_frequency_hz"] / 440.0))) for item in tonal]
    repeated = max(Counter(pitch_bins).values(), default=0)
    motif_score = _clamp(repeated / max(3.0, len(tonal) * 0.35))
    quality = _clamp(len(descriptors) / max(16.0, duration * 0.8))

    candidate_names = {
        "wide_clap": ["clap"],
        "short_rim_snap": ["rimshot", "finger_snap"],
        "short_metallic": ["closed_hihat", "cowbell", "clave"],
        "sustained_metallic": ["open_hihat", "ride", "crash"],
        "low_pitched_drum": ["low_tom", "surdo"],
        "mid_pitched_drum": ["tom", "conga", "bongo"],
        "hand_drum_family": ["conga", "bongo", "hand_drum"],
        "continuous_high_percussion": ["shaker", "tambourine", "continuous_hihat"],
        "tonal_percussion": ["cowbell", "clave", "woodblock", "tonal_drum"],
    }
    features = {}
    for name in predicates:
        items = comparison[name]
        matched = matches[name]
        score = _fraction(items, predicates[name], 0.32)
        features[name] = make_feature_evidence(
            score,
            threshold=0.58,
            confidence=quality,
            sources=["drums_stem", "drum_transcription"],
            analysis_method=method,
            time_ranges=[_range(item) for item in matched[:48]],
            evidence={
                "matched_event_count": len(matched),
                "comparison_event_count": len(items),
                "candidate_labels": candidate_names.get(name, []),
                "frequency_rule_hz": {
                    "short_metallic_min_centroid": 2500,
                    "low_pitched_drum_dominant": [55, 220],
                    "mid_pitched_drum_dominant": [220, 900],
                    "tonal_percussion_dominant": [180, 3200],
                },
            },
        )
    features["continuous_high_percussion"] = make_feature_evidence(
        continuity,
        threshold=0.52,
        confidence=quality,
        sources=["drums_stem", "drum_transcription"],
        analysis_method=method,
        time_ranges=[_range(item) for item in high[:48]],
        evidence={
            "high_event_rate_hz": round(high_rate, 4),
            "inter_event_count": len(intervals),
            "candidate_labels": candidate_names["continuous_high_percussion"],
        },
    )
    features["repeated_tonal_motif"] = make_feature_evidence(
        motif_score,
        threshold=0.58,
        confidence=quality,
        sources=["drums_stem"],
        analysis_method=method,
        time_ranges=[_range(item) for item in tonal[:48]],
        evidence={
            "tonal_event_count": len(tonal),
            "largest_repeated_pitch_bin_count": repeated,
            "pitch_resolution": "semitone",
        },
    )
    return {
        "version": PERCUSSION_FEATURE_VERSION,
        "status": "ready" if quality >= 0.55 else "degraded",
        "features": features,
        "events": descriptors,
        "confidence": round(quality, 4),
        "quality_flags": flags,
    }
