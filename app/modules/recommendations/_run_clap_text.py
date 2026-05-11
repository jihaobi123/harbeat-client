#!/usr/bin/env python3
"""Subprocess entry point: generate CLAP text embedding for a query.

Usage:
  python _run_clap_text.py <query_text>           single text -> single vector
  python _run_clap_text.py --batch                read JSON list from stdin,
                                                  output JSON list of vectors

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
CLAP_LOCAL_PATH = os.environ.get("CLAP_MODEL_PATH", os.path.join(_project_root, "data", "clap_model"))


def _load_clap():
    """Load CLAP model, preferring local path over download."""
    from transformers import ClapModel, AutoProcessor

    # 1. Try local directory (pre-downloaded)
    if os.path.isdir(CLAP_LOCAL_PATH) and os.path.isfile(os.path.join(CLAP_LOCAL_PATH, "config.json")):
        processor = AutoProcessor.from_pretrained(CLAP_LOCAL_PATH)
        model = ClapModel.from_pretrained(CLAP_LOCAL_PATH)
        return processor, model
    # 2. Try HF cache
    try:
        processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
        model = ClapModel.from_pretrained(CLAP_MODEL_NAME, local_files_only=True)
        return processor, model
    except Exception:
        pass
    # 3. Download from HuggingFace
    processor = AutoProcessor.from_pretrained(CLAP_MODEL_NAME)
    model = ClapModel.from_pretrained(CLAP_MODEL_NAME)
    return processor, model


def _embed_texts(texts: list[str], processor, model, device) -> list[list[float]]:
    """Batch-embed multiple texts at once, returning normalized vectors."""
    import numpy as np
    import torch

    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        features = model.get_text_features(**inputs)
        if hasattr(features, "pooler_output") and features.pooler_output is not None:
            arr = features.pooler_output.cpu().numpy()
        else:
            arr = features.cpu().numpy()

    # Normalize each row
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms < 1e-8, 1.0, norms)
    arr = arr / norms
    return arr.tolist()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python _run_clap_text.py <query_text>", file=sys.stderr)
        print("       python _run_clap_text.py --batch  (read JSON list from stdin)", file=sys.stderr)
        sys.exit(1)

    try:
        import torch
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        processor, model = _load_clap()
        model.to(device).eval()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(3)

    try:
        if sys.argv[1] == "--batch":
            texts = json.loads(sys.stdin.read())
            if not isinstance(texts, list):
                raise ValueError("stdin must be a JSON list of strings")
            embeddings = _embed_texts(texts, processor, model, device)
            json.dump(embeddings, sys.stdout)
        else:
            import numpy as np
            query_text = sys.argv[1]
            embeddings = _embed_texts([query_text], processor, model, device)
            json.dump(embeddings[0], sys.stdout)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
