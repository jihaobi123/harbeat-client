"""Phrase normalization and anchor extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.datatypes import BeatGrid, PhraseAnchor, PhraseSegment
from core.enums import PhraseType


@dataclass(slots=True)
class SongFormerClient:
    """Mockable wrapper around a SongFormer-like phrase segmentation model."""

    model_name: str = "songformer-mock"

    def infer_phrases(self, audio_path: str | Path, duration_seconds: float) -> list[dict[str, Any]]:
        duration = max(duration_seconds, 1.0)
        section = duration / 5.0
        return [
            {"label": "Intro", "start": 0.0, "end": min(section, duration), "confidence": 0.83},
            {"label": "Verse", "start": min(section, duration), "end": min(section * 2, duration), "confidence": 0.78},
            {"label": "Build", "start": min(section * 2, duration), "end": min(section * 3, duration), "confidence": 0.74},
            {"label": "Chorus", "start": min(section * 3, duration), "end": min(section * 4, duration), "confidence": 0.88},
            {"label": "Outro", "start": min(section * 4, duration), "end": duration, "confidence": 0.81},
        ]


@dataclass(slots=True)
class PhraseAnalyzer:
    """Normalizes structure model output into DJ-usable phrases and anchors."""

    songformer_client: SongFormerClient

    def analyze(self, path: Path, duration_seconds: float, beatgrid: BeatGrid) -> tuple[list[PhraseSegment], list[PhraseAnchor]]:
        raw_phrases = self.songformer_client.infer_phrases(path, duration_seconds)
        phrases = [self._build_segment(raw, beatgrid) for raw in raw_phrases]
        anchors = self._build_anchors(phrases)
        return phrases, anchors

    def normalize_phrase_label(self, label: str) -> PhraseType:
        lookup = {
            "intro": PhraseType.INTRO,
            "groove": PhraseType.VERSE,
            "verse": PhraseType.VERSE,
            "chorus": PhraseType.CHORUS,
            "bridge": PhraseType.BRIDGE,
            "build": PhraseType.BUILD,
            "drop": PhraseType.DROP,
            "break": PhraseType.BRIDGE,
            "reset": PhraseType.BRIDGE,
            "outro": PhraseType.OUTRO,
        }
        return lookup.get(label.strip().lower(), PhraseType.UNKNOWN)

    def _build_segment(self, raw: dict[str, Any], beatgrid: BeatGrid) -> PhraseSegment:
        start_bar = self._nearest_bar(float(raw["start"]), beatgrid, round_up=False)
        end_bar = self._nearest_bar(float(raw["end"]), beatgrid, round_up=True)
        end_bar = max(end_bar, start_bar)
        start_time = self._downbeat_time(start_bar, beatgrid, float(raw["start"]))
        end_time = self._downbeat_time(end_bar, beatgrid, float(raw["end"]))
        phrase_type = self.normalize_phrase_label(str(raw.get("label", "unknown")))
        confidence = float(raw.get("confidence", 1.0))
        total_bars = max(beatgrid.bars, 1)
        mix_role = self._infer_mix_role(phrase_type, start_bar, end_bar, total_bars)
        mix_in_score, mix_out_score, reset_score, sustain_score = self._segment_scores(
            phrase_type=phrase_type,
            mix_role=mix_role,
            confidence=confidence,
            start_bar=start_bar,
            end_bar=end_bar,
            total_bars=total_bars,
        )
        boundary_strength_in = self._boundary_strength_in(phrase_type, confidence, start_bar, end_bar, total_bars)
        boundary_strength_out = self._boundary_strength_out(phrase_type, confidence, start_bar, end_bar, total_bars)
        return PhraseSegment(
            phrase_type=phrase_type,
            start_time=start_time,
            end_time=end_time,
            start_bar=start_bar,
            end_bar=end_bar,
            confidence=confidence,
            mix_role=mix_role,
            boundary_strength_in=boundary_strength_in,
            boundary_strength_out=boundary_strength_out,
            mix_in_score=mix_in_score,
            mix_out_score=mix_out_score,
            reset_score=reset_score,
            sustain_score=sustain_score,
        )

    def _build_anchors(self, phrases: list[PhraseSegment]) -> list[PhraseAnchor]:
        anchors: list[PhraseAnchor] = []
        for phrase in phrases:
            anchors.append(
                PhraseAnchor(
                    bar=phrase.start_bar,
                    beat=1,
                    anchor_type="phrase_start",
                    strength=phrase.boundary_strength_in,
                    phrase_type=phrase.phrase_type,
                    mix_role=phrase.mix_role,
                    entry_score=phrase.mix_in_score,
                    exit_score=min(1.0, phrase.mix_out_score * 0.35),
                    boundary_confidence=phrase.boundary_strength_in,
                    notes=[f"{phrase.mix_role} phrase entry"],
                )
            )
            anchors.append(
                PhraseAnchor(
                    bar=phrase.end_bar,
                    beat=1,
                    anchor_type="phrase_end",
                    strength=phrase.boundary_strength_out,
                    phrase_type=phrase.phrase_type,
                    mix_role=phrase.mix_role,
                    entry_score=min(1.0, phrase.mix_in_score * 0.30),
                    exit_score=phrase.mix_out_score,
                    boundary_confidence=phrase.boundary_strength_out,
                    notes=[f"{phrase.mix_role} phrase release"],
                )
            )
            if phrase.reset_score >= 0.70:
                anchors.append(
                    PhraseAnchor(
                        bar=phrase.start_bar,
                        beat=1,
                        anchor_type="reset_point",
                        strength=max(phrase.boundary_strength_in, phrase.reset_score),
                        phrase_type=phrase.phrase_type,
                        mix_role=phrase.mix_role,
                        entry_score=phrase.mix_in_score,
                        exit_score=phrase.mix_out_score,
                        boundary_confidence=max(phrase.boundary_strength_in, phrase.reset_score),
                        notes=["reset-oriented phrase anchor"],
                    )
                )
            for bar in range(phrase.start_bar, phrase.end_bar + 1, 2):
                strength = float(0.52 + phrase.sustain_score * 0.25)
                if phrase.mix_role in {"safe_intro", "groove_entry"}:
                    strength += 0.08
                if phrase.mix_role == "reset_zone":
                    strength -= 0.08
                anchors.append(
                    PhraseAnchor(
                        bar=bar,
                        beat=1,
                        anchor_type="eight_count_start",
                        strength=float(min(max(strength, 0.35), 0.92)),
                        phrase_type=phrase.phrase_type,
                        mix_role=phrase.mix_role,
                        entry_score=min(1.0, phrase.mix_in_score * 0.85),
                        exit_score=min(1.0, phrase.mix_out_score * 0.85),
                        boundary_confidence=float(min(max((phrase.boundary_strength_in + phrase.boundary_strength_out) / 2.0, 0.35), 0.9)),
                        notes=["8-count continuity anchor"],
                    )
                )
        dedup: dict[tuple[int, str], PhraseAnchor] = {}
        for anchor in anchors:
            key = (anchor.bar, anchor.anchor_type)
            if key not in dedup or dedup[key].strength < anchor.strength:
                dedup[key] = anchor
        return sorted(dedup.values(), key=lambda item: (item.bar, item.anchor_type))

    def _infer_mix_role(self, phrase_type: PhraseType, start_bar: int, end_bar: int, total_bars: int) -> str:
        base_role = {
            PhraseType.INTRO: "safe_intro",
            PhraseType.VERSE: "groove_entry",
            PhraseType.BUILD: "energy_lift",
            PhraseType.CHORUS: "peak_release",
            PhraseType.DROP: "peak_release",
            PhraseType.BRIDGE: "reset_zone",
            PhraseType.OUTRO: "outro_release",
        }.get(phrase_type, "neutral")
        if phrase_type == PhraseType.OUTRO:
            return "outro_release"
        if phrase_type == PhraseType.INTRO:
            return "safe_intro"
        if phrase_type == PhraseType.UNKNOWN and end_bar >= max(total_bars - 1, 1):
            return "outro_release"
        if phrase_type == PhraseType.UNKNOWN and start_bar <= 2:
            return "safe_intro"
        return base_role

    def _segment_scores(
        self,
        phrase_type: PhraseType,
        mix_role: str,
        confidence: float,
        start_bar: int,
        end_bar: int,
        total_bars: int,
    ) -> tuple[float, float, float, float]:
        base = {
            "safe_intro": (0.88, 0.50, 0.20, 0.72),
            "groove_entry": (0.82, 0.58, 0.18, 0.80),
            "energy_lift": (0.62, 0.76, 0.22, 0.55),
            "peak_release": (0.78, 0.70, 0.12, 0.48),
            "reset_zone": (0.55, 0.83, 0.82, 0.32),
            "outro_release": (0.38, 0.92, 0.40, 0.35),
            "neutral": (0.50, 0.50, 0.20, 0.50),
        }[mix_role]
        mix_in_score, mix_out_score, reset_score, sustain_score = base
        length_bars = self._phrase_length_bars(start_bar, end_bar)
        confidence_bias = (confidence - 0.5) * 0.2
        mix_in_score += confidence_bias
        mix_out_score += confidence_bias
        if length_bars < 4:
            sustain_score -= 0.18
            mix_in_score -= 0.06
        elif length_bars >= 8 and mix_role in {"safe_intro", "groove_entry"}:
            sustain_score += 0.08
        if phrase_type == PhraseType.BUILD:
            mix_out_score += 0.05
        if phrase_type == PhraseType.OUTRO and end_bar >= max(total_bars - 1, 1):
            mix_out_score += 0.04
        return tuple(float(min(max(score, 0.0), 1.0)) for score in (mix_in_score, mix_out_score, reset_score, sustain_score))

    def _boundary_strength_in(self, phrase_type: PhraseType, confidence: float, start_bar: int, end_bar: int, total_bars: int) -> float:
        score = 0.40 + confidence * 0.35
        if phrase_type in {PhraseType.INTRO, PhraseType.VERSE, PhraseType.CHORUS, PhraseType.DROP}:
            score += 0.10
        if start_bar <= 2:
            score += 0.08
        if self._phrase_length_bars(start_bar, end_bar) < 4:
            score -= 0.08
        return float(min(max(score, 0.0), 1.0))

    def _boundary_strength_out(self, phrase_type: PhraseType, confidence: float, start_bar: int, end_bar: int, total_bars: int) -> float:
        score = 0.38 + confidence * 0.34
        if phrase_type in {PhraseType.BUILD, PhraseType.BRIDGE, PhraseType.OUTRO}:
            score += 0.12
        if end_bar >= max(total_bars - 1, 1):
            score += 0.10
        if self._phrase_length_bars(start_bar, end_bar) < 4:
            score -= 0.06
        return float(min(max(score, 0.0), 1.0))

    def _phrase_length_bars(self, start_bar: int, end_bar: int) -> int:
        return max(end_bar - start_bar + 1, 1)

    def _nearest_bar(self, timestamp: float, beatgrid: BeatGrid, round_up: bool) -> int:
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

    def _downbeat_time(self, bar: int, beatgrid: BeatGrid, fallback: float) -> float:
        for beat in beatgrid.beats:
            if beat.bar == bar and beat.is_downbeat:
                return float(beat.time)
        return fallback
