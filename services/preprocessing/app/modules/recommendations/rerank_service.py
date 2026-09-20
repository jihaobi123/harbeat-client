"""CLAP semantic reranking of Spotify candidate tracks.

Ported from FinalReco/services/rerank_service.py, adapted for the main
FastAPI service's subprocess-isolated CLAP architecture.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

_CLAP_TEXT_SCRIPT = __import__("os").path.join(
    __import__("os").path.dirname(__file__), "_run_clap_text.py"
)


def _encode_texts_batch(texts: List[str]) -> np.ndarray:
    """Encode multiple texts via a single CLAP subprocess call (--batch mode).

    Returns (N, 512) numpy array of L2-normalized vectors.
    """
    if not texts:
        return np.empty((0, 512), dtype=np.float32)

    result = subprocess.run(
        [sys.executable, _CLAP_TEXT_SCRIPT, "--batch"],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[-500:]
        raise RuntimeError(
            f"CLAP text batch subprocess exit={result.returncode} stderr={stderr}"
        )
    arr = np.array(json.loads(result.stdout), dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr


def _normalize(vector: np.ndarray) -> np.ndarray:
    """L2-normalize a vector (safe against zero vectors)."""
    arr = np.asarray(vector, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-8)


def rerank_tracks(vibe_description: str, tracks: List[dict]) -> List[dict]:
    """Re-rank Spotify candidate tracks by CLAP semantic similarity.

    Encodes the vibe description and each track's "name + artist" text into
    the same CLAP vector space, then sorts by cosine similarity.

    Returns the same list of tracks, each enriched with a ``semantic_score``
    field and sorted highest-first.
    """
    if not tracks:
        return []

    # Build text representations for all candidates
    candidate_texts: List[str] = []
    for track in tracks:
        name = str(track.get("name") or track.get("track_name") or "")
        artists_data = track.get("artists") or []
        if artists_data and isinstance(artists_data[0], dict):
            artists = ", ".join(
                str((artist or {}).get("name") or "") for artist in artists_data
            )
        else:
            artists = str(track.get("artist") or "")
        candidate_texts.append(
            " ".join(part for part in [name, artists] if part).strip()
        )

    # Encode everything in one batch: [vibe_description] + candidate_texts
    all_texts = [vibe_description] + candidate_texts
    try:
        all_embeddings = _encode_texts_batch(all_texts)
    except Exception:
        logger.warning("[rerank] CLAP batch encoding failed, returning unsorted tracks", exc_info=True)
        return tracks

    query_vector = _normalize(all_embeddings[0])
    candidate_embeddings = all_embeddings[1:]

    scored = []
    for track, embedding in zip(tracks, candidate_embeddings):
        score = float(np.dot(query_vector, _normalize(embedding)))
        enriched = dict(track)
        enriched["semantic_score"] = round(score, 6)
        scored.append((score, enriched))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [track for _, track in scored]
