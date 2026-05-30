"""Programmatic synthesis of street-dance DJ FX one-shots.

All sounds are synthesized on demand using numpy. No sample library on the edge
device. Each function returns a mono `np.ndarray[float32]` at the given sample
rate (default 44100 Hz), amplitude clipped to [-1, 1].

This version is tuned for street-dance battle / cypher atmosphere — the
references are battle DJs (Skeme Richards, Lean Rock, J. Carter, Renegade)
who layer air horns, sirens, scratch stabs, rewinds and bass drops to mark
freezes, finishers and round transitions.

Catalog (street-dance focused):
  air_horn          : 3-tone harmonized stadium horn (much fuller than v1).
  air_horn_burst    : Triple-burst horn (taa-taa-taa) for round openers.
  siren             : Police / dancehall siren (Mr. Vegas style), riser+drop.
  reload_cock       : Reggae sound-system "reload" / gun-cock — short metallic
                      click for hype call-outs.
  scratch_chirp     : Classic wikka — band-passed noise + chirp (improved
                      pitch contour & gritty noise mix).
  scratch_transformer : Transformer scratch — rapid amplitude gating during
                        a pitch bend.
  scratch_baby      : Baby scratch — single back-forth sweep.
  beat_juggle_stutter : 1/16 stutter loop of a kick+snare — for build-ups.
  snare_crack       : Sharp 909-ish snare hit.
  kick_roll         : Descending 1/8 kick roll.
  bass_drop         : Sub-bass impact + plate-like body — drop / freeze stab.
  reverse_cymbal    : Reverse cymbal swell — build into a drop.
  cymbal_swell      : Forward cymbal noise rise.
  rewind_zip        : Spin-back / rewind (improved with vinyl scrape texture).
  vinyl_stop        : Power-cut deceleration.
  laser_zap         : Sci-fi zap — short transient stab for accent freezes.
  mc_hype           : Synthesized "yeah!" hype hit (formant-shaped noise) —
                      no vocal sample needed, conveys MC energy.
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
    out = np.ones(n, dtype=np.float32)
    a = max(1, int(n * attack_frac))
    out[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    decay = np.exp(-decay_curve * np.linspace(0.0, 1.0, n - a, dtype=np.float32))
    out[a:] = decay
    return out


def _env_adsr(n: int, attack: float = 0.05, decay: float = 0.1,
              sustain_level: float = 0.7, release: float = 0.2) -> np.ndarray:
    """ADSR envelope normalised by sample count."""
    a = max(1, int(n * attack))
    d = max(1, int(n * decay))
    r = max(1, int(n * release))
    s = max(0, n - a - d - r)
    out = np.empty(n, dtype=np.float32)
    out[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    out[a:a + d] = np.linspace(1.0, sustain_level, d, dtype=np.float32)
    out[a + d:a + d + s] = sustain_level
    out[a + d + s:] = np.linspace(sustain_level, 0.0, n - a - d - s, dtype=np.float32)
    return out


def _normalize(x: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(x))) or 1.0
    return (x * (target_peak / peak)).astype(np.float32)


def _smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Simple moving-average low-pass (used to derive a high-pass by subtraction)."""
    if window <= 1:
        return x
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(x, kernel, mode="same").astype(np.float32)


def _bandpass_noise(n: int, sr: int, fc: float, q: float = 4.0) -> np.ndarray:
    """Cheap band-passed noise around fc by subtracting two smoothed copies."""
    noise = (np.random.rand(n).astype(np.float32) * 2 - 1)
    period = max(2, int(sr / max(fc, 50.0)))
    lo = _smooth(noise, period * 2)
    hi = _smooth(noise, max(2, period // 2))
    return (hi - lo).astype(np.float32)


# --------------------------------------------------------------------------- #
# Sounds — improved & new
# --------------------------------------------------------------------------- #
def air_horn(duration: float = 1.4, sr: int = SR_DEFAULT) -> np.ndarray:
    """3-tone harmonized horn (stack of major-third fifths) with vibrato + brass body."""
    t = _t(duration, sr)
    f0 = 220.0
    # vibrato profile — slower at start, faster at end (excitation)
    vibrato = 6.0 * np.sin(2 * math.pi * (5.0 + 3.0 * (t / duration)) * t)
    # three voices: f0, f0*5/4 (major third), f0*3/2 (perfect fifth)
    voices = [(1.00, 0.50), (1.25, 0.30), (1.50, 0.20)]
    body = np.zeros_like(t)
    for mult, gain in voices:
        f = f0 * mult + vibrato
        phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
        # Brass-like: square + saw + a touch of sine
        sq = np.sign(np.sin(phase))
        saw = 2 * ((phase / (2 * math.pi)) % 1) - 1
        sin = np.sin(phase)
        voice = 0.45 * sq + 0.40 * saw + 0.15 * sin
        body += gain * voice
    # add a soft sub octave for stadium weight
    sub = np.sin(2 * math.pi * f0 * 0.5 * t) * 0.25
    body = body + sub
    env = _env_adsr(len(t), attack=0.05, decay=0.10, sustain_level=0.85, release=0.30)
    return _normalize((body * env).astype(np.float32), 0.92)


def air_horn_burst(duration: float = 1.5, sr: int = SR_DEFAULT) -> np.ndarray:
    """3 short horn taa-taa-taa hits for round openers."""
    seg = duration / 3.0
    parts = [air_horn(duration=seg * 0.8, sr=sr) for _ in range(3)]
    out = np.zeros(int(duration * sr), dtype=np.float32)
    for i, p in enumerate(parts):
        start = int(i * seg * sr)
        end = start + len(p)
        if end > len(out):
            end = len(out)
            p = p[:end - start]
        out[start:end] += p * 0.9
    return _normalize(out, 0.92)


def siren(duration: float = 2.5, sr: int = SR_DEFAULT) -> np.ndarray:
    """Police / dancehall siren: 2 up-down sweeps + final long rise.

    Inspired by Mr. Vegas / dancehall DJ tags — used in cypher to mark a
    new dancer entering the circle."""
    t = _t(duration, sr)
    # Three-phase frequency contour
    phase_dur = duration / 3.0
    f = np.zeros_like(t)
    for i in range(len(t)):
        x = t[i]
        if x < phase_dur:
            f[i] = 800 + 1400 * abs(math.sin(2 * math.pi * (x / phase_dur) * 1.0))
        elif x < phase_dur * 2:
            local = (x - phase_dur) / phase_dur
            f[i] = 600 + 1800 * abs(math.sin(2 * math.pi * local * 1.0))
        else:
            local = (x - 2 * phase_dur) / phase_dur
            f[i] = 800 + 2200 * local
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    tone = 0.55 * np.sin(phase) + 0.30 * np.sign(np.sin(phase))  # sine + square hybrid
    # texture: thin noise band riding pitch
    noise = _bandpass_noise(len(t), sr, 3000.0) * 0.20
    env = _env_adsr(len(t), attack=0.05, decay=0.05, sustain_level=0.95, release=0.20)
    return _normalize(((tone + noise) * env).astype(np.float32), 0.85)


def reload_cock(duration: float = 0.50, sr: int = SR_DEFAULT) -> np.ndarray:
    """Sound-system reload click — short metallic snap.

    A high-frequency burst with a rapid downward formant sweep, simulating
    a gun-cock reggae sound-system hype call. Useful before a finisher."""
    t = _t(duration, sr)
    # First half: high white noise burst
    n = len(t)
    half = n // 2
    out = np.zeros(n, dtype=np.float32)
    # click 1
    noise1 = (np.random.rand(half).astype(np.float32) * 2 - 1)
    bright1 = noise1 - _smooth(noise1, 5)
    env1 = np.exp(-30.0 * np.linspace(0, 1, half, dtype=np.float32))
    out[:half] = bright1 * env1 * 0.9
    # click 2 (slightly lower)
    noise2 = (np.random.rand(n - half).astype(np.float32) * 2 - 1)
    bright2 = noise2 - _smooth(noise2, 10)
    env2 = np.exp(-22.0 * np.linspace(0, 1, n - half, dtype=np.float32))
    out[half:] = bright2 * env2 * 0.75
    # add subtle metallic tone
    metallic = np.sin(2 * math.pi * 1800 * t) * np.exp(-8.0 * (t / duration)) * 0.3
    out = out + metallic
    return _normalize(out, 0.95)


def scratch_chirp(duration: float = 0.45, sr: int = SR_DEFAULT) -> np.ndarray:
    """Classic wikka — triangle-modulated band-pass noise + chirp carrier.
    Improved with grittier noise mix and asymmetric pitch contour."""
    t = _t(duration, sr)
    # Pitch contour: fast up then slower down (left-to-right hand motion)
    norm_t = t / duration
    contour = np.where(norm_t < 0.4,
                       (norm_t / 0.4) ** 1.2,
                       1.0 - 0.7 * ((norm_t - 0.4) / 0.6) ** 1.5)
    f_lo, f_hi = 180.0, 2200.0
    f = f_lo + (f_hi - f_lo) * contour
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    carrier = np.sin(phase) * 0.45 + np.sign(np.sin(phase)) * 0.25
    # gritty band-passed noise riding the same pitch
    noise = _bandpass_noise(len(t), sr, 1200.0) * 0.7
    env = _env_ad(len(t), attack_frac=0.02, decay_curve=2.2)
    return _normalize((carrier + noise) * env, 0.88)


def scratch_transformer(duration: float = 0.7, sr: int = SR_DEFAULT) -> np.ndarray:
    """Transformer scratch: pitch bend + 1/32 amplitude gating (fader cuts)."""
    base = scratch_chirp(duration=duration, sr=sr)
    n = len(base)
    # Gate at ~24 Hz (rapid wrist cuts)
    gate_freq = 24.0
    gate_phase = np.linspace(0, gate_freq * duration * 2 * math.pi, n)
    gate = (np.sin(gate_phase) > 0).astype(np.float32) * 0.95 + 0.05
    # Soft edges to avoid clicks
    gate = _smooth(gate, 32)
    return _normalize(base * gate, 0.88)


def scratch_baby(duration: float = 0.35, sr: int = SR_DEFAULT) -> np.ndarray:
    """Baby scratch — simple back-forth pitch sweep (no fader cuts)."""
    t = _t(duration, sr)
    # half forward, half backward
    half = len(t) // 2
    norm = np.empty(len(t), dtype=np.float32)
    norm[:half] = np.linspace(0, 1, half)
    norm[half:] = np.linspace(1, 0, len(t) - half)
    f = 250 + 1500 * norm
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    tone = np.sin(phase) * 0.7
    noise = _bandpass_noise(len(t), sr, 1000.0) * 0.4
    env = _env_ad(len(t), attack_frac=0.03, decay_curve=1.8)
    return _normalize((tone + noise) * env, 0.85)


def beat_juggle_stutter(duration: float = 1.0, sr: int = SR_DEFAULT,
                         bpm: float = 96.0) -> np.ndarray:
    """1/16 stutter — alternating kick / snare hits @ BPM. Build-up trick."""
    sixteenth = 60.0 / bpm / 4
    n_hits = max(1, int(duration / sixteenth))
    out = np.zeros(int(duration * sr) + sr, dtype=np.float32)
    for i in range(n_hits):
        seg_n = int(min(sixteenth * 1.0, 0.15) * sr)
        st = _t(seg_n / sr, sr)
        if i % 2 == 0:
            f0 = 70.0
            hit = np.sin(2 * math.pi * f0 * st) * np.exp(-18.0 * st)
            hit += np.sin(2 * math.pi * (f0 * 0.5) * st) * np.exp(-8.0 * st) * 0.6
        else:
            # snare-ish
            noise = (np.random.rand(seg_n).astype(np.float32) * 2 - 1)
            bright = noise - _smooth(noise, 6)
            body = np.sin(2 * math.pi * 220 * st) * np.exp(-25 * st) * 0.6
            hit = (bright * np.exp(-22 * st) * 0.7 + body)
        start = int(i * sixteenth * sr)
        out[start:start + len(hit)] += hit.astype(np.float32)
    out = out[:int(duration * sr)]
    return _normalize(out, 0.92)


def snare_crack(duration: float = 0.20, sr: int = SR_DEFAULT) -> np.ndarray:
    """Sharp snare hit — body + bright noise transient."""
    t = _t(duration, sr)
    body = np.sin(2 * math.pi * 220.0 * t) * np.exp(-32.0 * t)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1)
    bright = (noise - _smooth(noise, 8)) * np.exp(-28.0 * t)
    out = 0.55 * body + 0.85 * bright
    return _normalize(out.astype(np.float32), 0.95)


def kick_roll(duration: float = 1.0, sr: int = SR_DEFAULT, bpm: float = 100.0) -> np.ndarray:
    """Descending 1/8 kick roll."""
    eighth = 60.0 / bpm / 2
    n_hits = max(1, int(duration / eighth))
    out = np.zeros(int(duration * sr) + sr, dtype=np.float32)
    for i in range(n_hits):
        f0 = 90.0 * math.pow(0.75, i)
        seg_n = int(min(eighth * 1.4, 0.30) * sr)
        st = _t(seg_n / sr, sr)
        click = np.sin(2 * math.pi * f0 * st) * np.exp(-15.0 * st)
        thump = np.sin(2 * math.pi * (f0 * 0.5) * st) * np.exp(-8.0 * st) * 0.6
        hit = (click + thump).astype(np.float32)
        start = int(i * eighth * sr)
        out[start:start + len(hit)] += hit
    out = out[:int(duration * sr)]
    return _normalize(out, 0.9)


def bass_drop(duration: float = 1.6, sr: int = SR_DEFAULT) -> np.ndarray:
    """Sub-bass drop impact: 808-style downward pitch + plate body."""
    t = _t(duration, sr)
    # Pitch from 90Hz to 35Hz exponentially
    f = 90.0 * np.exp(-1.5 * (t / duration)) + 28.0
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    sub = np.sin(phase) * 0.85
    # Click transient
    click_dur_n = int(0.012 * sr)
    click = np.zeros(len(t), dtype=np.float32)
    click[:click_dur_n] = (np.random.rand(click_dur_n).astype(np.float32) * 2 - 1) * 1.0
    click[:click_dur_n] *= np.exp(-50.0 * np.linspace(0, 1, click_dur_n))
    # Plate-like ringing tail (high noise filtered, short)
    plate_noise = _bandpass_noise(len(t), sr, 2500.0) * 0.20
    plate_env = np.exp(-6.0 * (t / duration))
    plate = plate_noise * plate_env
    env = _env_ad(len(t), attack_frac=0.005, decay_curve=2.8)
    return _normalize((sub + click + plate) * env, 0.95)


def reverse_cymbal(duration: float = 2.0, sr: int = SR_DEFAULT) -> np.ndarray:
    """Reverse-tape cymbal swell — quiet start, loud end. Build-up."""
    t = _t(duration, sr)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1)
    bright = noise - _smooth(noise, 80)
    # Exponentially rising envelope (slow start, hits peak right at the end)
    env = (np.linspace(0, 1, len(t), dtype=np.float32)) ** 3.5
    return _normalize((bright * env).astype(np.float32), 0.85)


def cymbal_swell(duration: float = 2.0, sr: int = SR_DEFAULT) -> np.ndarray:
    """Forward cymbal noise swell."""
    t = _t(duration, sr)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1)
    bright = noise - _smooth(noise, 64)
    env = np.linspace(0.0, 1.0, len(t), dtype=np.float32) ** 2.5
    return _normalize((bright * env).astype(np.float32), 0.78)


def rewind_zip(duration: float = 1.4, sr: int = SR_DEFAULT) -> np.ndarray:
    """Spin-back with grittier scrape texture."""
    t = _t(duration, sr)
    f = 800.0 * np.exp(-3.2 * (t / duration)) + 30.0
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    tone = 0.55 * np.sin(phase) + 0.20 * np.sign(np.sin(phase))
    scrape = _bandpass_noise(len(t), sr, 1500.0) * 0.45
    env = np.linspace(0.65, 1.0, len(t), dtype=np.float32) * (1.0 - 0.2 * np.exp(-0.6 * (1 - t / duration)))
    return _normalize((tone + scrape) * env, 0.92)


def vinyl_stop(duration: float = 0.6, sr: int = SR_DEFAULT) -> np.ndarray:
    """Power-cut deceleration."""
    t = _t(duration, sr)
    f = 220.0 * (1.0 - (t / duration)) ** 1.8 + 30.0
    phase = np.cumsum(2 * math.pi * f / sr).astype(np.float32)
    tone = np.sin(phase)
    noise = (np.random.rand(len(t)).astype(np.float32) * 2 - 1) * 0.3
    env = np.exp(-2.0 * (t / duration))
    return _normalize(((tone + noise) * env).astype(np.float32), 0.85)


def laser_zap(duration: float = 0.35, sr: int = SR_DEFAULT) -> np.ndarray:
    """Quick sci-fi zap — descending FM stab for freeze accents."""
    t = _t(duration, sr)
    f = 2500.0 * np.exp(-6.0 * (t / duration)) + 80.0
    # FM modulator
    mod = np.sin(2 * math.pi * 90.0 * t) * 600.0 * np.exp(-3.0 * (t / duration))
    phase = np.cumsum(2 * math.pi * (f + mod) / sr).astype(np.float32)
    tone = np.sin(phase) * 0.7 + np.sign(np.sin(phase)) * 0.25
    env = _env_ad(len(t), attack_frac=0.02, decay_curve=4.0)
    return _normalize((tone * env).astype(np.float32), 0.88)


def mc_hype(duration: float = 0.55, sr: int = SR_DEFAULT) -> np.ndarray:
    """Synthesized MC-style 'yeah!' shout via formant-shaped noise.

    Two-formant additive synthesis: low formant ~700 Hz (vowel body) +
    high formant ~2400 Hz (mouth brightness), modulated by an attack-decay
    envelope and a short pitch dip mimicking a shout's downward intonation."""
    t = _t(duration, sr)
    # Pitch contour: drops 200 -> 130 Hz across the shout
    pitch = 200.0 * np.exp(-1.2 * (t / duration)) + 110.0
    phase = np.cumsum(2 * math.pi * pitch / sr).astype(np.float32)
    glottal = (np.sign(np.sin(phase)) * 0.6 + np.sin(phase) * 0.4)
    # formant: bandpass around 700Hz and 2400Hz
    f1 = _bandpass_noise(len(t), sr, 700.0) * 0.8
    f2 = _bandpass_noise(len(t), sr, 2400.0) * 0.4
    body = glottal * (0.5 + 0.5 * (f1 + f2))
    env = np.zeros(len(t), dtype=np.float32)
    a = int(0.06 * len(t))
    env[:a] = np.linspace(0, 1, a)
    env[a:] = np.exp(-3.5 * np.linspace(0, 1, len(t) - a, dtype=np.float32))
    return _normalize((body * env).astype(np.float32), 0.92)


# --------------------------------------------------------------------------- #
# Catalog & encoding
# --------------------------------------------------------------------------- #
FX_CATALOG: dict[str, dict] = {
    # 5 core FX — rk_key 1-5 maps to numpad keys on the 9-key controller.
    # Volume is boosted 1.5x over music level (gain applied in render()).
    "air_horn":            {"label_zh": "喇叭长鸣",         "fn": air_horn,            "default_duration": 1.4,  "category": "hype",  "rk_key": 1},
    "bass_drop":           {"label_zh": "Bass Drop",        "fn": bass_drop,           "default_duration": 1.6,  "category": "drop",  "rk_key": 2},
    "vinyl_stop":          {"label_zh": "黑胶刹停",          "fn": vinyl_stop,          "default_duration": 0.6,  "category": "drop",  "rk_key": 3},
    "snare_crack":         {"label_zh": "嚓声",             "fn": snare_crack,         "default_duration": 0.20, "category": "drum",  "rk_key": 4},
    "beat_juggle_stutter": {"label_zh": "Beat Juggle",      "fn": beat_juggle_stutter, "default_duration": 1.0,  "category": "drum",  "rk_key": 5},
}


def list_fx() -> list[dict]:
    return [
        {
            "key": k,
            "label_zh": v["label_zh"],
            "default_duration": v["default_duration"],
            "category": v.get("category", "accent"),
            "rk_key": v.get("rk_key"),
        }
        for k, v in FX_CATALOG.items()
    ]


def render(fx_key: str, duration: float | None = None, sr: int = SR_DEFAULT, **kwargs) -> np.ndarray:
    spec = FX_CATALOG.get(fx_key)
    if spec is None:
        raise KeyError(f"unknown fx: {fx_key}")
    dur = duration if (duration is not None and duration > 0) else spec["default_duration"]
    samples = spec["fn"](duration=dur, sr=sr, **kwargs)
    # Boost FX volume 1.5x over music level
    return samples * 1.5


def render_to_wav_bytes(fx_key: str, duration: float | None = None, sr: int = SR_DEFAULT, **kwargs) -> bytes:
    samples = render(fx_key, duration=duration, sr=sr, **kwargs)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm_int = (pcm * 32767.0).astype("<i2")
    byte_data = pcm_int.tobytes()
    data_size = len(byte_data)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write((36 + data_size).to_bytes(4, "little"))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write((16).to_bytes(4, "little"))
    buf.write((1).to_bytes(2, "little"))
    buf.write((1).to_bytes(2, "little"))
    buf.write(sr.to_bytes(4, "little"))
    buf.write((sr * 2).to_bytes(4, "little"))
    buf.write((2).to_bytes(2, "little"))
    buf.write((16).to_bytes(2, "little"))
    buf.write(b"data")
    buf.write(data_size.to_bytes(4, "little"))
    buf.write(byte_data)
    return buf.getvalue()
