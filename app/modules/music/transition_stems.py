"""
Backend Pre-rendered Short Transition Stem Library
===================================================

Generates and caches short (1-8 bar) transitional audio clips that can be
inserted between any two songs during online playback. Each stem type uses
a distinct synthesis approach — no two sound the same.

Stem types (6 distinct synthesis strategies):
  riser          — White noise band-pass sweep (low→high) + volume ramp
  downlifter     — Sine sweep pitch-down + low-pass filter close
  impact         — Short noise burst + sub-bass hit + long reverb tail
  drum_fill      — Kick+snare pattern with increasing density + band-pass sweep
  reverse_cymbal — Reversed noise burst + swelling reverb (pre-verb)
  ambient_pad    — Filtered pink noise with slow LFO tremolo modulation

Architecture:
  - Stems are pre-rendered once and cached as WAV files on disk.
  - During online playback, the player selects a stem, seeks to it, and
    crossfades it between the outgoing and incoming tracks.
  - All synthesis is pure numpy/DSP — no ML, no GPU, sub-100ms generation.

Reference: GrooveEngine's 9 offline strategies (FILTER_SWAP, BACKSPIN_OUT,
LOOP_ROLL, etc.) — each stem type borrows a different FX combination.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

SR = 44100

# Stem type registry — each type maps to a distinct synthesis function
STEM_TYPES = [
    "riser",
    "downlifter",
    "impact",
    "drum_fill",
    "reverse_cymbal",
    "ambient_pad",
]

# How many variants per stem type (different lengths, keys, intensities)
VARIANTS_PER_TYPE = 3


@dataclass(slots=True)
class StemMeta:
    name: str
    stem_type: str
    duration_sec: float
    bars: int
    bpm: int
    energy: str  # low / medium / high
    file_path: str = ""


@dataclass
class StemLibrary:
    """In-memory catalog of available transition stems."""
    stems: list[StemMeta] = field(default_factory=list)

    def by_type(self, stem_type: str) -> list[StemMeta]:
        return [s for s in self.stems if s.stem_type == stem_type]

    def by_energy(self, energy: str) -> list[StemMeta]:
        return [s for s in self.stems if s.energy == energy]

    def random(self, stem_type: str | None = None,
               energy: str | None = None) -> StemMeta | None:
        import random
        candidates = self.stems
        if stem_type:
            candidates = self.by_type(stem_type)
        if energy:
            candidates = [s for s in candidates if s.energy == energy]
        return random.choice(candidates) if candidates else None


# ═══════════════════════════════════════════════════════════════════════════
#  SYNTHESIS FUNCTIONS — each uses a different DSP approach
# ═══════════════════════════════════════════════════════════════════════════

def _envelope(dur_sec: float, sr: int, shape: str = "linear") -> np.ndarray:
    """Generate an envelope of length dur_sec * sr samples."""
    n = int(dur_sec * sr)
    t = np.linspace(0, 1, n, endpoint=False)
    if shape == "linear":
        return t
    elif shape == "ease_in":
        return t ** 2
    elif shape == "ease_out":
        return 1 - (1 - t) ** 2
    elif shape == "bell":
        return np.exp(-((t - 0.5) ** 2) / 0.04)
    elif shape == "spike":
        return np.exp(-t * 8)
    return t


# ── Riser: white noise → band-pass sweep (low→high) + volume ramp ────────
# Reference: GrooveEngine RISER strategy (HPF sweep + noise riser + stutter)

def _synth_riser(dur_sec: float, bpm: int, energy: str) -> np.ndarray:
    n = int(dur_sec * SR)
    t = np.linspace(0, 1, n, endpoint=False)
    noise = np.random.randn(n).astype(np.float32)

    # Band-pass center frequency: low→high sweep
    freq_start = {"low": 100, "medium": 200, "high": 300}[energy]
    freq_end = {"low": 3000, "medium": 6000, "high": 10000}[energy]
    center_freq = freq_start + (freq_end - freq_start) * (t ** 1.5)
    bandwidth = 0.6 + 0.3 * t  # widening Q

    # Simple time-domain band-pass via two one-pole filters
    y = noise.copy()
    # Low-pass
    for _ in range(2):
        alpha = np.exp(-2 * np.pi * (center_freq + bandwidth * center_freq) / SR)
        alpha = np.clip(alpha, 0.001, 0.999)
        for i in range(1, n):
            y[i] = y[i] * (1 - alpha[i]) + y[i - 1] * alpha[i]
    # High-pass
    hp_cutoff = np.clip(center_freq - bandwidth * center_freq, 20, SR // 2 - 1)
    alpha_hp = np.exp(-2 * np.pi * hp_cutoff / SR)
    alpha_hp = np.clip(alpha_hp, 0.001, 0.999)
    y_hp = y.copy()
    for i in range(1, n):
        y_hp[i] = alpha_hp[i] * (y_hp[i - 1] + y[i] - y[i - 1])

    # Volume envelope: ramp up then spike at end
    env = _envelope(dur_sec, SR, "ease_in") * 0.7
    env[-int(SR * 0.05):] *= np.linspace(1, 0, int(SR * 0.05))  # quick tail
    result = y_hp * env
    return _normalize(result)


# ── Downlifter: sine sweep pitch-down + low-pass close ────────────────────
# Reference: GrooveEngine BACKSPIN_OUT (brake + LPF shutoff), reversed

def _synth_downlifter(dur_sec: float, bpm: int, energy: str) -> np.ndarray:
    n = int(dur_sec * SR)
    t = np.linspace(0, 1, n, endpoint=False)

    # Pitch sweep: 800Hz → 40Hz (exponential)
    start_freq = {"low": 500, "medium": 800, "high": 1200}[energy]
    end_freq = {"low": 60, "medium": 40, "high": 25}[energy]
    freq = start_freq * (end_freq / start_freq) ** t

    # Phase accumulation
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sine = np.sin(phase).astype(np.float32)

    # Add harmonics for richness
    sine += 0.3 * np.sin(2 * phase).astype(np.float32)
    sine += 0.15 * np.sin(3 * phase).astype(np.float32)

    # Low-pass filter: closes as pitch drops
    lp_cutoff = 12000 - t * 11800
    alpha = np.exp(-2 * np.pi * lp_cutoff / SR)
    alpha = np.clip(alpha, 0.001, 0.999)
    y = sine.copy()
    for i in range(1, n):
        y[i] = y[i] * (1 - alpha[i]) + y[i - 1] * alpha[i]

    # Envelope: ease-in then fade
    env = _envelope(dur_sec, SR, "ease_in") * _envelope(dur_sec, SR, "ease_out")
    return _normalize(y * env * 0.8)


# ── Impact: short noise burst + sub-bass hit + long reverb tail ───────────
# Reference: GrooveEngine CUT_SWAP (impact moment) + MELODIC_RESET (reverb)

def _synth_impact(dur_sec: float, bpm: int, energy: str) -> np.ndarray:
    n = int(dur_sec * SR)
    t = np.linspace(0, dur_sec, n, endpoint=False)

    # Sub-bass hit: 40-55Hz sine with fast decay
    bass_freq = {"low": 45, "medium": 50, "high": 55}[energy]
    bass = np.sin(2 * np.pi * bass_freq * t).astype(np.float32)
    bass_env = np.exp(-t * 15)  # fast decay
    bass = bass * bass_env

    # Noise burst: short white noise with spike envelope
    noise = np.random.randn(n).astype(np.float32)
    noise_env = np.exp(-t * 25)
    noise = noise * noise_env * 0.4

    # Reverb simulation: 4-tap comb filter with feedback
    combined = bass + noise
    reverb = np.zeros_like(combined)
    tap_delays = [int(SR * d) for d in [0.03, 0.05, 0.07, 0.11]]
    tap_gains = [0.6, 0.45, 0.35, 0.25]
    for delay, gain in zip(tap_delays, tap_gains):
        for i in range(delay, n):
            reverb[i] += combined[i - delay] * gain * np.exp(-(i - delay) / (SR * 1.5))

    result = (combined + reverb * 0.7)
    # Envelope: peak early, long tail
    env = np.exp(-t / (dur_sec * 0.3)) * 0.9
    return _normalize(result * env)


# ── Drum Fill: synthesized kick+snare with increasing density ─────────────
# Reference: GrooveEngine LOOP_ROLL (progressive shortening), percussive

def _synth_drum_fill(dur_sec: float, bpm: int, energy: str) -> np.ndarray:
    n = int(dur_sec * SR)
    result = np.zeros(n, dtype=np.float32)

    beat_sec = 60.0 / bpm
    total_beats = int(dur_sec / beat_sec)

    # Kick: 55Hz sine burst with fast exponential decay
    kick_len = int(SR * 0.08)
    kick_t = np.linspace(0, 0.08, kick_len, endpoint=False)
    kick = np.sin(2 * np.pi * 55 * kick_t) * np.exp(-kick_t * 30)
    kick = kick.astype(np.float32)

    # Snare: noise burst + 200Hz tone
    snare_len = int(SR * 0.06)
    snare_t = np.linspace(0, 0.06, snare_len, endpoint=False)
    snare_noise = np.random.randn(snare_len).astype(np.float32) * np.exp(-snare_t * 20)
    snare_tone = np.sin(2 * np.pi * 200 * snare_t).astype(np.float32) * np.exp(-snare_t * 25)
    snare = (snare_noise * 0.6 + snare_tone * 0.4)

    for beat_idx in range(total_beats):
        t_rel = beat_idx / max(total_beats - 1, 1)  # 0→1

        # Increasing density: more subdivisions as fill progresses
        subdivisions = int(1 + t_rel * 5)  # 1→6 subdivisions
        for sub in range(subdivisions):
            sub_t = beat_idx * beat_sec + sub * (beat_sec / subdivisions)
            sample = int(sub_t * SR)
            if sample >= n:
                break

            if sub % 2 == 0:
                # Kick on even subdivisions
                end = min(sample + kick_len, n)
                chunk = kick[:end - sample]
                # Kick amplitude decreases through fill (bass swaps out)
                gain = 1.0 - t_rel * 0.6
                result[sample:end] += chunk * gain
            else:
                # Snare on odd subdivisions
                end = min(sample + snare_len, n)
                chunk = snare[:end - sample]
                result[sample:end] += chunk

    # Band-pass filter: focus the drum energy
    # Simple: highpass at 60Hz + lowpass sweep from 8k→4k
    n_out = len(result)
    t_full = np.linspace(0, 1, n_out, endpoint=False)
    alpha_lp = np.exp(-2 * np.pi * (8000 - t_full * 4000) / SR)
    alpha_lp = np.clip(alpha_lp, 0.001, 0.999)
    y = result.copy()
    for i in range(1, n_out):
        y[i] = y[i] * (1 - alpha_lp[i]) + y[i - 1] * alpha_lp[i]

    return _normalize(y * 0.85)


# ── Reverse Cymbal: reversed noise burst + swelling reverb ────────────────
# Reference: GrooveEngine FILTER_SWAP (staged reveal), reversed dynamics

def _synth_reverse_cymbal(dur_sec: float, bpm: int, energy: str) -> np.ndarray:
    n = int(dur_sec * SR)
    t = np.linspace(0, 1, n, endpoint=False)

    # High-frequency noise: simulate cymbal wash
    noise = np.random.randn(n).astype(np.float32)
    # Highpass at 5kHz to get "shimmer"
    hp_alpha = np.exp(-2 * np.pi * 5000 / SR)
    y_hp = noise.copy()
    for i in range(1, n):
        y_hp[i] = hp_alpha * (y_hp[i - 1] + noise[i] - noise[i - 1])

    # Reverse: the "pre-verb" swell — volume builds up reversed
    rev_env = _envelope(dur_sec, SR, "ease_in")  # 0→1 (reversed: starts quiet)
    # Apply as reverse envelope (loudest at end)
    result = y_hp * rev_env * 0.6

    # Add metallic ringing: high sine tones that build up
    ring_freqs = [8000, 10000, 12000]
    for freq in ring_freqs:
        ring = np.sin(2 * np.pi * freq * np.linspace(0, dur_sec, n, endpoint=False))
        ring = ring.astype(np.float32) * rev_env * 0.15
        result += ring

    # Multi-tap reverb swell
    verb = np.zeros(n, dtype=np.float32)
    tap_delays = [int(SR * d) for d in [0.02, 0.04, 0.06, 0.09, 0.13]]
    for delay in tap_delays:
        for i in range(delay, n):
            decay = np.exp(-(i - delay) / (SR * 0.6))
            verb[i] += result[i - delay] * 0.35 * decay
    result += verb * 0.8

    return _normalize(result * 0.8)


# ── Ambient Pad: filtered pink noise with slow LFO tremolo ────────────────
# Reference: GrooveEngine MELODIC_RESET (atmospheric), pad-texture

def _synth_ambient_pad(dur_sec: float, bpm: int, energy: str) -> np.ndarray:
    n = int(dur_sec * SR)
    t = np.linspace(0, dur_sec, n, endpoint=False)

    # Pink noise: white noise with -3dB/oct filter (1/f)
    white = np.random.randn(n).astype(np.float32)
    pink = np.zeros(n, dtype=np.float32)
    b = [0.049922035, 0.050612754, 0.051199536, 0.050612754, 0.049922035]
    # Simple one-pole approximation of pink noise
    for i in range(1, n):
        pink[i] = 0.95 * pink[i - 1] + white[i] * 0.3

    # Band-pass at 300-3000Hz for warm midrange
    alpha_lp = np.exp(-2 * np.pi * 3000 / SR)
    alpha_hp = np.exp(-2 * np.pi * 300 / SR)
    y = pink.copy()
    for i in range(1, n):
        y[i] = y[i] * (1 - alpha_lp) + y[i - 1] * alpha_lp
    y2 = y.copy()
    for i in range(1, n):
        y2[i] = alpha_hp * (y2[i - 1] + y[i] - y[i - 1])

    # Slow LFO tremolo: amplitude modulation at ~0.3-0.5Hz
    lfo_freq = {"low": 0.35, "medium": 0.42, "high": 0.5}[energy]
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * lfo_freq * t)

    # Second LFO: subtle filter movement
    lfo2 = 0.4 + 0.6 * np.sin(2 * np.pi * (lfo_freq * 0.7) * t + 1.5)

    result = y2 * lfo * 0.5

    # Add subtle harmonic drone
    drone_freq = {"low": 110, "medium": 146.83, "high": 196}[energy]  # A2, D3, G3
    drone = np.sin(2 * np.pi * drone_freq * t).astype(np.float32) * 0.15
    drone += np.sin(2 * np.pi * drone_freq * 1.5 * t).astype(np.float32) * 0.08  # fifth
    result += drone * lfo2

    # Envelope: slow attack, sustain, slow release
    attack = min(int(SR * 0.3), n // 4)
    release = min(int(SR * 0.5), n // 3)
    env = np.ones(n, dtype=np.float32)
    env[:attack] = np.linspace(0, 1, attack)
    env[-release:] = np.linspace(1, 0, release)
    return _normalize(result * env * 0.8)


def _normalize(y: np.ndarray, peak: float = 0.95) -> np.ndarray:
    """Peak-normalize audio to avoid clipping."""
    max_val = np.max(np.abs(y))
    if max_val > 1e-8:
        y = y / max_val * peak
    return y.astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════
#  STEM LIBRARY — generation + caching
# ═══════════════════════════════════════════════════════════════════════════

_SYNTH_REGISTRY: dict[str, Callable] = {
    "riser": _synth_riser,
    "downlifter": _synth_downlifter,
    "impact": _synth_impact,
    "drum_fill": _synth_drum_fill,
    "reverse_cymbal": _synth_reverse_cymbal,
    "ambient_pad": _synth_ambient_pad,
}

# Bar lengths to generate for each type
_TYPE_BARS: dict[str, list[int]] = {
    "riser": [2, 4, 8],
    "downlifter": [1, 2, 4],
    "impact": [1, 1, 1],
    "drum_fill": [1, 2, 4],
    "reverse_cymbal": [1, 2, 4],
    "ambient_pad": [2, 4, 8],
}

_ENERGY_LEVELS = ["low", "medium", "high"]


def _get_stems_dir() -> Path:
    """Directory where rendered stem WAV files are cached."""
    base = Path(__file__).resolve().parent.parent.parent.parent
    d = base / "data" / "music-files" / "shared" / "transition_stems"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stem_path(stem_type: str, variant: int, bars: int, energy: str) -> Path:
    return _get_stems_dir() / f"{stem_type}_{bars}bar_{energy}_v{variant}.wav"


def build_stem_library(bpm: int = 120, force: bool = False) -> StemLibrary:
    """Generate (or load cached) all pre-rendered transition stems.

    Stems are cached on disk as WAV files. Pass force=True to regenerate.
    Returns a StemLibrary catalog with metadata for all available stems.
    """
    import soundfile as sf

    stems_dir = _get_stems_dir()
    library = StemLibrary()

    for stem_type in STEM_TYPES:
        synth_fn = _SYNTH_REGISTRY[stem_type]
        bar_options = _TYPE_BARS[stem_type]
        for variant in range(VARIANTS_PER_TYPE):
            bars = bar_options[variant]
            energy = _ENERGY_LEVELS[variant]
            dur_sec = bars * 60.0 / bpm
            path = _stem_path(stem_type, variant, bars, energy)

            if not force and path.exists():
                log.debug("stem cached: %s", path.name)
            else:
                log.info("generating stem: %s (%.1fs, %dbpm, %s)",
                         path.name, dur_sec, bpm, energy)
                audio = synth_fn(dur_sec, bpm, energy)
                sf.write(str(path), audio, SR)

            library.stems.append(StemMeta(
                name=path.stem,
                stem_type=stem_type,
                duration_sec=dur_sec,
                bars=bars,
                bpm=bpm,
                energy=energy,
                file_path=str(path),
            ))

    log.info("stem library ready: %d stems in %s", len(library.stems), stems_dir)
    return library


# Global singleton
_stem_library: StemLibrary | None = None


def get_stem_library(bpm: int = 120) -> StemLibrary:
    global _stem_library
    if _stem_library is None:
        _stem_library = build_stem_library(bpm=bpm)
    return _stem_library
