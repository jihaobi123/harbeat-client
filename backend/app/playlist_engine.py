from __future__ import annotations

import re
from typing import Iterable


class PlaylistEngine:
    CAM_KEY_RE = re.compile(r"^(1[0-2]|[1-9])([ABab])$")

    @classmethod
    def harmonic_candidates(cls, camelot_key: str) -> list[str]:
        """返回和谐混音 Key：同号、相邻号、同号异调。"""
        normalized = camelot_key.strip().upper()
        match = cls.CAM_KEY_RE.match(normalized)
        if not match:
            raise ValueError(f"Invalid Camelot key: {camelot_key}")

        number = int(match.group(1))
        mode = match.group(2)

        prev_number = 12 if number == 1 else number - 1
        next_number = 1 if number == 12 else number + 1
        opposite_mode = "B" if mode == "A" else "A"

        return [
            f"{number}{mode}",
            f"{prev_number}{mode}",
            f"{next_number}{mode}",
            f"{number}{opposite_mode}",
        ]

    @staticmethod
    def bpm_compatible(prev_bpm: float, candidate_bpm: float, tolerance: float = 0.05) -> bool:
        lower = prev_bpm * (1 - tolerance)
        upper = prev_bpm * (1 + tolerance)
        return lower <= candidate_bpm <= upper

    @staticmethod
    def _artist_of(track) -> str:
        tags = track.genre_tags or {}
        return str(tags.get("artist", "unknown")).strip().lower()

    @staticmethod
    def _style_of(track) -> tuple[str, ...]:
        tags = track.genre_tags or {}
        styles = tags.get("styles")
        if isinstance(styles, list) and styles:
            return tuple(sorted(str(s).strip().lower() for s in styles))

        fallback = tags.get("style") or tags.get("genre") or "unknown"
        return (str(fallback).strip().lower(),)

    @classmethod
    def diversity_ok(cls, sequence: list, candidate) -> bool:
        if len(sequence) < 2:
            return True

        last_two = sequence[-2:]
        cand_artist = cls._artist_of(candidate)
        cand_style = cls._style_of(candidate)

        if all(cls._artist_of(t) == cand_artist for t in last_two):
            return False

        if all(cls._style_of(t) == cand_style for t in last_two):
            return False

        return True

    @classmethod
    def build_practice_list(cls, tracks: Iterable, target_duration: int) -> list:
        pool = list(tracks)
        if not pool:
            return []

        target_count = max(1, target_duration // 3)
        sequence = [pool.pop(0)]

        while pool and len(sequence) < target_count:
            prev = sequence[-1]
            harmonic = set(cls.harmonic_candidates(prev.camelot_key))

            strict = [
                t
                for t in pool
                if t.camelot_key in harmonic
                and cls.bpm_compatible(prev.bpm, t.bpm)
                and cls.diversity_ok(sequence, t)
            ]

            medium = [
                t for t in pool if cls.bpm_compatible(prev.bpm, t.bpm) and cls.diversity_ok(sequence, t)
            ]

            loose = [t for t in pool if cls.diversity_ok(sequence, t)]

            candidates = strict or medium or loose or pool
            chosen = min(candidates, key=lambda t: abs(t.bpm - prev.bpm))

            sequence.append(chosen)
            pool.remove(chosen)

        return sequence
