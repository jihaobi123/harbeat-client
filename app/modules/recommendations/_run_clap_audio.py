#!/usr/bin/env python3
"""Subprocess entry point: generate CLAP audio embedding for a song.

Usage: python _run_clap_audio.py <audio_file_path>
Outputs: JSON list of floats (the embedding vector) on stdout.

Runs in an isolated process to keep the CLAP model (~1.5 GB) out of
the uvicorn worker's memory.
"""
from __future__ import annotations

import json
import sys
import os

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

CLAP_MODEL_NAME = "laion/clap-htsat-unfused"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python _run_clap_audio.py <audio_file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(2)

    try:
        import librosa
        import numpy as np
        import torch
        from transformers import ClapModel, AutoProcessor

        # Load model (try local cache first)
        try:
            processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
            model = ClapModel.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
        except Exception:
            processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME)
            model = ClapModel.from_pretrained(CLAP_MODEL_NAME)
        model.eval()

        # Load audio at 48kHz (CLAP's expected sample rate)
        audio, sr = librosa.load(file_path, sr=48000, mono=True)

        # Generate audio embedding
        inputs = processor(audios=audio, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            features = model.get_audio_features(**inputs)
            if hasattr(features, "pooler_output") and features.pooler_output is not None:
                embedding = features.pooler_output.cpu().numpy().flatten()
            else:
                embedding = features.cpu().numpy().flatten()

        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 1e-8:
            embedding = embedding / norm

        json.dump(embedding.tolist(), sys.stdout)

    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
