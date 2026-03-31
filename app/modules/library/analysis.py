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


def analyze_audio_file(file_path: str) -> dict:
    """Analyze an audio file and return BPM, key, energy, and duration."""
    import librosa

    y, sr = librosa.load(file_path, sr=22050)
    duration = float(librosa.get_duration(y=y, sr=sr))

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if not hasattr(tempo, '__len__') else float(tempo[0])

    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.clip(np.tanh(float(np.mean(rms)) * 8.0), 0.0, 1.0))

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

    return {
        "bpm": round(bpm, 1),
        "duration": round(duration, 2),
        "energy": round(energy, 3),
        "key": f"{root_note} {mode}",
        "camelot_key": camelot_key,
    }
