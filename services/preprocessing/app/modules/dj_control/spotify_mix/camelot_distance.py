"""Camelot Wheel distance calculation.

Camelot Wheel maps musical keys to 12 numbers (1-12) + letters (A=Minor, B=Major).
DJs use it to quickly judge harmonic compatibility between tracks.
"""
from __future__ import annotations

import re
from typing import Tuple

CAMELOT_PATTERN = re.compile(r'^(\d{1,2})([AB])$')


def parse_camelot(key: str) -> Tuple[int, str]:
    """Parse Camelot key string.

    Args:
        key: e.g., '8A', '12B'

    Returns:
        (number, letter) e.g., (8, 'A')

    Raises:
        ValueError: Invalid format
    """
    if not isinstance(key, str):
        raise ValueError(f"Camelot key must be str, got {type(key)}")

    match = CAMELOT_PATTERN.match(key.strip().upper())
    if not match:
        raise ValueError(f"Invalid Camelot key: {key}")

    number = int(match.group(1))
    letter = match.group(2)

    if not (1 <= number <= 12):
        raise ValueError(f"Camelot number must be 1-12, got {number}")

    return number, letter


def camelot_distance(key1: str, key2: str) -> int:
    """Calculate distance between two keys on Camelot Wheel.

    Distance rules:
        0: Same key (e.g., 8A → 8A)
        1: Adjacent number same letter (8A → 7A or 9A)
        1: Same number inner/outer swap (8A ↔ 8B)
        2: Distance 2 numbers (8A → 6A or 10A)
        3+: Incompatible

    Args:
        key1: Starting Camelot key
        key2: Target Camelot key

    Returns:
        Distance value (0-6)
    """
    if key1 == key2:
        return 0

    num1, letter1 = parse_camelot(key1)
    num2, letter2 = parse_camelot(key2)

    # Same number, inner/outer swap
    if num1 == num2:
        return 1

    # Same letter, different number (circular distance)
    if letter1 == letter2:
        diff = abs(num1 - num2)
        return min(diff, 12 - diff)

    # Different letter + different number: take number distance + 1
    diff = abs(num1 - num2)
    ring_diff = min(diff, 12 - diff)
    return ring_diff + 1


def is_harmonic_compatible(key1: str, key2: str) -> bool:
    """Check if two keys are harmonically compatible (distance ≤ 1)."""
    try:
        return camelot_distance(key1, key2) <= 1
    except ValueError:
        return False
