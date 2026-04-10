"""Offline analyzer pipeline for GrooveEngine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib

import librosa
import numpy as np

from core.datatypes import BeatGrid, BeatPoint, EnergyPoint, MusicalKey, PhraseSegment, TrackMetadata
from core.enums import PhraseType


@dataclass(slots=True)
class SongFormerClient:
    """Mockable wrapper around a SongFormer-like phrase segmentation model."""

    model_name: str = "songformer-mock"

    def infer_phrases(self, audio_path: str | Path, duration_seconds: float) -> list[dict[str, Any]]:
        """Return phrase-like segments for a track.

        This mock implementation partitions the song into common DJ-friendly sections.
        A real integration would call SongFormer and normalize its labels here.
        """

        duration = max(duration_seconds, 1.0)
        section = duration / 5.0
        raw = [
            {"label": "Intro", "start": 0.0, "end": min(section, duration), "confidence": 0.83},
            {"label": "Verse", "start": min(section, duration), "end": min(section * 2, duration), "confidence": 0.78},
            {"label": "Build", "start": min(section * 2, duration), "end": min(section * 3, duration), "confidence": 0.74},
            {"label": "Chorus", "start": min(section * 3, duration), "end": min(section * 4, duration), "confidence": 0.88},
            {"label": "Outro", "start": min(section * 4, duration), "end": duration, "confidence": 0.81},
        ]
        return raw

    def normalize_phrase_label(self, label: str) -> PhraseType:
        """Map external model labels to internal phrase enums."""

        lookup = {
            "intro": PhraseType.INTRO,
            "verse": PhraseType.VERSE,
            "chorus": PhraseType.CHORUS,
            "bridge": PhraseType.BRIDGE,
            "build": PhraseType.BUILD,
            "drop": PhraseType.DROP,
            "outro": PhraseType.OUTRO,
        }
        return lookup.get(label.strip().lower(), PhraseType.UNKNOWN)


class TrackAnalyzer:
    """Runs the full offline analysis pipeline for a single track."""

    def __init__(self, songformer_client: SongFormerClient | None = None) -> None:
        self.songformer_client = songformer_client or SongFormerClient()

    def analyze(self, audio_path: str | Path) -> TrackMetadata:
        """Analyze a track and return quantized metadata."""

        path = Path(audio_path)
        audio, sample_rate = librosa.load(path.as_posix(), sr=None, mono=False)
        if audio.ndim == 1:
            mono = audio
            channels = 1
        else:
            mono = librosa.to_mono(audio)
            channels = int(audio.shape[0])

        duration_seconds = float(librosa.get_duration(y=mono, sr=sample_rate))
        bpm, beat_times = self._extract_beatgrid(mono, sample_rate)
        beatgrid = self._build_beatgrid(bpm, beat_times)
        energy_bars = self._extract_energy_bars(mono, sample_rate, beatgrid)
        key = self._estimate_key(mono, sample_rate)
        phrases = self._extract_phrases(path, duration_seconds, beatgrid)

        track_id = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        return TrackMetadata(
            track_id=track_id,
            title=path.stem,
            artist=None,
            path=str(path.resolve()),
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
            beatgrid=beatgrid,
            phrases=phrases,
            energy_bars=energy_bars,
            key=key,
            analyzer_versions={
                "librosa": getattr(librosa, "__version__", "unknown"),
                "songformer": self.songformer_client.model_name,
                "beatnet": "mocked-via-librosa",
            },
        )

    def _extract_beatgrid(self, mono: np.ndarray, sample_rate: int) -> tuple[float, np.ndarray]:
        """Extract BPM and beat timestamps.

        BeatNet is requested in the target architecture. This prototype uses librosa as
        an interchangeable adapter point so the analyzer remains decoupled.
        """

        tempo, beats = librosa.beat.beat_track(y=mono, sr=sample_rate, units="frames")
        beat_times = librosa.frames_to_time(beats, sr=sample_rate)
        if len(beat_times) == 0:
            beat_times = np.array([0.0])
        return float(tempo), beat_times

    def _build_beatgrid(self, bpm: float, beat_times: np.ndarray) -> BeatGrid:
        """Map beat times to beat and bar coordinates."""

        beats: list[BeatPoint] = []
        for idx, beat_time in enumerate(beat_times, start=1):
            beat_in_bar = ((idx - 1) % 4) + 1
            bar = ((idx - 1) // 4) + 1
            beats.append(
                BeatPoint(
                    index=idx,
                    time=float(beat_time),
                    bar=bar,
                    beat_in_bar=beat_in_bar,
                    is_downbeat=beat_in_bar == 1,
                )
            )
        bars = max(beats[-1].bar, 1)
        downbeats = [beat.time for beat in beats if beat.is_downbeat]
        return BeatGrid(bpm=bpm, beats=beats, bars=bars, downbeats=downbeats)

    def _extract_energy_bars(self, mono: np.ndarray, sample_rate: int, beatgrid: BeatGrid) -> list[EnergyPoint]:
        """Compute RMS and spectral flux per bar."""

        hop_length = 512
        rms = librosa.feature.rms(y=mono, hop_length=hop_length)[0]
        onset = librosa.onset.onset_strength(y=mono, sr=sample_rate, hop_length=hop_length)
        frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sample_rate, hop_length=hop_length)

        energy_points: list[EnergyPoint] = []
        for bar in range(1, beatgrid.bars + 1):
            bar_beats = [beat for beat in beatgrid.beats if beat.bar == bar]
            if not bar_beats:
                continue
            start_time = bar_beats[0].time
            end_time = bar_beats[-1].time + (60.0 / max(beatgrid.bpm, 1.0))
            mask = (frame_times >= start_time) & (frame_times < end_time)
            bar_rms = float(np.mean(rms[mask])) if np.any(mask) else 0.0
            bar_flux = float(np.mean(onset[mask])) if np.any(mask) else 0.0
            combined = (bar_rms * 0.6) + (bar_flux * 0.4)
            energy_points.append(
                EnergyPoint(
                    bar=bar,
                    start_time=float(start_time),
                    end_time=float(end_time),
                    rms=bar_rms,
                    spectral_flux=bar_flux,
                    combined=combined,
                )
            )
        return self._normalize_energy(energy_points)

    def _normalize_energy(self, energy_points: list[EnergyPoint]) -> list[EnergyPoint]:
        """Normalize combined energy to a 0..1 range."""

        if not energy_points:
            return energy_points
        max_value = max(point.combined for point in energy_points) or 1.0
        normalized: list[EnergyPoint] = []
        for point in energy_points:
            normalized.append(
                EnergyPoint(
                    bar=point.bar,
                    start_time=point.start_time,
                    end_time=point.end_time,
                    rms=point.rms,
                    spectral_flux=point.spectral_flux,
                    combined=point.combined / max_value,
                )
            )
        return normalized

    def _estimate_key(self, mono: np.ndarray, sample_rate: int) -> MusicalKey:
        """Estimate a coarse key from chroma magnitudes."""

        chroma = librosa.feature.chroma_cqt(y=mono, sr=sample_rate)
        pitch_profile = np.mean(chroma, axis=1)
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        tonic = note_names[int(np.argmax(pitch_profile))]
        return MusicalKey(tonic=tonic, mode="unknown", camelot=None)

    def _extract_phrases(self, path: Path, duration_seconds: float, beatgrid: BeatGrid) -> list[PhraseSegment]:
        """Infer phrases and quantize them to bar boundaries."""

        raw_phrases = self.songformer_client.infer_phrases(path, duration_seconds)
        segments: list[PhraseSegment] = []
        for raw in raw_phrases:
            start_bar = self._nearest_bar(raw["start"], beatgrid, round_up=False)
            end_bar = self._nearest_bar(raw["end"], beatgrid, round_up=True)
            bar_beats = [beat for beat in beatgrid.beats if beat.bar == start_bar and beat.beat_in_bar == 1]
            start_time = bar_beats[0].time if bar_beats else float(raw["start"])
            end_bar_beats = [beat for beat in beatgrid.beats if beat.bar == end_bar and beat.beat_in_bar == 1]
            end_time = end_bar_beats[0].time if end_bar_beats else float(raw["end"])
            segments.append(
                PhraseSegment(
                    phrase_type=self.songformer_client.normalize_phrase_label(raw["label"]),
                    start_time=float(start_time),
                    end_time=float(end_time),
                    start_bar=start_bar,
                    end_bar=max(end_bar, start_bar),
                    confidence=float(raw.get("confidence", 1.0)),
                )
            )
        return segments

    def _nearest_bar(self, timestamp: float, beatgrid: BeatGrid, round_up: bool) -> int:
        """Convert a timestamp to the closest bar number."""

        downbeats = beatgrid.downbeats
        if not downbeats:
            return 1
        if round_up:
            for index, downbeat in enumerate(downbeats, start=1):
                if downbeat >= timestamp:
                    return index
            return len(downbeats)
        selected = 1
        for index, downbeat in enumerate(downbeats, start=1):
            if downbeat <= timestamp:
                selected = index
            else:
                break
        return selected
