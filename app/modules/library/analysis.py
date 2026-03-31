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

CUE_COLORS = ["#22c55e", "#3b82f6", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4", "#64748b"]


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


def analyze_audio_file(file_path: str) -> dict:
    """Full analysis: BPM, beat points, key, camelot key, energy, cue points, duration."""
    import librosa

    y, sr = librosa.load(file_path, sr=22050)
    duration = float(librosa.get_duration(y=y, sr=sr))

    # BPM + beat points
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_points = [round(float(t), 3) for t in beat_times]

    # Energy
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(np.tanh(float(np.mean(rms)) * 8.0), 0.0, 1.0))

    # Key detection (Krumhansl-Schmuckler)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_profile = np.mean(chroma, axis=1)
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

    # Section detection → cue points
    cue_points = _detect_sections(y, sr, duration)

    return {
        "bpm": round(bpm, 1),
        "duration": round(duration, 2),
        "energy": round(energy, 3),
        "key": f"{root_note} {mode}",
        "camelot_key": camelot_key,
        "beat_points": beat_points,
        "cue_points": cue_points,
    }
