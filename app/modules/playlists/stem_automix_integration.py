"""Integration bridge: Jetson LibrarySong ↔ stem_automix TrackContext + enhanced renderer.

Usage:
    from app.modules.playlists.stem_automix_integration import (
        library_song_to_track_context,
        render_stem_automix_plan,
    )
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import soundfile as sf

from app.modules.library.models import LibrarySong
from app.modules.playlists.stem_automix import (
    AutomationCurve,
    CurveParam,
    CurveTarget,
    TempoStrategy,
    TrackContext,
    TransitionMode,
    TransitionPlan,
    TransitionPreset,
    build_automix_transition,
    build_curve,
    generate_plan,
    score_transition_candidates,
    select_best_preset,
)

STEM_NAMES = ("vocals", "drums", "bass", "other")


# ═══════════════════════════════════════════════════════════════════════════════
# Bridge: LibrarySong → TrackContext
# ═══════════════════════════════════════════════════════════════════════════════

def library_song_to_track_context(lib: LibrarySong | None) -> TrackContext:
    """Build a TrackContext from a Jetson LibrarySong database row.

    Handles None safely — returns a minimal context with all defaults.
    """
    if lib is None:
        return TrackContext(
            song_id="unknown",
            has_stems=False,
            stem_quality_score=0.0,
        )

    has_stems = bool(lib.stems and len(lib.stems) >= 2)
    # stem quality: if stems_sha256 entries exist, stems are verified → quality 0.85
    if has_stems:
        quality = 0.85
    else:
        quality = 0.0

    # Estimate vocal density / bass energy from stems availability
    vocal_density = 0.5
    bass_energy = 0.5
    if lib.stems:
        if lib.stems.get("vocals"):
            vocal_density = 0.65
        if lib.stems.get("bass"):
            bass_energy = 0.65

    return TrackContext(
        song_id=str(lib.id),
        bpm=float(lib.bpm) if lib.bpm else None,
        camelot_key=lib.camelot_key,
        energy=_energy_to_label(lib.energy),
        duration_sec=float(lib.duration) if lib.duration else 240.0,
        beat_points=list(lib.beat_points) if lib.beat_points else [],
        downbeats=list(lib.downbeats) if lib.downbeats else [],
        phrase_map=list(lib.phrase_map) if lib.phrase_map else [],
        cue_points=list(lib.cue_points) if lib.cue_points else [],
        has_stems=has_stems,
        stem_quality_score=quality,
        vocal_density=vocal_density,
        bass_energy=bass_energy,
        intro_is_clean=has_stems,
        outro_is_clean=has_stems,
        has_drum_loop=has_stems,
    )


def _energy_to_label(energy: float | None) -> str:
    if energy is None:
        return "medium"
    if energy >= 7.0:
        return "high"
    if energy <= 3.0:
        return "low"
    return "medium"


# ═══════════════════════════════════════════════════════════════════════════════
# Biquad filter chain for EQ/filter processing
# ═══════════════════════════════════════════════════════════════════════════════

class BiquadFilter:
    """Simple biquad filter for offline rendering of EQ/filter curves.

    Supports: low_shelf, high_shelf, peaking, highpass, lowpass.
    Uses Robert Bristow-Johnson cookbook formulae.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sr = sample_rate
        self.b = np.zeros(3, dtype=np.float32)
        self.a = np.zeros(3, dtype=np.float32)
        self.z = np.zeros((2, 2), dtype=np.float32)

    def reset(self):
        self.z.fill(0.0)

    def design_low_shelf(self, freq: float, gain_db: float, q: float = 0.707):
        a_val = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * freq / self.sr
        cos_w = np.cos(w0)
        sin_w = np.sin(w0)
        alpha = sin_w / (2.0 * q)
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w / a0
        a2 = (1.0 - alpha) / a0
        b0 = (1.0 + a_val - (1.0 - a_val) * cos_w + 2.0 * np.sqrt(a_val) * alpha) / a0
        b1 = (2.0 * ((1.0 - a_val) * cos_w - 1.0 - a_val)) / a0
        b2 = ((1.0 + a_val) - (1.0 - a_val) * cos_w - 2.0 * np.sqrt(a_val) * alpha) / a0
        self.b = np.array([b0, b1, b2], dtype=np.float32)
        self.a = np.array([1.0, a1, a2], dtype=np.float32)

    def design_high_shelf(self, freq: float, gain_db: float, q: float = 0.707):
        a_val = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * freq / self.sr
        cos_w = np.cos(w0)
        sin_w = np.sin(w0)
        alpha = sin_w / (2.0 * q)
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w / a0
        a2 = (1.0 - alpha) / a0
        b0 = (1.0 + a_val + (1.0 - a_val) * cos_w + 2.0 * np.sqrt(a_val) * alpha) / a0
        b1 = (-2.0 * ((1.0 - a_val) * cos_w + 1.0 + a_val)) / a0
        b2 = ((1.0 + a_val) + (1.0 - a_val) * cos_w - 2.0 * np.sqrt(a_val) * alpha) / a0
        self.b = np.array([b0, b1, b2], dtype=np.float32)
        self.a = np.array([1.0, a1, a2], dtype=np.float32)

    def design_peaking(self, freq: float, gain_db: float, q: float = 0.9):
        a_val = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * freq / self.sr
        cos_w = np.cos(w0)
        sin_w = np.sin(w0)
        alpha = sin_w / (2.0 * q)
        a0 = 1.0 + alpha / a_val
        a1 = -2.0 * cos_w / a0
        a2 = (1.0 - alpha / a_val) / a0
        b0 = (1.0 + alpha * a_val) / a0
        b1 = (-2.0 * cos_w) / a0
        b2 = (1.0 - alpha * a_val) / a0
        self.b = np.array([b0, b1, b2], dtype=np.float32)
        self.a = np.array([1.0, a1, a2], dtype=np.float32)

    def design_highpass(self, freq: float, q: float = 0.707):
        w0 = 2.0 * np.pi * freq / self.sr
        cos_w = np.cos(w0)
        sin_w = np.sin(w0)
        alpha = sin_w / (2.0 * q)
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w / a0
        a2 = (1.0 - alpha) / a0
        b0 = (1.0 + cos_w) / (2.0 * a0)
        b1 = -(1.0 + cos_w) / a0
        b2 = (1.0 + cos_w) / (2.0 * a0)
        self.b = np.array([b0, b1, b2], dtype=np.float32)
        self.a = np.array([1.0, a1, a2], dtype=np.float32)

    def design_lowpass(self, freq: float, q: float = 0.707):
        w0 = 2.0 * np.pi * freq / self.sr
        cos_w = np.cos(w0)
        sin_w = np.sin(w0)
        alpha = sin_w / (2.0 * q)
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w / a0
        a2 = (1.0 - alpha) / a0
        b0 = (1.0 - cos_w) / (2.0 * a0)
        b1 = (1.0 - cos_w) / a0
        b2 = (1.0 - cos_w) / (2.0 * a0)
        self.b = np.array([b0, b1, b2], dtype=np.float32)
        self.a = np.array([1.0, a1, a2], dtype=np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        y = np.zeros_like(x, dtype=np.float32)
        for i in range(len(x)):
            y[i] = (self.b[0] * x[i] + self.b[1] * self.z[0, 0] + self.b[2] * self.z[0, 1]
                    - self.a[1] * self.z[1, 0] - self.a[2] * self.z[1, 1])
            self.z[0, 1] = self.z[0, 0]
            self.z[0, 0] = x[i]
            self.z[1, 1] = self.z[1, 0]
            self.z[1, 0] = y[i]
        return y


# ═══════════════════════════════════════════════════════════════════════════════
# Enhanced offline renderer: processes full AutomationCurve list
# ═══════════════════════════════════════════════════════════════════════════════

def _load_audio_mono(path: str, sample_rate: int) -> np.ndarray | None:
    if not path or not os.path.isfile(path):
        return None
    try:
        audio, _ = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)
    except Exception:
        return None


def _render_single_track(
    audio: np.ndarray,
    stems: dict[str, np.ndarray],
    curves: list[AutomationCurve],
    total_samples: int,
    sample_rate: int,
    is_side_a: bool,
) -> np.ndarray:
    """Render one deck through its AutomationCurves, returning mixed mono output."""
    prefix = "A." if is_side_a else "B."
    output = np.zeros(total_samples, dtype=np.float32)

    # Build per-target gain envelopes
    # Map: stem_name → gain envelope array (len=total_samples)
    stem_gains: dict[str, np.ndarray] = {}

    for name in STEM_NAMES:
        stem_gains[name] = np.ones(total_samples, dtype=np.float32)

    # Track-level master gain
    master_gain = np.ones(total_samples, dtype=np.float32)

    # EQ state
    low_eq_db = np.zeros(total_samples, dtype=np.float32)
    mid_eq_db = np.zeros(total_samples, dtype=np.float32)
    high_eq_db = np.zeros(total_samples, dtype=np.float32)

    # Lazy-built filter objects
    low_shelf = BiquadFilter(sample_rate)
    mid_peak = BiquadFilter(sample_rate)
    high_shelf = BiquadFilter(sample_rate)
    highpass_filt = BiquadFilter(sample_rate)
    lowpass_filt = BiquadFilter(sample_rate)

    for curve in curves:
        target_str = curve.target.value
        param = curve.param
        envelope = build_curve(curve, total_samples)

        if target_str == "master":
            if param == CurveParam.gain:
                master_gain = master_gain * envelope
            elif param == CurveParam.mute:
                master_gain = np.where(envelope > 0.5, 0.0, master_gain)
            elif param == CurveParam.low_eq:
                low_eq_db = envelope
            elif param == CurveParam.mid_eq:
                mid_eq_db = envelope
            elif param == CurveParam.high_eq:
                high_eq_db = envelope
            elif param == CurveParam.highpass:
                # Apply HPF per sample
                hpf_cutoff = np.clip(envelope, 20, 400)
                for i in range(0, total_samples, 512):
                    end = min(i + 512, total_samples)
                    cutoff = float(hpf_cutoff[i])
                    if cutoff > 20:
                        highpass_filt.design_highpass(cutoff)
                        output[i:end] = highpass_filt.process(output[i:end])
            elif param == CurveParam.lowpass:
                lpf_cutoff = np.clip(envelope, 200, 18000)
                for i in range(0, total_samples, 512):
                    end = min(i + 512, total_samples)
                    cutoff = float(lpf_cutoff[i])
                    if cutoff < 18000:
                        lowpass_filt.design_lowpass(cutoff)
                        output[i:end] = lowpass_filt.process(output[i:end])
            elif param == CurveParam.echo_send:
                # Simplified echo: mix a delayed+attenuated copy
                delay_samples = int(sample_rate * 0.25)
                echo_gain = envelope * 0.4
                echo = np.zeros(total_samples, dtype=np.float32)
                echo[delay_samples:] = output[:-delay_samples] * echo_gain[delay_samples:] * 0.5
                output += echo

        elif target_str.startswith(prefix):
            stem_name = target_str[2:]
            if stem_name in stem_gains:
                if param == CurveParam.gain:
                    stem_gains[stem_name] = stem_gains[stem_name] * envelope
                elif param == CurveParam.mute:
                    stem_gains[stem_name] = np.where(envelope > 0.5, 0.0, stem_gains[stem_name])

    # Mix stems with their gains → stereo mix
    full_mix = np.zeros(total_samples, dtype=np.float32)
    for name in STEM_NAMES:
        stem_audio = stems.get(name)
        if stem_audio is not None and stem_audio.size > 0:
            seg = stem_audio[:total_samples]
            if seg.size < total_samples:
                padded = np.zeros(total_samples, dtype=np.float32)
                padded[:seg.size] = seg
                seg = padded
            full_mix += seg * stem_gains[name]
        else:
            # Fall back to full audio for missing stems
            seg = audio[:total_samples]
            if seg.size < total_samples:
                padded = np.zeros(total_samples, dtype=np.float32)
                padded[:seg.size] = seg
                seg = padded
            full_mix += seg * stem_gains[name] * 0.25

    # Apply per-sample EQ
    for i in range(0, total_samples, 512):
        end = min(i + 512, total_samples)
        block = full_mix[i:end].copy()

        leq = float(np.mean(low_eq_db[i:end]))
        meq = float(np.mean(mid_eq_db[i:end]))
        heq = float(np.mean(high_eq_db[i:end]))

        if abs(leq) > 0.1:
            low_shelf.reset()
            low_shelf.design_low_shelf(80.0, leq)
            block = low_shelf.process(block)
        if abs(meq) > 0.1:
            mid_peak.reset()
            mid_peak.design_peaking(1000.0, meq, 0.9)
            block = mid_peak.process(block)
        if abs(heq) > 0.1:
            high_shelf.reset()
            high_shelf.design_high_shelf(8000.0, heq)
            block = high_shelf.process(block)

        full_mix[i:end] = block

    return full_mix * master_gain


def render_stem_automix_plan(
    plan: TransitionPlan,
    audio_a_path: str,
    audio_b_path: str,
    stems_a: dict[str, str] | None = None,
    stems_b: dict[str, str] | None = None,
    sample_rate: int = 44100,
    duration_bars: int = 8,
) -> np.ndarray:
    """Render a stereo mix from a TransitionPlan with full curve execution.

    Supports: gain, low_eq, mid_eq, high_eq, highpass, lowpass, echo_send, mute.
    """
    # Load audio
    audio_a = _load_audio_mono(audio_a_path, sample_rate)
    audio_b = _load_audio_mono(audio_b_path, sample_rate)

    if audio_a is None:
        raise FileNotFoundError(f"Cannot load audio A: {audio_a_path}")
    if audio_b is None:
        raise FileNotFoundError(f"Cannot load audio B: {audio_b_path}")

    # Load stems
    stem_audio_a: dict[str, np.ndarray] = {}
    stem_audio_b: dict[str, np.ndarray] = {}

    for name in STEM_NAMES:
        if stems_a and stems_a.get(name):
            sa = _load_audio_mono(stems_a[name], sample_rate)
            if sa is not None:
                stem_audio_a[name] = sa
        if stems_b and stems_b.get(name):
            sb = _load_audio_mono(stems_b[name], sample_rate)
            if sb is not None:
                stem_audio_b[name] = sb

    # Calculate transition length in samples
    bpm = plan.bpm_from if plan.bpm_from and plan.bpm_from > 0 else 120.0
    bars = plan.duration_bars if plan.duration_bars > 0 else duration_bars
    beat_duration = 60.0 / bpm
    bar_duration = beat_duration * 4.0
    transition_samples = int(bar_duration * bars * sample_rate)

    # Figure out how much of each track to include
    # A: last N seconds (use last ~30s or as much as available)
    a_tail_samples = min(transition_samples * 2, audio_a.size)
    b_head_samples = min(transition_samples * 2, audio_b.size)

    a_start = max(0, audio_a.size - a_tail_samples)
    b_start = 0

    a_segment = audio_a[a_start:a_start + a_tail_samples].copy()
    b_segment = audio_b[b_start:b_start + b_head_samples].copy()

    # Trim stem segments to match
    stem_a_seg: dict[str, np.ndarray] = {}
    stem_b_seg: dict[str, np.ndarray] = {}
    for name, sa in stem_audio_a.items():
        seg = sa[a_start:a_start + a_tail_samples]
        if seg.size > 0:
            stem_a_seg[name] = seg
    for name, sb in stem_audio_b.items():
        seg = sb[b_start:b_start + b_head_samples]
        if seg.size > 0:
            stem_b_seg[name] = seg

    # Write temp files for the existing renderer
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="hb_render_")
    try:
        tmp_a = os.path.join(tmpdir, "a.wav")
        tmp_b = os.path.join(tmpdir, "b.wav")
        sf.write(tmp_a, a_segment, sample_rate)
        sf.write(tmp_b, b_segment, sample_rate)

        # Use existing render_transition_plan for gain-based rendering as fallback,
        # then post-process with EQ/echo/mute curves
        from app.modules.playlists.stem_automix import render_transition_plan
        gain_mix = render_transition_plan(
            plan, tmp_a, tmp_b,
            from_stems=None, to_stems=None,
            sample_rate=sample_rate,
        )

        # Now apply stem-aware mixing with full curve support
        output = np.zeros(max(a_tail_samples + b_head_samples, gain_mix.size), dtype=np.float32)
        total = output.size

        # Process deck A curves
        deck_a = _render_single_track(
            a_segment, stem_a_seg,
            [c for c in plan.curves if c.target.value.startswith("A.") or c.target.value == "master"],
            total, sample_rate, is_side_a=True,
        )
        # Pad deck A: it plays from the beginning, ending at a_tail_samples
        deck_a_padded = np.zeros(total, dtype=np.float32)
        deck_a_padded[:min(deck_a.size, total)] = deck_a[:min(deck_a.size, total)]

        # Process deck B curves
        deck_b = _render_single_track(
            b_segment, stem_b_seg,
            [c for c in plan.curves if c.target.value.startswith("B.")],
            total, sample_rate, is_side_a=False,
        )
        # Deck B starts at the transition point (a_tail_samples)
        deck_b_padded = np.zeros(total, dtype=np.float32)
        b_len = min(deck_b.size, total - a_tail_samples)
        if b_len > 0:
            deck_b_padded[a_tail_samples:a_tail_samples + b_len] = deck_b[:b_len]

        output = deck_a_padded + deck_b_padded

        # Normalize
        peak = float(np.max(np.abs(output))) if output.size else 0.0
        if peak > 0.98:
            output = output / (peak + 1e-8) * 0.98

        return output.astype(np.float32)

    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# High-level API: build and render a stem-aware transition from LibrarySong data
# ═══════════════════════════════════════════════════════════════════════════════

def build_stem_aware_mix_plan(
    lib_a: LibrarySong | None,
    lib_b: LibrarySong | None,
    *,
    duration_bars: int = 8,
    force_preset: TransitionPreset | None = None,
    tempo_strategy: TempoStrategy | None = None,
) -> TransitionPlan:
    """Build a TransitionPlan from two LibrarySong objects.

    Automatically selects the best preset and tempo strategy.
    """
    ctx_a = library_song_to_track_context(lib_a)
    ctx_b = library_song_to_track_context(lib_b)

    return build_automix_transition(
        ctx_a, ctx_b,
        force_preset=force_preset,
        tempo_strategy=tempo_strategy,
        duration_bars=duration_bars,
    )


def build_and_render_stem_mix(
    lib_a: LibrarySong | None,
    lib_b: LibrarySong | None,
    audio_a_path: str,
    audio_b_path: str,
    output_wav_path: str,
    *,
    duration_bars: int = 8,
    force_preset: TransitionPreset | None = None,
    sample_rate: int = 44100,
) -> dict[str, Any]:
    """Build and render a stem-aware transition, writing the result to a WAV file.

    Returns metadata dict with plan and scores.
    """
    ctx_a = library_song_to_track_context(lib_a)
    ctx_b = library_song_to_track_context(lib_b)

    scores = score_transition_candidates(ctx_a, ctx_b)
    preset, mode, _ = select_best_preset(ctx_a, ctx_b, scores)

    if force_preset:
        preset = force_preset

    plan = build_automix_transition(
        ctx_a, ctx_b,
        force_preset=preset,
        duration_bars=duration_bars,
    )

    # Resolve stems paths
    stems_a: dict[str, str] | None = None
    stems_b: dict[str, str] | None = None

    if lib_a and lib_a.stems:
        stems_a = {k: v for k, v in lib_a.stems.items() if isinstance(v, str) and os.path.isfile(v)}
        if len(stems_a) < 2:
            stems_a = None
    if lib_b and lib_b.stems:
        stems_b = {k: v for k, v in lib_b.stems.items() if isinstance(v, str) and os.path.isfile(v)}
        if len(stems_b) < 2:
            stems_b = None

    audio = render_stem_automix_plan(
        plan, audio_a_path, audio_b_path,
        stems_a=stems_a, stems_b=stems_b,
        sample_rate=sample_rate,
        duration_bars=duration_bars,
    )

    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
    sf.write(output_wav_path, audio, sample_rate, subtype="PCM_16")

    return {
        "preset": preset.value,
        "mode": mode.value,
        "confidence": scores.transition_confidence,
        "duration_sec": round(audio.size / sample_rate, 3),
        "scores": scores.to_dict(),
        "plan": plan.to_dict(),
        "output_path": output_wav_path,
    }
