"""Pure protocol helpers for manual transition orchestration.

The deployed edge agent owns transport and device execution. This module keeps
only the deterministic validation, request construction, deadline checks, and
task-state rules so those concerns can be tested without Jetson or RK.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

VERIFIED_RENDERER = "three_band_default_v7_standalone_curve_no_energy_floor"
VERIFIED_FEATURE_SOURCE = "dj_structure_precomputed_window_v2"
TERMINAL_STATES = frozenset({"prewarmed", "scheduled", "executed", "expired", "failed", "cancelled"})
ACTIVE_STATES = frozenset({"accepted", "syncing", "cache_ready", "prepared"})
ALLOWED_TRANSITIONS = {
    "accepted": {"syncing", "cache_ready", "prewarmed", "failed", "expired", "cancelled"},
    "syncing": {"cache_ready", "failed", "expired", "cancelled"},
    "cache_ready": {"prepared", "prewarmed", "failed", "expired", "cancelled"},
    "prepared": {"scheduled", "failed", "expired", "cancelled"},
    "scheduled": {"executed"},
    "prewarmed": set(),
    "executed": set(),
    "failed": set(),
    "expired": set(),
    "cancelled": set(),
}


class OrchestrationValidationError(ValueError):
    """Raised when a plan/manifest pair is unsafe to execute."""

    def __init__(self, code: str, detail: Any = None):
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _default_mix(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(plan.get("default_mix"))


def _same(name: str, *values: Any) -> str:
    items = [str(v) for v in values if v not in (None, "")]
    if not items:
        raise OrchestrationValidationError(f"missing_{name}")
    if len(set(items)) != 1:
        raise OrchestrationValidationError(f"{name}_mismatch", items)
    return items[0]


def _plan_marker(plan: Mapping[str, Any], manifest: Mapping[str, Any], key: str) -> str:
    values = [manifest.get(key), _default_mix(plan).get(key), plan.get(key)]
    items = [str(v) for v in values if v not in (None, "")]
    if items and len(set(items)) != 1:
        raise OrchestrationValidationError(f"{key}_mismatch", items)
    return items[0] if items else ""


def _plan_pair_id(plan: Mapping[str, Any]) -> str:
    return _same("pair_id", plan.get("pair_id"), _default_mix(plan).get("pair_id"))


def _plan_song_id(plan: Mapping[str, Any], role: str) -> str:
    default = _default_mix(plan)
    nested = _mapping(plan.get("source" if role == "from" else "target"))
    keys = ("from_song_id", "prev_song_id") if role == "from" else ("to_song_id", "next_song_id")
    return _same(f"{role}_song_id", *(plan.get(k) for k in keys), default.get(keys[0]), nested.get("song_id"))


def _planned_from(plan: Mapping[str, Any]) -> float:
    values = [v for v in (plan.get("from_at_sec"), _default_mix(plan).get("from_at_sec")) if v is not None]
    try:
        numbers = [float(v) for v in values]
    except (TypeError, ValueError) as exc:
        raise OrchestrationValidationError("invalid_from_at_sec") from exc
    if not numbers or max(numbers) - min(numbers) > 0.001:
        raise OrchestrationValidationError("from_at_sec_mismatch")
    return numbers[0]


def validate_request(
    *,
    transition_id: str,
    trigger: str,
    from_song_id: Any,
    to_song_id: Any,
    transition_plan: Mapping[str, Any],
    pair_manifest: Mapping[str, Any],
    mode: str = "schedule",
    min_lead_sec: float = 1.5,
) -> dict[str, Any]:
    """Validate and normalize one manual orchestration request."""
    if not isinstance(transition_id, str) or not 8 <= len(transition_id) <= 128:
        raise OrchestrationValidationError("invalid_transition_id")
    if trigger not in {"fast_cut", "style_cut", "energy_cut"}:
        raise OrchestrationValidationError("invalid_trigger")
    if mode not in {"schedule", "prewarm"}:
        raise OrchestrationValidationError("invalid_mode")
    if float(min_lead_sec) < 1.0:
        raise OrchestrationValidationError("invalid_min_lead_sec")
    plan = _mapping(transition_plan)
    manifest = _mapping(pair_manifest)
    pair_id = _plan_pair_id(plan)
    if pair_id != str(manifest.get("pair_id") or manifest.get("id") or ""):
        raise OrchestrationValidationError("pair_id_mismatch")
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for ch in pair_id):
        raise OrchestrationValidationError("invalid_pair_id")
    if _plan_song_id(plan, "from") != str(from_song_id):
        raise OrchestrationValidationError("from_song_mismatch")
    if _plan_song_id(plan, "to") != str(to_song_id):
        raise OrchestrationValidationError("to_song_mismatch")
    files = _mapping(manifest.get("files"))
    render = _mapping(files.get("transition_render"))
    meta = _mapping(files.get("transition_render_meta"))
    if not render.get("url") or not meta.get("url"):
        raise OrchestrationValidationError("incomplete_pair_manifest")
    if _plan_marker(plan, manifest, "audio_feature_source") != VERIFIED_FEATURE_SOURCE:
        raise OrchestrationValidationError("unverified_audio_feature_source")
    renderer = _plan_marker(plan, manifest, "renderer_version")
    required = _plan_marker(plan, manifest, "required_renderer_version")
    if renderer != VERIFIED_RENDERER or required not in {"", VERIFIED_RENDERER}:
        raise OrchestrationValidationError("unverified_renderer")
    default = _default_mix(plan)
    if any(value is True for value in (plan.get("degraded"), plan.get("fallback_used"), default.get("degraded"), default.get("fallback_used"))):
        raise OrchestrationValidationError("degraded_plan_rejected")
    return {
        "transition_id": transition_id,
        "trigger": trigger,
        "mode": mode,
        "from_song_id": str(from_song_id),
        "to_song_id": str(to_song_id),
        "pair_id": pair_id,
        "planned_from_at_sec": _planned_from(plan),
        "min_lead_sec": float(min_lead_sec),
        "transition_plan": copy.deepcopy(dict(plan)),
        "default_mix_pair_manifest": copy.deepcopy(dict(manifest)),
    }


def build_priority_sync_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build the only sync request permitted for a manual pair."""
    return {
        "plan_id": str(request["transition_id"]),
        "tracks": [],
        "default_mix_pairs": [copy.deepcopy(dict(request["default_mix_pair_manifest"]))],
        "priority": True,
        "wait": False,
    }


def request_hash(request: Mapping[str, Any]) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def accept_task(request: Mapping[str, Any], *, now: str, deadline_epoch_sec: float) -> dict[str, Any]:
    """Create the persisted accepted task representation."""
    return {
        "transition_id": str(request["transition_id"]),
        "request_hash": request_hash(request),
        "pair_id": str(request["pair_id"]),
        "trigger": str(request["trigger"]),
        "mode": str(request["mode"]),
        "from_song_id": str(request["from_song_id"]),
        "to_song_id": str(request["to_song_id"]),
        "state": "accepted",
        "created_at": now,
        "updated_at": now,
        "accepted_position_sec": None,
        "planned_from_at_sec": float(request["planned_from_at_sec"]),
        "deadline_epoch_sec": float(deadline_epoch_sec),
        "timings": {},
        "result": None,
        "error": None,
    }


def transition_task(task: Mapping[str, Any], state: str, **changes: Any) -> dict[str, Any]:
    """Apply one legal task-state transition and return a copy."""
    current = str(task.get("state") or "")
    if state not in ALLOWED_TRANSITIONS.get(current, set()):
        raise OrchestrationValidationError("invalid_state_transition", {"from": current, "to": state})
    out = copy.deepcopy(dict(task))
    out.update(copy.deepcopy(changes))
    out["state"] = state
    return out


def public_task(task: Mapping[str, Any], *, now_epoch_sec: float | None = None) -> dict[str, Any]:
    """Return a client-safe task, omitting the request hash."""
    out = copy.deepcopy(dict(task))
    out.pop("request_hash", None)
    if now_epoch_sec is not None and out.get("deadline_epoch_sec") is not None:
        out["deadline_in_sec"] = max(0.0, float(out["deadline_epoch_sec"]) - now_epoch_sec)
    out["ok"] = out.get("state") not in {"failed", "expired", "cancelled"}
    return out
