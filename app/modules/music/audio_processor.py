"""
Street-dance audio processor — professional pipeline.

Processing chain:
  1. Demucs v4 (HTDemucs) — 4-track source separation (drums/bass/vocals/other)
  2. Style-specific stem remixing with gain curves per dance genre
  3. Time-stretch to target BPM via librosa (pyrubberband fallback ready)
  4. Pedalboard DSP: compressor, EQ shelf, limiter per dance style
  5. Beat-synced groove pump (dynamic envelope on beat grid)
  6. EBU R128 loudness normalization via pyloudnorm
"""
from __future__ import annotations

import logging
import functools
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import soundfile as sf
import pyloudnorm as pyln
import torch
from pedalboard import (
    Compressor,
    Gain,
    HighShelfFilter,
    LowShelfFilter,
    Limiter,
    Pedalboard,
)

log = logging.getLogger(__name__)

# ── Target BPM per dance style ──────────────────────────────────────────────
STYLE_TARGET_BPM: dict[str, int] = {
    "hiphop": 92,
    "popping": 104,
    "locking": 112,
    "breaking": 128,
    "house": 124,
    "krump": 96,
    "waacking": 122,
}

# ── Stem mixing ratios: (drums, bass, vocals, other) per style ──────────────
# These ratios determine how each separated stem is mixed back.
# Higher drum/bass = harder groove feel. Lower vocals = instrumental focus.
STYLE_STEM_MIX: dict[str, tuple[float, float, float, float]] = {
    # style:       (drums,  bass,  vocals, other)
    "breaking":    (1.40,   1.15,  0.30,   0.35),  # heavy drums+bass, minimal vocals
    "krump":       (1.50,   1.20,  0.25,   0.30),  # hardest hitting
    "house":       (1.30,   1.20,  0.40,   0.50),  # four-on-floor kick focus
    "waacking":    (1.25,   1.00,  0.50,   0.60),  # disco-funk balance
    "popping":     (1.20,   1.05,  0.45,   0.55),  # clean funk groove
    "locking":     (1.15,   1.10,  0.50,   0.55),  # funky, keep groove
    "hiphop":      (1.10,   1.05,  0.55,   0.60),  # balanced, slight drum boost
}

DEFAULT_STEM_MIX = (1.10, 1.00, 0.55, 0.60)

# ── Pedalboard DSP presets per style ────────────────────────────────────────
# Each returns a Pedalboard effects chain
def _dsp_chain(style: str, sr: int) -> Pedalboard:
    """Build a pedalboard DSP chain tuned per dance style."""
    s = style.lower().strip()

    if s in {"breaking", "krump"}:
        return Pedalboard([
            LowShelfFilter(cutoff_frequency_hz=120.0, gain_db=5.0, q=0.7),    # sub bass boost
            HighShelfFilter(cutoff_frequency_hz=8000.0, gain_db=-2.0, q=0.7),  # tame highs
            Compressor(threshold_db=-18.0, ratio=5.0, attack_ms=5.0, release_ms=80.0),  # aggressive
            Gain(gain_db=2.0),
            Limiter(threshold_db=-1.0, release_ms=100.0),
        ])
    elif s in {"house", "waacking"}:
        return Pedalboard([
            LowShelfFilter(cutoff_frequency_hz=100.0, gain_db=3.5, q=0.7),
            HighShelfFilter(cutoff_frequency_hz=6000.0, gain_db=1.5, q=0.7),   # bright disco
            Compressor(threshold_db=-20.0, ratio=3.5, attack_ms=10.0, release_ms=100.0),
            Gain(gain_db=1.5),
            Limiter(threshold_db=-1.0, release_ms=120.0),
        ])
    elif s in {"popping", "locking"}:
        return Pedalboard([
            LowShelfFilter(cutoff_frequency_hz=100.0, gain_db=3.0, q=0.7),
            HighShelfFilter(cutoff_frequency_hz=5000.0, gain_db=1.0, q=0.7),
            Compressor(threshold_db=-22.0, ratio=3.0, attack_ms=12.0, release_ms=120.0),
            Gain(gain_db=1.0),
            Limiter(threshold_db=-1.0, release_ms=150.0),
        ])
    else:  # hiphop / default
        return Pedalboard([
            LowShelfFilter(cutoff_frequency_hz=100.0, gain_db=2.5, q=0.7),
            HighShelfFilter(cutoff_frequency_hz=7000.0, gain_db=0.5, q=0.7),
            Compressor(threshold_db=-24.0, ratio=2.5, attack_ms=15.0, release_ms=150.0),
            Gain(gain_db=1.0),
            Limiter(threshold_db=-1.0, release_ms=150.0),
        ])


# ── Demucs separation ──────────────────────────────────────────────────────
_demucs_model_cache: dict[str, object] = {}


def _get_demucs_model(name: str = "htdemucs"):
    """Load and cache Demucs model (lazy singleton)."""
    if name not in _demucs_model_cache:
        from demucs.pretrained import get_model
        log.info("Loading Demucs model '%s' …", name)
        model = get_model(name)
        model.eval()
        _demucs_model_cache[name] = model
    return _demucs_model_cache[name]


def _separate_stems(y_mono: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    """
    Separate audio into 4 stems using Demucs: drums, bass, vocals, other.
    Returns dict of mono numpy arrays at original sr.
    Falls back to HPSS if Demucs fails.
    """
    try:
        from demucs.apply import apply_model
        model = _get_demucs_model("htdemucs")

        # Demucs expects (batch, channels, samples) tensor
        # The model operates at its own sample rate, resample if needed
        model_sr = model.samplerate
        if sr != model_sr:
            y_resampled = librosa.resample(y_mono, orig_sr=sr, target_sr=model_sr)
        else:
            y_resampled = y_mono

        # Stereo duplicate for model input
        wav = torch.tensor(y_resampled, dtype=torch.float32).unsqueeze(0).expand(2, -1).unsqueeze(0)
        # wav shape: (1, 2, samples)

        with torch.no_grad():
            sources = apply_model(model, wav, device="cpu", split=True, overlap=0.25)
        # sources shape: (1, num_sources, 2, samples)

        source_names = model.sources  # typically ['drums', 'bass', 'other', 'vocals']
        stems: dict[str, np.ndarray] = {}
        for i, name in enumerate(source_names):
            stem_stereo = sources[0, i].cpu().numpy()  # (2, samples)
            stem_mono = stem_stereo.mean(axis=0)        # mix to mono
            # Resample back if needed
            if sr != model_sr:
                stem_mono = librosa.resample(stem_mono, orig_sr=model_sr, target_sr=sr)
            stems[name] = stem_mono

        log.info("Demucs separation OK: %s", list(stems.keys()))
        return stems

    except Exception as exc:
        log.warning("Demucs separation failed (%s), falling back to HPSS", exc)
        return _hpss_fallback(y_mono, sr)


def _hpss_fallback(y: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    """HPSS fallback: simulate drum/bass/other/vocals from harmonic/percussive split."""
    harmonic, percussive = librosa.effects.hpss(y)
    return {
        "drums": percussive,
        "bass": percussive * 0.3 + harmonic * 0.2,
        "vocals": harmonic * 0.5,
        "other": harmonic * 0.5,
    }


# ── Time-stretch ────────────────────────────────────────────────────────────
def _time_stretch(y: np.ndarray, rate: float) -> np.ndarray:
    """Time-stretch audio by rate factor. Tries pyrubberband, falls back to librosa."""
    if abs(rate - 1.0) < 0.02:
        return y

    try:
        import pyrubberband as pyrb
        return pyrb.time_stretch(y, sr=44100, rate=rate)
    except Exception:
        return librosa.effects.time_stretch(y, rate=rate)


# ── Beat-synced groove pump ─────────────────────────────────────────────────
def _groove_pump(y: np.ndarray, sr: int, beat_samples: np.ndarray,
                 depth: float = 0.22, style: str = "") -> np.ndarray:
    """Apply a beat-synced volume pump for groove emphasis."""
    if beat_samples.size == 0:
        return y

    s = style.lower().strip()
    # Adjust pump characteristics per style
    if s in {"breaking", "krump"}:
        depth = max(depth, 0.30)
        pulse_ms = 60   # short aggressive pulse
    elif s in {"house"}:
        depth = max(depth, 0.25)
        pulse_ms = 80   # four-on-floor pump
    elif s in {"popping", "locking"}:
        depth = max(depth, 0.20)
        pulse_ms = 70
    else:
        pulse_ms = 90

    pulse_len = int(pulse_ms / 1000.0 * sr)
    env = np.ones_like(y)
    for b in beat_samples:
        b = int(b)
        end = min(y.shape[0], b + pulse_len)
        if end <= b:
            continue
        t = np.linspace(0, 1, end - b, endpoint=False)
        env[b:end] *= 1.0 - depth * (1.0 - t)
    return y * env


# ── Transient emphasis ──────────────────────────────────────────────────────
def _transient_boost(y: np.ndarray, sr: int, strength: float = 0.25) -> np.ndarray:
    """Boost transients using onset strength envelope for dance accent clarity."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    if onset_env.max() < 1e-8:
        return y
    onset_norm = (onset_env - onset_env.min()) / (onset_env.max() - onset_env.min() + 1e-8)

    hop = 512
    gain = np.ones_like(y)
    for i in range(len(onset_norm)):
        start = i * hop
        if start >= y.shape[0]:
            break
        end = min(y.shape[0], start + hop)
        gain[start:end] *= 1.0 + strength * float(onset_norm[i])
    return y * gain


# ── Loudness normalization ──────────────────────────────────────────────────
def _loudness_normalize(y: np.ndarray, sr: int, target_lufs: float = -14.0) -> np.ndarray:
    """EBU R128 loudness normalization using pyloudnorm."""
    meter = pyln.Meter(sr)
    try:
        current_lufs = meter.integrated_loudness(y)
        if np.isinf(current_lufs) or np.isnan(current_lufs):
            raise ValueError("invalid loudness measurement")
        y = pyln.normalize.loudness(y, current_lufs, target_lufs)
        # Prevent clipping after loudness normalization
        y = np.clip(y, -1.0, 1.0)
    except Exception:
        # Fallback: peak normalize
        peak = float(np.max(np.abs(y)))
        if peak > 1e-7:
            y = y / peak * 0.95
    return y


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def process_audio_for_style(
    input_path: str,
    output_path: str,
    style: str,
    target_bpm: Optional[int] = None,
    target_energy: Optional[str] = None,
) -> dict[str, float | int | str | None]:
    """
    Full processing pipeline for street-dance style audio.

    Pipeline:
      1. Load audio (44.1 kHz mono)
      2. BPM detection + time-stretch to target BPM
      3. Demucs 4-track separation (drums/bass/vocals/other)
      4. Style-specific stem remixing
      5. Transient emphasis for dance accents
      6. Pedalboard DSP chain (compressor, EQ, limiter)
      7. Beat-synced groove pump
      8. EBU R128 loudness normalization
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"input file not found: {src}")

    sr = 44100
    style_key = style.lower().strip()

    # ── Step 1: Load ──
    log.info("Loading audio: %s", src.name)
    y, sr = librosa.load(str(src), sr=sr, mono=True)
    if y.size == 0:
        raise ValueError("empty audio")

    # ── Step 2: BPM + time-stretch ──
    bpm_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(bpm_raw) if bpm_raw else 0.0
    desired_bpm = target_bpm or STYLE_TARGET_BPM.get(style_key)

    if desired_bpm and bpm > 1:
        stretch_rate = float(desired_bpm) / bpm
        stretch_rate = float(np.clip(stretch_rate, 0.78, 1.3))
        log.info("Time-stretch: %.1f BPM → %d BPM (rate=%.3f)", bpm, desired_bpm, stretch_rate)
        y = _time_stretch(y, stretch_rate)
        bpm = float(desired_bpm)

    # ── Step 3: Demucs separation ──
    log.info("Separating stems with Demucs …")
    stems = _separate_stems(y, sr)

    # ── Step 4: Style-specific stem remix ──
    mix_gains = STYLE_STEM_MIX.get(style_key, DEFAULT_STEM_MIX)
    drums_g, bass_g, vocals_g, other_g = mix_gains

    # Ensure all stems have the same length
    target_len = max(s.shape[0] for s in stems.values())
    def _pad(arr: np.ndarray) -> np.ndarray:
        if arr.shape[0] < target_len:
            return np.pad(arr, (0, target_len - arr.shape[0]))
        return arr[:target_len]

    # Pad all stems to the same length
    padded_stems = {name: _pad(arr) for name, arr in stems.items()}

    mixed = (
        padded_stems.get("drums", np.zeros(target_len)) * drums_g
        + padded_stems.get("bass", np.zeros(target_len)) * bass_g
        + padded_stems.get("vocals", np.zeros(target_len)) * vocals_g
        + padded_stems.get("other", np.zeros(target_len)) * other_g
    )
    log.info("Stem remix: drums=%.2f bass=%.2f vocals=%.2f other=%.2f",
             drums_g, bass_g, vocals_g, other_g)

    # ── Step 5: Transient emphasis ──
    transient_strength = 0.30 if style_key in {"breaking", "krump"} else 0.20
    mixed = _transient_boost(mixed, sr, strength=transient_strength)

    # ── Step 6: Pedalboard DSP ──
    board = _dsp_chain(style_key, sr)
    # Pedalboard expects (channels, samples) float32
    mixed_2d = mixed.astype(np.float32).reshape(1, -1)
    mixed_2d = board(mixed_2d, sr)
    mixed = mixed_2d.flatten()
    log.info("DSP chain applied: %d effects", len(board))

    # ── Step 7: Beat-synced groove pump ──
    _, new_beat_frames = librosa.beat.beat_track(y=mixed, sr=sr)
    new_beat_samples = librosa.frames_to_samples(new_beat_frames)
    pump_depth = 0.22
    if (target_energy or "").lower() in {"high", "explosive"}:
        pump_depth = 0.32
    mixed = _groove_pump(mixed, sr, new_beat_samples, depth=pump_depth, style=style_key)

    # ── Step 8: Loudness normalize ──
    mixed = _loudness_normalize(mixed, sr, target_lufs=-14.0)

    # ── Write output ──
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), mixed, sr)
    log.info("Output written: %s (%.1f MB)", out.name, out.stat().st_size / 1024 / 1024)

    # ── Write individual stem files ──
    stem_paths: dict[str, str] = {}
    stem_base = out.stem  # e.g. "363_breaking_balanced"
    stem_dir = out.parent
    for stem_name in ("drums", "bass", "vocals", "other"):
        stem_arr = padded_stems.get(stem_name)
        if stem_arr is None:
            continue
        # Apply per-stem loudness normalization
        stem_norm = _loudness_normalize(stem_arr.copy(), sr, target_lufs=-16.0)
        stem_file = stem_dir / f"{stem_base}_{stem_name}.wav"
        sf.write(str(stem_file), stem_norm, sr)
        stem_paths[stem_name] = str(stem_file)
    log.info("Stems written: %s", list(stem_paths.keys()))

    return {
        "detected_bpm": float(bpm_raw) if bpm_raw else None,
        "target_bpm": int(desired_bpm) if desired_bpm else None,
        "sr": sr,
        "samples": int(mixed.shape[0]),
        "energy": target_energy,
        "pipeline": "demucs_v4+pedalboard+pyloudnorm",
        "stem_files": stem_paths,
    }
