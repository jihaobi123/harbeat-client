from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import numpy as np

from app.shared.config import get_settings

logger = logging.getLogger(__name__)


def _normalise_label(label: str) -> str:
    text = label.strip().lower()
    for prefix in ("genre---", "style---", "discogs400---"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.replace("_", " ").replace("---", " ").strip()


@lru_cache(maxsize=1)
def _load_essentia_models() -> tuple[Any, Any]:
    settings = get_settings()
    embedding_model_path = settings.essentia_discogs_effnet_model_path
    classifier_model_path = settings.essentia_discogs_classifier_model_path

    if not embedding_model_path or not classifier_model_path:
        raise RuntimeError(
            "Essentia Discogs EffNet model paths are not configured. "
            "Set ESSENTIA_DISCOGS_EFFNET_MODEL_PATH and ESSENTIA_DISCOGS_CLASSIFIER_MODEL_PATH."
        )
    if not os.path.isfile(embedding_model_path):
        raise FileNotFoundError(f"Essentia embedding model not found: {embedding_model_path}")
    if not os.path.isfile(classifier_model_path):
        raise FileNotFoundError(f"Essentia classifier model not found: {classifier_model_path}")

    try:
        import essentia.standard as es
    except Exception as exc:
        raise RuntimeError("Essentia is not installed or cannot be imported") from exc

    embedding_model = es.TensorflowPredictEffnetDiscogs(graphFilename=embedding_model_path)
    classifier_model = es.TensorflowPredict2D(graphFilename=classifier_model_path)
    return embedding_model, classifier_model


def _extract_predictions(predictions: Any, classifier_model: Any, top_k: int) -> list[dict[str, Any]]:
    scores = np.asarray(predictions, dtype=float)
    if scores.ndim > 1:
        scores = np.mean(scores, axis=0)
    scores = scores.reshape(-1)

    labels: list[str] = []
    metadata = getattr(classifier_model, "metadata", lambda: {})()
    classes = metadata.get("classes") or metadata.get("labels") or []
    if isinstance(classes, dict):
        classes = classes.get("classes") or classes.get("labels") or []
    if classes:
        labels = [str(item) for item in classes]

    if not labels or len(labels) != len(scores):
        labels = [f"discogs_label_{idx}" for idx in range(len(scores))]

    top_indices = np.argsort(scores)[::-1][:top_k]
    result: list[dict[str, Any]] = []
    for idx in top_indices:
        confidence = float(scores[idx])
        if confidence <= 0:
            continue
        result.append({
            "name": _normalise_label(labels[int(idx)]),
            "confidence": round(confidence, 4),
            "source": "essentia_discogs_effnet",
        })
    return result


def _metadata_fallback_genres(title: str, artist: str, top_k: int) -> list[dict[str, Any]]:
    try:
        from app.modules.library.bpm_lookup import lookup_track_info
        info = lookup_track_info(title, artist)
    except Exception:
        logger.debug("genre metadata fallback failed", exc_info=True)
        return []

    if not info:
        return []
    raw_genres = info.get("genres") or info.get("genre") or []
    if isinstance(raw_genres, str):
        raw_genres = [raw_genres]
    genres = []
    for item in raw_genres[:top_k]:
        if not item:
            continue
        genres.append({
            "name": _normalise_label(str(item)),
            "confidence": 0.45,
            "source": "metadata_fallback",
        })
    return genres


def analyze_genres(file_path: str, title: str = "", artist: str = "", top_k: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    top_k = top_k or settings.essentia_genre_top_k

    try:
        import essentia.standard as es
        embedding_model, classifier_model = _load_essentia_models()
        audio = es.MonoLoader(filename=file_path, sampleRate=16000, resampleQuality=4)()
        embeddings = embedding_model(audio)
        predictions = classifier_model(embeddings)
        genres = _extract_predictions(predictions, classifier_model, top_k)
        return {
            "genres": genres,
            "genre_status": "completed",
            "genre_source": "essentia_discogs_effnet",
            "genre_error": None,
        }
    except Exception as exc:
        logger.warning("Essentia Discogs EffNet genre analysis failed: %s", exc)
        fallback = _metadata_fallback_genres(title, artist, top_k)
        if fallback:
            return {
                "genres": fallback,
                "genre_status": "completed_with_fallback",
                "genre_source": "metadata_fallback",
                "genre_error": str(exc),
            }
        return {
            "genres": [],
            "genre_status": "error",
            "genre_source": "essentia_discogs_effnet",
            "genre_error": str(exc),
        }
