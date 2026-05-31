"""C6 Queue manager — maintains the upcoming track buffer.

Ensures 2-3 candidates are always ready before the current track ends.
Manages play history for repetition control.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from .schemas import Candidate, CandidateList

logger = logging.getLogger(__name__)

# ── Repetition control ───────────────────────────────────────────────────────
REPETITION_WINDOW_SEC = 1800  # 30 min
SAME_ARTIST_PENALTY = 0.5
SAME_REMIX_PENALTY = 0.3


class QueueManager:
    """Manages the upcoming track queue and play history."""

    def __init__(self, buffer_size: int = 3):
        self._buffer_size = buffer_size
        self._queue: deque[Candidate] = deque(maxlen=buffer_size)
        self._history: list[dict] = []  # [{track_id, artist, played_at, energy}]
        self._current_track_id: str = ""
        self._current_artist: str = ""
        self._current_energy: float = 0.5

    # ── current track ────────────────────────────────────────────────────

    def set_current(self, track_id: str, artist: str = "", energy: float = 0.5) -> None:
        """Set the currently playing track and push previous to history."""
        if self._current_track_id:
            self._history.append({
                "track_id": self._current_track_id,
                "artist": self._current_artist,
                "energy": self._current_energy,
                "played_at": time.time(),
            })
            # Trim history older than repetition window
            cutoff = time.time() - REPETITION_WINDOW_SEC
            self._history = [h for h in self._history if h["played_at"] > cutoff]

        self._current_track_id = track_id
        self._current_artist = artist
        self._current_energy = energy

    @property
    def current_track_id(self) -> str:
        return self._current_track_id

    @property
    def current_energy(self) -> float:
        return self._current_energy

    # ── queue ────────────────────────────────────────────────────────────

    def refill(self, candidates: CandidateList) -> int:
        """Replace the queue with new candidates. Returns count added."""
        self._queue.clear()
        count = 0
        for c in candidates.candidates:
            if c.track_id == self._current_track_id:
                continue
            self._queue.append(c)
            count += 1
            if count >= self._buffer_size:
                break
        logger.debug("[queue] refilled with %d candidates", count)
        return count

    def push(self, candidate: Candidate) -> None:
        """Push a single candidate to the queue."""
        if candidate.track_id == self._current_track_id:
            return
        # Avoid duplicates
        existing_ids = {c.track_id for c in self._queue}
        if candidate.track_id not in existing_ids:
            self._queue.append(candidate)

    def pop(self) -> Candidate | None:
        """Pop the next candidate from the queue."""
        if self._queue:
            return self._queue.popleft()
        return None

    def peek(self, index: int = 0) -> Candidate | None:
        """Peek at the candidate at the given index."""
        if 0 <= index < len(self._queue):
            return self._queue[index]
        return None

    def next_best(self) -> Candidate | None:
        """Get the best (highest-scored) candidate from the queue."""
        if not self._queue:
            return None
        return max(self._queue, key=lambda c: c.score)

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0

    @property
    def size(self) -> int:
        return len(self._queue)

    # ── repetition control ───────────────────────────────────────────────

    def repetition_penalty(self, track_id: str, artist: str = "") -> float:
        """Calculate repetition penalty for a track (0.0 = fresh, 1.0 = heavily penalized)."""
        penalty = 0.0

        # Check history
        for h in self._history:
            if h["track_id"] == track_id:
                age = time.time() - h["played_at"]
                if age < 600:  # 10 min
                    penalty += 1.0  # hard block
                elif age < REPETITION_WINDOW_SEC:
                    penalty += 0.5 * (1.0 - age / REPETITION_WINDOW_SEC)

        if artist and artist == self._current_artist:
            penalty += SAME_ARTIST_PENALTY

        return min(1.0, penalty)

    def recently_played_ids(self) -> set[str]:
        """Get the set of recently played track IDs."""
        return {h["track_id"] for h in self._history}

    # ── history ──────────────────────────────────────────────────────────

    @property
    def history_count(self) -> int:
        return len(self._history)

    def history_energy_trend(self, window: int = 3) -> str:
        """Energy trend over last N tracks: 'rising', 'falling', 'stable'."""
        if len(self._history) < window:
            return "stable"
        recent = [h["energy"] for h in self._history[-window:]]
        if recent[-1] > recent[0] + 0.15:
            return "rising"
        elif recent[-1] < recent[0] - 0.15:
            return "falling"
        return "stable"

    def snapshot(self) -> dict:
        return {
            "current_track_id": self._current_track_id,
            "current_energy": round(self._current_energy, 3),
            "queue_size": self.size,
            "queue_ids": [c.track_id for c in self._queue],
            "history_count": self.history_count,
            "energy_trend": self.history_energy_trend(),
        }
