"""Default playlist ordering based on pair compatibility.

The source offline prototype scores BPM, Camelot/key, energy and bass
similarity.  This runtime implementation uses already persisted LibrarySong
analysis fields so sequence requests stay fast and do not run STFT/librosa in
the live path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ..band_analysis import band_density, clamp01
from ..energy_hiphop import compute_dance_energy


CAM_MAJOR_TO_CAMELOT = {
    "B": "1B",
    "F#": "2B",
    "Gb": "2B",
    "Db": "3B",
    "C#": "3B",
    "Ab": "4B",
    "G#": "4B",
    "Eb": "5B",
    "D#": "5B",
    "Bb": "6B",
    "A#": "6B",
    "F": "7B",
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
}

CAM_MINOR_TO_CAMELOT = {
    "Ab": "1A",
    "G#": "1A",
    "Eb": "2A",
    "D#": "2A",
    "Bb": "3A",
    "A#": "3A",
    "F": "4A",
    "C": "5A",
    "G": "6A",
    "D": "7A",
    "A": "8A",
    "E": "9A",
    "B": "10A",
    "F#": "11A",
    "Gb": "11A",
    "C#": "12A",
    "Db": "12A",
}


@dataclass(frozen=True)
class TrackProfile:
    song: Any
    song_id: str
    title: str
    artist: str
    bpm: float
    camelot: str | None
    key: str | None
    energy: float
    bass_strength: float
    vocal_density: float


def camelot_from_key(key: str | None, scale: str | None = None) -> str | None:
    if not key:
        return None
    clean_key = str(key).strip()
    clean_scale = (scale or "").lower().strip()
    if not clean_scale:
        lowered = clean_key.lower()
        if "minor" in lowered or lowered.endswith(" min"):
            clean_scale = "minor"
        elif "major" in lowered or lowered.endswith(" maj"):
            clean_scale = "major"
        clean_key = (
            clean_key.replace("minor", "")
            .replace("major", "")
            .replace("min", "")
            .replace("maj", "")
            .strip()
        )
    if clean_scale == "major":
        return CAM_MAJOR_TO_CAMELOT.get(clean_key)
    if clean_scale == "minor":
        return CAM_MINOR_TO_CAMELOT.get(clean_key)
    return None


def build_track_profile(song: Any) -> TrackProfile:
    bands = band_density(song)
    music_features = getattr(song, "music_features", None) or {}
    dj = music_features.get("dj") if isinstance(music_features.get("dj"), dict) else {}
    energy = getattr(song, "energy", None)
    if energy is None:
        try:
            energy = compute_dance_energy(song).total
        except Exception:
            energy = 0.5
    bpm = (
        getattr(song, "bpm", None)
        or (music_features.get("bpm") if isinstance(music_features, dict) else None)
        or 120.0
    )
    vocal_density = (
        dj.get("vocal_density")
        or (getattr(song, "genre_profile", None) or {}).get("vocal_density")
        or bands["mid"]
    )
    bass_strength = (
        dj.get("bass_strength")
        or dj.get("bass_dominance")
        or dj.get("low_ratio")
        or bands["low"]
    )
    key = getattr(song, "key", None)
    scale = getattr(song, "scale", None) or getattr(song, "mode", None)
    camelot = getattr(song, "camelot_key", None) or camelot_from_key(key, scale)
    return TrackProfile(
        song=song,
        song_id=str(getattr(song, "id", "")),
        title=str(getattr(song, "title", "")),
        artist=str(getattr(song, "artist", "")),
        bpm=float(bpm or 120.0),
        camelot=camelot,
        key=key,
        energy=clamp01(energy, 0.5),
        bass_strength=clamp01(bass_strength, 0.5),
        vocal_density=clamp01(vocal_density, 0.5),
    )


def bpm_compatibility_score(a: TrackProfile, b: TrackProfile) -> float:
    diff = abs(a.bpm - b.bpm)
    if diff <= 1.0:
        return 1.0
    if diff <= 2.0:
        return 0.92
    if diff <= 4.0:
        return 0.80
    if diff <= 6.0:
        return 0.62
    if diff <= 8.0:
        return 0.42
    if diff <= 10.0:
        return 0.24
    return 0.0


def camelot_distance(a: str | None, b: str | None) -> float:
    if not a or not b or len(a) < 2 or len(b) < 2:
        return 3.5
    try:
        num_a = int(a[:-1])
        num_b = int(b[:-1])
    except ValueError:
        return 3.5
    ring = abs(num_a - num_b)
    ring = min(ring, 12 - ring)
    mode_penalty = 0.0 if a[-1:] == b[-1:] else 0.5
    return float(ring + mode_penalty)


def key_compatibility_score(a: TrackProfile, b: TrackProfile) -> float:
    if a.camelot and b.camelot:
        if a.camelot == b.camelot:
            return 1.0
        try:
            num_a = int(a.camelot[:-1])
            num_b = int(b.camelot[:-1])
        except ValueError:
            return max(0.10, 1.0 - camelot_distance(a.camelot, b.camelot) / 4.0)
        mode_a = a.camelot[-1]
        mode_b = b.camelot[-1]
        ring = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
        if num_a == num_b and mode_a != mode_b:
            return 0.92
        if ring == 1 and mode_a == mode_b:
            return 0.88
        if ring == 1 and mode_a != mode_b:
            return 0.78
        if ring == 2 and mode_a == mode_b:
            return 0.64
        if ring <= 3:
            return 0.48
        return 0.20
    if a.key and b.key and a.key == b.key:
        return 0.82
    return max(0.10, 1.0 - camelot_distance(a.camelot, b.camelot) / 4.0)


def energy_similarity_score(a: TrackProfile, b: TrackProfile) -> float:
    diff = abs(a.energy - b.energy) / max(a.energy, b.energy, 1e-6)
    return float(max(0.0, 1.0 - diff))


def pair_score(a: TrackProfile, b: TrackProfile) -> dict[str, float]:
    bpm_score = bpm_compatibility_score(a, b)
    key_score = key_compatibility_score(a, b)
    energy_score = energy_similarity_score(a, b)
    bass_score = max(0.0, 1.0 - abs(a.bass_strength - b.bass_strength) / 0.35)
    total = (
        0.42 * bpm_score
        + 0.34 * key_score
        + 0.14 * energy_score
        + 0.10 * bass_score
    )
    return {
        "total": round(float(total), 4),
        "bpm_score": round(float(bpm_score), 4),
        "key_score": round(float(key_score), 4),
        "energy_score": round(float(energy_score), 4),
        "bass_score": round(float(bass_score), 4),
    }


def choose_start_track(tracks: list[TrackProfile]) -> TrackProfile:
    bpm_values = sorted(track.bpm for track in tracks)
    median_bpm = bpm_values[len(bpm_values) // 2]
    return min(
        tracks,
        key=lambda t: (
            abs(t.bpm - median_bpm) * 0.8
            + abs(t.energy - 0.18) * 2.0
            + t.vocal_density * 0.8
        ),
    )


def plan_default_sequence(songs: Sequence[Any]) -> dict[str, Any]:
    profiles = [build_track_profile(song) for song in songs]
    if not profiles:
        return {"ordering_mode": "default", "sequence": [], "pair_scores": []}
    start = choose_start_track(profiles)
    ordered = [start]
    remaining = [track for track in profiles if track.song_id != start.song_id]
    pair_details: list[dict[str, Any]] = []
    while remaining:
        current = ordered[-1]
        scored: list[tuple[float, TrackProfile, dict[str, float]]] = []
        for candidate in remaining:
            score = pair_score(current, candidate)
            if score["bpm_score"] <= 0.0:
                continue
            scored.append((score["total"], candidate, score))
        if not scored:
            break
        scored.sort(key=lambda item: item[0], reverse=True)
        _, chosen, chosen_score = scored[0]
        ordered.append(chosen)
        remaining = [track for track in remaining if track.song_id != chosen.song_id]
        pair_details.append(
            {
                "from": current.song_id,
                "to": chosen.song_id,
                "from_song_id": current.song_id,
                "to_song_id": chosen.song_id,
                "from_title": current.title,
                "to_title": chosen.title,
                "from_bpm": round(current.bpm, 3),
                "to_bpm": round(chosen.bpm, 3),
                "from_camelot": current.camelot,
                "to_camelot": chosen.camelot,
                **chosen_score,
            }
        )

    sequence = []
    for idx, profile in enumerate(ordered):
        sequence.append(
            {
                "song_id": profile.song_id,
                "position": idx,
                "target_energy": round(profile.energy, 4),
                "actual_energy": round(profile.energy, 4),
                "breakdown": {
                    "ordering_mode": "default",
                    "bpm": round(profile.bpm, 3),
                    "camelot": profile.camelot,
                    "bass_strength": round(profile.bass_strength, 4),
                    "vocal_density": round(profile.vocal_density, 4),
                },
            }
        )
    return {
        "ordering_mode": "default",
        "sequence": sequence,
        "pair_scores": pair_details,
        "pair_breakdowns": pair_details,
        "start_track_id": start.song_id,
        "default_mix_debug": {
            "start_track_id": start.song_id,
            "start_track_reason": (
                "choose_start_track: closest to median BPM, moderate-low energy target 0.18, "
                "and lower vocal density."
            ),
            "pair_scores": pair_details,
        },
    }
