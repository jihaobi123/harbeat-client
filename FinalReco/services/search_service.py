from __future__ import annotations

from typing import Dict, List, Optional

from services.clap_service import encode_texts
from services.library_service import create_collection


def _style_bonus(row: dict, style_ratios: Dict[str, float]) -> float:
    if not style_ratios:
        return 0.0
    styles = row.get("dominant_styles") or []
    if not isinstance(styles, list):
        return 0.0
    normalized = {str(k).strip().lower(): float(v) for k, v in (style_ratios or {}).items() if str(k).strip()}
    if not normalized:
        return 0.0
    return max((normalized.get(str(style).strip().lower(), 0.0) for style in styles), default=0.0)


def _rows_from_query_results(results: dict) -> List[dict]:
    metadatas = results.get("metadatas", [[]])
    distances = results.get("distances", [[]])
    documents = results.get("documents", [[]])
    rows = []

    for metadata, distance, document in zip(
        metadatas[0] if metadatas else [],
        distances[0] if distances else [],
        documents[0] if documents else [],
    ):
        item = dict(metadata or {})
        item["distance"] = float(distance)
        item["document"] = document
        rows.append(item)

    return rows


def search_collection(query_text: str, collection_name: str, top_k: int = 10) -> List[dict]:
    collection = create_collection(collection_name)
    query_embedding = encode_texts([query_text])[0].flatten().tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas", "distances", "documents"],
    )

    rows = _rows_from_query_results(results)
    rows.sort(key=lambda item: item.get("distance", 0.0))
    return rows


def fetch_with_multiplier(
    collection_name: str,
    target_length: int,
    style_ratios: Dict[str, float],
    multiplier: int = 5,
    query_text: Optional[str] = None,
) -> List[dict]:
    """
    Oversampling candidate recall for DJ planning.

    If query_text is provided, this function performs semantic query recall from ChromaDB.
    If query_text is empty, it falls back to collection.get(...) and still returns an
    oversampled pool sorted by style preference + distance proxy.
    """
    if target_length <= 0:
        return []

    collection = create_collection(collection_name)
    top_k = max(target_length * max(1, multiplier), target_length)

    rows: List[dict] = []
    if query_text and query_text.strip():
        query_embedding = encode_texts([query_text])[0].flatten().tolist()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["metadatas", "distances", "documents"],
        )
        rows = _rows_from_query_results(results)
    else:
        # No semantic query text: recall directly from the collection.
        payload = collection.get(limit=top_k, include=["metadatas", "documents"])
        metadatas = payload.get("metadatas", []) or []
        documents = payload.get("documents", []) or []
        for idx, metadata in enumerate(metadatas):
            item = dict(metadata or {})
            item["distance"] = 1.0  # neutral distance when no query text is supplied
            item["document"] = documents[idx] if idx < len(documents) else ""
            rows.append(item)

    # Re-rank oversampled rows: semantic distance first, style bonus second.
    for row in rows:
        row["_style_bonus"] = _style_bonus(row, style_ratios)

    rows.sort(key=lambda item: (item.get("distance", 1.0), -item.get("_style_bonus", 0.0)))
    for row in rows:
        row.pop("_style_bonus", None)

    return rows[:top_k]
