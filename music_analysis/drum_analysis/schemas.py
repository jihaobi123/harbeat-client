"""Shared public types for the five-class drum analysis contract."""

from __future__ import annotations

from pathlib import Path

try:
    from typing import NotRequired, TypedDict
except ImportError:  # Python 3.10; NotRequired moved into typing in Python 3.11.
    from typing import TypedDict
    from typing_extensions import NotRequired


DRUM_CLASSES = ("kick", "snare", "hihat", "tom", "cymbal")


class DrumEvent(TypedDict):
    time: float
    confidence: NotRequired[float]


class DrumAnalysisResult(TypedDict):
    stems: dict[str, str]
    events: dict[str, list[DrumEvent]]
    midi_path: str


def empty_events() -> dict[str, list[DrumEvent]]:
    """Create an independent empty list for every public drum class."""
    return {name: [] for name in DRUM_CLASSES}


def string_paths(paths: dict[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items()}
