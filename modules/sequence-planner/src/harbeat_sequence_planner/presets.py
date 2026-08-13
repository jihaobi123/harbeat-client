"""Versioned preset names and explicit compatibility resolution."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PRESET = "battle_4rounds"
CURRENT_PRESETS = (
    "default",
    "battle_4rounds",
    "cypher_circle",
    "class_choreo",
    "showcase",
    "battle_1v1_short",
)
COMPATIBILITY_PRESETS = ("warmup_to_peak", "wave", "rise_fall", "battle")
PRESETS = list(CURRENT_PRESETS + COMPATIBILITY_PRESETS)


@dataclass(frozen=True, slots=True)
class PresetResolution:
    requested: str
    resolved: str
    compatibility_used: bool
    reason: str | None = None


def resolve_preset(requested: str) -> PresetResolution:
    value = str(requested or "").strip()
    if value in CURRENT_PRESETS:
        return PresetResolution(value, value, False)
    if value in COMPATIBILITY_PRESETS:
        return PresetResolution(value, value, True, "version_0_1_compatibility_preset")
    return PresetResolution(value, DEFAULT_PRESET, True, "unknown_preset_normalized")
