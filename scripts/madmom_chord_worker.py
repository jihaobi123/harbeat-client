#!/usr/bin/env python3
"""Isolated JSON worker for madmom CNN+CRF chord recognition."""
from __future__ import annotations

import argparse
import collections
import collections.abc
import json
from pathlib import Path
import warnings

import numpy as np
import librosa
import soundfile as sf


def _compatibility_shims() -> None:
    for name in ("MutableSequence", "MutableMapping", "Mapping", "Sequence"):
        if not hasattr(collections, name):
            setattr(collections, name, getattr(collections.abc, name))
    for name, value in (
        ("float", float), ("int", int), ("bool", bool),
        ("complex", complex), ("object", object), ("str", str),
    ):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            if not hasattr(np, name):
                setattr(np, name, value)


class ChordRecognizer:
    """Reusable madmom processors for corpus evaluation and single-file workers."""

    def __init__(self) -> None:
        _compatibility_shims()
        from madmom.features.chords import CNNChordFeatureProcessor, CRFChordRecognitionProcessor

        self.feature_processor = CNNChordFeatureProcessor()
        self.recognition_processor = CRFChordRecognitionProcessor()

    def segments(self, audio_path: Path) -> list[dict]:
        from madmom.audio.signal import Signal

        audio, sample_rate = sf.read(str(audio_path), always_2d=False)
        if np.asarray(audio).ndim > 1:
            audio = np.mean(audio, axis=1)
        if int(sample_rate) != 44100:
            audio = librosa.resample(
                np.asarray(audio, dtype=np.float32), orig_sr=int(sample_rate), target_sr=44100,
            )
            sample_rate = 44100
        signal = Signal(np.asarray(audio, dtype=np.float32), sample_rate=int(sample_rate))
        features = self.feature_processor(signal)
        segments = self.recognition_processor(features)
        return [
            {
                "start": round(float(start), 4),
                "end": round(float(end), 4),
                "label": str(label),
            }
            for start, end, label in segments
            if float(end) > float(start)
        ]


def recognize(audio_path: Path, *, recognizer: ChordRecognizer | None = None) -> dict:
    _compatibility_shims()
    normalized = (recognizer or ChordRecognizer()).segments(audio_path)
    return {
        "engine": "madmom_cnn_crf_chords",
        "model_name": "madmom CNNChordFeatureProcessor + CRFChordRecognitionProcessor",
        "model_version": "0.16.1",
        "license": "BSD-3-Clause-code; bundled-model-license-review-required",
        "chord_vocabulary": "major_minor_no_chord",
        "segments": normalized,
        "segment_count": len(normalized),
        "limitations": [
            "major_minor_vocabulary_cannot_identify_sevenths_or_extended_chords",
            "major_minor_label_accuracy_is_below_0_80_on_guitarset",
            "change_activity_only_is_validated_on_isolated_guitar_accompaniment",
            "full_mix_target_domain_validation_is_still_required",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(recognize(args.audio), ensure_ascii=False))


if __name__ == "__main__":
    main()
