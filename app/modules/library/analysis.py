from __future__ import annotations

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

MAJOR_TEMPLATE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_TEMPLATE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_MODE_TO_CAMELOT = {
    ("C", "major"): "8B", ("C#", "major"): "3B", ("D", "major"): "10B",
    ("D#", "major"): "5B", ("E", "major"): "12B", ("F", "major"): "7B",
    ("F#", "major"): "2B", ("G", "major"): "9B", ("G#", "major"): "4B",
    ("A", "major"): "11B", ("A#", "major"): "6B", ("B", "major"): "1B",
    ("C", "minor"): "5A", ("C#", "minor"): "12A", ("D", "minor"): "7A",
    ("D#", "minor"): "2A", ("E", "minor"): "9A", ("F", "minor"): "4A",
    ("F#", "minor"): "11A", ("G", "minor"): "6A", ("G#", "minor"): "1A",
    ("A", "minor"): "8A", ("A#", "minor"): "3A", ("B", "minor"): "10A",
}

# Camelot number lookup for distance calculation
CAMELOT_NUMBER = {v: (int(v[:-1]), v[-1]) for v in NOTE_MODE_TO_CAMELOT.values()}

CUE_COLORS = ["#22c55e", "#3b82f6", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4", "#64748b"]

# ── DJ Hot Cue semantic labels ──────────────────────────────────────────────
DJ_HOT_CUE_DEFS = [
    {"name": "intro_end",     "label": "Intro End",    "color": "#22c55e", "desc": "前奏结束，鼓点/贝斯进入"},
    {"name": "main_groove",   "label": "Main Groove",  "color": "#3b82f6", "desc": "主律动段，最适合跳舞"},
    {"name": "first_drop",    "label": "First Drop",   "color": "#ef4444", "desc": "第一个高潮/爆点"},
    {"name": "best_loop",     "label": "Best Loop",    "color": "#f59e0b", "desc": "最适合 Loop 的段落"},
    {"name": "outro_start",   "label": "Outro Start",  "color": "#64748b", "desc": "尾奏开始，适合作为切出点"},
]


def _generate_dj_hot_cues(
    phrase_map: list[dict],
    transition_windows: list[dict],
    energy_curve: list[dict],
    duration: float,
) -> list[dict]:
    """Generate DJ-oriented hot cue points from structural analysis.

    Returns 5 semantic cue points: intro_end, main_groove, first_drop,
    best_loop, outro_start. Each includes time, confidence, and the
    reasoning (which phrase/section was used).
    """
    cues: list[dict] = []
    pm = phrase_map or []
    tw = transition_windows or []

    if not pm:
        return cues

    # ── intro_end: first phrase with energy > 0.35 after intro ──
    intro_end_time = None
    for p in pm:
        if float(p.get("energy", 0)) > 0.35 and p.get("label") != "intro":
            intro_end_time = float(p.get("start", 0))
            break
    if intro_end_time is None and len(pm) >= 2:
        intro_end_time = float(pm[1].get("start", 0))
    if intro_end_time is not None:
        cues.append({
            "name": "intro_end", "label": "Intro End",
            "time": round(intro_end_time, 2),
            "color": "#22c55e",
            "confidence": 0.75,
            "source": "phrase_energy",
        })

    # ── main_groove: highest intensity section ──
    best_groove = max(pm, key=lambda p: float(p.get("intensity", p.get("energy", 0))))
    cues.append({
        "name": "main_groove", "label": "Main Groove",
        "time": round(float(best_groove.get("start", 0)), 2),
        "color": "#3b82f6",
        "confidence": round(float(best_groove.get("intensity", 0.5)), 3),
        "source": f"phrase={best_groove.get('label', '?')}",
    })

    # ── first_drop: first peak section ──
    first_drop = None
    for p in pm:
        if p.get("is_peak_section") or p.get("label") in ("drop",):
            first_drop = p
            break
    if first_drop is None:
        # fallback: highest energy section
        first_drop = max(pm, key=lambda p: float(p.get("energy", 0)))
    cues.append({
        "name": "first_drop", "label": "First Drop",
        "time": round(float(first_drop.get("start", 0)), 2),
        "color": "#ef4444",
        "confidence": round(float(first_drop.get("intensity", first_drop.get("energy", 0.5))), 3),
        "source": f"phrase={first_drop.get('label', '?')}",
    })

    # ── best_loop: highest mix_in_score + clean_candidate ──
    best_loop_window = None
    best_loop_score = -1.0
    for w in tw:
        if w.get("clean_candidate"):
            score = float(w.get("mix_in_score", 0)) * 0.6 + float(w.get("mix_out_score", 0)) * 0.4
            if score > best_loop_score:
                best_loop_score = score
                best_loop_window = w
    if best_loop_window is None and tw:
        best_loop_window = max(tw, key=lambda w: float(w.get("mix_in_score", 0)))
    if best_loop_window:
        cues.append({
            "name": "best_loop", "label": "Best Loop",
            "time": round(float(best_loop_window.get("start", 0)), 2),
            "color": "#f59e0b",
            "confidence": round(float(best_loop_window.get("mix_in_score", 0.5)), 3),
            "source": f"label={best_loop_window.get('label', '?')} tags={best_loop_window.get('stem_tags', [])}",
        })

    # ── outro_start: last phrase with label outro, or last breakdown ──
    outro_start_time = None
    for p in reversed(pm):
        if p.get("label") in ("outro",):
            outro_start_time = float(p.get("start", 0))
            break
    if outro_start_time is None:
        # fallback: last breakdown, or 80% of duration
        for p in reversed(pm):
            if p.get("label") in ("breakdown",) and float(p.get("start", 0)) > duration * 0.6:
                outro_start_time = float(p.get("start", 0))
                break
    if outro_start_time is None:
        outro_start_time = duration * 0.8
    cues.append({
        "name": "outro_start", "label": "Outro Start",
        "time": round(outro_start_time, 2),
        "color": "#64748b",
        "confidence": 0.7,
        "source": "phrase_label" if any(p.get("label") == "outro" for p in pm) else "duration_fallback",
    })

    return cues


# ═══════════════════════════════════════════════════════════════════════════════
# Key / tonal analysis — comprehensive DJ-oriented key detection
# ═══════════════════════════════════════════════════════════════════════════════

def _analyze_key(y: np.ndarray, sr: int) -> dict:
    """Comprehensive key detection with cross-validation, candidates, and tonal clarity.

    Uses two chroma representations (CQT + CENS) with Krumhansl-Schmuckler template
    matching, then cross-validates to produce a confidence-weighted result.

    Returns:
        key, camelot_key, key_confidence, candidates (top 3), tonal_clarity,
        relative_ambiguity, method
    """
    import librosa

    if len(y) < sr:
        return {
            "key": "C major", "camelot_key": "8B",
            "key_confidence": 0.0, "tonal_clarity": 0.0,
            "relative_ambiguity": False, "candidates": [],
            "method": "fallback_short_audio",
        }

    # ── 1. CQT Chroma (standard, wide-band) ──────────────────────────
    try:
        chroma_cqt = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=24)
        cqt_profile = np.mean(chroma_cqt, axis=1)
        if len(cqt_profile) == 12:
            chroma_12 = np.asarray(cqt_profile, dtype=float)
        elif len(cqt_profile) >= 24:
            chroma_12 = np.asarray(cqt_profile[:12] + cqt_profile[12:24], dtype=float)
        else:
            chroma_12 = np.zeros(12, dtype=float)
    except Exception:
        chroma_12 = np.zeros(12, dtype=float)

    # ── 2. CENS Chroma (noise-robust, timbre-invariant) ──────────────
    try:
        chroma_cens = librosa.feature.chroma_cens(y=y, sr=sr)
        cens_profile = np.mean(chroma_cens, axis=1)
    except Exception:
        cens_profile = np.zeros(12, dtype=float)

    # ── 3. Tonal clarity: how "peaky" is the chroma distribution ─────
    def _tonal_clarity(profile: np.ndarray) -> float:
        if np.sum(profile) <= 1e-9:
            return 0.0
        p = profile / (np.sum(profile) + 1e-9)
        # Entropy-based: low entropy = clear tonality (one note dominates)
        entropy = -np.sum(p * np.log(p + 1e-9)) / np.log(12)
        return float(np.clip(1.0 - entropy, 0.0, 1.0))

    cqt_clarity = _tonal_clarity(chroma_12)
    cens_clarity = _tonal_clarity(cens_profile)
    tonal_clarity = round(float(np.clip(cqt_clarity * 0.6 + cens_clarity * 0.4, 0.0, 1.0)), 4)

    # ── 4. K-S template matching on both chromas ─────────────────────
    def _match_templates(profile: np.ndarray) -> list[dict]:
        if np.sum(profile) <= 1e-9:
            return [{"root": "C", "mode": "major", "camelot": "8B", "score": 0.0}]
        prof = profile / (np.linalg.norm(profile) + 1e-9)
        results = []
        for idx, note in enumerate(NOTE_NAMES):
            for template, m in [(MAJOR_TEMPLATE, "major"), (MINOR_TEMPLATE, "minor")]:
                rotated = np.roll(template, idx)
                rotated = rotated / (np.linalg.norm(rotated) + 1e-9)
                score = float(np.dot(prof, rotated))
                results.append({
                    "root": note, "mode": m,
                    "camelot": NOTE_MODE_TO_CAMELOT[(note, m)],
                    "score": round(max(0.0, min(1.0, score)), 4),
                })
        results.sort(key=lambda r: -r["score"])
        return results

    cqt_results = _match_templates(chroma_12)
    cens_results = _match_templates(cens_profile)

    # ── 5. Cross-validate: weighted consensus ────────────────────────
    key_scores: dict[tuple[str, str], float] = {}  # (root, mode) → weighted score
    for i, r in enumerate(cqt_results):
        w = 0.6 * (1.0 / (i + 1))  # rank-weighted, CQT weight 0.6
        k = (r["root"], r["mode"])
        key_scores[k] = key_scores.get(k, 0.0) + w * r["score"]
    for i, r in enumerate(cens_results):
        w = 0.4 * (1.0 / (i + 1))  # rank-weighted, CENS weight 0.4
        k = (r["root"], r["mode"])
        key_scores[k] = key_scores.get(k, 0.0) + w * r["score"]

    ranked = sorted(key_scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return {
            "key": "C major", "camelot_key": "8B",
            "key_confidence": 0.0, "tonal_clarity": 0.0,
            "relative_ambiguity": False, "candidates": [],
            "method": "fallback_no_match",
        }

    # ── 6. Build candidates with cross-validated scores ──────────────
    max_score = ranked[0][1] if ranked else 1.0
    candidates = []
    for (root, mode), score in ranked[:6]:
        candidates.append({
            "root": root, "mode": mode,
            "camelot": NOTE_MODE_TO_CAMELOT[(root, mode)],
            "score": round(score / (max_score + 1e-9), 4),
        })

    best = candidates[0]
    key_confidence = round(float(np.clip(best["score"] * 0.7 + tonal_clarity * 0.3, 0.0, 1.0)), 4)

    # ── 7. Relative ambiguity detection ──────────────────────────────
    # Check if the relative major/minor is a close second
    # e.g., C major ↔ A minor (same notes, different tonal center)
    relative_ambiguity = False
    if len(candidates) >= 2:
        best_key = (best["root"], best["mode"])
        for c in candidates[1:4]:
            other_key = (c["root"], c["mode"])
            # Same set of notes = relative major/minor
            best_idx = NOTE_NAMES.index(best["root"])
            other_idx = NOTE_NAMES.index(c["root"])
            semitone_diff = (other_idx - best_idx) % 12
            # Relative minor is 3 semitones down from major (or 9 up)
            # Relative major is 3 semitones up from minor (or 9 down)
            is_relative = (best["mode"] == "major" and c["mode"] == "minor" and semitone_diff == 9) or \
                          (best["mode"] == "minor" and c["mode"] == "major" and semitone_diff == 3)
            if is_relative and c["score"] > 0.7:
                relative_ambiguity = True
                break

    # ── 8. Determine method ──────────────────────────────────────────
    cqt_best = cqt_results[0] if cqt_results else None
    cens_best = cens_results[0] if cens_results else None
    if cqt_best and cens_best and \
       cqt_best["root"] == cens_best["root"] and cqt_best["mode"] == cens_best["mode"]:
        method = "ks_cqt_cens_agree"
    else:
        method = "ks_cqt_cens_weighted"

    return {
        "key": f"{best['root']} {best['mode']}",
        "camelot_key": best["camelot"],
        "key_confidence": key_confidence,
        "tonal_clarity": tonal_clarity,
        "relative_ambiguity": relative_ambiguity,
        "candidates": candidates[:3],
        "method": method,
    }


def _build_bpm_curve(
    beat_times: list[float] | np.ndarray,
    *,
    window_beats: int = 16,
    hop_beats: int = 8,
) -> tuple[list[dict], float]:
    """Summarize local tempo and report how stable the beat grid is."""
    beats = np.asarray(beat_times, dtype=float)
    if len(beats) < 3:
        return [], 0.0

    intervals = np.diff(beats)
    intervals = intervals[(intervals > 0.15) & (intervals < 2.5)]
    if len(intervals) < 2:
        return [], 0.0

    window = max(2, min(int(window_beats), len(intervals)))
    hop = max(1, int(hop_beats))
    starts = list(range(0, max(len(intervals) - window + 1, 1), hop))
    last_start = max(0, len(intervals) - window)
    if not starts or starts[-1] != last_start:
        starts.append(last_start)

    curve: list[dict] = []
    for start in starts:
        chunk = intervals[start:start + window]
        median_interval = float(np.median(chunk))
        mean_interval = float(np.mean(chunk))
        if median_interval <= 1e-9 or mean_interval <= 1e-9:
            continue
        local_stability = float(np.clip(1.0 - np.std(chunk) / mean_interval, 0.0, 1.0))
        curve.append({
            "start": round(float(beats[start]), 3),
            "end": round(float(beats[min(start + window, len(beats) - 1)]), 3),
            "bpm": round(60.0 / median_interval, 2),
            "stability": round(local_stability, 4),
        })

    if not curve:
        return [], 0.0

    local_mean = float(np.mean([item["stability"] for item in curve]))
    local_bpms = np.asarray([item["bpm"] for item in curve], dtype=float)
    median_bpm = float(np.median(local_bpms))
    tempo_consistency = (
        float(np.clip(1.0 - np.std(local_bpms) / median_bpm, 0.0, 1.0))
        if median_bpm > 1e-9 else 0.0
    )
    stability = float(np.clip(local_mean * 0.6 + tempo_consistency * 0.4, 0.0, 1.0))
    return curve, round(stability, 4)


def _summarize_beatgrid(
    beat_times: list[float] | np.ndarray,
    bpm_curve: list[dict],
    tempo_stability: float,
) -> dict:
    """Describe whether a beat grid is reliable enough for phrase-aligned mixing."""
    beats = np.asarray(beat_times, dtype=float)
    valid_intervals = np.diff(beats)
    valid_intervals = valid_intervals[(valid_intervals > 0.15) & (valid_intervals < 2.5)]
    if len(valid_intervals) == 0:
        interval = 0.0
        offset = float(beats[0]) if len(beats) else 0.0
        phase_consistency = 0.0
    else:
        interval = float(np.median(valid_intervals))
        offset = float(beats[0] % interval) if interval > 1e-9 else 0.0
        local_deviation = float(np.mean(np.abs(valid_intervals - interval)))
        phase_consistency = float(np.clip(1.0 - local_deviation / interval * 4.0, 0.0, 1.0))

    count_confidence = float(np.clip(len(beats) / 64.0, 0.0, 1.0))
    curve_confidence = float(np.clip(len(bpm_curve) / 4.0, 0.0, 1.0))
    confidence = float(np.clip(
        float(tempo_stability) * 0.50
        + phase_consistency * 0.30
        + count_confidence * 0.15
        + curve_confidence * 0.05,
        0.0,
        1.0,
    ))
    needs_review = confidence < 0.72 or len(beats) < 16 or interval <= 1e-9
    return {
        "beat_confidence": round(confidence, 4),
        "beat_confidence_details": {
            "tempo_stability": round(float(tempo_stability), 4),
            "phase_consistency": round(phase_consistency, 4),
            "beat_count_confidence": round(count_confidence, 4),
            "curve_confidence": round(curve_confidence, 4),
        },
        "beat_grid_offset": round(offset, 4),
        "beat_grid_interval": round(interval, 4),
        "beat_engines_used": ["librosa"],
        "beat_needs_review": bool(needs_review),
    }


def _build_energy_curve(
    y: np.ndarray,
    sr: int,
    *,
    window_sec: float = 2.0,
    hop_sec: float = 1.0,
) -> list[dict]:
    """Build a compact loudness contour for energy-aware phrase selection."""
    if sr <= 0 or len(y) == 0:
        return []

    mono = np.asarray(y, dtype=float)
    if mono.ndim > 1:
        mono = np.mean(mono, axis=0)
    frame_length = max(1, int(sr * window_sec))
    hop_length = max(1, int(sr * hop_sec))
    if len(mono) < frame_length:
        frame_length = len(mono)

    rms_values: list[tuple[int, int, float]] = []
    for start in range(0, max(len(mono) - frame_length + 1, 1), hop_length):
        end = min(start + frame_length, len(mono))
        chunk = mono[start:end]
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
        rms_values.append((start, end, rms))

    if not rms_values:
        return []
    peak_rms = max(item[2] for item in rms_values) or 1.0
    return [{
        "start": round(start / sr, 3),
        "end": round(end / sr, 3),
        "energy": round(float(np.clip(np.tanh(rms * 8.0), 0.0, 1.0)), 4),
        "relative_energy": round(float(np.clip(rms / peak_rms, 0.0, 1.0)), 4),
    } for start, end, rms in rms_values]


def _analyze_loudness(
    y: np.ndarray,
    sr: int,
    *,
    target_lufs: float = -14.0,
    peak_headroom_db: float = 1.0,
) -> dict:
    """Measure playback loudness and derive a conservative replay gain."""
    audio = np.asarray(y, dtype=float)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0)
    audio = audio.reshape(-1)

    if sr <= 0 or len(audio) == 0:
        audio = np.zeros(1, dtype=float)

    abs_audio = np.abs(audio)
    peak = float(np.max(abs_audio))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if peak <= 1e-9 or rms <= 1e-9:
        return {
            "integrated_lufs": None,
            "loudness_method": "silence",
            "peak_dbfs": None,
            "rms_dbfs": None,
            "crest_factor_db": 0.0,
            "clip_ratio": 0.0,
            "replay_gain_db": 0.0,
            "clipping_risk": False,
        }

    peak_dbfs = 20.0 * np.log10(peak)
    rms_dbfs = 20.0 * np.log10(rms)
    loudness_method = "rms_dbfs_fallback"
    integrated_lufs = rms_dbfs
    try:
        import pyloudnorm as pyln

        measured = float(pyln.Meter(sr).integrated_loudness(audio))
        if np.isfinite(measured):
            integrated_lufs = measured
            loudness_method = "ebu_r128"
    except Exception:
        pass

    clip_ratio = float(np.mean(abs_audio >= 0.999))
    target_gain = float(target_lufs - integrated_lufs)
    max_gain_with_headroom = float(-peak_headroom_db - peak_dbfs)
    replay_gain = min(target_gain, max_gain_with_headroom)
    replay_gain = float(np.clip(replay_gain, -12.0, 12.0))
    clipping_risk = clip_ratio > 0.00001 or peak_dbfs >= -0.1

    return {
        "integrated_lufs": round(float(integrated_lufs), 3),
        "loudness_method": loudness_method,
        "peak_dbfs": round(float(peak_dbfs), 3),
        "rms_dbfs": round(float(rms_dbfs), 3),
        "crest_factor_db": round(float(peak_dbfs - rms_dbfs), 3),
        "clip_ratio": round(clip_ratio, 6),
        "replay_gain_db": round(replay_gain, 3),
        "clipping_risk": bool(clipping_risk),
    }


def _attach_phrase_energy(phrase_map: list[dict], energy_curve: list[dict]) -> list[dict]:
    """Attach average relative energy to phrase windows without mutating input."""
    enriched: list[dict] = []
    for phrase in phrase_map:
        item = dict(phrase)
        start = float(item.get("start", 0.0))
        end = float(item.get("end", start))
        values = [
            float(window.get("relative_energy", window.get("energy", 0.0)))
            for window in energy_curve
            if float(window.get("start", 0.0)) < end
            and float(window.get("end", window.get("start", 0.0))) > start
        ]
        if values:
            item["energy"] = round(float(np.mean(values)), 4)
        enriched.append(item)
    return enriched


def _build_transition_windows(phrase_map: list[dict]) -> list[dict]:
    """Score phrase-sized windows for safe mix-in and mix-out decisions."""
    role_scores = {
        "intro": (0.92, 0.35),
        "verse": (0.68, 0.58),
        "buildup": (0.45, 0.72),
        "drop": (0.52, 0.48),
        "breakdown": (0.74, 0.80),
        "outro": (0.30, 0.94),
    }
    windows: list[dict] = []
    for phrase in phrase_map:
        label = str(phrase.get("label", "verse")).lower()
        mix_in, mix_out = role_scores.get(label, (0.55, 0.55))
        energy = float(phrase.get("energy", 0.5))
        bars = int(phrase.get("bars", 0) or 0)
        if energy < 0.45:
            mix_in += 0.06
            mix_out += 0.04
        if energy > 0.82:
            mix_in -= 0.08
            mix_out -= 0.06
        if bars and bars < 4:
            mix_in -= 0.08
            mix_out -= 0.08
        clean_candidate = label in {"intro", "breakdown", "outro"} and energy <= 0.55
        windows.append({
            "start": round(float(phrase.get("start", 0.0)), 3),
            "end": round(float(phrase.get("end", phrase.get("start", 0.0))), 3),
            "label": label,
            "bars": bars,
            "energy": round(energy, 4),
            "mix_in_score": round(float(np.clip(mix_in, 0.0, 1.0)), 4),
            "mix_out_score": round(float(np.clip(mix_out, 0.0, 1.0)), 4),
            "clean_candidate": clean_candidate,
        })
    return windows


def camelot_distance(key_a: str, key_b: str) -> int:
    """
    Compute the Camelot Wheel distance between two keys.
    Returns 0 for perfect match, 1 for adjacent (harmonic), 2 for energy boost, 7+ for clash.
    """
    if not key_a or not key_b:
        return 99
    try:
        num_a, mode_a = int(key_a[:-1]), key_a[-1]
        num_b, mode_b = int(key_b[:-1]), key_b[-1]
    except (ValueError, IndexError):
        return 99
    if num_a == num_b and mode_a == mode_b:
        return 0  # same key
    if num_a == num_b and mode_a != mode_b:
        return 1  # relative major/minor
    if mode_a == mode_b:
        diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
        return diff
    # Cross-mode non-same-number
    diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    return diff + 1


def camelot_score(key_a: str, key_b: str) -> int:
    """Score 0-100 for harmonic compatibility on the Camelot Wheel."""
    d = camelot_distance(key_a, key_b)
    if d == 0:
        return 100
    if d == 1:
        return 80
    if d == 2:
        return 60
    if d == 3:
        return 30
    return 0


def _detect_sections(y: np.ndarray, sr: int, duration: float) -> list[dict]:
    """Detect song sections via energy envelope transitions (port of Electron audioAnalyzer)."""
    import librosa

    # RMS energy with 2-second windows and 1-second hop
    hop_length = sr
    frame_length = sr * 2
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    sec_fps = sr / hop_length

    if len(rms) < 4:
        return [{"time": 0, "label": "Intro", "color": "#22c55e"}]

    # Smooth energy contour (moving average ~4s)
    smooth_win = max(1, round(sec_fps * 4))
    smoothed = np.convolve(rms, np.ones(smooth_win) / smooth_win, mode="same")

    # Derivative (rate of change)
    deriv = np.diff(smoothed, prepend=smoothed[0])

    # Find significant transitions
    mean_abs = float(np.mean(np.abs(deriv))) + 1e-9
    transitions = []
    for i in range(2, len(deriv) - 1):
        abs_der = abs(deriv[i])
        if abs_der > mean_abs * 2.5:
            t = i / sec_fps
            if not transitions or t - transitions[-1]["time"] > 3:
                transitions.append({"time": t, "strength": abs_der, "rising": deriv[i] > 0})

    transitions.sort(key=lambda x: -x["strength"])
    top = sorted(transitions[:8], key=lambda x: x["time"])

    cue_points: list[dict] = [{"time": 0, "label": "Intro", "color": "#22c55e"}]

    for t in top:
        if t["time"] < 3 or t["time"] > duration - 3:
            continue
        rel_pos = t["time"] / duration
        if rel_pos < 0.12:
            label, color = "Verse", "#3b82f6"
        elif t["rising"] and rel_pos < 0.5:
            label, color = "Chorus", "#ef4444"
        elif not t["rising"] and rel_pos < 0.5:
            label, color = "Verse", "#3b82f6"
        elif t["rising"]:
            label, color = "Chorus", "#ef4444"
        elif rel_pos > 0.8:
            label, color = "Outro", "#64748b"
        else:
            label, color = "Bridge", "#f59e0b"
        cue_points.append({"time": round(t["time"], 2), "label": label, "color": color})

    # Ensure Outro marker
    if duration > 30 and not any(c["label"] == "Outro" for c in cue_points):
        outro_cand = [t for t in transitions if not t["rising"] and t["time"] > duration * 0.7]
        outro_time = outro_cand[0]["time"] if outro_cand else duration - 15
        cue_points.append({"time": round(outro_time, 2), "label": "Outro", "color": "#64748b"})

    return cue_points


def _infer_downbeats_and_time_signature(
    beat_times: list[float] | np.ndarray,
    beat_strengths: list[float] | np.ndarray,
) -> tuple[list[float], dict]:
    """Infer bar meter and downbeat phase from per-beat accent strengths."""
    beats = np.asarray(beat_times, dtype=float)
    strengths = np.asarray(beat_strengths, dtype=float)
    usable = min(len(beats), len(strengths))
    if usable < 8:
        downbeats = [round(float(beats[0]), 3)] if len(beats) else []
        return downbeats, {
            "numerator": 4,
            "denominator": 4,
            "confidence": 0.0,
            "candidates": [{"numerator": 4, "denominator": 4, "score": 0.0}],
            "method": "fallback",
            "needs_review": True,
        }

    beats = beats[:usable]
    strengths = strengths[:usable]
    scale = float(np.max(strengths) - np.min(strengths))
    if scale <= 1e-9:
        normalized = np.zeros_like(strengths)
    else:
        normalized = (strengths - np.min(strengths)) / scale

    candidates: list[dict] = []
    for numerator in (4, 3, 6, 2):
        best_phase = 0
        best_score = -1.0
        for phase in range(numerator):
            accent_mask = np.arange(usable) % numerator == phase
            accent_mean = float(np.mean(normalized[accent_mask]))
            other_mean = float(np.mean(normalized[~accent_mask])) if np.any(~accent_mask) else 0.0
            contrast = float(np.clip(accent_mean - other_mean, 0.0, 1.0))
            support = float(np.clip(np.sum(accent_mask) / 8.0, 0.0, 1.0))
            score = contrast * 0.85 + support * 0.15
            if numerator == 4:
                score += 0.015
            if score > best_score:
                best_score = score
                best_phase = phase
        candidates.append({
            "numerator": numerator,
            "denominator": 4,
            "score": round(float(np.clip(best_score, 0.0, 1.0)), 4),
            "phase": best_phase,
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    if float(best["score"]) < 0.45:
        raw_best = best
        best = next(item for item in candidates if item["numerator"] == 4)
        numerator = 4
        phase = int(best["phase"])
        downbeats = [
            round(float(beats[index]), 3)
            for index in range(phase, len(beats), numerator)
        ]
        return downbeats, {
            "numerator": 4,
            "denominator": 4,
            "confidence": round(float(best["score"]), 4),
            "candidates": candidates[:3],
            "method": "beat_accent_periodicity_fallback_4_4",
            "needs_review": True,
            "raw_best_numerator": int(raw_best["numerator"]),
        }
    numerator = int(best["numerator"])
    phase = int(best["phase"])
    downbeats = [
        round(float(beats[index]), 3)
        for index in range(phase, len(beats), numerator)
    ]
    return downbeats, {
        "numerator": numerator,
        "denominator": int(best["denominator"]),
        "confidence": round(float(best["score"]), 4),
        "candidates": candidates[:3],
        "method": "beat_accent_periodicity",
        "needs_review": False,
    }


def _detect_downbeats_with_meter(
    y: np.ndarray,
    sr: int,
    beat_times: np.ndarray,
) -> tuple[list[float], dict]:
    """
    Detect downbeats and meter from the same beat-accent evidence.
    """
    import librosa

    if len(beat_times) < 4:
        downbeats = [round(float(beat_times[0]), 3)] if len(beat_times) > 0 else []
        return downbeats, {
            "numerator": 4,
            "denominator": 4,
            "confidence": 0.0,
            "candidates": [{"numerator": 4, "denominator": 4, "score": 0.0}],
            "method": "fallback",
            "needs_review": True,
        }

    # Compute onset strength at each beat position
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    hop = 512
    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop)
    beat_frames = np.clip(beat_frames, 0, len(onset_env) - 1)
    beat_strengths = onset_env[beat_frames]

    return _infer_downbeats_and_time_signature(beat_times, beat_strengths)


def _detect_downbeats(y: np.ndarray, sr: int, beat_times: np.ndarray) -> list[float]:
    """Compatibility wrapper for callers that only need bar boundaries."""
    downbeats, _time_signature = _detect_downbeats_with_meter(y, sr, beat_times)
    return downbeats


def _detect_phrase_structure(
    y: np.ndarray, sr: int, duration: float, downbeat_times: list[float]
) -> list[dict]:
    """
    Build a phrase structure map by analyzing energy over 8-bar phrases.
    Labels: intro, buildup, drop, breakdown, outro.
    """
    import librosa

    if len(downbeat_times) < 4:
        return [{"start": 0, "end": duration, "label": "intro", "bars": 0}]

    # Compute RMS energy at each downbeat
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    db_frames = librosa.time_to_frames(downbeat_times, sr=sr, hop_length=hop)
    db_frames = np.clip(db_frames, 0, len(rms) - 1)

    # Group into 8-bar phrases
    phrase_size = 8  # bars per phrase
    phrases: list[dict] = []
    i = 0
    while i < len(downbeat_times):
        end_i = min(i + phrase_size, len(downbeat_times))
        start_t = downbeat_times[i]
        end_t = downbeat_times[end_i - 1] if end_i < len(downbeat_times) else duration

        # Average energy in this phrase
        frame_start = db_frames[i]
        frame_end = db_frames[min(end_i, len(db_frames) - 1)]
        if frame_end > frame_start:
            avg_energy = float(np.mean(rms[frame_start:frame_end]))
        else:
            avg_energy = float(rms[frame_start]) if frame_start < len(rms) else 0.0

        phrases.append({
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "bars": end_i - i,
            "energy": round(avg_energy, 4),
        })
        i = end_i

    if not phrases:
        return [{"start": 0, "end": duration, "label": "intro", "bars": 0}]

    # Normalize energies
    energies = np.array([p["energy"] for p in phrases])
    max_e = float(energies.max()) if energies.max() > 1e-8 else 1.0
    norm_energies = energies / max_e

    # Label phrases based on energy profile and position
    total = len(phrases)
    for idx, p in enumerate(phrases):
        ne = norm_energies[idx]
        rel = idx / max(total - 1, 1)

        if rel < 0.12 or (idx == 0 and ne < 0.4):
            p["label"] = "intro"
        elif rel > 0.85 and ne < 0.5:
            p["label"] = "outro"
        elif ne >= 0.75:
            p["label"] = "drop"
        elif idx > 0 and norm_energies[idx] > norm_energies[idx - 1] + 0.15:
            p["label"] = "buildup"
        elif ne < 0.4:
            p["label"] = "breakdown"
        else:
            p["label"] = "verse"

        p["energy"] = round(float(ne), 4)

    return phrases


# ═══════════════════════════════════════════════════════════════════════════════
# Extended analysis: time signature, section intensity, groove, vocal events,
# bass risk, stem-aware transition scoring.
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_time_signature(
    beat_times: list[float] | np.ndarray,
    downbeat_times: list[float],
    *,
    bpm: float = 0.0,
) -> dict:
    """Detect time signature by measuring beats between consecutive downbeats.

    Returns {numerator, denominator, confidence, candidates}.
    """
    beats = np.asarray(beat_times, dtype=float)
    downs = np.asarray(downbeat_times, dtype=float)

    if len(downs) < 3 or len(beats) < 8:
        return {
            "numerator": 4, "denominator": 4,
            "confidence": 0.0,
            "candidates": [{"numerator": 4, "denominator": 4, "score": 0.0}],
            "method": "fallback",
        }

    # Count beats between consecutive downbeats
    bar_beat_counts: list[int] = []
    for i in range(len(downs) - 1):
        count = int(np.sum((beats >= downs[i]) & (beats < downs[i + 1])))
        if count > 0:
            bar_beat_counts.append(count)

    if not bar_beat_counts:
        return {
            "numerator": 4, "denominator": 4,
            "confidence": 0.0,
            "candidates": [],
            "method": "empty",
        }

    values, counts = np.unique(bar_beat_counts, return_counts=True)
    total = len(bar_beat_counts)

    # Check common signatures: 4, 3, 6, 5, 7 beats per bar
    candidates = []
    for num in [4, 3, 6, 5, 7, 2, 8]:
        idx = np.where(values == num)[0]
        if len(idx) > 0:
            match_pct = float(counts[idx][0]) / total
            # Bonus: if this matches the downbeat detection's implied signature
            phase_bonus = 0.0
            if num == 4:
                phase_bonus = 0.10  # slight prior for 4/4 (most dance music)
            score = float(np.clip(match_pct + phase_bonus, 0.0, 1.0))
            candidates.append({"numerator": int(num), "denominator": 4, "score": round(score, 4)})

    candidates.sort(key=lambda c: -c["score"])

    # Also check for 6/8 (compound: 2 beats per bar with triplet feel)
    if bpm > 0 and len(beats) >= 16:
        intervals = np.diff(beats)
        intervals = intervals[(intervals > 0.15) & (intervals < 2.5)]
        if len(intervals) >= 8:
            median_beat = float(np.median(intervals))
            # In 6/8, the "beat" is dotted quarter, so librosa might report it as
            # either the dotted quarter (slow) or eighth note (fast).
            # If median beat is very fast (<0.25s → >240bpm equivalent), might be 6/8
            if median_beat < 0.22:
                candidates.append({"numerator": 6, "denominator": 8, "score": 0.4})

    if not candidates:
        candidates = [{"numerator": 4, "denominator": 4, "score": 0.0}]

    best = candidates[0]
    confidence = best["score"] if best["score"] >= 0.6 else float(np.clip(best["score"] * 1.3, 0.0, 0.55))

    return {
        "numerator": best["numerator"],
        "denominator": best["denominator"],
        "confidence": round(confidence, 4),
        "candidates": candidates[:3],
        "method": "bar_beat_histogram",
    }


def _score_section_intensity(
    phrase_map: list[dict],
    energy_curve: list[dict],
    y: np.ndarray | None = None,
    sr: int = 22050,
) -> list[dict]:
    """Score structural sections by energy dynamics and spectral contrast.

    Adds 'intensity' (0-1), 'energy_range', 'is_peak_section', 'is_valley_section'
    to each phrase entry.
    """
    if not phrase_map:
        return phrase_map

    # Collect all phrase energies for relative ranking
    energies = np.array([float(p.get("energy", 0.5)) for p in phrase_map])
    median_e = float(np.median(energies)) if len(energies) else 0.5
    max_e = float(energies.max()) if len(energies) else 1.0

    # Per-phrase energy range from energy_curve
    phrase_ranges: list[float] = []
    for p in phrase_map:
        p_start = float(p.get("start", 0))
        p_end = float(p.get("end", p_start))
        vals = [
            float(w.get("relative_energy", w.get("energy", 0.0)))
            for w in energy_curve
            if float(w.get("start", 0)) < p_end and float(w.get("end", 0)) > p_start
        ]
        if vals and len(vals) >= 2:
            phrase_ranges.append(float(np.max(vals) - np.min(vals)))
        else:
            phrase_ranges.append(0.0)

    max_range = max(phrase_ranges) if phrase_ranges else 1.0

    # Spectral contrast per phrase (if audio available)
    spectral_contrasts: list[float] = []
    if y is not None and sr > 0 and len(y) >= sr:
        try:
            import librosa
            S = np.abs(librosa.stft(np.asarray(y, dtype=float).flatten()))
            for p in phrase_map:
                p_start = max(0, int(float(p.get("start", 0)) * sr / 512))
                p_end = min(S.shape[1], int(float(p.get("end", p.get("start", 0))) * sr / 512))
                if p_end > p_start + 1:
                    band_means = np.mean(S[:, p_start:p_end], axis=1)
                    if len(band_means) >= 6:
                        spectral_contrasts.append(float(np.std(band_means) / (np.mean(band_means) + 1e-8)))
                    else:
                        spectral_contrasts.append(0.0)
                else:
                    spectral_contrasts.append(0.0)
        except Exception:
            spectral_contrasts = [0.0] * len(phrase_map)
    else:
        spectral_contrasts = [0.0] * len(phrase_map)

    max_contrast = max(spectral_contrasts) if spectral_contrasts else 1.0

    enriched: list[dict] = []
    for i, p in enumerate(phrase_map):
        item = dict(p)
        e = float(p.get("energy", 0.5))
        r = phrase_ranges[i] if i < len(phrase_ranges) else 0.0
        sc = spectral_contrasts[i] if i < len(spectral_contrasts) else 0.0

        # Intensity = weighted combo of absolute energy + range + spectral contrast
        intensity = float(np.clip(
            (e / (max_e + 1e-8)) * 0.45
            + (r / (max_range + 1e-8)) * 0.30
            + (sc / (max_contrast + 1e-8)) * 0.25,
            0.0, 1.0,
        ))
        item["intensity"] = round(intensity, 4)
        item["energy_range"] = round(r, 4)
        if sc > 0:
            item["spectral_variation"] = round(sc, 4)
        # Lower thresholds when spectral data unavailable (intensity capped at ~0.45)
        has_spectral = max_contrast > 1e-8
        peak_intensity_threshold = 0.55 if has_spectral else 0.4
        valley_intensity_threshold = 0.45 if has_spectral else 0.5
        item["is_peak_section"] = bool(e >= max_e * 0.85 and intensity >= peak_intensity_threshold)
        item["is_valley_section"] = bool(e <= max(median_e * 0.8, 0.15) and intensity <= valley_intensity_threshold)
        enriched.append(item)

    return enriched


def _compute_groove_score(
    beat_times: list[float] | np.ndarray,
    downbeat_times: list[float],
    bpm_curve: list[dict],
    tempo_stability: float,
) -> dict:
    """Compute a DJ-oriented 'groove' score: how reliably danceable the rhythm is.

    Returns {score, breakdown: {steady_beat, syncopation, downbeat_clarity, tempo_lock}}.
    High score = consistent beat + moderate syncopation + clear downbeats.
    """
    beats = np.asarray(beat_times, dtype=float)
    downs = np.asarray(downbeat_times, dtype=float)

    if len(beats) < 16:
        return {
            "score": 0.0,
            "breakdown": {"steady_beat": 0.0, "syncopation": 0.0,
                          "downbeat_clarity": 0.0, "tempo_lock": 0.0},
            "method": "insufficient_data",
        }

    # 1. Steady beat: how consistent are inter-beat intervals
    ibi = np.diff(beats)
    ibi = ibi[(ibi > 0.15) & (ibi < 2.5)]
    if len(ibi) >= 8:
        median_ibi = float(np.median(ibi))
        ibi_cv = float(np.std(ibi) / (median_ibi + 1e-6))  # coefficient of variation
        steady_beat = float(np.clip(1.0 - ibi_cv * 2.5, 0.0, 1.0))
    else:
        steady_beat = 0.0

    # 2. Syncopation: moderate variation in beat intervals (not perfectly metronomic, not chaotic)
    #    DJs want some "feel" — groove_complexity from the feature extractor
    if len(ibi) >= 8:
        odd = ibi[0::2]; even = ibi[1::2]
        n = min(len(odd), len(even))
        if n >= 2:
            swing = float(np.clip(
                1.0 - abs(float(odd[:n].mean() / (even[:n].mean() + 1e-6)) - 1.0) * 4.0,
                0.0, 1.0,
            ))
        else:
            swing = 0.5
        # Syncopation sweet spot: some variation but not chaotic
        groove_complexity = float(np.clip(ibi_cv * 5.0, 0.0, 1.0))
        syncopation = float(np.clip(groove_complexity * 0.5 + swing * 0.5, 0.0, 1.0))
    else:
        syncopation = 0.5

    # 3. Downbeat clarity: how consistently spaced are downbeats
    if len(downs) >= 4:
        dbi = np.diff(downs)
        dbi = dbi[(dbi > 0.3) & (dbi < 8.0)]
        if len(dbi) >= 3:
            dbi_cv = float(np.std(dbi) / (np.mean(dbi) + 1e-6))
            downbeat_clarity = float(np.clip(1.0 - dbi_cv * 2.0, 0.0, 1.0))
        else:
            downbeat_clarity = 0.3
    else:
        downbeat_clarity = 0.0

    # 4. Tempo lock: from bpm_curve stability + tempo_stability
    tempo_lock = float(tempo_stability) if tempo_stability else steady_beat * 0.6

    # Combined groove score
    score = float(np.clip(
        steady_beat * 0.30
        + syncopation * 0.30
        + downbeat_clarity * 0.22
        + tempo_lock * 0.18,
        0.0, 1.0,
    ))

    label = "stiff" if (steady_beat > 0.9 and syncopation < 0.3) else \
            "loose" if steady_beat < 0.4 else \
            "groovy" if score >= 0.65 else \
            "steady" if score >= 0.4 else \
            "unstable"

    return {
        "score": round(score, 4),
        "label": label,
        "breakdown": {
            "steady_beat": round(steady_beat, 4),
            "syncopation": round(syncopation, 4),
            "downbeat_clarity": round(downbeat_clarity, 4),
            "tempo_lock": round(tempo_lock, 4),
        },
        "method": "rhythm_statistical",
    }


def _analyze_dancefloor_profile(
    *,
    bpm: float,
    energy: float,
    groove: dict | None,
    stem_activity: dict | None = None,
    spectral_centroid: float | None = None,
    phrase_map: list[dict] | None = None,
) -> dict:
    """Summarize how a track feels on a dance floor, with explainable factors."""
    groove = groove or {}
    stems = stem_activity or {}
    groove_score = float(np.clip(groove.get("score", 0.5), 0.0, 1.0))
    drums = float(np.clip(stems.get("drums", groove_score), 0.0, 1.0))
    bass = float(np.clip(stems.get("bass", energy), 0.0, 1.0))
    vocals = float(np.clip(stems.get("vocals", 0.35), 0.0, 1.0))
    brightness = float(np.clip(((spectral_centroid or 2200.0) - 900.0) / 3200.0, 0.0, 1.0))
    tempo_fit = float(np.clip(1.0 - abs(float(bpm) - 115.0) / 80.0, 0.0, 1.0))
    peak_intensity = max(
        [float(item.get("intensity", item.get("energy", 0.0))) for item in (phrase_map or [])]
        or [float(energy)]
    )

    danceability = float(np.clip(
        groove_score * 0.45 + drums * 0.20 + bass * 0.12
        + tempo_fit * 0.15 + peak_intensity * 0.08,
        0.0, 1.0,
    ))
    physical_energy = float(np.clip(
        float(energy) * 0.50 + drums * 0.25 + bass * 0.20 + peak_intensity * 0.05,
        0.0, 1.0,
    ))
    tension = float(np.clip(
        float(energy) * 0.35 + brightness * 0.20 + vocals * 0.15 + peak_intensity * 0.30,
        0.0, 1.0,
    ))
    fatigue_risk = float(np.clip(
        float(energy) * 0.35
        + np.clip((float(bpm) - 105.0) / 80.0, 0.0, 1.0) * 0.25
        + brightness * 0.20 + drums * 0.20,
        0.0, 1.0,
    ))

    mood_tags: list[str] = []
    if physical_energy >= 0.70:
        mood_tags.append("driving")
    if tension >= 0.72:
        mood_tags.append("tense")
    if groove_score >= 0.68:
        mood_tags.append("groovy")
    if physical_energy <= 0.40:
        mood_tags.append("laid_back")
    if brightness >= 0.65:
        mood_tags.append("bright")
    if brightness <= 0.25:
        mood_tags.append("dark")
    if vocals >= 0.60:
        mood_tags.append("vocal_led")
    if not mood_tags:
        mood_tags.append("balanced")

    return {
        "danceability_score": round(danceability, 4),
        "danceability_label": (
            "high" if danceability >= 0.72
            else "medium" if danceability >= 0.48
            else "low"
        ),
        "physical_energy": round(physical_energy, 4),
        "tension": round(tension, 4),
        "peakness": round(float(np.clip(peak_intensity, 0.0, 1.0)), 4),
        "fatigue_risk": round(fatigue_risk, 4),
        "mood_tags": mood_tags,
        "breakdown": {
            "groove": round(groove_score, 4),
            "drums": round(drums, 4),
            "bass": round(bass, 4),
            "vocals": round(vocals, 4),
            "brightness": round(brightness, 4),
            "tempo_fit": round(tempo_fit, 4),
        },
        "method": "explainable_audio_features",
    }


def _detect_vocal_events(
    stem_activity_windows: list[dict],
    *,
    entry_threshold: float = 0.35,
    exit_threshold: float = 0.25,
    min_gap_sec: float = 2.0,
) -> list[dict]:
    """Detect vocal enter/exit events from stem activity windows.

    Each event: {time, type: "enter"|"exit", confidence, vocal_level}.
    """
    if not stem_activity_windows:
        return []

    events: list[dict] = []
    was_active = False

    for i, w in enumerate(stem_activity_windows):
        vocal = float(w.get("vocals", 0.0))
        t = float(w.get("start", 0.0))

        if not was_active and vocal >= entry_threshold:
            # Vocal enters
            peak_idx = i
            peak_val = vocal
            for j in range(i, min(i + 4, len(stem_activity_windows))):
                v = float(stem_activity_windows[j].get("vocals", 0.0))
                if v > peak_val:
                    peak_val = v
                    peak_idx = j
            events.append({
                "time": round(float(stem_activity_windows[peak_idx].get("start", t)), 2),
                "type": "enter",
                "confidence": round(min(1.0, vocal / 0.7), 3),
                "vocal_level": round(vocal, 3),
            })
            was_active = True

        elif was_active and vocal <= exit_threshold:
            # Vocal exits — confirm with next windows
            confirmed = True
            for j in range(i + 1, min(i + 3, len(stem_activity_windows))):
                if float(stem_activity_windows[j].get("vocals", 0.0)) > exit_threshold:
                    confirmed = False
                    break
            if confirmed:
                events.append({
                    "time": round(t, 2),
                    "type": "exit",
                    "confidence": round(min(1.0, (exit_threshold - vocal) / exit_threshold), 3),
                    "vocal_level": round(vocal, 3),
                })
                was_active = False

    # Deduplicate: merge events closer than min_gap_sec
    if len(events) >= 2:
        merged: list[dict] = [events[0]]
        for e in events[1:]:
            last = merged[-1]
            if (e["time"] - last["time"]) < min_gap_sec and e["type"] == last["type"]:
                # Keep the one with higher confidence
                if e["confidence"] > last["confidence"]:
                    merged[-1] = e
            else:
                merged.append(e)
        events = merged

    return events


def _compute_bass_risk_windows(
    stem_activity_windows: list[dict],
    *,
    heavy_threshold: float = 0.55,
) -> list[dict]:
    """Tag windows where bass is dominant → potential cross-song bass conflict.

    Returns per-window bass risk info: {start, end, bass_level, bass_dominance, risk}.
    """
    if not stem_activity_windows:
        return []

    windows: list[dict] = []
    for w in stem_activity_windows:
        bass = float(w.get("bass", 0.0))
        drums = float(w.get("drums", 0.0))
        vocals = float(w.get("vocals", 0.0))
        other = float(w.get("other", 0.0))
        total = bass + drums + vocals + other
        if total <= 1e-8:
            continue

        bass_dominance = bass / total
        is_heavy = bass > heavy_threshold
        risk = "high" if is_heavy and bass_dominance > 0.4 else \
               "medium" if is_heavy else \
               "low"

        windows.append({
            "start": float(w.get("start", 0.0)),
            "end": float(w.get("end", 0.0)),
            "bass_level": round(bass, 4),
            "bass_dominance": round(bass_dominance, 4),
            "risk": risk,
        })
    return windows


def _enhance_transition_windows(
    transition_windows: list[dict],
    stem_activity_windows: list[dict],
) -> list[dict]:
    """Add stem-aware scores to transition windows: tag vocal-free, drum-heavy, bass-solo.

    Adjusts mix_in_score and mix_out_score using real stem activity data.
    """
    if not transition_windows:
        return transition_windows

    # Build stem activity index for fast lookup
    def _stem_for_range(start: float, end: float) -> dict:
        vocals_vals: list[float] = []
        drums_vals: list[float] = []
        bass_vals: list[float] = []
        other_vals: list[float] = []
        for w in stem_activity_windows:
            ws = float(w.get("start", 0))
            we = float(w.get("end", ws + 2))
            if ws < end and we > start:
                vocals_vals.append(float(w.get("vocals", 0)))
                drums_vals.append(float(w.get("drums", 0)))
                bass_vals.append(float(w.get("bass", 0)))
                other_vals.append(float(w.get("other", 0)))
        return {
            "vocals": float(np.mean(vocals_vals)) if vocals_vals else 0.0,
            "drums": float(np.mean(drums_vals)) if drums_vals else 0.0,
            "bass": float(np.mean(bass_vals)) if bass_vals else 0.0,
            "other": float(np.mean(other_vals)) if other_vals else 0.0,
        }

    enhanced: list[dict] = []
    for tw in transition_windows:
        item = dict(tw)
        t_start = float(tw.get("start", 0))
        t_end = float(tw.get("end", t_start + 8))
        stem = _stem_for_range(t_start, t_end) if stem_activity_windows else {}

        # Stem tags
        tags: list[str] = []
        if stem.get("vocals", 0.5) < 0.2:
            tags.append("vocal_free")
        if stem.get("drums", 0.5) > 0.5:
            tags.append("drum_heavy")
        if stem.get("bass", 0.5) > 0.55:
            tags.append("bass_heavy")
        if stem.get("bass", 0.5) < 0.2 and stem.get("drums", 0.5) < 0.2:
            tags.append("ambient")
        if stem.get("vocals", 0.5) > 0.5:
            tags.append("vocal_led")
        if stem.get("drums", 0.5) > 0.5 and stem.get("vocals", 0.5) < 0.15 and stem.get("bass", 0.5) < 0.25:
            tags.append("drum_solo")
        item["stem_tags"] = tags

        # Store stem activity snapshot
        item["stem_snapshot"] = {
            k: round(v, 3) for k, v in stem.items()
        } if stem else {}

        # Adjust scores based on stem data
        mix_in = float(item.get("mix_in_score", 0.5))
        mix_out = float(item.get("mix_out_score", 0.5))

        if "vocal_free" in tags:
            mix_in += 0.10  # clean entry point
        if "drum_heavy" in tags:
            mix_in += 0.06  # good rhythmic anchor for incoming track
            mix_out += 0.04  # good rhythmic anchor for outgoing
        if "bass_heavy" in tags:
            mix_in -= 0.08  # bass conflict risk
            mix_out -= 0.06
        if "ambient" in tags:
            mix_out += 0.12  # easy to fade out
            mix_in -= 0.04  # weak entry
        if "vocal_led" in tags:
            mix_in -= 0.10  # vocal clash if incoming has vocals
            mix_out -= 0.08  # hard to exit during vocals

        item["mix_in_score"] = round(float(np.clip(mix_in, 0.0, 1.0)), 4)
        item["mix_out_score"] = round(float(np.clip(mix_out, 0.0, 1.0)), 4)

        # Clean candidate refined with stem data
        label = str(item.get("label", "")).lower()
        has_vocal_free = "vocal_free" in tags
        has_drums = stem.get("drums", 0) > 0.25
        energy = float(item.get("energy", 0.5))
        if label in ("intro", "breakdown", "outro"):
            item["clean_candidate"] = bool(has_vocal_free and has_drums and energy <= 0.6)
        else:
            item["clean_candidate"] = bool(item.get("clean_candidate", False))

        enhanced.append(item)

    return enhanced


def _recommend_transition_techniques(
    phrase_map: list[dict],
    transition_windows: list[dict],
    stem_activity_windows: list[dict] | None = None,
) -> list[dict]:
    """For each phrase section, recommend the best transition presets.

    Returns a list of transition recommendations, one per phrase, each with:
      - time range
      - section label
      - best MIX-IN presets (B enters here)
      - best MIX-OUT presets (A exits here)
      - overall recommendation type (entry_point, exit_point, both, avoid)

    The logic encodes DJ knowledge about which structural positions work
    with which transition techniques.
    """
    if not phrase_map:
        return []

    # ── Preset categories for recommendation ──────────────────────────
    IN_PRESETS_BY_ROLE = {
        "clean_entry":   ["fade", "neural_fade", "melt"],
        "rhythm_entry":  ["filter_sweep", "eq_bass_swap", "wave"],
        "energy_entry":  ["riser", "breakdown_drop", "hard_cut"],
        "ambient_entry": ["dissolve", "lunar_echo", "harmonic_sustain"],
        "dramatic_entry":["hydrant", "sweep", "neural_echo_out"],
    }
    OUT_PRESETS_BY_ROLE = {
        "clean_exit":    ["fade", "melt", "neural_fade"],
        "echo_exit":     ["echo_freeze", "lunar_echo", "neural_echo_out"],
        "energy_exit":   ["riser", "hydrant", "sweep"],
        "ambient_exit":  ["dissolve", "tremolo", "harmonic_sustain"],
        "cut_exit":      ["hard_cut", "breakdown_drop", "eq_bass_swap"],
    }

    # ── Score a window for each role ───────────────────────────────────
    def _score_role(window: dict, role: str, direction: str) -> float:
        """Score 0-1 how well this window fits a given role."""
        label = str(window.get("label", "")).lower()
        energy = float(window.get("energy", 0.5))
        intensity = float(window.get("intensity", energy))
        is_peak = bool(window.get("is_peak_section", False))
        is_valley = bool(window.get("is_valley_section", False))
        clean = bool(window.get("clean_candidate", False))
        stem_tags = window.get("stem_tags", [])

        score = 0.3  # baseline

        if role == "clean_entry":
            if label in ("intro",):        score += 0.4
            if clean:                       score += 0.2
            if "vocal_free" in stem_tags:   score += 0.15
            if energy < 0.5:                score += 0.1

        elif role == "rhythm_entry":
            if label in ("intro", "buildup"): score += 0.25
            if "drum_heavy" in stem_tags:    score += 0.3
            if energy > 0.4:                 score += 0.15

        elif role == "energy_entry":
            if is_peak:                      score += 0.35
            if label in ("drop", "buildup"): score += 0.3
            if intensity > 0.6:             score += 0.15

        elif role == "ambient_entry":
            if is_valley:                    score += 0.3
            if label in ("breakdown",):      score += 0.35
            if energy < 0.4:                score += 0.15

        elif role == "dramatic_entry":
            if is_peak:                      score += 0.3
            if energy > 0.7:                score += 0.2
            if label in ("drop",):           score += 0.2

        # ── Direction adjustments ──
        if direction == "out":
            if role == "clean_exit":
                if label in ("outro",):         score += 0.4
                if energy < 0.45:               score += 0.15
                if "vocal_free" in stem_tags:   score += 0.1
            elif role == "echo_exit":
                if label in ("outro", "breakdown", "verse"): score += 0.25
                if "vocal_led" in stem_tags:    score += 0.2
            elif role == "energy_exit":
                if is_peak:                      score += 0.35
                if intensity > 0.65:            score += 0.2
            elif role == "ambient_exit":
                if is_valley:                    score += 0.3
                if label in ("breakdown",):      score += 0.3
            elif role == "cut_exit":
                if label in ("drop", "outro"):   score += 0.2
                if energy > 0.6:                score += 0.15

        return float(min(1.0, score))

    # ── Build recommendations per window ───────────────────────────────
    recommendations: list[dict] = []
    windows = transition_windows if transition_windows else phrase_map

    for i, w in enumerate(windows):
        start = float(w.get("start", 0))
        end = float(w.get("end", start + 8))
        label = str(w.get("label", "?"))
        energy = float(w.get("energy", 0.5))

        # Score all roles
        in_scores = {role: _score_role(w, role, "in") for role in IN_PRESETS_BY_ROLE}
        out_scores = {role: _score_role(w, role, "out") for role in OUT_PRESETS_BY_ROLE}

        # Pick top 2 roles for each direction
        top_in = sorted(in_scores.items(), key=lambda x: -x[1])[:2]
        top_out = sorted(out_scores.items(), key=lambda x: -x[1])[:2]

        # Collect recommended presets
        in_presets: list[dict] = []
        for role, score in top_in:
            if score < 0.4:
                continue
            for p in IN_PRESETS_BY_ROLE[role][:2]:
                if not any(x["preset"] == p for x in in_presets):
                    in_presets.append({"preset": p, "role": role, "score": round(score, 3)})

        out_presets: list[dict] = []
        for role, score in top_out:
            if score < 0.4:
                continue
            for p in OUT_PRESETS_BY_ROLE[role][:2]:
                if not any(x["preset"] == p for x in out_presets):
                    out_presets.append({"preset": p, "role": role, "score": round(score, 3)})

        # Determine recommendation type
        best_in_score = top_in[0][1] if top_in else 0.0
        best_out_score = top_out[0][1] if top_out else 0.0

        if best_in_score > 0.55 and best_out_score > 0.55:
            rec_type = "both"
        elif best_in_score > 0.55:
            rec_type = "entry_point"
        elif best_out_score > 0.55:
            rec_type = "exit_point"
        elif best_in_score < 0.3 and best_out_score < 0.3:
            rec_type = "avoid"
        else:
            rec_type = "neutral"

        # Position context
        rel_pos = start / max(float(phrase_map[-1].get("end", 1)) if phrase_map else 1, 1)
        if rel_pos < 0.12:
            position = "beginning"
        elif rel_pos > 0.85:
            position = "ending"
        elif 0.3 < rel_pos < 0.7:
            position = "middle"
        else:
            position = "transition_zone"

        recommendations.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "label": label,
            "energy": round(energy, 3),
            "position": position,
            "type": rec_type,
            "best_for_mix_in": in_presets[:4],
            "best_for_mix_out": out_presets[:4],
            "role_scores_in": {k: round(v, 3) for k, v in sorted(in_scores.items(), key=lambda x: -x[1]) if v > 0.25},
            "role_scores_out": {k: round(v, 3) for k, v in sorted(out_scores.items(), key=lambda x: -x[1]) if v > 0.25},
        })

    return recommendations


MAX_ANALYSIS_DURATION = 420.0  # 7 min cap — sufficient for BPM/key/energy; prevents OOM on long mixes


def analyze_audio_file(file_path: str, *, title: str | None = None, artist: str | None = None, **_kwargs) -> dict:
    """Full analysis: BPM, beat points, downbeats, key, camelot key, energy, cue points, phrase map, duration.

    `title` / `artist` are accepted for forward-compatibility with callers that
    pass song metadata (used by future genre/style classifiers); currently ignored.
    """
    import librosa
    import soundfile as sf

    # Get real file duration from metadata (no audio decode) so we always report true length
    try:
        real_duration = float(sf.info(file_path).duration)
    except Exception:
        real_duration = None

    y, sr = librosa.load(file_path, sr=22050, duration=MAX_ANALYSIS_DURATION)
    # Duration used for analysis-relative positioning (capped)
    analysis_duration = float(librosa.get_duration(y=y, sr=sr))
    # Reported duration = real file length when available
    duration = real_duration if real_duration is not None else analysis_duration

    # BPM + beat points
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_points = [round(float(t), 3) for t in beat_times]
    bpm_curve, tempo_stability = _build_bpm_curve(beat_times)
    beatgrid_summary = _summarize_beatgrid(beat_times, bpm_curve, tempo_stability)

    # Downbeats and meter are inferred from the same beat-accent evidence.
    downbeats, time_signature = _detect_downbeats_with_meter(y, sr, beat_times)

    # Energy
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(np.tanh(float(np.mean(rms)) * 8.0), 0.0, 1.0))
    energy_curve = _build_energy_curve(y, sr)
    loudness_profile = _analyze_loudness(y, sr)

    # Key detection (CQT + CENS cross-validated Krumhansl-Schmuckler)
    key_result = _analyze_key(y, sr)
    root_note, mode_str = key_result["key"].split(" ") if " " in key_result["key"] else (key_result["key"], "major")
    key_confidence = key_result["key_confidence"]
    camelot_key = key_result["camelot_key"]

    # Section detection → cue points (use analysis_duration for relative-position labels)
    cue_points = _detect_sections(y, sr, analysis_duration)

    # Phrase structure (8-bar segments with labels)
    phrase_map = _detect_phrase_structure(y, sr, analysis_duration, downbeats)
    phrase_map = _attach_phrase_energy(phrase_map, energy_curve)

    # ── Extended analysis ──────────────────────────────────────────
    # Section intensity scoring
    phrase_map = _score_section_intensity(phrase_map, energy_curve, y, sr)

    # Groove / danceability score
    groove = _compute_groove_score(beat_times, downbeats, bpm_curve, tempo_stability)

    # Transition windows (label/energy based, will be enhanced with stem data later)
    transition_windows = _build_transition_windows(phrase_map)
    spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    dancefloor_profile = _analyze_dancefloor_profile(
        bpm=bpm,
        energy=energy,
        groove=groove,
        spectral_centroid=spectral_centroid,
        phrase_map=phrase_map,
    )

    return {
        "bpm": round(bpm, 1),
        "duration": round(duration, 2),
        "energy": round(energy, 3),
        "key": key_result["key"],
        "camelot_key": key_result["camelot_key"],
        "key_confidence": key_result["key_confidence"],
        "key_profile": {
            "tonal_clarity": key_result["tonal_clarity"],
            "relative_ambiguity": key_result["relative_ambiguity"],
            "candidates": key_result["candidates"],
            "method": key_result["method"],
        },
        "beat_points": beat_points,
        "bpm_curve": bpm_curve,
        "tempo_stability": tempo_stability,
        **beatgrid_summary,
        "downbeats": downbeats,
        "cue_points": cue_points,
        "phrase_map": phrase_map,
        "energy_curve": energy_curve,
        "loudness_profile": loudness_profile,
        "transition_windows": transition_windows,
        "time_signature": time_signature,
        "groove": groove,
        "danceability_score": dancefloor_profile["danceability_score"],
        "dancefloor_profile": dancefloor_profile,
        "dj_hot_cues": _generate_dj_hot_cues(phrase_map, transition_windows, energy_curve, duration),
        "transition_recommendations": _recommend_transition_techniques(
            phrase_map, transition_windows,
        ),
    }
