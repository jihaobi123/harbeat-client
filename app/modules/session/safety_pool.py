"""C6 Safety pool — guaranteed "can't go wrong" fallback tracks.

Every scene has 10-30 tracks that are safe to play at any moment.
These are the emergency fallback when:
  - The network fails (play from local cache)
  - The candidate selector returns nothing
  - Emergency next is triggered
  - The current track is clearly wrong for the room
"""

from __future__ import annotations

import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

# ── Default safety pool: tracks that work in most street dance scenarios ─────
# These are genre-safe, BPM-safe defaults that can be customized per user/scene.
DEFAULT_SAFETY_TRACK_CRITERIA = {
    "min_bpm": 80,
    "max_bpm": 130,
    "min_energy": 0.3,
    "max_energy": 0.8,
    "prefer_genres": ["hip-hop", "house", "funk", "r-and-b", "pop"],
    "avoid_tags": ["too_commercial", "long_intro_risk", "experimental"],
    "require_beatgrid": True,
    "require_intro_clean": False,  # emergency can skip intro
}


class SafetyPool:
    """Manages the collection of safe fallback tracks for a session."""

    def __init__(self, config: dict | None = None):
        self._config = {**DEFAULT_SAFETY_TRACK_CRITERIA, **(config or {})}
        self._pool: list[str] = []  # track IDs
        self._local_cache: dict[str, dict] = {}  # track_id → cached analysis

    def build(
        self,
        candidate_tracks: list[dict],
        *,
        min_tracks: int = 10,
        max_tracks: int = 30,
    ) -> list[str]:
        """Build the safety pool from a list of candidate track summaries.

        Each candidate dict should have: track_id, bpm, energy, genre, tags.
        """
        criteria = self._config
        scored: list[tuple[str, float]] = []

        for track in candidate_tracks:
            tid = str(track.get("track_id", ""))
            if not tid:
                continue

            bpm = float(track.get("bpm", 0))
            energy = float(track.get("energy", 0.5))
            genre = str(track.get("primary_genre", track.get("genre", ""))).lower()
            tags = [str(t).lower() for t in track.get("tags", [])]

            # Filter
            if not (criteria["min_bpm"] <= bpm <= criteria["max_bpm"]):
                continue
            if not (criteria["min_energy"] <= energy <= criteria["max_energy"]):
                continue
            has_beatgrid = bool(track.get("beat_points"))
            if criteria["require_beatgrid"] and not has_beatgrid:
                continue

            # Avoid tags
            avoid = criteria["avoid_tags"]
            if any(t in avoid for t in tags):
                continue

            # Score: prefer genres + moderate energy + clean intro/outro
            score = 1.0
            if genre in criteria["prefer_genres"]:
                score += 0.3
            if abs(energy - 0.5) < 0.2:
                score += 0.2
            if track.get("intro_is_clean"):
                score += 0.15
            if track.get("outro_is_clean"):
                score += 0.15
            if track.get("beat_confidence", 0) > 0.9:
                score += 0.1

            scored.append((tid, score))

        scored.sort(key=lambda x: -x[1])

        # Take top tracks, ensuring genre diversity
        seen_genres: set[str] = set()
        diverse: list[str] = []
        for tid, score in scored:
            if len(diverse) >= max_tracks:
                break
            track_genre = ""
            for t in candidate_tracks:
                if str(t.get("track_id", "")) == tid:
                    track_genre = str(t.get("primary_genre", t.get("genre", ""))).lower()
                    break
            if track_genre and track_genre not in seen_genres and len(diverse) < min_tracks:
                diverse.append(tid)
                seen_genres.add(track_genre)
            elif len(diverse) >= min_tracks or track_genre in seen_genres:
                diverse.append(tid)

        self._pool = diverse
        logger.info("[safety] built pool: %d tracks, %d genres",
                    len(self._pool), len(seen_genres))
        return self._pool

    def add_track(self, track_id: str) -> None:
        """Add a track to the safety pool."""
        if track_id not in self._pool:
            self._pool.append(track_id)

    def remove_track(self, track_id: str) -> None:
        """Remove a track from the safety pool."""
        if track_id in self._pool:
            self._pool.remove(track_id)

    def get_random(self, exclude: list[str] | None = None) -> str | None:
        """Get a random safety track, optionally excluding some."""
        candidates = [t for t in self._pool if t not in (exclude or [])]
        if not candidates:
            candidates = self._pool
        return random.choice(candidates) if candidates else None

    def get_safest(self, exclude: list[str] | None = None) -> str | None:
        """Get the safest track (first in the pool)."""
        candidates = [t for t in self._pool if t not in (exclude or [])]
        return candidates[0] if candidates else (self._pool[0] if self._pool else None)

    @property
    def pool(self) -> list[str]:
        return list(self._pool)

    @property
    def size(self) -> int:
        return len(self._pool)

    def snapshot(self) -> dict:
        return {
            "size": self.size,
            "tracks": self._pool[:10],
            "config": self._config,
        }
