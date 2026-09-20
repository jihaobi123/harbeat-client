"""Musical key compatibility utilities."""

from __future__ import annotations

import re


_CAMELOT_RE = re.compile(r"^\s*(1[0-2]|[1-9])\s*([abAB])\s*$")

_MAJOR_CIRCLE = {
    "C": 0,
    "G": 1,
    "D": 2,
    "A": 3,
    "E": 4,
    "B": 5,
    "F#": 6,
    "GB": 6,
    "DB": 7,
    "C#": 7,
    "AB": 8,
    "EB": 9,
    "BB": 10,
    "F": 11,
}

_MINOR_CIRCLE = {
    "A": 0,
    "E": 1,
    "B": 2,
    "F#": 3,
    "C#": 4,
    "G#": 5,
    "D#": 6,
    "EB": 6,
    "BB": 7,
    "F": 8,
    "C": 9,
    "G": 10,
    "D": 11,
}


def _distance_on_12_clock(left: int, right: int) -> int:
    diff = abs(left - right) % 12
    return min(diff, 12 - diff)


def parse_camelot_key(value: str) -> tuple[int, str] | None:
    match = _CAMELOT_RE.match(value)
    if not match:
        return None
    number = int(match.group(1))
    letter = match.group(2).upper()
    return number, letter


def parse_musical_key(value: str) -> tuple[int, str] | None:
    cleaned = value.strip().replace("♭", "b").replace("♯", "#")
    cleaned = cleaned.replace(" minor", "m").replace(" Minor", "m")
    cleaned = cleaned.replace(" major", "").replace(" Major", "")
    cleaned = cleaned.replace("min", "m").replace("maj", "")
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return None

    mode = "minor" if cleaned.lower().endswith("m") else "major"
    root = cleaned[:-1] if mode == "minor" else cleaned
    root = root.upper().replace("B", "b").replace("b", "B")

    if mode == "major" and root in _MAJOR_CIRCLE:
        return _MAJOR_CIRCLE[root], mode
    if mode == "minor" and root in _MINOR_CIRCLE:
        return _MINOR_CIRCLE[root], mode
    return None


def harmonic_keys_compatible(left: str | None, right: str | None) -> bool:
    """Return True when keys are DJ-friendly on Camelot/circle-of-fifths rules."""

    if not left or not right:
        return False

    left_camelot = parse_camelot_key(left)
    right_camelot = parse_camelot_key(right)
    if left_camelot and right_camelot:
        left_number, left_letter = left_camelot
        right_number, right_letter = right_camelot
        same_or_neighbor = _distance_on_12_clock(left_number, right_number) <= 1
        same_mode = left_letter == right_letter
        relative_mode = left_number == right_number and left_letter != right_letter
        return (same_or_neighbor and same_mode) or relative_mode

    left_musical = parse_musical_key(left)
    right_musical = parse_musical_key(right)
    if not left_musical or not right_musical:
        return False

    left_index, left_mode = left_musical
    right_index, right_mode = right_musical
    same_or_neighbor = _distance_on_12_clock(left_index, right_index) <= 1
    same_mode = left_mode == right_mode
    relative_mode = left_index == right_index and left_mode != right_mode
    return (same_or_neighbor and same_mode) or relative_mode


def harmonic_compatibility_score(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.5
    return 1.0 if harmonic_keys_compatible(left, right) else 0.0

