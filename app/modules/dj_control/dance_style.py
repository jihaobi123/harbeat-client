"""Dance-style recommendation engine.

Heuristic classifier that scores how well each LibrarySong fits a dance style,
working ONLY on already-extracted features (bpm, beat_points, downbeats,
energy, key, phrase_map) — does NOT re-decode audio. Cheap, deterministic,
runs in milliseconds for thousands of songs.

Rationale (street-dance DJ knowledge):
- Breaking:   85-115 BPM, funk/break-beat drums, mid-snare crack, open hats,
              short phrases (8 bars), low harmonicity (lots of percussive content),
              "James Brown / Apache / Amen-break" lineage.
- Hip-hop:    85-100 BPM, sub-bass dominant, sparse drums, vocal-led phrases.
- Popping:    95-115 BPM, funk grooves (Zapp / Dazz Band lineage), syncopated
              bass, brassy mid-band energy.
- Locking:    100-115 BPM, brass-heavy funk (James Brown / Earth Wind & Fire),
              very steady backbeat, high harmonicity.
- House:      118-128 BPM, four-on-the-floor (kick on every beat), very steady,
              long 16-32-bar phrases.
- Krump:      75-95 BPM, very heavy sub bass, aggressive kick, dark mood.
- Waacking:   110-130 BPM (disco), four-on-the-floor + open hat off-beat,
              vocal-led, high harmonicity.

The scorer maps each style to a target feature vector and returns 1 / (1 + dist).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# --------------------------------------------------------------------------- #
# Style profiles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StyleProfile:
    key: str
    label_zh: str
    bpm_range: tuple[float, float]        # ideal BPM band
    bpm_tolerance: float                  # how forgiving outside the band
    energy_band: tuple[float, float]      # ideal `energy` (RMS-tanh) band
    beat_density_band: tuple[float, float]  # beats / second band
    four_on_floor_pref: float             # +1 prefers 4-on-floor, -1 avoids, 0 neutral
    phrase_len_pref_bars: tuple[float, float]


STYLE_PROFILES: dict[str, StyleProfile] = {
    "breaking": StyleProfile(
        key="breaking",
        label_zh="Breaking 霹雳舞",
        bpm_range=(88, 112),
        bpm_tolerance=8,
        energy_band=(0.55, 0.95),
        beat_density_band=(1.6, 2.1),
        four_on_floor_pref=-0.4,
        phrase_len_pref_bars=(8, 16),
    ),
    "hiphop": StyleProfile(
        key="hiphop",
        label_zh="Hip-Hop",
        bpm_range=(85, 100),
        bpm_tolerance=8,
        energy_band=(0.45, 0.85),
        beat_density_band=(1.4, 1.8),
        four_on_floor_pref=-0.2,
        phrase_len_pref_bars=(8, 16),
    ),
    "popping": StyleProfile(
        key="popping",
        label_zh="Popping 机械舞",
        bpm_range=(95, 115),
        bpm_tolerance=6,
        energy_band=(0.50, 0.85),
        beat_density_band=(1.7, 2.0),
        four_on_floor_pref=0.0,
        phrase_len_pref_bars=(8, 16),
    ),
    "locking": StyleProfile(
        key="locking",
        label_zh="Locking 锁舞",
        bpm_range=(100, 115),
        bpm_tolerance=6,
        energy_band=(0.55, 0.90),
        beat_density_band=(1.7, 2.0),
        four_on_floor_pref=0.3,
        phrase_len_pref_bars=(8, 16),
    ),
    "house": StyleProfile(
        key="house",
        label_zh="House 浩室",
        bpm_range=(118, 128),
        bpm_tolerance=4,
        energy_band=(0.55, 0.90),
        beat_density_band=(2.0, 2.2),
        four_on_floor_pref=1.0,
        phrase_len_pref_bars=(16, 32),
    ),
    "krump": StyleProfile(
        key="krump",
        label_zh="Krump",
        bpm_range=(78, 95),
        bpm_tolerance=6,
        energy_band=(0.65, 1.0),
        beat_density_band=(1.3, 1.7),
        four_on_floor_pref=-0.3,
        phrase_len_pref_bars=(8, 16),
    ),
    "waacking": StyleProfile(
        key="waacking",
        label_zh="Waacking 甩手舞",
        bpm_range=(110, 128),
        bpm_tolerance=6,
        energy_band=(0.50, 0.85),
        beat_density_band=(1.9, 2.2),
        four_on_floor_pref=0.8,
        phrase_len_pref_bars=(16, 32),
    ),
}


def list_styles() -> list[dict]:
    return [
        {
            "key": p.key,
            "label_zh": p.label_zh,
            "bpm_range": p.bpm_range,
        }
        for p in STYLE_PROFILES.values()
    ]


# --------------------------------------------------------------------------- #
# Feature derivation (from existing LibrarySong fields, no audio decoding)
# --------------------------------------------------------------------------- #
def _beat_density(beat_points: list[float], duration: float | None) -> float:
    if not beat_points or not duration or duration <= 0:
        return 0.0
    return len(beat_points) / duration


def _is_four_on_floor(downbeats: list[float], beat_points: list[float]) -> float:
    """Estimate '4-on-floor-ness' = ratio of beats that align near downbeats.

    Returns 0..1. Higher means the song behaves like a 4/4 with a kick on every beat
    (typical house / disco / waacking).
    """
    if not downbeats or not beat_points or len(beat_points) < 8:
        return 0.0
    # In 4/4 with detected downbeats per bar, downbeats/beats ratio is ~1/4.
    ratio = len(downbeats) / len(beat_points)
    # Penalize too-sparse downbeat tracks (likely break-beat / funk).
    return max(0.0, min(1.0, 1.0 - abs(ratio - 0.25) * 3.0))


def _avg_phrase_bars(phrase_map: list[dict], beat_points: list[float], bpm: float | None) -> float:
    if not phrase_map or not bpm or bpm <= 0:
        return 0.0
    bar_sec = 4 * 60.0 / bpm
    spans = []
    for ph in phrase_map:
        start = ph.get("start")
        end = ph.get("end")
        if start is None or end is None or end <= start:
            continue
        spans.append((end - start) / bar_sec)
    if not spans:
        return 0.0
    return sum(spans) / len(spans)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _band_score(value: float, band: tuple[float, float], tolerance: float = 0.0) -> float:
    """Returns 1.0 inside the band, decays linearly outside up to `tolerance` past the edge."""
    lo, hi = band
    if lo <= value <= hi:
        return 1.0
    if tolerance <= 0:
        return 0.0
    if value < lo:
        return max(0.0, 1.0 - (lo - value) / tolerance)
    return max(0.0, 1.0 - (value - hi) / tolerance)


def score_song_for_style(song, style_key: str) -> float:
    """Return 0..1 score for how well `song` matches `style_key`.

    `song` must be a LibrarySong-like object with attributes:
        bpm, energy, duration, beat_points, downbeats, phrase_map.
    Songs with no BPM (analysis_status != completed) get a small base score
    so they aren't fully excluded, but rank below analyzed candidates.
    """
    profile = STYLE_PROFILES.get(style_key)
    if profile is None:
        return 0.0

    bpm = float(song.bpm) if getattr(song, "bpm", None) else 0.0
    energy = float(song.energy) if getattr(song, "energy", None) is not None else 0.5
    duration = float(getattr(song, "duration", 0) or 0)
    beat_points = list(getattr(song, "beat_points", []) or [])
    downbeats = list(getattr(song, "downbeats", []) or [])
    phrase_map = list(getattr(song, "phrase_map", []) or [])

    if bpm <= 0:
        # Unanalyzed song — fall back to title/artist heuristics only.
        return 0.15

    # BPM band match
    bpm_s = _band_score(bpm, profile.bpm_range, profile.bpm_tolerance)
    # Energy band match
    e_s = _band_score(energy, profile.energy_band, 0.2)
    # Beat density match (proxy for groove complexity)
    bd = _beat_density(beat_points, duration)
    bd_s = _band_score(bd, profile.beat_density_band, 0.5)
    # 4-on-floor alignment (positive or negative pref)
    fof = _is_four_on_floor(downbeats, beat_points)
    if profile.four_on_floor_pref >= 0:
        fof_s = fof if profile.four_on_floor_pref > 0 else 0.5
    else:
        fof_s = 1.0 - fof
    fof_weight = abs(profile.four_on_floor_pref)
    # Phrase length match
    avg_bars = _avg_phrase_bars(phrase_map, beat_points, bpm)
    if avg_bars > 0:
        ph_s = _band_score(avg_bars, profile.phrase_len_pref_bars, 4.0)
    else:
        ph_s = 0.5

    # Weighted combination (BPM is dominant; others refine)
    score = (
        0.40 * bpm_s
        + 0.15 * e_s
        + 0.20 * bd_s
        + 0.15 * fof_weight * fof_s + 0.15 * (1.0 - fof_weight) * 0.5
        + 0.10 * ph_s
    )
    return float(max(0.0, min(1.0, score)))


def rank_songs_for_style(
    songs: Iterable,
    style_key: str,
    limit: int | None = None,
    min_score: float = 0.35,
) -> list[tuple[object, float]]:
    """Score every song and return (song, score) sorted desc, filtered by min_score."""
    scored = []
    for s in songs:
        sc = score_song_for_style(s, style_key)
        if sc >= min_score:
            scored.append((s, sc))
    scored.sort(key=lambda x: x[1], reverse=True)
    if limit is not None:
        scored = scored[:limit]
    return scored


def pick_songs_for_duration(
    songs: Iterable,
    style_key: str,
    target_seconds: float,
    min_score: float = 0.35,
) -> list[tuple[object, float]]:
    """Greedy pick top-scoring songs until cumulative duration >= target.

    Adds a small diversity tiebreaker (BPM spread) to avoid 6 nearly identical tracks.
    """
    candidates = rank_songs_for_style(songs, style_key, limit=None, min_score=min_score)
    picked: list[tuple[object, float]] = []
    total = 0.0
    used_bpm_buckets: set[int] = set()
    # Two passes: first pass prefers BPM diversity; second pass fills any remaining slot.
    for pass_idx in (0, 1):
        for song, sc in candidates:
            if (song, sc) in picked:
                continue
            bpm = int(round((song.bpm or 0) / 2.0)) if pass_idx == 0 else None
            if pass_idx == 0 and bpm in used_bpm_buckets:
                continue
            dur = float(getattr(song, "duration", 0) or 0)
            if dur <= 0:
                continue
            picked.append((song, sc))
            total += dur
            if bpm is not None:
                used_bpm_buckets.add(bpm)
            if total >= target_seconds:
                return picked
        if total >= target_seconds:
            break
    return picked
