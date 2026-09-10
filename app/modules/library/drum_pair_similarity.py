"""Explainable, cacheable drum-pattern similarity for two analyzed songs.

The score is deliberately separate from playlist ordering until the provisional
weights and thresholds have held-out, human-labelled validation evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


DRUM_PAIR_SCORE_VERSION = "drum_pair_similarity_v2"
DRUM_GROUPS = ("kick", "snare_clap", "hihat", "bass_808", "percussion")
GROUP_ALIASES = {
    "kick": ("kick",),
    "snare_clap": ("snare_clap", "snare", "clap"),
    "hihat": ("hihat", "closed_hihat", "open_hihat"),
    "bass_808": ("bass_808", "808", "bass"),
    "percussion": ("percussion", "tom", "cymbal"),
}
GROUP_WEIGHTS = {
    "kick": 0.30,
    "snare_clap": 0.25,
    "hihat": 0.20,
    "bass_808": 0.15,
    "percussion": 0.10,
}


@dataclass(frozen=True)
class DrumPairScoreConfig:
    category_weight: float = 0.40
    rhythm_weight: float = 0.60
    low_threshold: float = 0.70
    high_threshold: float = 0.85
    rhythm_step_tolerance: int = 1
    minimum_pattern_bars: int = 4

    def validate(self) -> None:
        if abs(self.category_weight + self.rhythm_weight - 1.0) > 1e-9:
            raise ValueError("category_weight and rhythm_weight must sum to 1")
        if not 0.0 <= self.low_threshold < self.high_threshold <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= low < high <= 1")
        if self.rhythm_step_tolerance < 0:
            raise ValueError("rhythm_step_tolerance cannot be negative")
        if self.minimum_pattern_bars < 1:
            raise ValueError("minimum_pattern_bars must be positive")


DEFAULT_CONFIG = DrumPairScoreConfig()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def analysis_fingerprint(analysis: Mapping[str, Any] | None) -> str:
    """Hash only pair-scoring inputs so cache entries invalidate predictably."""
    value = _mapping(analysis)
    relevant = {
        "version": value.get("version"),
        "status": value.get("status"),
        "needs_review": value.get("needs_review"),
        "detector_mode": value.get("detector_mode"),
        "counts": value.get("counts"),
        "events": value.get("events"),
        "pattern": value.get("pattern"),
        "confidence": value.get("confidence"),
        "quality_flags": value.get("quality_flags"),
    }
    return hashlib.sha256(_canonical_json(relevant).encode("utf-8")).hexdigest()


def _group_event_count(analysis: Mapping[str, Any], name: str) -> int | None:
    counts = _mapping(analysis.get("counts"))
    events = _mapping(analysis.get("events"))
    aliases = GROUP_ALIASES[name]
    if name in counts:
        aliases = (name,)
    available = False
    total = 0
    for alias in aliases:
        if alias in counts:
            available = True
            try:
                total += max(0, int(counts[alias]))
            except (TypeError, ValueError):
                pass
        elif alias in events and isinstance(events[alias], list):
            available = True
            total += len(events[alias])
    return total if available else None


def category_overlap_score(
    analysis_a: Mapping[str, Any],
    analysis_b: Mapping[str, Any],
) -> tuple[float | None, dict[str, Any]]:
    """Weighted Jaccard overlap of detected drum categories.

    A class absent from both songs is ignored instead of being counted as a
    match. This prevents sparse or failed analyses from receiving high scores.
    """
    details: dict[str, Any] = {}
    numerator = 0.0
    denominator = 0.0
    for name in DRUM_GROUPS:
        count_a = _group_event_count(analysis_a, name)
        count_b = _group_event_count(analysis_b, name)
        if count_a is None or count_b is None:
            details[name] = {
                "status": "unavailable",
                "count_a": count_a,
                "count_b": count_b,
                "weight": GROUP_WEIGHTS[name],
            }
            continue
        present_a = count_a > 0
        present_b = count_b > 0
        weight = GROUP_WEIGHTS[name]
        if present_a or present_b:
            denominator += weight
            if present_a and present_b:
                numerator += weight
        details[name] = {
            "status": "ready",
            "present_a": present_a,
            "present_b": present_b,
            "count_a": count_a,
            "count_b": count_b,
            "weight": weight,
        }
    if denominator <= 0.0:
        return None, details
    return numerator / denominator, details


def _pattern_positions(analysis: Mapping[str, Any], name: str) -> set[int] | None:
    dominant = _mapping(_mapping(analysis.get("pattern")).get("dominant"))
    aliases = GROUP_ALIASES[name]
    if name in dominant:
        aliases = (name,)
    available = False
    positions: set[int] = set()
    for alias in aliases:
        raw = dominant.get(alias)
        if not isinstance(raw, str) or len(raw) != 16:
            continue
        available = True
        positions.update(
            index for index, symbol in enumerate(raw) if symbol != "."
        )
    return positions if available else None


def _step_distance(left: int, right: int, resolution: int = 16) -> int:
    distance = abs(left - right)
    return min(distance, resolution - distance)


def _pattern_f1(
    positions_a: set[int],
    positions_b: set[int],
    *,
    tolerance: int,
) -> float:
    if not positions_a and not positions_b:
        return 1.0
    if not positions_a or not positions_b:
        return 0.0
    exact = positions_a & positions_b
    remaining_a = positions_a - exact
    unmatched = positions_b - exact
    credit = float(len(exact))
    for left in sorted(remaining_a):
        if not unmatched:
            break
        right = min(unmatched, key=lambda value: (_step_distance(left, value), value))
        distance = _step_distance(left, right)
        if distance <= tolerance:
            credit += 0.5
            unmatched.remove(right)
    precision = credit / len(positions_a)
    recall = credit / len(positions_b)
    if precision + recall <= 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def rhythm_landing_similarity_score(
    analysis_a: Mapping[str, Any],
    analysis_b: Mapping[str, Any],
    *,
    tolerance: int = 1,
) -> tuple[float | None, dict[str, Any]]:
    """Compare downbeat-aligned 16-step dominant patterns per drum class."""
    details: dict[str, Any] = {}
    weighted = 0.0
    total_weight = 0.0
    for name in DRUM_GROUPS:
        positions_a = _pattern_positions(analysis_a, name)
        positions_b = _pattern_positions(analysis_b, name)
        if positions_a is None or positions_b is None:
            details[name] = {"status": "unavailable"}
            continue
        if not positions_a and not positions_b:
            details[name] = {
                "status": "ignored_both_absent",
                "steps_a": [],
                "steps_b": [],
            }
            continue
        score = _pattern_f1(positions_a, positions_b, tolerance=tolerance)
        weight = GROUP_WEIGHTS[name]
        weighted += weight * score
        total_weight += weight
        details[name] = {
            "status": "ready",
            "score": round(score, 4),
            "steps_a": sorted(positions_a),
            "steps_b": sorted(positions_b),
            "weight": weight,
        }
    if total_weight <= 0.0:
        return None, details
    return weighted / total_weight, details


def route_overlap_score(
    score: float,
    *,
    low_threshold: float = 0.70,
    high_threshold: float = 0.85,
) -> dict[str, str]:
    """Apply the exact three bands in the supplied transition proposal."""
    if score < low_threshold:
        return {
            "band": "below_low_threshold",
            "proposal_action": "fx_transition_case_1",
        }
    if score <= high_threshold:
        return {
            "band": "between_thresholds_inclusive",
            "proposal_action": "standard_mix",
        }
    return {
        "band": "above_high_threshold",
        "proposal_action": "continue_to_harmonic_check",
    }


class DrumPairScoreCache:
    """Content-addressed JSON cache suitable for a Jetson-local cache folder."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve()

    def cache_key(
        self,
        song_a_id: str,
        analysis_a: Mapping[str, Any],
        song_b_id: str,
        analysis_b: Mapping[str, Any],
        config: DrumPairScoreConfig,
    ) -> str:
        pairs = sorted(
            [
                (str(song_a_id), analysis_fingerprint(analysis_a)),
                (str(song_b_id), analysis_fingerprint(analysis_b)),
            ]
        )
        payload = {
            "version": DRUM_PAIR_SCORE_VERSION,
            "pairs": pairs,
            "config": asdict(config),
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def path_for(self, cache_key: str) -> Path:
        return self.root / cache_key[:2] / f"{cache_key}.json"

    def read(self, cache_key: str) -> dict[str, Any] | None:
        path = self.path_for(cache_key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("version") != DRUM_PAIR_SCORE_VERSION:
            return None
        payload["cache"] = {"hit": True, "key": cache_key, "path": str(path)}
        return payload

    def write(self, cache_key: str, payload: Mapping[str, Any]) -> Path:
        path = self.path_for(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return path


def score_drum_pair(
    song_a_id: str,
    analysis_a: Mapping[str, Any] | None,
    song_b_id: str,
    analysis_b: Mapping[str, Any] | None,
    *,
    config: DrumPairScoreConfig = DEFAULT_CONFIG,
    cache_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Return an explainable symmetric score without changing playlist policy."""
    config.validate()
    original_first = _mapping(analysis_a)
    original_second = _mapping(analysis_b)
    canonical_inputs = sorted(
        [
            (str(song_a_id), analysis_fingerprint(original_first), original_first),
            (str(song_b_id), analysis_fingerprint(original_second), original_second),
        ],
        key=lambda item: (item[0], item[1]),
    )
    first_id, first_fingerprint, first = canonical_inputs[0]
    second_id, second_fingerprint, second = canonical_inputs[1]
    resolved_cache = cache_dir or os.getenv("HARBEAT_DRUM_PAIR_CACHE_DIR")
    cache = DrumPairScoreCache(resolved_cache) if resolved_cache else None
    cache_key = (
        cache.cache_key(first_id, first, second_id, second, config) if cache else None
    )
    if cache and cache_key:
        cached = cache.read(cache_key)
        if cached is not None:
            return cached

    category_score, category_details = category_overlap_score(first, second)
    rhythm_score, rhythm_details = rhythm_landing_similarity_score(
        first,
        second,
        tolerance=config.rhythm_step_tolerance,
    )
    flags: list[str] = []
    if category_score is None:
        flags.append("category_evidence_unavailable")
    if rhythm_score is None:
        flags.append("rhythm_pattern_unavailable")
    for name, detail in category_details.items():
        if detail.get("status") == "unavailable":
            flags.append(f"category_group_unavailable:{name}")
    for name, detail in rhythm_details.items():
        if detail.get("status") == "unavailable":
            flags.append(f"rhythm_group_unavailable:{name}")
    for side, analysis in (("a", first), ("b", second)):
        pattern = _mapping(analysis.get("pattern"))
        try:
            bars = int(pattern.get("bars_analyzed", 0))
        except (TypeError, ValueError):
            bars = 0
        if bars < config.minimum_pattern_bars:
            flags.append(f"insufficient_pattern_bars:{side}")
        if analysis.get("needs_review"):
            flags.append(f"source_needs_review:{side}")
        if analysis.get("status") not in {"ready", "degraded"}:
            flags.append(f"source_unavailable:{side}")

    combined: float | None = None
    route: dict[str, str] = {
        "band": "insufficient_data",
        "proposal_action": "manual_review",
    }
    raw_threshold_route: dict[str, str] | None = None
    if category_score is not None and rhythm_score is not None:
        combined = (
            config.category_weight * category_score
            + config.rhythm_weight * rhythm_score
        )
        raw_threshold_route = route_overlap_score(
            combined,
            low_threshold=config.low_threshold,
            high_threshold=config.high_threshold,
        )
        if not flags:
            route = raw_threshold_route
        else:
            route = {
                "band": "quality_gate_failed",
                "proposal_action": "manual_review",
            }

    status = "unavailable" if combined is None else ("degraded" if flags else "ready")
    payload: dict[str, Any] = {
        "version": DRUM_PAIR_SCORE_VERSION,
        "scope": {
            "style_precondition": "caller_guaranteed_same_style",
            "style_scoring_applied": False,
            "comparison_groups": list(DRUM_GROUPS),
        },
        "pair": {
            "song_ids": [first_id, second_id],
            "songs": [
                {"song_id": first_id, "analysis_fingerprint": first_fingerprint},
                {"song_id": second_id, "analysis_fingerprint": second_fingerprint},
            ],
            "symmetric": True,
        },
        "status": status,
        "needs_review": bool(flags) or combined is None,
        "calibration": {
            "status": "provisional_unvalidated",
            "selection_applied": False,
            "reason": "70/85 thresholds and score weights require held-out human pair labels",
        },
        "scores": {
            "drum_overlap_score": round(combined, 4) if combined is not None else None,
            "category_overlap_score": (
                round(category_score, 4) if category_score is not None else None
            ),
            "rhythm_landing_similarity_score": (
                round(rhythm_score, 4) if rhythm_score is not None else None
            ),
        },
        "weights": {
            "category": config.category_weight,
            "rhythm_landing": config.rhythm_weight,
            "groups": GROUP_WEIGHTS,
        },
        "thresholds": {
            "low": config.low_threshold,
            "high": config.high_threshold,
            "boundary_rule": "score < low; low <= score <= high; score > high",
        },
        "proposal_route": route,
        "raw_threshold_route": raw_threshold_route,
        "evidence": {
            "category": category_details,
            "rhythm_landing": rhythm_details,
        },
        "quality_flags": sorted(set(flags)),
        "cache": {"hit": False, "key": cache_key, "path": None},
    }
    if cache and cache_key:
        path = cache.write(cache_key, payload)
        payload["cache"]["path"] = str(path)
    return payload


__all__ = [
    "DEFAULT_CONFIG",
    "DRUM_PAIR_SCORE_VERSION",
    "DRUM_GROUPS",
    "GROUP_WEIGHTS",
    "DrumPairScoreCache",
    "DrumPairScoreConfig",
    "analysis_fingerprint",
    "category_overlap_score",
    "rhythm_landing_similarity_score",
    "route_overlap_score",
    "score_drum_pair",
]
