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

from app.modules.dj_control.style_reference_profiles import STYLE_REFERENCE_PROFILES


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
    "jazz":     StyleProfile("jazz",     "Jazz",           (88, 125), 10,
                             (0.35, 0.80), (1.2, 2.0), -0.1, (8, 32)),
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
    "jazz": {
        "bpm":                (88, 125, 2.0),
        "beat_density":       (1.1, 2.1, 1.0),
        "groove_complexity":  (0.05, 0.28, 1.6),
        "swing_ratio":        (0.90, 1.18, 1.5),
        "spectral_contrast_mean": (16, 32, 1.2),
        "brass_likely":       (0.15, 0.65, 1.0),
        "drums_to_vocals_ratio": (0.3, 2.8, 0.8),
        "energy":             (0.35, 0.82, 0.8),
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


STYLE_TAG_SIGNALS: dict[str, dict[str, set[str]]] = {
    "popping": {
        "strong": {"electro", "boogie", "funk", "electro funk", "g funk", "synth funk"},
        "medium": {"old school", "groovy", "robotic", "west coast"},
    },
    "locking": {
        "strong": {"funk", "soul", "disco", "jazz funk"},
        "medium": {"upbeat", "funky", "old school", "dance"},
    },
    "breaking": {
        "strong": {"breakbeat", "old school hip hop", "boom bap", "funk breaks", "b boy"},
        "medium": {"hip hop", "electro", "raw", "drum breaks"},
    },
    "house": {
        "strong": {"house", "deep house", "garage house", "jackin house", "soulful house"},
        "medium": {"club", "dance", "4/4", "percussive"},
    },
    "waacking": {
        "strong": {"disco", "funk", "soul", "vocal house", "diva vocal"},
        "medium": {"dramatic", "glamorous", "dance", "vocal"},
    },
    "krump": {
        "strong": {"krump", "aggressive hip hop", "trap", "battle beats", "hard rap"},
        "medium": {"dark", "heavy bass", "high energy", "urban"},
    },
    "hiphop": {
        "strong": {"hip hop", "boom bap", "rap", "old school hip hop", "r&b"},
        "medium": {"urban", "groove", "vocal", "street"},
    },
    "jazz": {
        "strong": {"jazz", "swing", "electro swing", "jazz pop", "big band", "jump blues"},
        "medium": {"latin jazz", "soul jazz", "funk", "shuffle", "brass", "walking bass"},
    },
}

MULTISOURCE_WEIGHTS = {
    "fingerprint": 0.35,
    "platform_tags": 0.25,
    "reference_similarity": 0.20,
    "manual_feedback": 0.10,
    "mixability": 0.10,
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


def _clamp01(value: float | int | None, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _norm_label(label: object) -> str:
    return str(label or "").strip().lower().replace("_", " ").replace("-", " ")


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


def _fingerprint_component(song, style_key: str) -> dict:
    score, source, breakdown = score_song_combined(song, style_key)
    matched = [
        key for key, value in (breakdown or {}).items()
        if not key.startswith("_") and _clamp01(value) >= 0.70
    ]
    if source == "v3":
        confidence = 0.82 if matched else 0.65
    elif source == "v1":
        confidence = 0.52
    else:
        confidence = 0.45
    return {
        "score": round(_clamp01(score), 4),
        "confidence": round(confidence, 3),
        "version": source,
        "matched_features": matched,
        "breakdown": breakdown or {},
        "available": True,
    }


def _labels_from_genre_profile(genre_profile: dict | None) -> list[tuple[str, str, float]]:
    """Return (label, source, confidence) from cached genre profile only."""
    if not isinstance(genre_profile, dict):
        return []
    out: list[tuple[str, str, float]] = []

    def add(label: object, source: str = "genre_profile", confidence: float = 0.55) -> None:
        norm = _norm_label(label)
        if norm:
            out.append((norm, source, _clamp01(confidence, 0.55)))

    for item in genre_profile.get("genres") or []:
        if isinstance(item, dict):
            add(item.get("name"), str(item.get("source") or "genre_profile"), item.get("confidence", 0.55))
        else:
            add(item)
    add(genre_profile.get("primary_genre"), "genre_profile", genre_profile.get("primary_confidence", 0.55))

    # Existing classifier cache shape.
    for key in ("discogs_labels_raw", "spotify_genres_raw", "lastfm_tags_raw", "musicbrainz_tags_raw"):
        for label in genre_profile.get(key) or []:
            source = key.split("_")[0]
            add(label, source, 0.65)

    # New adapter cache shape.
    sources = genre_profile.get("sources") or {}
    if isinstance(sources, dict):
        for source, payload in sources.items():
            if not isinstance(payload, dict):
                continue
            confidence = _clamp01(payload.get("confidence"), 0.60)
            for label in payload.get("labels") or []:
                add(label, str(source), confidence)
    elif isinstance(sources, list):
        for payload in sources:
            if not isinstance(payload, dict):
                continue
            confidence = _clamp01(payload.get("confidence"), 0.60)
            source = str(payload.get("source") or "external")
            for label in payload.get("labels") or []:
                add(label, source, confidence)

    # Preserve order while removing exact duplicates.
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str, float]] = []
    for label, source, confidence in out:
        key = (label, source)
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, source, confidence))
    return unique


def _match_style_labels(style_key: str, labels: list[tuple[str, str, float]]) -> tuple[float | None, list[str], list[str]]:
    signals = STYLE_TAG_SIGNALS.get(style_key) or {}
    strong = signals.get("strong", set())
    medium = signals.get("medium", set())
    if not labels:
        return None, [], []

    matched: list[str] = []
    reasons: list[str] = []
    weighted = 0.0
    total_conf = 0.0
    for label, source, confidence in labels:
        hit = 0.0
        for candidate in strong:
            if candidate in label or label in candidate:
                hit = max(hit, 1.0)
        for candidate in medium:
            if candidate in label or label in candidate:
                hit = max(hit, 0.62)
        if hit <= 0:
            continue
        matched.append(label)
        reasons.append(f"{source} tag matched {label}")
        weighted += hit * max(0.15, confidence)
        total_conf += max(0.15, confidence)

    if total_conf <= 0:
        return 0.35, [], []
    score = weighted / total_conf
    return _clamp01(score), list(dict.fromkeys(matched))[:8], reasons[:4]


def compute_platform_tag_score(style_key: str, genre_profile: dict | None) -> dict:
    labels = _labels_from_genre_profile(genre_profile)
    score, matched, reasons = _match_style_labels(style_key, labels)
    if score is None:
        return {"score": None, "available": False, "confidence": 0.0, "matched_labels": []}
    label_conf = [c for label, _src, c in labels if label in matched]
    confidence = min(0.90, 0.45 + 0.12 * len(matched) + (sum(label_conf) / max(1, len(label_conf))) * 0.20)
    return {
        "score": round(score, 4),
        "available": True,
        "confidence": round(confidence, 3),
        "matched_labels": matched,
        "reason": reasons,
    }


def compute_reference_similarity_score(style_key: str, song, evidence: dict | None = None) -> dict:
    profile = STYLE_REFERENCE_PROFILES.get(style_key)
    if not profile:
        return {"score": None, "available": False, "confidence": 0.0, "matched_refs": []}
    labels = _labels_from_genre_profile(getattr(song, "genre_profile", None) or {})
    labels_only = [label for label, _source, _conf in labels]
    artist = _norm_label(getattr(song, "artist", ""))
    matched_refs: list[str] = []
    for ref in profile.get("reference_tags") or []:
        norm_ref = _norm_label(ref)
        if any(norm_ref in label or label in norm_ref for label in labels_only):
            matched_refs.append(norm_ref)
    for ref_artist in profile.get("reference_artists") or []:
        norm_artist = _norm_label(ref_artist)
        if norm_artist and (norm_artist in artist or artist in norm_artist):
            matched_refs.append(norm_artist)

    if not matched_refs:
        platform = (evidence or {}).get("platform_tags") or {}
        if platform.get("available") and platform.get("score") is not None:
            score = max(0.35, _clamp01(platform["score"]) * 0.70)
            return {
                "score": round(score, 4),
                "available": True,
                "confidence": 0.45,
                "method": "platform_tag_proxy_v1",
                "matched_refs": [],
            }
        return {"score": None, "available": False, "confidence": 0.0, "matched_refs": []}

    score = min(1.0, 0.45 + 0.17 * len(set(matched_refs)))
    return {
        "score": round(score, 4),
        "available": True,
        "confidence": round(min(0.85, 0.55 + 0.08 * len(set(matched_refs))), 3),
        "method": "tag_reference_profile_v1",
        "matched_refs": list(dict.fromkeys(matched_refs))[:8],
    }


def compute_manual_feedback_score(style_key: str, song) -> dict:
    feedback_items = []
    gp = getattr(song, "genre_profile", None) or {}
    if isinstance(gp, dict):
        feedback_items.extend(gp.get("style_feedback") or [])
    feedback_items.extend(getattr(song, "style_feedback", None) or [])
    if not feedback_items:
        return {"score": None, "available": False, "confidence": 0.0}

    best_score: float | None = None
    reason = ""
    for item in feedback_items:
        if not isinstance(item, dict):
            continue
        style = str(item.get("style") or "")
        target = str(item.get("target_style") or "")
        ftype = str(item.get("feedback_type") or "")
        weight = _clamp01(item.get("weight"), 1.0)
        if ftype == "suitable" and style == style_key:
            score = 0.90 * weight
            reason = "manual feedback marked suitable"
        elif ftype == "unsuitable" and style == style_key:
            score = 0.10
            reason = "manual feedback marked unsuitable"
        elif ftype == "better_as" and target == style_key:
            score = 0.90 * weight
            reason = "manual feedback marked better as this style"
        elif ftype == "better_as" and style == style_key:
            score = 0.20
            reason = "manual feedback redirected to another style"
        else:
            continue
        if best_score is None or score > best_score:
            best_score = score
    if best_score is None:
        return {"score": None, "available": False, "confidence": 0.0}
    return {
        "score": round(_clamp01(best_score), 4),
        "available": True,
        "confidence": 0.95,
        "reason": reason,
    }


def compute_mixability_score(song) -> dict:
    parts: list[float] = []
    reasons: list[str] = []

    beat_conf = getattr(song, "beat_confidence", None)
    if beat_conf is not None:
        parts.append(_clamp01(beat_conf))
        if _clamp01(beat_conf) >= 0.65:
            reasons.append("beat confidence is usable")

    stability = getattr(song, "tempo_stability", None)
    if stability is not None:
        parts.append(_clamp01(stability))
        if _clamp01(stability) >= 0.65:
            reasons.append("tempo is stable")

    windows = getattr(song, "transition_windows", None) or []
    parts.append(0.85 if windows else 0.42)
    if windows:
        reasons.append("transition windows are available")

    intro = getattr(song, "intro_clean_score", None)
    outro = getattr(song, "outro_clean_score", None)
    if intro is not None:
        parts.append(_clamp01(intro))
    if outro is not None:
        parts.append(_clamp01(outro))
    if intro is not None and outro is not None and (_clamp01(intro) + _clamp01(outro)) / 2 >= 0.60:
        reasons.append("intro/outro are clean enough")

    stem_quality = getattr(song, "stem_quality_score", None)
    if stem_quality is not None:
        parts.append(0.45 + 0.55 * _clamp01(stem_quality))

    duration = float(getattr(song, "duration", 0) or 0)
    if duration:
        if 90 <= duration <= 420:
            parts.append(0.82)
        elif duration < 45 or duration > 600:
            parts.append(0.35)
        else:
            parts.append(0.58)

    status = str(getattr(song, "analysis_status", "") or "").lower()
    if status in {"failed", "error"}:
        parts.append(0.15)
        reasons.append("analysis failed")
    elif status in {"ready", "completed", "done", "analyzed"}:
        parts.append(0.75)

    if not parts:
        return {"score": None, "available": False, "confidence": 0.0}
    score = sum(parts) / len(parts)
    return {
        "score": round(_clamp01(score), 4),
        "available": True,
        "confidence": round(min(0.90, 0.45 + 0.08 * len(parts)), 3),
        "reason": reasons[:4],
    }


def _component_value(component: dict) -> float | None:
    if not component or component.get("available") is False:
        return None
    score = component.get("score")
    if score is None:
        return None
    return _clamp01(score)


def _reason_for_fingerprint(style_key: str, component: dict) -> str:
    matched = component.get("matched_features") or []
    label = STYLE_PROFILES.get(style_key).label_zh if style_key in STYLE_PROFILES else style_key
    if matched:
        return f"{label} fingerprint matched {', '.join(matched[:4])}"
    return f"{label} fingerprint score available"


def score_song_multisource(style: str, song) -> dict:
    """Score a song for one dance style using cached multi-source evidence."""
    if style not in STYLE_PROFILES:
        return {
            "style": style,
            "final_pick_score": 0.0,
            "confidence": 0.0,
            "components": {},
            "reason": ["unknown style"],
            "matched_labels": [],
            "version": "style_picker_multisource_v1",
        }

    gp = getattr(song, "genre_profile", None) or {}
    components: dict[str, dict] = {}
    components["fingerprint"] = _fingerprint_component(song, style)
    components["platform_tags"] = compute_platform_tag_score(style, gp)
    components["reference_similarity"] = compute_reference_similarity_score(style, song, components)
    components["manual_feedback"] = compute_manual_feedback_score(style, song)
    components["mixability"] = compute_mixability_score(song)

    weighted = 0.0
    weight_sum = 0.0
    confidence_parts: list[float] = []
    for key, weight in MULTISOURCE_WEIGHTS.items():
        value = _component_value(components.get(key, {}))
        if value is None:
            continue
        weighted += value * weight
        weight_sum += weight
        confidence_parts.append(_clamp01(components[key].get("confidence"), 0.50))
    final_score = weighted / weight_sum if weight_sum > 0 else 0.0
    confidence = sum(confidence_parts) / len(confidence_parts) if confidence_parts else 0.0

    reasons = [_reason_for_fingerprint(style, components["fingerprint"])]
    platform = components["platform_tags"]
    if platform.get("matched_labels"):
        reasons.append("Platform tags matched " + ", ".join(platform["matched_labels"][:4]))
    ref = components["reference_similarity"]
    if ref.get("matched_refs"):
        reasons.append("Reference profile matched " + ", ".join(ref["matched_refs"][:4]))
    manual = components["manual_feedback"]
    if manual.get("reason"):
        reasons.append(str(manual["reason"]))
    mix = components["mixability"]
    if mix.get("reason"):
        reasons.extend(str(r) for r in mix["reason"][:2])

    return {
        "style": style,
        "final_pick_score": round(_clamp01(final_score), 4),
        "confidence": round(_clamp01(confidence), 4),
        "components": components,
        "matched_labels": platform.get("matched_labels", []),
        "recommendation_reason": list(dict.fromkeys(reasons))[:6],
        "version": "style_picker_multisource_v1",
    }


def _component_score_breakdown(evidence: dict) -> dict:
    if evidence.get("score_breakdown_v1"):
        return dict(evidence["score_breakdown_v1"])
    components = evidence.get("components") or {}
    out = {}
    for key in MULTISOURCE_WEIGHTS:
        value = _component_value(components.get(key, {}))
        out[key] = None if value is None else round(value, 4)
    return out


def _persisted_style_pick_evidence(style_key: str, song) -> dict | None:
    gp = getattr(song, "genre_profile", None) or {}
    if not isinstance(gp, dict):
        return None
    style_evidence = gp.get("style_evidence_v1") or {}
    evidence = style_evidence.get(style_key)
    scores = getattr(song, "dance_style_scores", None) or {}
    score = None
    if isinstance(evidence, dict):
        score = evidence.get("final_score")
    if score is None and isinstance(scores, dict):
        score = scores.get(style_key)
    if score is None:
        return None
    external_sources = {
        key: {
            "status": value.get("status"),
            "labels": value.get("labels", []),
            "confidence": value.get("confidence"),
        }
        for key, value in (gp.get("sources") or {}).items()
        if isinstance(value, dict) and key in {"discogs", "lastfm", "musicbrainz"}
    }
    breakdown = {
        "external_platform_score": evidence.get("external_platform_score") if isinstance(evidence, dict) else None,
        "local_fingerprint_score": evidence.get("local_fingerprint_score") if isinstance(evidence, dict) else None,
        "manual_style_score": evidence.get("manual_style_score") if isinstance(evidence, dict) else None,
        "tunable_adjustment_score": evidence.get("tunable_adjustment_score") if isinstance(evidence, dict) else None,
    }
    reason = evidence.get("reason", []) if isinstance(evidence, dict) else []
    return {
        "style": style_key,
        "final_pick_score": round(_clamp01(score), 4),
        "confidence": (evidence or {}).get("confidence", 0.0) if isinstance(evidence, dict) else 0.0,
        "components": {},
        "matched_labels": [
            label
            for source in external_sources.values()
            for label in (source.get("labels") or [])
        ][:8],
        "recommendation_reason": reason or ["读取已保存的舞种评分"],
        "version": "style_evidence_v1",
        "score_breakdown_v1": breakdown,
        "style_evidence_status": (evidence or {}).get("status") if isinstance(evidence, dict) else getattr(song, "dance_style_status", "local_only"),
        "external_sources": external_sources,
    }


def style_pick_evidence(style_key: str, song) -> dict:
    persisted = _persisted_style_pick_evidence(style_key, song)
    if persisted is not None:
        return persisted
    fallback = score_song_multisource(style_key, song)
    fallback["style_evidence_status"] = "local_only"
    fallback["external_sources"] = {}
    fallback["score_breakdown_v1"] = {
        "external_platform_score": None,
        "local_fingerprint_score": fallback.get("components", {}).get("fingerprint", {}).get("score"),
        "manual_style_score": fallback.get("components", {}).get("manual_feedback", {}).get("score"),
        "tunable_adjustment_score": fallback.get("components", {}).get("mixability", {}).get("score"),
    }
    return fallback


def persist_multisource_style_evidence(song) -> tuple[list[dict], dict]:
    """Refresh JSON evidence fields on a LibrarySong-like object.

    This does not commit; callers own the DB session.
    """
    genre_profile = dict(getattr(song, "genre_profile", None) or {})
    style_evidence = dict(genre_profile.get("style_evidence") or {})
    scores: dict[str, float] = {}
    ranked: list[dict] = []
    for style_key in STYLE_PROFILES:
        evidence = score_song_multisource(style_key, song)
        score = float(evidence["final_pick_score"])
        scores[style_key] = round(score, 4)
        style_evidence[style_key] = {
            "fingerprint": evidence["components"].get("fingerprint"),
            "platform_tags": evidence["components"].get("platform_tags"),
            "reference_similarity": evidence["components"].get("reference_similarity"),
            "manual_feedback": evidence["components"].get("manual_feedback"),
            "mixability": evidence["components"].get("mixability"),
            "final_pick_score": round(score, 4),
            "confidence": evidence["confidence"],
            "version": evidence["version"],
            "matched_labels": evidence.get("matched_labels", []),
            "recommendation_reason": evidence.get("recommendation_reason", []),
        }
        ranked.append({
            "style": style_key,
            "score": round(score, 4),
            "source": evidence["version"],
            "confidence": evidence["confidence"],
            "breakdown": _component_score_breakdown(evidence),
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    genre_profile["style_evidence"] = style_evidence
    song.genre_profile = genre_profile
    song.dance_style_scores = scores
    song.dance_styles = ranked
    song.dance_style_status = "completed"
    return ranked, scores


def rank_songs_for_style(
    songs: Iterable,
    style_key: str,
    limit: int | None = None,
    min_score: float = 0.35,
) -> list[tuple[object, float, dict]]:
    scored = []
    for s in songs:
        evidence = style_pick_evidence(style_key, s)
        score = float(evidence.get("final_pick_score", 0.0) or 0.0)
        if score >= min_score:
            scored.append((s, score, evidence))
    scored.sort(key=lambda x: (x[1], x[2].get("confidence", 0.0)), reverse=True)
    if limit is not None:
        scored = scored[:limit]
    return scored


def _energy_bucket(song) -> str:
    energy = _clamp01(getattr(song, "energy", None), 0.5)
    if energy < 0.40:
        return "low"
    if energy < 0.65:
        return "mid"
    if energy < 0.82:
        return "high"
    return "peak"


def _substyle_bucket(evidence: dict) -> str:
    labels = evidence.get("matched_labels") or []
    return _norm_label(labels[0]) if labels else ""


def _diversity_key(song, evidence: dict) -> tuple[int, str, str, str]:
    bpm = float(getattr(song, "bpm", 0) or 0)
    bpm_bucket = int(round(bpm / 5.0) * 5) if bpm > 0 else 0
    artist = _norm_label(getattr(song, "artist", ""))
    return (bpm_bucket, _energy_bucket(song), artist, _substyle_bucket(evidence))


def pick_songs_for_duration(
    songs: Iterable,
    style_key: str,
    target_seconds: float,
    min_score: float = 0.35,
) -> list[tuple[object, float, dict]]:
    """Greedy pick top-scoring songs until cumulative duration >= target.

    Two passes: first pass enforces BPM-bucket diversity (rounded to 2bpm)
    so the user doesn't get six near-identical tracks; second pass fills any
    leftover time budget without that constraint.
    """
    candidates = rank_songs_for_style(songs, style_key, limit=None, min_score=min_score)
    picked: list[tuple[object, float, dict]] = []
    picked_ids: set[object] = set()
    used_bpm: set[int] = set()
    used_energy: set[str] = set()
    used_artist: set[str] = set()
    used_substyle: set[str] = set()
    total = 0.0
    for pass_idx in (0, 1):
        for song, sc, evidence in candidates:
            identity = getattr(song, "id", id(song))
            if identity in picked_ids:
                continue
            bpm_bucket, energy_bucket, artist_bucket, substyle_bucket = _diversity_key(song, evidence)
            if pass_idx == 0:
                if bpm_bucket and bpm_bucket in used_bpm:
                    continue
                if energy_bucket in used_energy and len(used_energy) < 3:
                    continue
                if artist_bucket and artist_bucket in used_artist:
                    continue
                if substyle_bucket and substyle_bucket in used_substyle and len(used_substyle) < 3:
                    continue
            dur = float(getattr(song, "duration", 0) or 0)
            if dur <= 0:
                continue
            picked.append((song, sc, evidence))
            picked_ids.add(identity)
            total += dur
            if bpm_bucket:
                used_bpm.add(bpm_bucket)
            used_energy.add(energy_bucket)
            if artist_bucket:
                used_artist.add(artist_bucket)
            if substyle_bucket:
                used_substyle.add(substyle_bucket)
            if total >= target_seconds:
                return picked
        if total >= target_seconds:
            break
    return picked
