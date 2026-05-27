"""Programmatic synthesis of DJ "加花" one-shots.

These are NOT pre-recorded samples — we synthesize each on demand using numpy
so the edge device doesn't need a sample library. Each function returns a
mono `np.ndarray[float32]` at the given sample rate (default 44100 Hz),
amplitude clipped to [-1, 1].

Catalog:
  scratch_chirp     : the classic "wikka-wikka" — modulated white-noise band
                      with fast pitch-bend.
  air_horn          : reggae/hip-hop horn — square + sawtooth stack with
                      vibrato.
  snare_crack       : white-noise burst + 200 Hz body, very short decay.
  kick_roll         : descending tom-fill / kick roll, 1/8-note timing.
  rewind_zip        : 1.5 s pitch-down sweep (the "spin-back" effect).
  cymbal_swell      : noise-band rising crescendo (for build-ups).
  vinyl_stop        : abrupt deceleration noise + low-pass sweep down.

All sounds are short (≤ 2.5 s) and self-normalising. They're returned as raw
float32 and can be written to WAV with `soundfile.write`. A convenience
`render_to_wav_bytes` returns 16-bit PCM bytes for HTTP responses.
"""
from __future__ import annotations

import io
import math
from typing import Callable

import numpy as np


SR_DEFAULT = 44100


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #
def _t(duration: float, sr: int) -> np.ndarray:
    return np.linspace(0.0, duration, int(duration * sr), endpoint=False, dtype=np.float32)


def _env_ad(n: int, attack_frac: float = 0.02, decay_curve: float = 4.0) -> np.ndarray:
    """Attack-decay envelope, exponentially decaying."""
    out = np.ones(n, dtype=np.float32)
    a = max(1, int(n * attack_frac))
    out[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    decay = np.exp(-decay_curve * np.linspace(0.0, 1.0, n - a, dtype=np.float32))
    out[a:] = decay
    return out


def _normalize(x: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(x))) or 1.0
    return (x * (target_peak / peak)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Sounds
# --------------------------------------------------------------------------- #
def scratch_chirp(duration: float = 0.45, sr: int = SR_DEFAULT) -> np.ndarray:
    t = _t(duration, sr)
    # Pitch-modulated band-passed noise to mimic a vinyl scratch.
    # We synthesize a chirp signal whose center frequency rides a triangle wave.
    f_lo, f_hi = 220.0, 1800.0
    # Triangle modulator (2 cycles within the duration)
    mod = np.abs((2 * (t / duration) * 2) % 2 - 1)
    f = f_lo + (f_hi - f_lo) * mod
    phase = np.cumsum(2 * np.pi * f / sr).astype(np.float32)
    carrier = np.sin(phase)
    # Add gritty noise modulated by the same envelope
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1) * 0.5
    out = (carrier * 0.7 + noise) * _env_ad(len(t), attack_frac=0.05, decay_curve=3.0)
    return _normalize(out, 0.85)


def air_horn(duration: float = 1.2, sr: int = SR_DEFAULT) -> np.ndarray:
    t = _t(duration, sr)
    f0 = 220.0
    vibrato = 4.0 * np.sin(2 * math.pi * 5.5 * t)  # 5.5 Hz vibrato, ±4 Hz
    phase = np.cumsum(2 * math.pi * (f0 + vibrato) / sr).astype(np.float32)
    # Stack square + saw + sub for that hand-held horn feel
    sq = np.sign(np.sin(phase))
    saw = 2 * ((phase / (2 * math.pi)) % 1) - 1
    sub = np.sin(phase * 0.5)
    body = 0.45 * sq + 0.45 * saw + 0.20 * sub
    env = _env_ad(len(t), attack_frac=0.08, decay_curve=1.2)
    # Slight ducking at the end (release)
    env[-int(0.15 * sr):] *= np.linspace(1.0, 0.0, int(0.15 * sr), dtype=np.float32)
    return _normalize((body * env).astype(np.float32), 0.85)


def snare_crack(duration: float = 0.20, sr: int = SR_DEFAULT) -> np.ndarray:
    t = _t(duration, sr)
    # Body: a 200 Hz sine that decays fast
    body = np.sin(2 * math.pi * 200.0 * t) * np.exp(-30.0 * t)
    # Top: white noise with bright high-pass-ish character (subtract a smoothed copy)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1)
    kernel = np.ones(8, dtype=np.float32) / 8
    smoothed = np.convolve(noise, kernel, mode="same")
    bright_noise = (noise - smoothed) * np.exp(-25.0 * t)
    out = 0.5 * body + 0.7 * bright_noise
    return _normalize(out.astype(np.float32), 0.95)


def kick_roll(duration: float = 1.0, sr: int = SR_DEFAULT, bpm: float = 100.0) -> np.ndarray:
    """1/8-note kick roll at given BPM, descending pitch (4 → 1 octave drop)."""
    eighth = 60.0 / bpm / 2  # 1/8 note seconds
    n_hits = max(1, int(duration / eighth))
    out = np.zeros(int(duration * sr) + sr, dtype=np.float32)
    for i in range(n_hits):
        f0 = 90.0 * math.pow(0.75, i)  # descend
        seg_n = int(min(eighth * 1.4, 0.30) * sr)
        st = _t(seg_n / sr, sr)
        click = np.sin(2 * math.pi * f0 * st) * np.exp(-15.0 * st)
        thump = np.sin(2 * math.pi * (f0 * 0.5) * st) * np.exp(-8.0 * st) * 0.6
        hit = (click + thump).astype(np.float32)
        start = int(i * eighth * sr)
        out[start:start + len(hit)] += hit
    out = out[:int(duration * sr)]
    return _normalize(out, 0.9)


def rewind_zip(duration: float = 1.4, sr: int = SR_DEFAULT) -> np.ndarray:
    """Spin-back: 1.5 s downward pitch sweep, modulated noise."""
    t = _t(duration, sr)
    f = 800.0 * np.exp(-3.0 * (t / duration))  # 800 → ~40 Hz
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    tone = np.sin(phase) * 0.6
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1) * 0.4
    env = np.linspace(0.7, 1.0, len(t), dtype=np.float32) * np.exp(-0.8 * (1 - t / duration))
    out = (tone + noise) * env
    return _normalize(out.astype(np.float32), 0.9)


def cymbal_swell(duration: float = 2.0, sr: int = SR_DEFAULT) -> np.ndarray:
    t = _t(duration, sr)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1)
    # Subtract heavy low-frequency smoothing → cheap high-pass for that "tssss"
    kernel = np.ones(64, dtype=np.float32) / 64
    smoothed = np.convolve(noise, kernel, mode="same")
    bright = noise - smoothed
    env = np.linspace(0.0, 1.0, len(t), dtype=np.float32) ** 2.5
    return _normalize((bright * env).astype(np.float32), 0.7)


def vinyl_stop(duration: float = 0.6, sr: int = SR_DEFAULT) -> np.ndarray:
    """The classic DJ stop — quick deceleration with a low rumble."""
    t = _t(duration, sr)
    f = 220.0 * (1.0 - (t / duration)) ** 1.8 + 30.0
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    tone = np.sin(phase)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1) * 0.3
    env = np.exp(-2.0 * (t / duration))
    return _normalize(((tone + noise) * env).astype(np.float32), 0.85)


# --------------------------------------------------------------------------- #
# Catalog & encoding
# --------------------------------------------------------------------------- #
FX_CATALOG: dict[str, dict] = {
    "scratch_chirp": {"label_zh": "搓碟 Wikka",  "fn": scratch_chirp,   "default_duration": 0.45},
    "air_horn":      {"label_zh": "喇叭",          "fn": air_horn,        "default_duration": 1.2},
    "snare_crack":   {"label_zh": "嚓声",          "fn": snare_crack,     "default_duration": 0.20},
    "kick_roll":     {"label_zh": "Kick Roll",   "fn": kick_roll,       "default_duration": 1.0},
    "rewind_zip":    {"label_zh": "倒带",          "fn": rewind_zip,      "default_duration": 1.4},
    "cymbal_swell":  {"label_zh": "镲片渐强",      "fn": cymbal_swell,    "default_duration": 2.0},
    "vinyl_stop":    {"label_zh": "黑胶刹停",      "fn": vinyl_stop,      "default_duration": 0.6},
}


def list_fx() -> list[dict]:
    return [{"key": k, "label_zh": v["label_zh"], "default_duration": v["default_duration"]} for k, v in FX_CATALOG.items()]


def render(fx_key: str, duration: float | None = None, sr: int = SR_DEFAULT, **kwargs) -> np.ndarray:
    spec = FX_CATALOG.get(fx_key)
    if spec is None:
        raise KeyError(f"unknown fx: {fx_key}")
    dur = duration if (duration is not None and duration > 0) else spec["default_duration"]
    return spec["fn"](duration=dur, sr=sr, **kwargs)


def render_to_wav_bytes(fx_key: str, duration: float | None = None, sr: int = SR_DEFAULT, **kwargs) -> bytes:
    """Render and encode as 16-bit PCM mono WAV bytes (no external deps)."""
    samples = render(fx_key, duration=duration, sr=sr, **kwargs)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm_int = (pcm * 32767.0).astype("<i2")  # little-endian int16

    # Minimal WAV header (PCM, mono)
    n_samples = len(pcm_int)
    byte_data = pcm_int.tobytes()
    data_size = len(byte_data)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write((36 + data_size).to_bytes(4, "little"))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write((16).to_bytes(4, "little"))     # PCM chunk size
    buf.write((1).to_bytes(2, "little"))       # format = PCM
    buf.write((1).to_bytes(2, "little"))       # channels
    buf.write(sr.to_bytes(4, "little"))         # sample rate
    buf.write((sr * 2).to_bytes(4, "little"))   # byte rate
    buf.write((2).to_bytes(2, "little"))        # block align
    buf.write((16).to_bytes(2, "little"))       # bits per sample
    buf.write(b"data")
    buf.write(data_size.to_bytes(4, "little"))
    buf.write(byte_data)
    return buf.getvalue()
