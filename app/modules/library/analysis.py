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


def _detect_downbeats(y: np.ndarray, sr: int, beat_times: np.ndarray) -> list[float]:
    """
    Detect downbeats (bar boundaries) by finding beat positions
    with strongest onset energy, assuming 4/4 time signature.
    """
    import librosa

    if len(beat_times) < 4:
        return [round(float(beat_times[0]), 3)] if len(beat_times) > 0 else []

    # Compute onset strength at each beat position
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    hop = 512
    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop)
    beat_frames = np.clip(beat_frames, 0, len(onset_env) - 1)
    beat_strengths = onset_env[beat_frames]

    # Find the phase offset (0-3) that maximizes total onset energy at downbeats
    best_phase = 0
    best_score = -1.0
    for phase in range(4):
        indices = list(range(phase, len(beat_strengths), 4))
        score = float(np.mean(beat_strengths[indices])) if indices else 0.0
        if score > best_score:
            best_score = score
            best_phase = phase

    downbeats = [round(float(beat_times[i]), 3) for i in range(best_phase, len(beat_times), 4)]
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

        del p["energy"]  # don't store raw energy in structure

    return phrases


def analyze_audio_file(file_path: str) -> dict:
    """Full analysis: BPM, beat points, downbeats, key, camelot key, energy, cue points, phrase map, duration."""
    import librosa

    y, sr = librosa.load(file_path, sr=22050)
    duration = float(librosa.get_duration(y=y, sr=sr))

    # BPM + beat points
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_points = [round(float(t), 3) for t in beat_times]

    # Downbeats (bar boundaries, 4/4 time)
    downbeats = _detect_downbeats(y, sr, beat_times)

    # Energy
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(np.tanh(float(np.mean(rms)) * 8.0), 0.0, 1.0))

    # Key detection (Krumhansl-Schmuckler)
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
        # Confidence: how well the best template matches (cosine similarity, 0-1)
        key_confidence = round(max(0, min(1, best_score)), 3)

    # Section detection → cue points
    cue_points = _detect_sections(y, sr, duration)

    # Phrase structure (8-bar segments with labels)
    phrase_map = _detect_phrase_structure(y, sr, duration, downbeats)

    return {
        "bpm": round(bpm, 1),
        "duration": round(duration, 2),
        "energy": round(energy, 3),
        "key": f"{root_note} {mode}",
        "camelot_key": camelot_key,
        "key_confidence": key_confidence,
        "beat_points": beat_points,
        "downbeats": downbeats,
        "cue_points": cue_points,
        "phrase_map": phrase_map,
    }
