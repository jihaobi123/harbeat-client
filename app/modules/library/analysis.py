from __future__ import annotations

import logging
from collections import Counter

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

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

CAMELOT_NUMBER = {v: (int(v[:-1]), v[-1]) for v in NOTE_MODE_TO_CAMELOT.values()}

CUE_COLORS = ["#22c55e", "#3b82f6", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4", "#64748b"]

SECTION_COLORS = {
    "Intro": "#22c55e", "Verse": "#3b82f6", "Chorus": "#ef4444",
    "Bridge": "#f59e0b", "Outro": "#64748b", "Break": "#8b5cf6",
    "Solo": "#ec4899", "Inst": "#06b6d4",
}

# ── Camelot helpers ────────────────────────────────────────────────────────


def camelot_distance(key_a: str, key_b: str) -> int:
    if not key_a or not key_b:
        return 99
    try:
        num_a, mode_a = int(key_a[:-1]), key_a[-1]
        num_b, mode_b = int(key_b[:-1]), key_b[-1]
    except (ValueError, IndexError):
        return 99
    if num_a == num_b and mode_a == mode_b:
        return 0
    if num_a == num_b and mode_a != mode_b:
        return 1
    if mode_a == mode_b:
        diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
        return diff
    diff = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    return diff + 1


def camelot_score(key_a: str, key_b: str) -> int:
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


# ── Beat / Downbeat / BPM (multi-engine: madmom + BeatNet + librosa) ──────


def _detect_beats_and_downbeats(
    file_path: str, y: np.ndarray, sr: int,
) -> tuple[list[float], list[float], float, dict]:
    """Detect beats, downbeats, BPM using multi-engine beat analysis.

    Returns (beat_points, downbeats, bpm, beat_meta) where beat_meta contains
    confidence, grid info, and engine details.
    """
    from app.modules.library.beat_engine import analyze_beats

    duration = float(len(y) / sr)
    result = analyze_beats(file_path, y, sr, duration)

    beat_meta = {
        "confidence": result.confidence,
        "confidence_details": result.confidence_details,
        "grid_offset": result.grid_offset,
        "grid_interval": result.grid_interval,
        "engines_used": result.engines_used,
        "needs_review": result.needs_review,
    }

    logger.info(
        "beat analysis: BPM=%.1f, %d beats, %d downbeats, confidence=%.2f, engines=%s%s",
        result.bpm, len(result.beat_points), len(result.downbeats),
        result.confidence, result.engines_used,
        " [NEEDS REVIEW]" if result.needs_review else "",
    )

    return result.beat_points, result.downbeats, result.bpm, beat_meta


# ── Structure detection (SSM + Checkerboard Novelty → energy fallback) ────


def _detect_structure(y: np.ndarray, sr: int, duration: float) -> list[dict]:
    """Detect song structure.  Primary: Self-Similarity Matrix; Fallback: energy envelope."""
    if duration < 15:
        return [{"time": 0, "label": "Intro", "color": SECTION_COLORS["Intro"]}]
    try:
        result = _structure_via_ssm(y, sr, duration)
        if len(result) >= 2:
            return result
        logger.info("SSM returned only %d cue(s), falling back to energy method", len(result))
    except Exception:
        logger.warning("SSM structure detection failed, using energy fallback", exc_info=True)
    return _structure_via_energy(y, sr, duration)


def _structure_via_ssm(y: np.ndarray, sr: int, duration: float) -> list[dict]:
    """Self-Similarity Matrix + Foote checkerboard kernel → boundaries → labels."""
    import librosa
    from scipy.ndimage import gaussian_filter, uniform_filter1d
    from scipy.signal import find_peaks
    from scipy.spatial.distance import cdist

    hop = 4096

    # Combined features: chroma (harmony) + MFCC (timbre)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
    feat = np.vstack([
        librosa.util.normalize(chroma, axis=1),
        librosa.util.normalize(mfcc, axis=1),
    ])

    n_frames = feat.shape[1]
    if n_frames < 10:
        return [{"time": 0, "label": "Intro", "color": SECTION_COLORS["Intro"]}]

    # Self-Similarity Matrix (cosine affinity)
    ssm = 1.0 - cdist(feat.T, feat.T, metric="cosine")
    ssm = gaussian_filter(ssm, sigma=2.0)

    # Checkerboard kernel novelty (Foote 2000)
    ks = min(64, n_frames // 3)
    ks = max(ks, 4)
    ks -= ks % 2  # ensure even
    novelty = _checkerboard_novelty(ssm, ks)

    nmax = novelty.max()
    if nmax > 1e-8:
        novelty /= nmax
    novelty = uniform_filter1d(novelty, size=3)

    # Peak-pick segment boundaries
    hop_time = hop / sr
    min_dist = max(1, int(8.0 / hop_time))  # ≥ 8 s between sections
    peaks, _ = find_peaks(novelty, height=0.10, distance=min_dist, prominence=0.04)

    boundaries: list[float] = [0.0]
    for p in peaks:
        t = round(float(p) * hop_time, 2)
        if 2.0 < t < duration - 2.0:
            boundaries.append(t)
    boundaries.append(round(duration, 2))

    # Label segments via feature clustering + energy
    labels = _label_segments(y, sr, hop, feat, boundaries, duration)

    cue_points = [
        {"time": boundaries[i], "label": lab, "color": SECTION_COLORS.get(lab, "#06b6d4")}
        for i, lab in enumerate(labels)
    ]
    return cue_points or [{"time": 0, "label": "Intro", "color": SECTION_COLORS["Intro"]}]


def _checkerboard_novelty(ssm: np.ndarray, kernel_size: int = 64) -> np.ndarray:
    """Foote checkerboard kernel applied along the diagonal of the SSM."""
    n = ssm.shape[0]
    half = kernel_size // 2
    k = np.ones((kernel_size, kernel_size))
    k[:half, :half] = -1
    k[half:, half:] = -1

    novelty = np.zeros(n)
    for i in range(half, n - half):
        novelty[i] = float(np.sum(ssm[i - half:i + half, i - half:i + half] * k))
    return np.maximum(novelty, 0)


def _label_segments(
    y: np.ndarray, sr: int, hop: int, feat: np.ndarray,
    boundaries: list[float], duration: float,
) -> list[str]:
    """Assign musical labels (Intro/Verse/Chorus/Bridge/Outro) via cosine clustering + energy."""
    import librosa
    from scipy.spatial.distance import cdist

    n_segs = len(boundaries) - 1
    if n_segs <= 0:
        return ["Intro"]

    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    seg_feats: list[np.ndarray] = []
    seg_energies: list[float] = []

    for i in range(n_segs):
        sf = max(0, min(int(boundaries[i] * sr / hop), feat.shape[1] - 1))
        ef = max(sf + 1, min(int(boundaries[i + 1] * sr / hop), feat.shape[1]))
        seg_feats.append(np.mean(feat[:, sf:ef], axis=1))
        rs, re = min(sf, len(rms) - 1), min(ef, len(rms))
        seg_energies.append(float(np.mean(rms[rs:re])) if re > rs else 0.0)

    seg_feats_arr = np.array(seg_feats)
    seg_e = np.array(seg_energies)
    max_e = seg_e.max() if seg_e.max() > 1e-8 else 1.0
    norm_e = seg_e / max_e

    # Greedy cosine clustering
    if n_segs > 1:
        d = cdist(seg_feats_arr, seg_feats_arr, metric="cosine")
        cids = [-1] * n_segs
        nc = 0
        for i in range(n_segs):
            if cids[i] >= 0:
                continue
            cids[i] = nc
            for j in range(i + 1, n_segs):
                if cids[j] < 0 and d[i][j] < 0.35:
                    cids[j] = nc
            nc += 1
    else:
        cids = [0]

    # Cluster statistics
    counts = Counter(cids)
    c_energy: dict[int, list[float]] = {}
    for i, c in enumerate(cids):
        c_energy.setdefault(c, []).append(norm_e[i])
    avg_e = {k: float(np.mean(v)) for k, v in c_energy.items()}

    # Map clusters → musical labels (most repeated high-energy = Chorus, etc.)
    sorted_c = sorted(avg_e, key=lambda c: (-counts[c], -avg_e[c]))
    c_label: dict[int, str] = {}
    used: set[str] = set()
    for c in sorted_c:
        if counts[c] >= 2 and avg_e[c] >= 0.55 and "Chorus" not in used:
            c_label[c] = "Chorus"
            used.add("Chorus")
        elif counts[c] >= 2 and "Verse" not in used:
            c_label[c] = "Verse"
            used.add("Verse")
        elif counts[c] >= 2:
            c_label[c] = "Bridge"
        elif avg_e[c] >= 0.5:
            c_label[c] = "Bridge"
        else:
            c_label[c] = "Break"

    # Position-based overrides for first / last segment
    labels: list[str] = []
    for i in range(n_segs):
        if i == 0 and (norm_e[i] < 0.5 or boundaries[i] / duration < 0.03):
            labels.append("Intro")
        elif i == n_segs - 1 and (norm_e[i] < 0.5 or boundaries[i] / duration > 0.8):
            labels.append("Outro")
        else:
            labels.append(c_label.get(cids[i], "Verse"))
    return labels


def _structure_via_energy(y: np.ndarray, sr: int, duration: float) -> list[dict]:
    """Fallback: energy-envelope heuristic (original method)."""
    import librosa

    rms = librosa.feature.rms(y=y, frame_length=sr * 2, hop_length=sr)[0]
    sec_fps = 1.0

    if len(rms) < 4:
        return [{"time": 0, "label": "Intro", "color": "#22c55e"}]

    smooth_win = max(1, round(sec_fps * 4))
    smoothed = np.convolve(rms, np.ones(smooth_win) / smooth_win, mode="same")
    deriv = np.diff(smoothed, prepend=smoothed[0])

    mean_abs = float(np.mean(np.abs(deriv))) + 1e-9
    transitions: list[dict] = []
    for i in range(2, len(deriv) - 1):
        if abs(deriv[i]) > mean_abs * 2.5:
            t = float(i / sec_fps)
            if not transitions or t - transitions[-1]["time"] > 3:
                transitions.append({"time": t, "strength": abs(deriv[i]), "rising": deriv[i] > 0})

    transitions.sort(key=lambda x: -x["strength"])
    top = sorted(transitions[:8], key=lambda x: x["time"])

    cue_points: list[dict] = [{"time": 0, "label": "Intro", "color": "#22c55e"}]
    for t in top:
        if t["time"] < 3 or t["time"] > duration - 3:
            continue
        rp = t["time"] / duration
        if rp < 0.12:
            lab, col = "Verse", "#3b82f6"
        elif t["rising"] and rp < 0.5:
            lab, col = "Chorus", "#ef4444"
        elif not t["rising"] and rp < 0.5:
            lab, col = "Verse", "#3b82f6"
        elif t["rising"]:
            lab, col = "Chorus", "#ef4444"
        elif rp > 0.8:
            lab, col = "Outro", "#64748b"
        else:
            lab, col = "Bridge", "#f59e0b"
        cue_points.append({"time": round(t["time"], 2), "label": lab, "color": col})

    if duration > 30 and not any(c["label"] == "Outro" for c in cue_points):
        oc = [t for t in transitions if not t["rising"] and t["time"] > duration * 0.7]
        ot = oc[0]["time"] if oc else duration - 15
        cue_points.append({"time": round(ot, 2), "label": "Outro", "color": "#64748b"})

    return cue_points


# ── Phrase structure (8-bar energy labeling) ───────────────────────────────


def _detect_phrase_structure(
    y: np.ndarray, sr: int, duration: float, downbeat_times: list[float],
) -> list[dict]:
    import librosa

    if len(downbeat_times) < 4:
        return [{"start": 0, "end": duration, "label": "intro", "bars": 0}]

    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    db_frames = librosa.time_to_frames(downbeat_times, sr=sr, hop_length=hop)
    db_frames = np.clip(db_frames, 0, len(rms) - 1)

    phrase_size = 8
    phrases: list[dict] = []
    i = 0
    while i < len(downbeat_times):
        end_i = min(i + phrase_size, len(downbeat_times))
        start_t = downbeat_times[i]
        end_t = downbeat_times[end_i - 1] if end_i < len(downbeat_times) else duration

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

    energies = np.array([p["energy"] for p in phrases])
    max_e = float(energies.max()) if energies.max() > 1e-8 else 1.0
    norm_energies = energies / max_e

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

        del p["energy"]

    return phrases


# ── Lightweight beat tracking with known BPM ──────────────────────────────


def _generate_beats_from_known_bpm(
    y: np.ndarray, sr: int, bpm: float, duration: float,
) -> tuple[list[float], list[float], dict]:
    """Generate beatgrid using librosa beat_track with a known BPM prior.

    Much faster than full multi-engine analysis (~2s vs ~120s).
    Returns (beat_points, downbeats, beat_meta).
    """
    import librosa

    # librosa beat_track with BPM prior — fast and accurate
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, bpm=bpm, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_points = [round(float(t), 3) for t in beat_times]

    if not beat_points:
        # Fallback: generate uniform grid
        interval = 60.0 / bpm
        beat_points = [round(i * interval, 3) for i in range(int(duration / interval) + 1)]

    # Compute grid interval and offset
    if len(beat_points) >= 2:
        intervals = np.diff(beat_points)
        grid_interval = round(float(np.median(intervals)), 4)
        grid_offset = round(beat_points[0], 4)
    else:
        grid_interval = round(60.0 / bpm, 4)
        grid_offset = 0.0

    # Snap to uniform grid
    grid_beats = []
    t = grid_offset
    while t < duration:
        grid_beats.append(round(t, 3))
        t += grid_interval
    if grid_beats:
        beat_points = grid_beats

    # Downbeats: every 4 beats
    downbeats = [beat_points[i] for i in range(0, len(beat_points), 4)]

    beat_meta = {
        "confidence": 0.95,  # high confidence — BPM from Spotify
        "confidence_details": {"source": "online_lookup", "engine_agreement": 1.0},
        "grid_offset": grid_offset,
        "grid_interval": grid_interval,
        "engines_used": ["online_lookup"],
        "needs_review": False,
    }

    return beat_points, downbeats, beat_meta


# ── Main entry point ───────────────────────────────────────────────────────


def analyze_audio_file(
    file_path: str,
    title: str = "",
    artist: str = "",
) -> dict:
    """Full analysis: BPM, beats, downbeats, key, energy, structure, phrases.

    Strategy:
    1. Try online lookup (Deezer API) for BPM — instant (<1s)
    2. If found → use online BPM + lightweight librosa beat tracking (~2s)
    3. If not found → full multi-engine local analysis (madmom + BeatNet + librosa)
    """
    import librosa

    y, sr = librosa.load(file_path, sr=22050)
    duration = float(librosa.get_duration(y=y, sr=sr))

    # ── Step 1: Try online BPM lookup ─────────────────────────────────
    online_info = None
    if title or artist:
        try:
            from app.modules.library.bpm_lookup import lookup_track_info, normalize_bpm
            online_info = lookup_track_info(title, artist, file_duration=duration)
        except Exception:
            logger.warning("Online BPM lookup module failed", exc_info=True)

    # ── Step 2: BPM + Beat tracking ───────────────────────────────────
    if online_info and online_info.get("bpm"):
        # Fast path: use online BPM + lightweight beat tracking
        raw_bpm = online_info["bpm"]
        bpm = normalize_bpm(raw_bpm, online_info.get("alt_bpm"))
        if bpm != raw_bpm:
            logger.info("BPM normalized: %s → %.0f (DJ range)", raw_bpm, bpm)
        logger.info("Using %s BPM=%.1f for '%s - %s'",
                    online_info.get('source', 'online'), bpm, artist, title)
        beat_points, downbeats, beat_meta = _generate_beats_from_known_bpm(
            y, sr, bpm, duration,
        )
    else:
        # Slow path: full local multi-engine analysis
        logger.info("No online BPM found, running local analysis for '%s - %s'",
                    artist, title)
        beat_points, downbeats, bpm, beat_meta = _detect_beats_and_downbeats(
            file_path, y, sr,
        )

    # ── Step 3: Energy ────────────────────────────────────────────────
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(np.tanh(float(np.mean(rms)) * 8.0), 0.0, 1.0))

    # Use online energy if available (some sources provide it)
    if online_info and online_info.get("energy") is not None:
        energy = online_info["energy"]

    # ── Step 4: Key detection ─────────────────────────────────────────
    # Prefer online key if available; otherwise local Krumhansl-Schmuckler
    if online_info and online_info.get("key") and online_info.get("camelot_key"):
        key_str = online_info["key"]
        camelot_key = online_info["camelot_key"]
        key_confidence = 0.90
    else:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_profile = np.mean(chroma, axis=1)
        key_confidence = 0.0
        if np.sum(chroma_profile) == 0:
            root_note, mode, camelot_key = "C", "major", "8B"
        else:
            chroma_profile = chroma_profile / (np.linalg.norm(chroma_profile) + 1e-9)
            best_score = -1e9
            root_note, mode = "C", "major"
            for idx, note in enumerate(NOTE_NAMES):
                for template, m in [(MAJOR_TEMPLATE, "major"), (MINOR_TEMPLATE, "minor")]:
                    rotated = np.roll(template, idx)
                    rotated = rotated / (np.linalg.norm(rotated) + 1e-9)
                    score = float(np.dot(chroma_profile, rotated))
                    if score > best_score:
                        best_score = score
                        root_note, mode = note, m
            camelot_key = NOTE_MODE_TO_CAMELOT[(root_note, mode)]
            key_confidence = round(max(0, min(1, best_score)), 3)
        key_str = f"{root_note} {mode}"

    # ── Step 5: Structure detection (always local — Spotify doesn't have this)
    cue_points = _detect_structure(y, sr, duration)

    # ── Step 6: Phrase structure ──────────────────────────────────────
    phrase_map = _detect_phrase_structure(y, sr, duration, downbeats)

    return {
        "bpm": round(bpm, 1),
        "duration": round(duration, 2),
        "energy": round(energy, 3),
        "key": key_str,
        "camelot_key": camelot_key,
        "key_confidence": key_confidence,
        "beat_points": beat_points,
        "downbeats": downbeats,
        "cue_points": cue_points,
        "phrase_map": phrase_map,
        "beat_confidence": float(beat_meta["confidence"]),
        "beat_confidence_details": beat_meta["confidence_details"],
        "beat_grid_offset": float(beat_meta["grid_offset"]),
        "beat_grid_interval": float(beat_meta["grid_interval"]),
        "beat_engines_used": beat_meta["engines_used"],
        "beat_needs_review": bool(beat_meta["needs_review"]),
    }
