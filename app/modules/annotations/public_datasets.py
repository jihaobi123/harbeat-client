"""Deterministic mappings from public annotation taxonomies to HarBeat V1."""
from __future__ import annotations

import re


SECTION_LABELS = {"intro", "main", "build", "breakdown", "outro", "unknown"}


def _normalize_label(label: str) -> str:
    value = re.sub(r"[\s_]+", "-", str(label or "").strip().lower())
    value = re.sub(r"-?\d+$", "", value)
    return value.strip("-")


def map_raveform_section_label(label: str) -> str:
    """Map Raveform's EDM functions to the frozen coarse HarBeat taxonomy."""
    normalized = _normalize_label(label)
    if normalized in {"intro", "ambient-intro"}:
        return "intro"
    if normalized in {"buildup", "build-up", "build"}:
        return "build"
    if normalized in {"breakdown", "ambient-breakdown"}:
        return "breakdown"
    if normalized in {"outro", "ambient-outro"}:
        return "outro"
    if normalized in {
        "drop",
        "cooldown",
        "bridge",
        "verse",
        "chorus",
        "instrumental",
        "main",
    }:
        return "main"
    return "unknown"

