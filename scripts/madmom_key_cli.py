#!/usr/bin/env python3
"""Small JSON adapter for madmom's CNN key recognizer.

Run this script from a dedicated Python 3.10 environment because upstream
madmom 0.16.1 is not compatible with the API removals in Python 3.12.
"""
from __future__ import annotations

import json
import sys

import numpy as np
from madmom.features.key import CNNKeyRecognitionProcessor, KEY_LABELS


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: madmom_key_cli.py AUDIO_FILE", file=sys.stderr)
        return 2
    probabilities = np.asarray(CNNKeyRecognitionProcessor()(sys.argv[1]), dtype=float).reshape(-1)
    indices = np.argsort(probabilities)[::-1][:3]
    payload = {
        "key": KEY_LABELS[int(indices[0])],
        "confidence": float(probabilities[int(indices[0])]),
        "candidates": [
            {"key": KEY_LABELS[int(index)], "score": float(probabilities[int(index)])}
            for index in indices
        ],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
