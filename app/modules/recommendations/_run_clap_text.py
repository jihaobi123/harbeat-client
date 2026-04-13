#!/usr/bin/env python3
"""Subprocess entry point: generate CLAP text embedding for a query.

Usage: python _run_clap_text.py <query_text>
Outputs: JSON list of floats (the embedding vector) on stdout.

Runs in an isolated process to keep the CLAP model out of uvicorn memory.
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
        print("Usage: python _run_clap_text.py <query_text>", file=sys.stderr)
        sys.exit(1)

    query_text = sys.argv[1]

    try:
        import numpy as np
        import torch
        from transformers import ClapModel, AutoProcessor

        try:
            processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
            model = ClapModel.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
        except Exception:
            processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME)
            model = ClapModel.from_pretrained(CLAP_MODEL_NAME)
        model.eval()

        inputs = processor(text=[query_text], return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            features = model.get_text_features(**inputs)
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
