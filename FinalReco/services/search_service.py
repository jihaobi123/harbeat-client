from __future__ import annotations

from math import floor
from typing import Dict, List, Optional, Tuple

from services.clap_service import encode_texts
from services.library_service import create_collection


def _normalize_style_ratios(style_ratios: Dict[str, float]) -> Dict[str, float]:
    cleaned: Dict[str, float] = {}
    for key, value in (style_ratios or {}).items():
        name = str(key).strip().lower()
        if not name:
            continue
        try:
            ratio = float(value)
        except (TypeError, ValueError):
            continue
        if ratio > 0:
            cleaned[name] = ratio
    total = sum(cleaned.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in cleaned.items()}


def _extract_styles(row: dict) -> List[str]:
    styles = row.get("dominant_styles") or row.get("metadata", {}).get("dominant_styles") or []
    if isinstance(styles, list):
        return [str(s).strip().lower() for s in styles if str(s).strip()]
    if styles:
        return [str(styles).strip().lower()]
    return []


def _extract_energy(row: dict) -> float:
    raw = row.get("energy", row.get("metadata", {}).get("energy", 5.0))
    try:
        return max(1.0, min(10.0, float(raw)))
    except (TypeError, ValueError):
        return 5.0


def _style_bonus(row: dict, style_ratios: Dict[str, float]) -> float:
    normalized = _normalize_style_ratios(style_ratios)
    if not normalized:
        return 0.0
    styles = _extract_styles(row)
    return max((normalized.get(style, 0.0) for style in styles), default=0.0)


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
    recall_all_under: int = 0,
) -> List[dict]:
    if target_length <= 0:
        return []

    collection = create_collection(collection_name)

    collection_size = 0
    try:
        collection_size = int(collection.count())
    except Exception:
        collection_size = 0

    top_k = max(target_length * max(1, multiplier), target_length)
    if recall_all_under > 0 and collection_size > 0 and collection_size <= recall_all_under:
        top_k = collection_size

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
        payload = collection.get(limit=top_k, include=["metadatas", "documents"])
        metadatas = payload.get("metadatas", []) or []
        documents = payload.get("documents", []) or []
        for idx, metadata in enumerate(metadatas):
            item = dict(metadata or {})
            item["distance"] = 1.0
            item["document"] = documents[idx] if idx < len(documents) else ""
            rows.append(item)

    for row in rows:
        row["_style_bonus"] = _style_bonus(row, style_ratios)

    rows.sort(key=lambda item: (item.get("distance", 1.0), -item.get("_style_bonus", 0.0)))
    for row in rows:
        row.pop("_style_bonus", None)

    return rows[:top_k]


def _build_style_targets(style_ratios: Dict[str, float], slot_count: int) -> Dict[str, int]:
    normalized = _normalize_style_ratios(style_ratios)
    if not normalized or slot_count <= 0:
        return {}

    floors: Dict[str, int] = {}
    fractional: List[Tuple[float, str]] = []
    used = 0
    for style, ratio in normalized.items():
        raw = ratio * slot_count
        val = floor(raw)
        floors[style] = val
        used += val
        fractional.append((raw - val, style))

    fractional.sort(reverse=True)
    idx = 0
    while used < slot_count and fractional:
        style = fractional[idx % len(fractional)][1]
        floors[style] = floors.get(style, 0) + 1
        used += 1
        idx += 1

    return floors


def _split_energy_stages(target_energy_curve: List[float], target_length: int) -> List[dict]:
    curve = [max(1.0, min(10.0, float(v))) for v in (target_energy_curve or [])]
    if not curve:
        curve = [7.0] * target_length
    if len(curve) < target_length:
        curve.extend([curve[-1]] * (target_length - len(curve)))
    curve = curve[:target_length]

    stage_count = min(3, target_length)
    base = target_length // stage_count
    remainder = target_length % stage_count

    stages: List[dict] = []
    cursor = 0
    for stage_idx in range(stage_count):
        slot_count = base + (1 if stage_idx < remainder else 0)
        values = curve[cursor: cursor + slot_count]
        cursor += slot_count
        e_min = max(1.0, min(values) - 0.6)
        e_max = min(10.0, max(values) + 0.6)
        stages.append(
            {
                "stage_idx": stage_idx,
                "slot_count": slot_count,
                "energy_min": round(e_min, 3),
                "energy_max": round(e_max, 3),
                "target_curve": values,
            }
        )
    return stages


def _pick_rows_for_style(rows: List[dict], style: str, count: int, used_ids: set[str]) -> List[dict]:
    picked: List[dict] = []
    if count <= 0:
        return picked
    for row in rows:
        track_id = str(row.get("spotify_id") or row.get("track_id") or row.get("id") or "").strip()
        if not track_id or track_id in used_ids:
            continue
        styles = _extract_styles(row)
        if style in styles:
            picked.append(row)
            used_ids.add(track_id)
            if len(picked) >= count:
                break
    return picked


def fetch_stage_candidates(
    collection_name: str,
    target_length: int,
    target_energy_curve: List[float],
    style_ratios: Dict[str, float],
    multiplier: int = 5,
    query_text: Optional[str] = None,
    recall_all_under: int = 0,
) -> Dict[str, object]:
    """
    Stage-wise recall for DJ planning:
    1) Oversample pool from collection
    2) Split target energy curve into 3 macro stages
    3) For each stage, filter by energy range first
    4) Enforce style quota inside stage as much as possible
    """
    base_rows = fetch_with_multiplier(
        collection_name=collection_name,
        target_length=target_length,
        style_ratios=style_ratios,
        multiplier=multiplier,
        query_text=query_text,
        recall_all_under=recall_all_under,
    )

    stages = _split_energy_stages(target_energy_curve, target_length)
    used_ids: set[str] = set()
    merged_pool: List[dict] = []
    stage_outputs: List[dict] = []

    normalized = _normalize_style_ratios(style_ratios)

    for stage in stages:
        slot_count = int(stage["slot_count"])
        e_min = float(stage["energy_min"])
        e_max = float(stage["energy_max"])

        energy_filtered = [
            row for row in base_rows
            if e_min <= _extract_energy(row) <= e_max
        ]
        if not energy_filtered:
            energy_filtered = list(base_rows)

        # Stable sort by distance and style bonus within stage.
        energy_filtered.sort(key=lambda r: (r.get("distance", 1.0), -_style_bonus(r, normalized)))

        style_target = _build_style_targets(normalized, slot_count)
        local_used = set(used_ids)
        stage_selected: List[dict] = []

        for style, quota in style_target.items():
            stage_selected.extend(_pick_rows_for_style(energy_filtered, style, quota, local_used))

        for row in energy_filtered:
            if len(stage_selected) >= slot_count:
                break
            track_id = str(row.get("spotify_id") or row.get("track_id") or row.get("id") or "").strip()
            if not track_id or track_id in local_used:
                continue
            stage_selected.append(row)
            local_used.add(track_id)

        used_ids = local_used

        style_actual: Dict[str, int] = {}
        for row in stage_selected:
            styles = _extract_styles(row)
            if not styles:
                style_actual["unknown"] = style_actual.get("unknown", 0) + 1
                continue
            matched = [s for s in styles if s in normalized]
            key = matched[0] if matched else styles[0]
            style_actual[key] = style_actual.get(key, 0) + 1

        merged_pool.extend(stage_selected)
        stage_outputs.append(
            {
                "stage_idx": stage["stage_idx"],
                "slot_count": slot_count,
                "energy_min": stage["energy_min"],
                "energy_max": stage["energy_max"],
                "target_curve": stage["target_curve"],
                "style_target": style_target,
                "style_actual": style_actual,
                "candidates": stage_selected,
            }
        )

    # Fill missing to target_length if stage allocations were short.
    if len(merged_pool) < target_length:
        for row in base_rows:
            track_id = str(row.get("spotify_id") or row.get("track_id") or row.get("id") or "").strip()
            if not track_id or track_id in used_ids:
                continue
            merged_pool.append(row)
            used_ids.add(track_id)
            if len(merged_pool) >= target_length:
                break

    return {
        "pool": merged_pool,
        "stages": stage_outputs,
    }
