"""Offline analyzer pipeline for GrooveEngine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib

import librosa
import numpy as np

from analyzer.beatgrid import BeatGridAnalyzer
from analyzer.descriptors import DescriptorAnalyzer
from analyzer.phrasing import PhraseAnalyzer, SongFormerClient
from core.datatypes import MusicalKey, TrackMetadata


@dataclass(slots=True)
class TrackAnalyzer:
    """Runs the full offline analysis pipeline for a single track."""

    songformer_client: SongFormerClient | None = None
    beatgrid_analyzer: BeatGridAnalyzer | None = None
    descriptor_analyzer: DescriptorAnalyzer | None = None
    phrase_analyzer: PhraseAnalyzer | None = None

    def __post_init__(self) -> None:
        self.songformer_client = self.songformer_client or SongFormerClient()
        self.beatgrid_analyzer = self.beatgrid_analyzer or BeatGridAnalyzer()
        self.descriptor_analyzer = self.descriptor_analyzer or DescriptorAnalyzer()
        self.phrase_analyzer = self.phrase_analyzer or PhraseAnalyzer(self.songformer_client)

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
        beatgrid, beat_analysis = self.beatgrid_analyzer.analyze(mono, sample_rate)
        phrases, phrase_anchors = self.phrase_analyzer.analyze(path, duration_seconds, beatgrid)
        energy_bars, band_descriptors, loudness_profile, stereo_profile, danceability_profile = self.descriptor_analyzer.analyze(
            audio=audio,
            mono=mono,
            sample_rate=sample_rate,
            beatgrid=beatgrid,
        )
        key = self._estimate_key(mono, sample_rate)

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
            beat_analysis=beat_analysis,
            phrases=phrases,
            phrase_anchors=phrase_anchors,
            energy_bars=energy_bars,
            band_descriptors=band_descriptors,
            loudness_profile=loudness_profile,
            stereo_profile=stereo_profile,
            danceability_profile=danceability_profile,
            key=key,
            analyzer_versions={
                "librosa": getattr(librosa, "__version__", "unknown"),
                "songformer": self.songformer_client.model_name,
                "beatgrid_backend": self.beatgrid_analyzer.preferred_backend,
                "beatgrid_backend_selected": beat_analysis.source,
                "beatgrid_backend_candidates": ",".join(extractor.source_name for extractor in (self.beatgrid_analyzer.extractors or [])),
                "descriptor_stack": "spectral-band-v1",
            },
        )

    def _estimate_key(self, mono: np.ndarray, sample_rate: int) -> MusicalKey:
        """Estimate a coarse key from chroma magnitudes."""

        chroma = librosa.feature.chroma_cqt(y=mono, sr=sample_rate)
        pitch_profile = np.mean(chroma, axis=1)
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        tonic = note_names[int(np.argmax(pitch_profile))]
        return MusicalKey(tonic=tonic, mode="unknown", camelot=None)
