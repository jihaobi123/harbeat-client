"""Energy-curve sequencer.

Given a list of songs, sort them according to one of four preset curves of
street-dance DJ energy. Each preset has its own ordering objective:

  1) warmup_to_peak:  monotonically non-decreasing energy. Classic warm-up set.
  2) wave:            sinusoidal — 2 peaks and 2 valleys across the set.
  3) rise_fall:       single arc (intro → climax → cool-down).
  4) battle:          aggressive zig-zag — alternates high/low energy to keep
                      cyphers moving.

The implementation uses a target energy curve and assigns each song to the slot
whose target it is closest to (Hungarian-lite greedy assignment).
"""
from __future__ import annotations

import math
from typing import Sequence

from .energy_hiphop import compute_dance_energy


PRESETS = ["warmup_to_peak", "wave", "rise_fall", "battle"]


def _target_curve(preset: str, n: int) -> list[float]:
    if n <= 1:
        return [0.5] * n
    if preset == "warmup_to_peak":
        return [0.30 + 0.65 * (i / (n - 1)) for i in range(n)]
    if preset == "wave":
        return [0.50 + 0.40 * math.sin(2 * math.pi * i / max(1, n - 1) - math.pi / 2) for i in range(n)]
    if preset == "rise_fall":
        return [0.30 + 0.65 * math.sin(math.pi * i / (n - 1)) for i in range(n)]
    if preset == "battle":
        return [0.40 + 0.50 * (0.5 + 0.5 * math.sin(math.pi * i)) if i % 2 == 0 else 0.85 for i in range(n)]
    # fallback
    return [0.5] * n


def sequence_songs(songs: Sequence, preset: str = "warmup_to_peak") -> list[dict]:
    """Return [{ "song_id", "position", "target_energy", "actual_energy", "breakdown" }, ...]
    in the chosen order."""
    if preset not in PRESETS:
        preset = "warmup_to_peak"
    enriched = []
    for s in songs:
        eb = compute_dance_energy(s)
        enriched.append({"song": s, "energy": eb.total, "breakdown": eb.as_dict()})

    n = len(enriched)
    targets = _target_curve(preset, n)
    # Greedy: for each slot in order, assign the unused song with energy closest to target.
    remaining = list(range(n))
    result: list[dict] = []
    for slot, tgt in enumerate(targets):
        best_idx = None
        best_cost = None
        for r in remaining:
            cost = abs(enriched[r]["energy"] - tgt)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_idx = r
        if best_idx is None:
            break
        s = enriched[best_idx]
        remaining.remove(best_idx)
        result.append({
            "song_id": getattr(s["song"], "id", None),
            "position": slot,
            "target_energy": round(tgt, 4),
            "actual_energy": round(s["energy"], 4),
            "breakdown": {k: round(v, 4) for k, v in s["breakdown"].items()},
        })
    return result
