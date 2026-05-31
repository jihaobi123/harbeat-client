"""Dance-style scoring v3: weighted fingerprint over the rich DJ feature set.

Each style has a fingerprint = a list of (feature_name, low, high, weight)
ranges. A song's score for that style is the weighted mean of how well each
feature falls inside its target band, with linear decay outside.

Why this beats CLAP for our use case
------------------------------------
- Closed set of 7 known street-dance styles → no need for free-form NLP.
- Stem-aware: bass_dominance, sub_bass_score, brass_likely directly capture
  the audio characteristics dancers describe ("punchy bass", "808 sub", "horns")
  without needing a black-box embedding.
- Explainable: every style returns per-feature hit fractions, so the UI can
  show users exactly *why* a song matched.
- Adaptive: when the user adds a song to a style pool, the fingerprint can
  re-fit its (low,high) bands to that user's curated set (TODO).
- Cheap at runtime: pure numpy / dict math, ~1ms per (song,style) pair.

This replaces the v1 BPM-only heuristic and the never-quite-worked CLAP v2.
v1 logic is kept intact below as a fallback for songs without dj_features.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# --------------------------------------------------------------------------- #
# v1 (legacy heuristic) — kept for backwards compatibility
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StyleProfile:
    key: str
    label_zh: str
    bpm_range: tuple[float, float]
    bpm_tolerance: float
    energy_band: tuple[float, float]
    beat_density_band: tuple[float, float]
    four_on_floor_pref: float
    phrase_len_pref_bars: tuple[float, float]


STYLE_PROFILES: dict[str, StyleProfile] = {
    "breaking": StyleProfile("breaking", "Breaking 霹雳舞", (88, 112), 8,
                             (0.55, 0.95), (1.6, 2.1), -0.4, (8, 16)),
    "hiphop":   StyleProfile("hiphop",   "Hip-Hop",        (85, 100), 8,
                             (0.45, 0.85), (1.4, 1.8), -0.2, (8, 16)),
    "popping":  StyleProfile("popping",  "Popping 机械舞", (95, 115), 6,
                             (0.50, 0.85), (1.7, 2.0),  0.0, (8, 16)),
    "locking":  StyleProfile("locking",  "Locking 锁舞",   (100, 115), 6,
                             (0.55, 0.90), (1.7, 2.0),  0.3, (8, 16)),
    "house":    StyleProfile("house",    "House 浩室",     (118, 128), 4,
                             (0.55, 0.90), (2.0, 2.2),  1.0, (16, 32)),
    "krump":    StyleProfile("krump",    "Krump",          (78, 95), 6,
                             (0.65, 1.0),  (1.3, 1.7), -0.3, (8, 16)),
    "waacking": StyleProfile("waacking", "Waacking 甩手舞", (110, 128), 6,
                             (0.50, 0.85), (1.9, 2.2),  0.8, (16, 32)),
}


def list_styles() -> list[dict]:
    return [
        {"key": p.key, "label_zh": p.label_zh, "bpm_range": p.bpm_range}
        for p in STYLE_PROFILES.values()
    ]


# --------------------------------------------------------------------------- #
# v3 fingerprints — feature-name → (low, high, weight)
#
# Weights guide what dominates the score. BPM and stem-bass features are
# heaviest because dancers' first filter is always "is the tempo right + does
# the rhythm section feel right". Timbre features fine-tune.
# --------------------------------------------------------------------------- #
StyleFingerprint = dict[str, tuple[float, float, float]]


STYLE_FINGERPRINTS: dict[str, StyleFingerprint] = {
    "breaking": {
        "bpm":                (88, 112,  3.0),
        "beat_density":       (1.5, 2.2, 1.0),
        "four_on_floor":      (0.0, 0.5, 1.5),  # break-beat, NOT 4-on-floor
        "groove_complexity":  (0.05, 0.20, 1.5),  # syncopated, not stiff
        "drums_to_vocals_ratio": (0.8, 4.0, 1.0),
        "spectral_contrast_mean": (18, 30, 1.0),
        "energy":             (0.55, 0.95, 1.0),
        "swing_ratio":        (0.95, 1.10, 0.5),
    },
    "hiphop": {
        "bpm":                (82, 102, 3.0),
        "beat_density":       (1.3, 1.9, 1.0),
        "bass_dominance":     (0.30, 0.55, 2.0),  # bass-led
        "sub_bass_score":     (0.30, 0.65, 1.5),
        "groove_complexity":  (0.04, 0.18, 1.0),
        "drums_to_vocals_ratio": (0.6, 2.5, 1.0),
        "energy":             (0.45, 0.85, 0.8),
        "spectral_centroid":  (1200, 2400, 0.8),
    },
    "popping": {
        "bpm":                (95, 115, 3.0),
        "bass_dominance":     (0.30, 0.55, 2.0),  # syncopated bass
        "brass_likely":       (0.25, 0.55, 1.8),  # funk horns common
        "groove_complexity":  (0.05, 0.18, 1.5),
        "four_on_floor":      (0.2, 0.7, 1.0),
        "spectral_centroid":  (1500, 2900, 1.0),
        "energy":             (0.50, 0.85, 0.8),
    },
    "locking": {
        "bpm":                (100, 118, 3.0),
        "brass_likely":       (0.30, 0.65, 2.5),  # brass-heavy funk is the genre marker
        "four_on_floor":      (0.4, 0.9, 1.5),    # steady backbeat
        "downbeat_consistency": (0.7, 1.0, 1.0),
        "bass_dominance":     (0.25, 0.55, 1.0),
        "spectral_contrast_mean": (18, 28, 1.0),
        "energy":             (0.55, 0.92, 0.8),
    },
    "house": {
        "bpm":                (118, 128, 4.0),    # hard tempo lock
        "four_on_floor":      (0.7, 1.0, 3.0),    # defining feature
        "downbeat_consistency": (0.85, 1.0, 1.5),
        "drums_to_vocals_ratio": (1.5, 6.0, 1.5),
        "spectral_rolloff":   (5500, 9500, 1.0),  # bright open hats
        "groove_complexity":  (0.02, 0.10, 1.0),  # very steady
        "energy":             (0.55, 0.92, 0.8),
    },
    "krump": {
        "bpm":                (78, 98, 3.0),
        "sub_bass_score":     (0.55, 1.0, 3.0),   # 808 sub is the marker
        "bass_dominance":     (0.40, 0.70, 1.5),
        "energy":             (0.65, 1.0, 2.0),   # aggressive
        "spectral_centroid":  (800, 1800, 1.0),   # darker mids
        "spectral_contrast_mean": (20, 35, 0.8),
        "four_on_floor":      (0.0, 0.5, 1.0),
    },
    "waacking": {
        "bpm":                (108, 128, 3.0),
        "four_on_floor":      (0.65, 1.0, 2.5),   # disco 4-on-floor
        "drums_to_vocals_ratio": (0.4, 1.8, 2.0), # vocal-led
        "vocals_rms":         (0.20, 0.55, 1.5),
        "spectral_rolloff":   (5000, 9000, 1.0),
        "downbeat_consistency": (0.80, 1.0, 1.0),
        "energy":             (0.50, 0.85, 0.8),
    },
}


def _band_fit(value: float, lo: float, hi: float) -> float:
    """Return 1.0 inside [lo,hi], decays linearly to 0 over band-width on each side."""
    if hi <= lo:
        return 0.0
    if lo <= value <= hi:
        return 1.0
    width = hi - lo
    if value < lo:
        return max(0.0, 1.0 - (lo - value) / width)
    return max(0.0, 1.0 - (value - hi) / width)


def _bpm_hard_filter(value: float, lo: float, hi: float, tolerance_pct: float = 0.20) -> bool:
    """Reject songs whose BPM is more than 20% outside the style band — saves
    the rest of the fingerprint from giving silly scores to clearly wrong tempos.
    """
    if value <= 0:
        return True   # unanalysed — let it through, scored low by feature absence
    margin = (hi - lo) * tolerance_pct
    return (lo - margin) <= value <= (hi + margin)


def score_song_for_style_v3(features: dict, style_key: str) -> tuple[float, dict[str, float]]:
    """Return (final_score 0..1, per_feature_hit_fractions).

    `features` is the dj feature dict from extract_dj_features() — typically
    `library_song.music_features.get('dj', {})`.
    """
    fp = STYLE_FINGERPRINTS.get(style_key)
    if not fp:
        return 0.0, {}
    if not features:
        return 0.0, {"_error": 0.0}  # caller should fallback to v1

    # Hard tempo filter
    if "bpm" in fp:
        lo, hi, _ = fp["bpm"]
        if not _bpm_hard_filter(float(features.get("bpm", 0)), lo, hi):
            return 0.0, {"_bpm_reject": 0.0}

    total_w = 0.0
    total_s = 0.0
    breakdown: dict[str, float] = {}
    for feat, (lo, hi, w) in fp.items():
        val = features.get(feat)
        if val is None:
            # Feature missing: penalize lightly (~0.5 hit) so we don't reward
            # incomplete data, but don't reject the song outright.
            f = 0.5
        else:
            f = _band_fit(float(val), lo, hi)
        breakdown[feat] = round(f, 3)
        total_s += f * w
        total_w += w
    score = total_s / total_w if total_w > 0 else 0.0
    return float(max(0.0, min(1.0, score))), breakdown


# --------------------------------------------------------------------------- #
# v1 heuristic (kept for unanalysed songs / songs without dj features)
# --------------------------------------------------------------------------- #
def _beat_density(beat_points, duration):
    if not beat_points or not duration or duration <= 0:
        return 0.0
    return len(beat_points) / duration


def _is_four_on_floor(downbeats, beat_points):
    if not downbeats or not beat_points or len(beat_points) < 8:
        return 0.0
    ratio = len(downbeats) / len(beat_points)
    return max(0.0, min(1.0, 1.0 - abs(ratio - 0.25) * 3.0))


def _avg_phrase_bars(phrase_map, beat_points, bpm):
    if not phrase_map or not bpm or bpm <= 0:
        return 0.0
    bar_sec = 4 * 60.0 / bpm
    spans = []
    for ph in phrase_map:
        start = ph.get("start"); end = ph.get("end")
        if start is None or end is None or end <= start:
            continue
        spans.append((end - start) / bar_sec)
    if not spans:
        return 0.0
    return sum(spans) / len(spans)


def _band_score(value, band, tolerance=0.0):
    lo, hi = band
    if lo <= value <= hi:
        return 1.0
    if tolerance <= 0:
        return 0.0
    if value < lo:
        return max(0.0, 1.0 - (lo - value) / tolerance)
    return max(0.0, 1.0 - (value - hi) / tolerance)


def score_song_for_style(song, style_key: str) -> float:
    """v1 heuristic scorer — only uses bpm/beats/energy/phrase_map."""
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
        return 0.15
    bpm_s = _band_score(bpm, profile.bpm_range, profile.bpm_tolerance)
    e_s = _band_score(energy, profile.energy_band, 0.2)
    bd = _beat_density(beat_points, duration)
    bd_s = _band_score(bd, profile.beat_density_band, 0.5)
    fof = _is_four_on_floor(downbeats, beat_points)
    if profile.four_on_floor_pref >= 0:
        fof_s = fof if profile.four_on_floor_pref > 0 else 0.5
    else:
        fof_s = 1.0 - fof
    fof_weight = abs(profile.four_on_floor_pref)
    avg_bars = _avg_phrase_bars(phrase_map, beat_points, bpm)
    ph_s = _band_score(avg_bars, profile.phrase_len_pref_bars, 4.0) if avg_bars > 0 else 0.5
    score = (
        0.40 * bpm_s
        + 0.15 * e_s
        + 0.20 * bd_s
        + 0.15 * fof_weight * fof_s + 0.15 * (1.0 - fof_weight) * 0.5
        + 0.10 * ph_s
    )
    return float(max(0.0, min(1.0, score)))


# --------------------------------------------------------------------------- #
# Combined entry — prefers v3 fingerprint when dj features exist, else v1
# --------------------------------------------------------------------------- #
def score_song_combined(song, style_key: str) -> tuple[float, str, dict[str, float]]:
    """Return (score, source, breakdown).

    source ∈ {"v3", "v1", "v1-fallback"} — UI can show which path was used.
    """
    mf = getattr(song, "music_features", None) or {}
    dj = mf.get("dj") if isinstance(mf, dict) else None
    if dj and isinstance(dj, dict):
        s, breakdown = score_song_for_style_v3(dj, style_key)
        if s > 0:
            return s, "v3", breakdown
        # v3 hard-rejected (BPM way off) → use v1 to give it a low non-zero score
        return score_song_for_style(song, style_key), "v1-fallback", breakdown
    return score_song_for_style(song, style_key), "v1", {}


def rank_songs_for_style(
    songs: Iterable,
    style_key: str,
    limit: int | None = None,
    min_score: float = 0.35,
) -> list[tuple[object, float]]:
    scored = []
    for s in songs:
        score, _src, _br = score_song_combined(s, style_key)
        if score >= min_score:
            scored.append((s, score))
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

    Two passes: first pass enforces BPM-bucket diversity (rounded to 2bpm)
    so the user doesn't get six near-identical tracks; second pass fills any
    leftover time budget without that constraint.
    """
    candidates = rank_songs_for_style(songs, style_key, limit=None, min_score=min_score)
    picked: list[tuple[object, float]] = []
    used_buckets: set[int] = set()
    total = 0.0
    for pass_idx in (0, 1):
        for song, sc in candidates:
            if (song, sc) in picked:
                continue
            bucket = int(round((song.bpm or 0) / 2.0)) if pass_idx == 0 else None
            if pass_idx == 0 and bucket in used_buckets:
                continue
            dur = float(getattr(song, "duration", 0) or 0)
            if dur <= 0:
                continue
            picked.append((song, sc))
            total += dur
            if bucket is not None:
                used_buckets.add(bucket)
            if total >= target_seconds:
                return picked
        if total >= target_seconds:
            break
    return picked
