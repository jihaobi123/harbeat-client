from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import librosa, numpy as np
from core.datatypes import BeatAnalysis, BeatGrid, BeatPoint, PhaseCorrectionResult, RawBeatSequence

class BeatExtractor(Protocol):
    source_name: str
    def extract(self, mono: np.ndarray, sample_rate: int) -> RawBeatSequence: ...

@dataclass(slots=True)
class LibrosaBeatExtractor:
    source_name: str = "librosa"
    hop_length: int = 512
    def extract(self, mono: np.ndarray, sample_rate: int) -> RawBeatSequence:
        tempo, frames = librosa.beat.beat_track(y=mono, sr=sample_rate, hop_length=self.hop_length, units="frames")
        beats = librosa.frames_to_time(frames, sr=sample_rate, hop_length=self.hop_length).tolist()
        bpm = float(tempo) if float(tempo) > 0 else 0.0
        fallback = False
        if not beats:
            fallback = True
            duration = float(librosa.get_duration(y=mono, sr=sample_rate))
            bpm = bpm if bpm > 0 else 120.0
            interval = 60.0 / bpm
            beats = list(np.arange(0.0, max(duration, interval), interval))
        if bpm <= 0:
            bpm = self._estimate_bpm(beats)
        return RawBeatSequence(bpm=max(float(bpm), 1.0), beat_times=[float(t) for t in beats], source=self.source_name, confidence_hint=self._confidence_hint(beats), frame_hop_length=self.hop_length, fallback_used=fallback)
    def _confidence_hint(self, beats: list[float]) -> float:
        if len(beats) < 8: return 0.35
        intervals = np.diff(beats)
        if len(intervals) == 0: return 0.35
        mean = float(np.mean(intervals))
        return 0.35 if mean <= 1e-6 else float(np.clip(1.0 - float(np.std(intervals) / mean), 0.35, 0.92))
    def _estimate_bpm(self, beats: list[float]) -> float:
        if len(beats) < 2: return 120.0
        mean = float(np.mean(np.diff(beats)))
        return 120.0 if mean <= 1e-6 else 60.0 / mean

@dataclass(slots=True)
class StableGridBeatExtractor:
    source_name: str = "stable_grid"
    base_bpm: float = 120.0
    hop_length: int = 512
    def extract(self, mono: np.ndarray, sample_rate: int) -> RawBeatSequence:
        tempo, _ = librosa.beat.beat_track(y=mono, sr=sample_rate, hop_length=self.hop_length, units="frames")
        bpm = max(float(tempo) if float(tempo) > 0 else self.base_bpm, 1.0)
        duration = float(librosa.get_duration(y=mono, sr=sample_rate))
        interval = 60.0 / bpm
        beats = list(np.arange(0.0, max(duration, interval), interval))
        return RawBeatSequence(bpm=bpm, beat_times=[float(t) for t in beats], source=self.source_name, confidence_hint=0.55, frame_hop_length=self.hop_length, fallback_used=False)

@dataclass(slots=True)
class BeatAnalysisCandidate:
    raw: RawBeatSequence
    phase: PhaseCorrectionResult
    grid: BeatGrid
    analysis: BeatAnalysis
    backend_name: str
    selection_score: float

@dataclass(slots=True)
class BarPhaseCorrector:
    low_band_weight: float = 0.50
    onset_weight: float = 0.35
    regularity_weight: float = 0.15
    ambiguity_threshold: float = 0.08
    def correct(self, mono: np.ndarray, sample_rate: int, raw: RawBeatSequence) -> PhaseCorrectionResult:
        beats = raw.beat_times
        if len(beats) < 8:
            return PhaseCorrectionResult(selected_offset=0, offset_scores=[0.5] * 4, confidence=0.35, ambiguous=True, low_band_scores=[0.5] * 4, onset_scores=[0.5] * 4, regularity_scores=[0.5] * 4, notes=["Insufficient beats for reliable bar-phase correction."])
        low = self._normalize([self._low(mono, sample_rate, beats, offset) for offset in range(4)])
        onset = self._normalize([self._onset(mono, sample_rate, beats, offset) for offset in range(4)])
        reg = self._normalize([self._regularity(beats, offset) for offset in range(4)])
        scores = [float(np.clip(low[i] * self.low_band_weight + onset[i] * self.onset_weight + reg[i] * self.regularity_weight, 0.0, 1.0)) for i in range(4)]
        selected = int(np.argmax(scores)); ordered = sorted(scores, reverse=True); margin = ordered[0] - ordered[1]; ambiguous = margin < self.ambiguity_threshold
        notes = [f"Selected bar-phase offset {selected}."]
        if ambiguous: notes.append("Bar phase is ambiguous; top candidate only weakly leads.")
        return PhaseCorrectionResult(selected_offset=selected, offset_scores=scores, confidence=float(np.clip(ordered[0] * 0.7 + margin * 1.5, 0.0, 1.0)), ambiguous=ambiguous, low_band_scores=low, onset_scores=onset, regularity_scores=reg, notes=notes)
    def _candidate_downbeats(self, beats: list[float], offset: int) -> list[float]: return [beats[i] for i in range(offset, len(beats), 4)]
    def _low(self, mono: np.ndarray, sample_rate: int, beats: list[float], offset: int) -> float:
        freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=1024); mask = (freqs >= 30) & (freqs < 180); values = []
        for time in self._candidate_downbeats(beats, offset):
            start = max(0, int((time - 0.03) * sample_rate)); end = min(len(mono), int((time + 0.12) * sample_rate))
            if end <= start: continue
            spectrum = np.abs(librosa.stft(mono[start:end], n_fft=1024, hop_length=256))
            if np.any(mask): values.append(float(np.mean(spectrum[mask])))
        return float(np.mean(values)) if values else 0.0
    def _onset(self, mono: np.ndarray, sample_rate: int, beats: list[float], offset: int) -> float:
        env = librosa.onset.onset_strength(y=mono, sr=sample_rate, hop_length=512); values = []
        for time in self._candidate_downbeats(beats, offset):
            frame = int(librosa.time_to_frames(time, sr=sample_rate, hop_length=512)); left = max(0, frame - 1); right = min(len(env), frame + 2)
            if right > left: values.append(float(np.max(env[left:right])))
        return float(np.mean(values)) if values else 0.0
    def _regularity(self, beats: list[float], offset: int) -> float:
        downbeats = self._candidate_downbeats(beats, offset)
        if len(downbeats) < 3: return 0.35
        intervals = np.diff(downbeats); mean = float(np.mean(intervals))
        return 0.35 if mean <= 1e-6 else float(np.clip(1.0 - float(np.std(intervals) / mean), 0.35, 0.95))
    def _normalize(self, values: list[float]) -> list[float]:
        low, high = min(values), max(values)
        if abs(high - low) < 1e-9: return [0.5 for _ in values]
        return [float((value - low) / (high - low)) for value in values]

@dataclass(slots=True)
class BeatGridBuilder:
    trim_leading_beats: bool = True
    def build(self, raw: RawBeatSequence, offset: int) -> BeatGrid:
        beats = raw.beat_times or [0.0]
        if self.trim_leading_beats and offset < len(beats): beats = beats[offset:] or [beats[0]]
        points = [BeatPoint(index=i, time=float(t), bar=((i - 1) // 4) + 1, beat_in_bar=((i - 1) % 4) + 1, is_downbeat=((i - 1) % 4) == 0) for i, t in enumerate(beats, start=1)]
        return BeatGrid(bpm=max(float(raw.bpm), 1.0), beats=points, bars=max(points[-1].bar, 1), downbeats=[point.time for point in points if point.is_downbeat])

@dataclass(slots=True)
class BeatConfidenceEvaluator:
    long_blend_threshold: float = 0.68
    phrase_sync_threshold: float = 0.64
    local_window_beats: int = 16
    unstable_window_threshold: float = 0.54
    def evaluate(self, raw: RawBeatSequence, phase: PhaseCorrectionResult, grid: BeatGrid) -> BeatAnalysis:
        bc, stability, local_min, local_mean, unstable_segments, beat_warnings = self._beat(raw, grid)
        dc, regular, low = self._down(phase, grid)
        pc, onset, ambiguous = self._phase(phase)
        sub = self._sub_beat_confidence(raw, bc, stability, onset)
        drift = self._phase_drift_risk(local_min, local_mean, regular, ambiguous, sub, unstable_segments)
        phase_error = self._estimated_phase_error(ambiguous, pc, sub)
        long_stability = self._long_blend_stability(local_min, local_mean, regular, sub, drift)
        recommended_overlap = self._recommended_max_overlap_beats(drift, long_stability, ambiguous, raw.fallback_used)
        beat_usable = bc >= 0.56
        phrase_ok = dc >= self.phrase_sync_threshold and pc >= 0.60 and not ambiguous and sub >= 0.52 and local_min >= 0.48
        long_ok = bc >= self.long_blend_threshold and dc >= 0.62 and pc >= 0.60 and sub >= 0.55 and local_min >= 0.48 and unstable_segments <= 2 and drift <= 0.45
        drift_prone = drift >= 0.58 or ambiguous or local_min < 0.46
        sync_warnings = self._sync_warnings(ambiguous, sub, drift, recommended_overlap, local_min, regular, raw.fallback_used)
        warnings = list(dict.fromkeys(beat_warnings + self._warnings(raw, phase, bc, dc, pc, local_min, unstable_segments) + sync_warnings))
        return BeatAnalysis(beat_confidence=bc, downbeat_confidence=dc, bar_phase_confidence=pc, sub_beat_confidence=sub, source=raw.source, fallback_used=raw.fallback_used, estimated_phase_offset=phase.selected_offset, beat_count=len(grid.beats), local_tempo_stability=stability, downbeat_regularness=regular, onset_alignment_strength=onset, low_band_alignment_strength=low, local_window_stability_min=local_min, local_window_stability_mean=local_mean, unstable_segments_detected=unstable_segments, phase_drift_risk=drift, long_blend_stability=long_stability, estimated_phase_error_beats=phase_error, recommended_max_overlap_beats=recommended_overlap, beat_usable=beat_usable, phrase_sync_usable=phrase_ok, long_blend_usable=long_ok, drift_prone=drift_prone, usable_for_long_blend=long_ok, usable_for_phrase_sync=phrase_ok, ambiguous_bar_phase=ambiguous, warnings=warnings, sync_warnings=sync_warnings)
    def _beat(self, raw: RawBeatSequence, grid: BeatGrid) -> tuple[float, float, float, float, int, list[str]]:
        beats = raw.beat_times
        if len(beats) < 8: return 0.35, 0.35, 0.35, 0.35, 1, ["Very few beat detections; beat confidence reduced."]
        intervals = np.diff(beats)
        if len(intervals) == 0: return 0.35, 0.35, 0.35, 0.35, 1, ["No beat intervals available; beat confidence reduced."]
        mean = float(np.mean(intervals))
        if mean <= 1e-6: return 0.35, 0.35, 0.35, 0.35, 1, ["Invalid mean beat interval; beat confidence reduced."]
        stability = float(np.clip(1.0 - float(np.std(intervals) / mean), 0.0, 1.0)); duration = beats[-1] - beats[0]; expected = duration / mean if mean > 0 else float(len(beats)); density = float(np.clip(len(beats) / max(expected, 1.0), 0.0, 1.0)); continuity = float(np.clip(1.0 - (sum(1 for item in intervals if item > mean * 1.8) / max(len(intervals), 1)), 0.0, 1.0)); local_min, local_mean, unstable_segments = self._local_stability(beats)
        score = stability * 0.45 + density * 0.18 + continuity * 0.12 + local_mean * 0.15 + local_min * 0.10; warnings: list[str] = []
        if raw.fallback_used: score *= 0.75; warnings.append("Fallback beat sequence used.")
        if stability < 0.60: warnings.append("Beat intervals appear unstable.")
        if local_min < 0.48: warnings.append("Local beat stability dips in one or more sections.")
        if unstable_segments > 0: warnings.append(f"Detected {unstable_segments} unstable beat windows.")
        if len(grid.beats) < 16: warnings.append("Short aligned beat grid may limit long transitions.")
        return float(np.clip(score, 0.0, 1.0)), stability, local_min, local_mean, unstable_segments, warnings
    def _down(self, phase: PhaseCorrectionResult, grid: BeatGrid) -> tuple[float, float, float]:
        if len(grid.downbeats) < 3: return 0.40, 0.40, 0.40
        intervals = np.diff(grid.downbeats); mean = float(np.mean(intervals)) if len(intervals) else 0.0; regular = 0.40 if mean <= 1e-6 else float(np.clip(1.0 - float(np.std(intervals) / mean), 0.0, 1.0)); selected = phase.selected_offset; low = phase.low_band_scores[selected] if selected < len(phase.low_band_scores) else 0.5; onset = phase.onset_scores[selected] if selected < len(phase.onset_scores) else 0.5; score = low * 0.45 + onset * 0.35 + regular * 0.20
        if phase.ambiguous: score *= 0.88
        return float(np.clip(score, 0.0, 1.0)), regular, low
    def _phase(self, phase: PhaseCorrectionResult) -> tuple[float, float, bool]:
        if not phase.offset_scores: return 0.40, 0.40, True
        selected = phase.selected_offset; chosen = phase.offset_scores[selected] if selected < len(phase.offset_scores) else 0.5; ordered = sorted(phase.offset_scores, reverse=True); margin = max(0.0, ordered[0] - ordered[1]); onset = phase.onset_scores[selected] if selected < len(phase.onset_scores) else 0.5
        return float(np.clip(margin * 0.70 + chosen * 0.30, 0.0, 1.0)), onset, phase.ambiguous
    def _local_stability(self, beats: list[float]) -> tuple[float, float, int]:
        intervals = np.diff(beats)
        if len(intervals) < 4: return 0.40, 0.40, 1
        window = min(self.local_window_beats, max(len(intervals), 4)); scores: list[float] = []; step = max(window // 2, 1)
        for start in range(0, max(len(intervals) - window + 1, 1), step):
            chunk = intervals[start:start + window]
            if len(chunk) < 4: continue
            mean = float(np.mean(chunk)); scores.append(0.35 if mean <= 1e-6 else float(np.clip(1.0 - float(np.std(chunk) / mean), 0.0, 1.0)))
        if not scores:
            mean = float(np.mean(intervals))
            if mean <= 1e-6: return 0.35, 0.35, 1
            single = float(np.clip(1.0 - float(np.std(intervals) / mean), 0.0, 1.0))
            return single, single, int(single < self.unstable_window_threshold)
        local_min = float(min(scores)); local_mean = float(sum(scores) / len(scores)); unstable_segments = sum(1 for score in scores if score < self.unstable_window_threshold)
        return local_min, local_mean, unstable_segments
    def _sub_beat_confidence(self, raw: RawBeatSequence, beat_confidence: float, stability: float, onset: float) -> float:
        fallback_penalty = 0.12 if raw.fallback_used else 0.0
        return float(np.clip(beat_confidence * 0.45 + stability * 0.30 + onset * 0.25 - fallback_penalty, 0.0, 1.0))
    def _phase_drift_risk(self, local_min: float, local_mean: float, regular: float, ambiguous: bool, sub: float, unstable_segments: int) -> float:
        risk = (1.0 - local_min) * 0.34 + (1.0 - local_mean) * 0.18 + (1.0 - regular) * 0.18 + (1.0 - sub) * 0.18
        if ambiguous: risk += 0.16
        risk += min(unstable_segments * 0.05, 0.18)
        return float(np.clip(risk, 0.0, 1.0))
    def _long_blend_stability(self, local_min: float, local_mean: float, regular: float, sub: float, drift: float) -> float:
        return float(np.clip(local_min * 0.34 + local_mean * 0.22 + regular * 0.18 + sub * 0.18 + (1.0 - drift) * 0.08, 0.0, 1.0))
    def _estimated_phase_error(self, ambiguous: bool, phase_confidence: float, sub: float) -> float:
        base = (1.0 - phase_confidence) * 0.7 + (1.0 - sub) * 0.45 + (0.35 if ambiguous else 0.0)
        return float(np.clip(base, 0.0, 1.5))
    def _recommended_max_overlap_beats(self, drift: float, long_stability: float, ambiguous: bool, fallback_used: bool) -> int:
        if fallback_used or ambiguous or drift >= 0.72 or long_stability < 0.38: return 4
        if drift >= 0.56 or long_stability < 0.52: return 8
        if drift >= 0.38 or long_stability < 0.68: return 16
        return 32
    def _sync_warnings(self, ambiguous: bool, sub: float, drift: float, recommended_overlap: int, local_min: float, regular: float, fallback_used: bool) -> list[str]:
        warnings: list[str] = []
        if ambiguous: warnings.append("Bar phase is ambiguous.")
        if sub < 0.55: warnings.append("Low sub-beat confidence; keep phase offsets conservative.")
        if local_min < 0.48: warnings.append("Local stability floor is low for long blend.")
        if regular < 0.62: warnings.append("Downbeat regularness suggests conservative overlap.")
        if drift >= 0.58: warnings.append("Analyzer estimates elevated drift risk for long overlap.")
        if fallback_used: warnings.append("Fallback beat generation limits sync certainty.")
        warnings.append(f"Recommended maximum overlap is {recommended_overlap} beats.")
        return list(dict.fromkeys(warnings))
    def _warnings(self, raw: RawBeatSequence, phase: PhaseCorrectionResult, bc: float, dc: float, pc: float, local_min: float, unstable_segments: int) -> list[str]:
        warnings = []
        if raw.fallback_used: warnings.append("Beat extractor used fallback beat generation.")
        if len(raw.beat_times) < 16: warnings.append("Short beat sequence; confidence may be unstable.")
        if bc < 0.60: warnings.append("Beat confidence is too low for reliable long blends.")
        if dc < 0.65: warnings.append("Downbeat confidence is weak; phrase entry may be unreliable.")
        if phase.ambiguous or pc < 0.65: warnings.append("Bar phase is ambiguous; avoid strict phrase-locked transitions.")
        if local_min < 0.48: warnings.append("Local beat stability is weak in at least one section.")
        if unstable_segments > 1: warnings.append("Multiple unstable beat windows detected; prefer conservative transitions.")
        warnings.extend(phase.notes[:2]); return warnings

@dataclass(slots=True)
class BeatGridAnalyzer:
    preferred_backend: str = "librosa"
    extractor: BeatExtractor | None = None
    extractors: list[BeatExtractor] | None = None
    phase_corrector: BarPhaseCorrector | None = None
    grid_builder: BeatGridBuilder | None = None
    confidence_evaluator: BeatConfidenceEvaluator | None = None
    def __post_init__(self) -> None:
        base = self.extractor or LibrosaBeatExtractor(); self.extractors = self.extractors or [base, StableGridBeatExtractor()]; self.phase_corrector = self.phase_corrector or BarPhaseCorrector(); self.grid_builder = self.grid_builder or BeatGridBuilder(); self.confidence_evaluator = self.confidence_evaluator or BeatConfidenceEvaluator()
    def analyze(self, mono: np.ndarray, sample_rate: int) -> tuple[BeatGrid, BeatAnalysis]:
        candidates = [self._build_candidate(mono, sample_rate, extractor) for extractor in (self.extractors or [])]; best = self._select_best_candidate(candidates); self.preferred_backend = best.backend_name
        return best.grid, best.analysis.model_copy(update={"source": best.backend_name})
    def _build_candidate(self, mono: np.ndarray, sample_rate: int, extractor: BeatExtractor) -> BeatAnalysisCandidate:
        raw = extractor.extract(mono, sample_rate); phase = self.phase_corrector.correct(mono, sample_rate, raw); grid = self.grid_builder.build(raw, phase.selected_offset); analysis = self.confidence_evaluator.evaluate(raw, phase, grid)
        return BeatAnalysisCandidate(raw=raw, phase=phase, grid=grid, analysis=analysis, backend_name=raw.source, selection_score=self._selection_score(analysis))
    def _selection_score(self, analysis: BeatAnalysis) -> float:
        score = analysis.beat_confidence * 0.22 + analysis.downbeat_confidence * 0.18 + analysis.bar_phase_confidence * 0.15 + analysis.sub_beat_confidence * 0.12 + analysis.long_blend_stability * 0.10 + analysis.local_tempo_stability * 0.08 + analysis.downbeat_regularness * 0.06 + analysis.local_window_stability_mean * 0.05 + analysis.local_window_stability_min * 0.04
        score -= analysis.phase_drift_risk * 0.08
        if analysis.fallback_used: score -= 0.06
        if analysis.ambiguous_bar_phase: score -= 0.04
        if analysis.unstable_segments_detected > 1: score -= min(0.025 * analysis.unstable_segments_detected, 0.08)
        score -= min(len(analysis.warnings) * 0.004, 0.04)
        return float(np.clip(score, 0.0, 1.0))
    def _select_best_candidate(self, candidates: list[BeatAnalysisCandidate]) -> BeatAnalysisCandidate:
        if not candidates: raise ValueError("BeatGridAnalyzer requires at least one candidate.")
        return max(candidates, key=lambda item: (item.selection_score, item.analysis.beat_confidence, item.analysis.downbeat_confidence, -item.analysis.unstable_segments_detected))
