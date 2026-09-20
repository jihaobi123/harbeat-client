#!/usr/bin/env python3
"""Small JSON adapter for madmom's CNN key recognizer.

Run this script from a dedicated Python 3.10 environment because upstream
madmom 0.16.1 is not compatible with the API removals in Python 3.12.
"""
from __future__ import annotations

import json
import sys
import collections
import collections.abc
import warnings

import numpy as np
import librosa
import soundfile as sf

# madmom 0.16.1 still imports these aliases from ``collections``. Python 3.10
# moved them to ``collections.abc``; keep the compatibility shim isolated in
# this adapter instead of patching the application process.
for _name in ("MutableSequence", "MutableMapping", "Mapping", "Sequence"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
for _name, _value in (
    ("float", float), ("int", int), ("bool", bool),
    ("complex", complex), ("object", object), ("str", str),
):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        if not hasattr(np, _name):
            setattr(np, _name, _value)

from madmom.features.key import CNNKeyRecognitionProcessor, KEY_LABELS
from madmom.audio.signal import Signal


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: madmom_key_cli.py AUDIO_FILE", file=sys.stderr)
        return 2
    audio, sample_rate = sf.read(sys.argv[1], always_2d=False)
    if np.asarray(audio).ndim > 1:
        audio = np.mean(audio, axis=1)
    if int(sample_rate) != 44100:
        audio = librosa.resample(
            np.asarray(audio, dtype=np.float32), orig_sr=int(sample_rate), target_sr=44100,
        )
        sample_rate = 44100
    signal = Signal(np.asarray(audio, dtype=np.float32), sample_rate=int(sample_rate))
    probabilities = np.asarray(CNNKeyRecognitionProcessor()(signal), dtype=float).reshape(-1)
    indices = np.argsort(probabilities)[::-1][:3]
    payload = {
        "key": KEY_LABELS[int(indices[0])],
        "confidence": float(probabilities[int(indices[0])]),
        "candidates": [
            {"key": KEY_LABELS[int(index)], "score": float(probabilities[int(index)])}
            for index in indices
        ],
        "engine": "madmom_cnn_key_recognition",
        "model_version": "0.16.1",
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
