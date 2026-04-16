"""Per-bar descriptor extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import librosa, numpy as np
from core.datatypes import BandDescriptor, BeatGrid, DanceabilityPoint, EnergyPoint, LoudnessPoint, StereoPoint

@dataclass(slots=True)
class DescriptorAnalyzer:
    def analyze(self, audio: np.ndarray, mono: np.ndarray, sample_rate: int, beatgrid: BeatGrid) -> tuple[list[EnergyPoint], list[BandDescriptor], list[LoudnessPoint], list[StereoPoint], list[DanceabilityPoint]]:
        energy = self._extract_energy_bars(mono, sample_rate, beatgrid)
        bands = self._extract_band_descriptors(mono, sample_rate, beatgrid)
        loudness = self._extract_loudness_profile(audio, mono, sample_rate, beatgrid)
        stereo = self._extract_stereo_profile(audio, sample_rate, beatgrid)
        dance = self._extract_danceability_profile(beatgrid, energy)
        return energy, bands, loudness, stereo, dance

    def _extract_energy_bars(self, mono: np.ndarray, sample_rate: int, beatgrid: BeatGrid) -> list[EnergyPoint]:
        hop = 512; rms = librosa.feature.rms(y=mono, hop_length=hop)[0]; onset = librosa.onset.onset_strength(y=mono, sr=sample_rate, hop_length=hop); frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sample_rate, hop_length=hop); points=[]
        for bar in range(1, beatgrid.bars + 1):
            start, end = self._bar_window(bar, beatgrid); mask = (frame_times >= start) & (frame_times < end); bar_rms = float(np.mean(rms[mask])) if np.any(mask) else 0.0; bar_flux = float(np.mean(onset[mask])) if np.any(mask) else 0.0
            points.append(EnergyPoint(bar=bar, start_time=start, end_time=end, rms=bar_rms, spectral_flux=bar_flux, combined=(bar_rms * 0.6) + (bar_flux * 0.4)))
        return self._normalize_energy(points)

    def _extract_band_descriptors(self, mono: np.ndarray, sample_rate: int, beatgrid: BeatGrid) -> list[BandDescriptor]:
        stft = np.abs(librosa.stft(mono, n_fft=2048, hop_length=512)); freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=2048); frame_times = librosa.frames_to_time(np.arange(stft.shape[1]), sr=sample_rate, hop_length=512); desc=[]
        for bar in range(1, beatgrid.bars + 1):
            start, end = self._bar_window(bar, beatgrid); time_mask = (frame_times >= start) & (frame_times < end)
            if not np.any(time_mask): desc.append(BandDescriptor(bar=bar)); continue
            spec = stft[:, time_mask]
            desc.append(BandDescriptor(bar=bar, sub=self._band_mean(spec, freqs, 20, 60), bass=self._band_mean(spec, freqs, 60, 180), low_mid=self._band_mean(spec, freqs, 180, 600), mid=self._band_mean(spec, freqs, 600, 2500), high=self._band_mean(spec, freqs, 2500, 12000), vocal_presence=float(np.clip(self._band_mean(spec, freqs, 300, 3000) / 10.0, 0.0, 1.0)), transient_density=float(np.mean(librosa.onset.onset_strength(S=spec, sr=sample_rate)))))
        return self._normalize_band_descriptors(desc)

    def _extract_loudness_profile(self, audio: np.ndarray, mono: np.ndarray, sample_rate: int, beatgrid: BeatGrid) -> list[LoudnessPoint]:
        values=[]; mono_audio = mono if mono.ndim == 1 else librosa.to_mono(mono)
        for bar in range(1, beatgrid.bars + 1):
            start, end = self._bar_window(bar, beatgrid); start_idx = int(start * sample_rate); end_idx = max(start_idx + 1, int(end * sample_rate)); block = mono_audio[start_idx:end_idx]
            if len(block) == 0: values.append(LoudnessPoint(bar=bar)); continue
            rms = float(np.sqrt(np.mean(np.square(block))) + 1e-9); peak = float(np.max(np.abs(block)) + 1e-9)
            values.append(LoudnessPoint(bar=bar, rms_db=float(20 * np.log10(rms)), peak_db=float(20 * np.log10(peak)), short_loudness=float(np.clip(rms * 4.0, 0.0, 1.0))))
        return values

    def _extract_stereo_profile(self, audio: np.ndarray, sample_rate: int, beatgrid: BeatGrid) -> list[StereoPoint]:
        if audio.ndim == 1: return [StereoPoint(bar=bar, width=0.0, balance=0.0) for bar in range(1, beatgrid.bars + 1)]
        left, right = audio[0], (audio[1] if audio.shape[0] > 1 else audio[0]); points=[]
        for bar in range(1, beatgrid.bars + 1):
            start, end = self._bar_window(bar, beatgrid); s = int(start * sample_rate); e = max(s + 1, int(end * sample_rate)); l = left[s:e]; r = right[s:e]
            if len(l) == 0 or len(r) == 0: points.append(StereoPoint(bar=bar)); continue
            mid = (l + r) * 0.5; side = (l - r) * 0.5; mid_energy = float(np.sqrt(np.mean(np.square(mid))) + 1e-9); side_energy = float(np.sqrt(np.mean(np.square(side))) + 1e-9); width = float(np.clip(side_energy / (mid_energy + side_energy), 0.0, 1.0)); balance = float(np.clip((np.mean(np.abs(l)) - np.mean(np.abs(r))) / (np.mean(np.abs(l)) + np.mean(np.abs(r)) + 1e-9), -1.0, 1.0)); points.append(StereoPoint(bar=bar, width=width, balance=balance))
        return points

    def _extract_danceability_profile(self, beatgrid: BeatGrid, energy: list[EnergyPoint]) -> list[DanceabilityPoint]:
        energy_by_bar = {point.bar: point for point in energy}; values=[]
        for point in energy:
            two_bar = self._two_bar_stability(point.bar, energy_by_bar); pulse = self._pulse_clarity(point.bar, beatgrid, energy_by_bar); groove = self._groove_stability(point.bar, energy_by_bar); eight = float(np.clip((0.58 if (point.bar - 1) % 2 == 0 else 0.46) + two_bar * 0.32 + pulse * 0.10, 0.0, 1.0)); downbeat = float(np.clip(0.22 + pulse * 0.45 + two_bar * 0.20 + point.combined * 0.13, 0.0, 1.0)); follow = self._followability_score(eight, downbeat, groove, two_bar, pulse); safe = self._is_transition_safe(eight, downbeat, groove, follow)
            values.append(DanceabilityPoint(bar=point.bar, eight_count_clarity=eight, downbeat_clarity=downbeat, groove_stability=groove, followability=follow, two_bar_stability=two_bar, pulse_clarity=pulse, transition_safe=safe))
        return values

    def _two_bar_stability(self, bar: int, energy_by_bar: dict[int, EnergyPoint]) -> float:
        partner = bar + 1 if bar % 2 == 1 else bar - 1; current = energy_by_bar.get(bar); pair = energy_by_bar.get(partner, current)
        if not current or not pair: return 0.5
        pair_score = 1.0 - min(abs(current.combined - pair.combined) / 0.35, 1.0); prev = energy_by_bar.get(max(1, min(bar, partner) - 1)); nxt = energy_by_bar.get(max(bar, partner) + 1); neighbor_values = [p.combined for p in (prev, nxt) if p]
        if not neighbor_values: return float(np.clip(pair_score, 0.0, 1.0))
        window_mean = (current.combined + pair.combined) / 2.0; continuity = 1.0 - min(abs(window_mean - (sum(neighbor_values) / len(neighbor_values))) / 0.45, 1.0)
        return float(np.clip(pair_score * 0.65 + continuity * 0.35, 0.0, 1.0))

    def _pulse_clarity(self, bar: int, beatgrid: BeatGrid, energy_by_bar: dict[int, EnergyPoint]) -> float:
        current = energy_by_bar.get(bar)
        if not current: return 0.5
        prev = energy_by_bar.get(max(1, bar - 1), current); nxt = energy_by_bar.get(min(beatgrid.bars, bar + 1), current); local = abs(current.combined - prev.combined) + abs(current.combined - nxt.combined); consistency = 1.0 - min(local / 0.75, 1.0); accent = 0.08 if (bar - 1) % 2 == 0 else 0.0
        return float(np.clip(current.combined * 0.55 + consistency * 0.37 + accent, 0.0, 1.0))

    def _groove_stability(self, bar: int, energy_by_bar: dict[int, EnergyPoint]) -> float:
        current = energy_by_bar.get(bar)
        if not current: return 0.5
        neighbors = [energy_by_bar.get(max(1, bar - 1), current), energy_by_bar.get(bar + 1, current)]; deltas = [abs(current.combined - point.combined) for point in neighbors if point]; continuity = 1.0 - min((sum(deltas) / max(len(deltas), 1)) / 0.4, 1.0)
        return float(np.clip(current.combined * 0.40 + continuity * 0.60, 0.0, 1.0))

    def _followability_score(self, eight: float, downbeat: float, groove: float, two_bar: float, pulse: float) -> float:
        score = eight * 0.22 + downbeat * 0.22 + groove * 0.20 + two_bar * 0.20 + pulse * 0.16
        if min(eight, downbeat, groove, two_bar) < 0.40: score -= 0.10
        return float(np.clip(score, 0.0, 1.0))

    def _is_transition_safe(self, eight: float, downbeat: float, groove: float, follow: float) -> bool:
        return bool(follow >= 0.68 and eight >= 0.60 and downbeat >= 0.58 and groove >= 0.55)

    def _bar_window(self, bar: int, beatgrid: BeatGrid) -> tuple[float, float]:
        bar_beats = [beat for beat in beatgrid.beats if beat.bar == bar]
        if not bar_beats:
            beat_length = 60.0 / max(beatgrid.bpm, 1.0); start = (bar - 1) * beat_length * 4; return start, start + beat_length * 4
        start = bar_beats[0].time; end = bar_beats[-1].time + (60.0 / max(beatgrid.bpm, 1.0)); return float(start), float(end)

    def _normalize_energy(self, energy_points: list[EnergyPoint]) -> list[EnergyPoint]:
        if not energy_points: return energy_points
        max_value = max(point.combined for point in energy_points) or 1.0
        return [EnergyPoint(bar=point.bar, start_time=point.start_time, end_time=point.end_time, rms=point.rms, spectral_flux=point.spectral_flux, combined=point.combined / max_value) for point in energy_points]

    def _band_mean(self, spec: np.ndarray, freqs: np.ndarray, low: float, high: float) -> float:
        mask = (freqs >= low) & (freqs < high)
        return 0.0 if not np.any(mask) else float(np.mean(spec[mask]))

    def _normalize_band_descriptors(self, descriptors: list[BandDescriptor]) -> list[BandDescriptor]:
        if not descriptors: return descriptors
        maxima = {"sub": max((i.sub for i in descriptors), default=1.0) or 1.0, "bass": max((i.bass for i in descriptors), default=1.0) or 1.0, "low_mid": max((i.low_mid for i in descriptors), default=1.0) or 1.0, "mid": max((i.mid for i in descriptors), default=1.0) or 1.0, "high": max((i.high for i in descriptors), default=1.0) or 1.0, "transient_density": max((i.transient_density for i in descriptors), default=1.0) or 1.0}
        return [BandDescriptor(bar=i.bar, sub=i.sub / maxima["sub"], bass=i.bass / maxima["bass"], low_mid=i.low_mid / maxima["low_mid"], mid=i.mid / maxima["mid"], high=i.high / maxima["high"], vocal_presence=i.vocal_presence, transient_density=i.transient_density / maxima["transient_density"]) for i in descriptors]
