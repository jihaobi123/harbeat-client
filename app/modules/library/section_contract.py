"""Canonical label layers shared by section-analysis producers and consumers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


LABEL_CONTRACT_VERSION = "songformer_label_contract_v2"

SECTION_CONTRACT_FIELDS = (
    "boundary_source",
    "songformer_label",
    "structure_label_candidate",
    "structure_label_probabilities",
    "structure_label_confidence",
    "structure_label_margin",
    "mix_roles",
    "mix_role_scores",
    "label_status",
    "label_evidence_status",
    "label_contract_version",
)

_STRUCTURE_LABEL_ALIASES = {
    "inst": "instrumental",
}

_MIX_ROLE_SCORES = {
    "instrumental": {"instrumental_focus": 1.0},
    "pre-chorus": {"transition": 1.0, "buildup": 0.7},
}


def canonical_structure_label(raw_label: object) -> str:
    """Normalize one model label without erasing its semantic meaning."""
    normalized = str(raw_label or "unknown").strip().lower()
    if not normalized:
        normalized = "unknown"
    return _STRUCTURE_LABEL_ALIASES.get(normalized, normalized)


def normalize_structure_probabilities(raw: object) -> dict[str, float]:
    """Return a finite, non-negative probability distribution with canonical keys."""
    if not isinstance(raw, Mapping):
        return {}

    accumulated: dict[str, float] = {}
    for raw_label, raw_value in raw.items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        label = canonical_structure_label(raw_label)
        accumulated[label] = accumulated.get(label, 0.0) + value

    total = sum(accumulated.values())
    if total <= 0:
        return {}
    return {label: value / total for label, value in accumulated.items()}


def _confidence_and_margin(
    probabilities: Mapping[str, float],
    candidate: str,
) -> tuple[float | None, float | None]:
    if not probabilities:
        return None, None
    ranked = sorted((float(value) for value in probabilities.values()), reverse=True)
    confidence = probabilities.get(candidate)
    runner_up = ranked[1] if len(ranked) > 1 else 0.0
    return confidence, ranked[0] - runner_up


def _boundary_source(source: str) -> str:
    normalized = str(source or "unknown").strip().lower()
    if normalized.startswith("songformer"):
        return "songformer"
    if normalized.startswith("all_in_one"):
        return "all_in_one"
    return normalized or "unknown"


def enrich_section_segment(item: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    """Apply the versioned HarBeat section contract to one normalized segment."""
    raw_label = str(
        item.get("songformer_label")
        or item.get("structure_label_candidate")
        or item.get("label")
        or "unknown"
    ).strip().lower()
    candidate = canonical_structure_label(
        item.get("structure_label_candidate") or raw_label
    )
    raw_probabilities = item.get("structure_label_probabilities")
    if raw_probabilities is None:
        raw_probabilities = item.get("label_probabilities")
    probabilities = normalize_structure_probabilities(raw_probabilities)
    confidence, margin = _confidence_and_margin(probabilities, candidate)
    role_scores = dict(_MIX_ROLE_SCORES.get(candidate, {}))
    songformer_source = str(source or "").strip().lower().startswith("songformer")

    result = dict(item)
    result.pop("label_probabilities", None)
    result.pop("label_confidence", None)
    result.pop("label_margin", None)
    result.update(
        {
            "boundary_source": _boundary_source(source),
            "songformer_label": raw_label if songformer_source else None,
            "structure_label_candidate": candidate,
            "structure_label_probabilities": probabilities,
            "structure_label_confidence": confidence,
            "structure_label_margin": margin,
            "mix_roles": list(role_scores),
            "mix_role_scores": role_scores,
            "label": candidate,
            "label_status": "candidate",
            "label_evidence_status": "available" if probabilities else "missing",
            "label_contract_version": LABEL_CONTRACT_VERSION,
            "source": source,
        }
    )
    return result
