"""Real audio playback engine for RK3588 edge agent.

Dual-deck architecture:
  - Two independent playback decks (A and B), each with up to 4 stem tracks.
  - Crossfade: both decks output simultaneously, mixed with per-stem gain curves.
  - Curve engine: reads AutomationCurves from TransitionPlan, interpolates gain/EQ
    values per audio callback block, applies to corresponding stem buffers.

Uses sounddevice for real-time ALSA/PulseAudio output.
Falls back to stub mode when sounddevice is unavailable (lightweight envs).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .config import DeckSide, PlaybackTier, get_config
from .session_manager import get_session_manager
from .state_manager import get_state_manager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Audio constants
# ═══════════════════════════════════════════════════════════════════════════════

BLOCK_SIZE = 512          # samples per callback
SAMPLE_RATE = 44100        # target output sample rate
N_CHANNELS = 2             # stereo output
STEM_NAMES = ("vocals", "drums", "bass", "other")

try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except ImportError:
    _HAS_SOUNDDEVICE = False
    logger.warning("sounddevice not installed — audio engine running in stub mode")


# ═══════════════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StemBuffer:
    """Pre-loaded stem audio and playback cursor."""
    name: str
    audio: np.ndarray          # mono float32 [-1, 1]
    sample_rate: int
    cursor: int = 0            # current playhead in samples
    gain: float = 1.0
    muted: bool = False

    @property
    def remaining(self) -> int:
        return max(0, len(self.audio) - self.cursor)

    @property
    def finished(self) -> bool:
        return self.cursor >= len(self.audio)

    def read_block(self, n: int) -> np.ndarray:
        """Read n samples, advance cursor. Returns zero-padded on underrun."""
        if self.muted or self.finished:
            return np.zeros(n, dtype=np.float32)
        end = min(self.cursor + n, len(self.audio))
        out = self.audio[self.cursor:end].copy()
        self.cursor += n
        if len(out) < n:
            out = np.pad(out, (0, n - len(out)))
        return out * self.gain


@dataclass
class Deck:
    """One playback deck with up to 4 stems + full mix."""
    side: DeckSide
    song_id: str | None = None
    playing: bool = False
    stems: dict[str, StemBuffer] = field(default_factory=dict)
    full_mix: np.ndarray | None = None    # pre-loaded full track (mono)
    full_mix_sr: int = SAMPLE_RATE
    cursor: int = 0
    bpm: float = 120.0

    @property
    def has_stems(self) -> bool:
        return len(self.stems) >= 2

    def mix_block(self, n: int, stem_gains: dict[str, float] | None = None) -> np.ndarray:
        """Mix stems + full track for n samples."""
        out = np.zeros(n, dtype=np.float32)
        if self.stems:
            for name, buf in self.stems.items():
                g = (stem_gains or {}).get(name, buf.gain)
                if buf.muted:
                    continue
                seg = buf.read_block(n)
                out += seg * g
        elif self.full_mix is not None:
            end = min(self.cursor + n, len(self.full_mix))
            seg = self.full_mix[self.cursor:end].copy()
            self.cursor += n
            if len(seg) < n:
                seg = np.pad(seg, (0, n - len(seg)))
            out += seg
        else:
            self.cursor += n
        return out

    def reset(self):
        self.cursor = 0
        for buf in self.stems.values():
            buf.cursor = 0


class AudioEngineError(Exception):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Audio Engine
# ═══════════════════════════════════════════════════════════════════════════════

class AudioEngine:
    """Dual-deck DJ audio engine with stem-aware crossfading."""

    def __init__(self):
        self._config = get_config()
        self._state = get_state_manager()
        self._session = get_session_manager()

        self._deck_a = Deck(DeckSide.A)
        self._deck_b = Deck(DeckSide.B)

        # Crossfade state
        self._xfade_active = False
        self._xfade_style: str | None = None
        self._xfade_curves: list[Any] = []
        self._xfade_duration_samples: int = 0
        self._xfade_elapsed: int = 0
        self._xfade_from: DeckSide | None = None
        self._xfade_to: DeckSide | None = None

        # Audio output
        self._stream: sd.OutputStream | None = None
        self._stream_lock = threading.Lock()
        self._running = False

        # Beat alignment
        self._next_beat_sample: int = 0
        self._beat_interval_samples: int = int(SAMPLE_RATE * 60.0 / 120.0)

        # Underflow protection
        self._underrun_count: int = 0
        self._silence_block = np.zeros((BLOCK_SIZE, N_CHANNELS), dtype=np.float32)

        logger.info("audio engine initialized (sounddevice=%s)", _HAS_SOUNDDEVICE)

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def connect(self) -> bool:
        if not _HAS_SOUNDDEVICE:
            logger.warning("sounddevice unavailable — stub mode")
            return False
        try:
            sd.default.samplerate = SAMPLE_RATE
            sd.default.channels = N_CHANNELS
            sd.default.dtype = 'float32'
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=N_CHANNELS,
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
                latency='low',
            )
            self._stream.start()
            self._running = True
            logger.info("audio engine stream started (sr=%d, block=%d)", SAMPLE_RATE, BLOCK_SIZE)
            return True
        except Exception as exc:
            logger.error("audio engine start failed: %s", exc)
            return False

    async def disconnect(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.info("audio engine stopped")

    # ── Audio Callback ──────────────────────────────────────────────────

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status):
        """Real-time audio callback — called by sounddevice."""
        if status:
            self._underrun_count += 1
            logger.debug("audio underrun #%d: %s", self._underrun_count, status)

        if not self._running:
            outdata[:] = 0.0
            return

        try:
            self._render_block(outdata, frames)
        except Exception:
            logger.exception("audio callback error")
            outdata[:] = 0.0

    def _render_block(self, outdata: np.ndarray, frames: int):
        """Render one block of audio output."""
        # During crossfade: mix both decks
        if self._xfade_active:
            progress = min(1.0, self._xfade_elapsed / max(self._xfade_duration_samples, 1))
            self._xfade_elapsed += frames

            # Compute stem gains from curves at current progress
            gains_a, gains_b = self._eval_curves(progress)

            a_mix = self._deck_a.mix_block(frames, gains_a)
            b_mix = self._deck_b.mix_block(frames, gains_b)

            # Stereo output
            mix_mono = a_mix + b_mix
            outdata[:, 0] = mix_mono
            outdata[:, 1] = mix_mono

            # Check if crossfade complete
            if self._xfade_elapsed >= self._xfade_duration_samples:
                self._finish_xfade()
            return

        # Normal playback: one deck active
        active = self._deck_a if self._deck_a.playing else self._deck_b
        if not active.playing:
            outdata[:] = 0.0
            return

        mix = active.mix_block(frames)
        outdata[:, 0] = mix
        outdata[:, 1] = mix

    # ── Curve Evaluation ────────────────────────────────────────────────

    def _eval_curves(self, progress: float) -> tuple[dict[str, float], dict[str, float]]:
        """Evaluate all crossfade curves at the given progress fraction.

        Returns (deck_a_gains, deck_b_gains) where each maps stem_name → gain.
        """
        gains_a: dict[str, float] = {n: 1.0 for n in STEM_NAMES}
        gains_b: dict[str, float] = {n: 1.0 for n in STEM_NAMES}

        if not self._xfade_curves:
            # Default equal-power crossfade
            cos_fade = math.cos(progress * math.pi / 2.0)
            sin_fade = math.sin(progress * math.pi / 2.0)
            for n in STEM_NAMES:
                gains_a[n] = cos_fade
                gains_b[n] = sin_fade
            return gains_a, gains_b

        for curve in self._xfade_curves:
            val = self._interp_curve(curve, progress)
            target = curve.get("target", "")
            param = curve.get("param", "gain")

            if param == "mute":
                val = 0.0 if val > 0.5 else 1.0

            if param not in ("gain", "mute"):
                continue  # EQ/filter params not applied per-sample in this engine

            if target.startswith("A."):
                stem = target[2:]
                if stem in gains_a:
                    gains_a[stem] *= val
            elif target.startswith("B."):
                stem = target[2:]
                if stem in gains_b:
                    gains_b[stem] *= val

        return gains_a, gains_b

    @staticmethod
    def _interp_curve(curve: dict, progress: float) -> float:
        """Interpolate a single AutomationCurve at progress ∈ [0,1]."""
        pts = curve.get("points", [[0.0, 1.0], [1.0, 0.0]])
        shape = curve.get("shape", "equal_power")

        if shape == "linear":
            # Simple linear interpolation through points
            for i in range(len(pts) - 1):
                t0, v0 = pts[i]
                t1, v1 = pts[i + 1]
                if t0 <= progress <= t1:
                    frac = (progress - t0) / max(t1 - t0, 1e-8)
                    return v0 + (v1 - v0) * frac
            return pts[-1][1] if progress >= pts[-1][0] else pts[0][1]

        elif shape == "equal_power":
            v0 = pts[0][1]
            v1 = pts[-1][1]
            cos_fade = math.cos(progress * math.pi / 2.0)
            sin_fade = math.sin(progress * math.pi / 2.0)
            return v0 * cos_fade + v1 * sin_fade

        elif shape == "s_curve":
            raw = AudioEngine._interp_curve(
                {**curve, "shape": "linear"}, progress
            )
            s = 3.0 * raw ** 2 - 2.0 * raw ** 3
            return s

        elif shape == "exponential":
            # Log-linear through points
            for i in range(len(pts) - 1):
                t0, v0 = pts[i]
                t1, v1 = pts[i + 1]
                if t0 <= progress <= t1:
                    frac = (progress - t0) / max(t1 - t0, 1e-8)
                    lv0 = math.log(max(v0, 1e-6))
                    lv1 = math.log(max(v1, 1e-6))
                    return math.exp(lv0 + (lv1 - lv0) * frac)
            return pts[-1][1] if progress >= pts[-1][0] else pts[0][1]

        # Fallback
        return pts[-1][1] if progress >= pts[-1][0] else pts[0][1]

    # ── Load ────────────────────────────────────────────────────────────

    async def load_deck(self, side: DeckSide, song_id: str, file_path: str,
                        stems: dict[str, str] | None = None,
                        bpm: float = 120.0) -> dict[str, Any]:
        """Load audio + optional stems into a deck."""
        deck = self._deck_a if side == DeckSide.A else self._deck_b
        deck.song_id = song_id
        deck.bpm = bpm
        deck.stems.clear()
        deck.full_mix = None
        deck.reset()

        if stems:
            for name in STEM_NAMES:
                spath = stems.get(name)
                if spath and Path(spath).is_file():
                    try:
                        audio, sr = self._read_audio(spath)
                        if audio is not None:
                            deck.stems[name] = StemBuffer(
                                name=name, audio=audio, sample_rate=sr,
                            )
                    except Exception as exc:
                        logger.warning("failed to load stem %s/%s: %s", song_id, name, exc)

        # Load full mix as fallback
        try:
            audio, sr = self._read_audio(file_path)
            if audio is not None:
                if sr != SAMPLE_RATE:
                    audio = self._resample(audio, sr, SAMPLE_RATE)
                deck.full_mix = audio
                deck.full_mix_sr = SAMPLE_RATE
        except Exception as exc:
            logger.warning("failed to load full mix %s: %s", song_id, exc)

        loaded = True
        stems_ok = len(deck.stems) >= 2
        await self._state.update_deck(side, song_id=song_id, stems_loaded=stems_ok)
        await self._session.record("load", deck=side.value, song_id=song_id, stems_ok=stems_ok)
        logger.info("deck %s loaded: %s (stems=%s)", side.value, song_id, stems_ok)

        # Auto-detect tier
        if self._deck_a.has_stems and self._deck_b.has_stems:
            await self._state.set_tier(PlaybackTier.stem_aware)
        elif self._deck_a.full_mix is not None or self._deck_b.full_mix is not None:
            await self._state.set_tier(PlaybackTier.non_stem)

        return {"ok": True, "deck": side.value, "song_id": song_id,
                "stems_loaded": stems_ok}

    @staticmethod
    def _read_audio(path: str) -> tuple[np.ndarray | None, int]:
        """Read audio file to mono float32."""
        try:
            import soundfile as sf
            audio, sr = sf.read(path, dtype='float32')
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            return audio.astype(np.float32), sr
        except ImportError:
            logger.warning("soundfile not installed — cannot read audio files")
            return None, SAMPLE_RATE
        except Exception:
            return None, SAMPLE_RATE

    @staticmethod
    def _resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
        """Simple linear resampling."""
        if src_sr == dst_sr:
            return audio
        from scipy import signal as sp_signal
        num_samples = int(len(audio) * dst_sr / src_sr)
        return sp_signal.resample(audio, num_samples).astype(np.float32)

    # ── Playback ────────────────────────────────────────────────────────

    async def play(self, side: DeckSide, start_sec: float = 0.0) -> dict[str, Any]:
        deck = self._deck_a if side == DeckSide.A else self._deck_b
        if deck.song_id is None:
            return {"ok": False, "error": "deck not loaded"}

        if start_sec > 0:
            deck.cursor = int(start_sec * SAMPLE_RATE)
            for buf in deck.stems.values():
                buf.cursor = deck.cursor
        else:
            deck.reset()

        deck.playing = True
        # Stop the other deck if playing
        other = self._deck_b if side == DeckSide.A else self._deck_a
        other.playing = False

        # Beat-align start
        self._beat_interval_samples = int(SAMPLE_RATE * 60.0 / max(deck.bpm, 1.0))

        await self._state.update_deck(side, playing=True, position_sec=start_sec)
        await self._session.record("play_started", deck=side.value, start_sec=start_sec)
        logger.info("play %s: %s @ %.1fs", side.value, deck.song_id, start_sec)
        return {"ok": True, "deck": side.value, "song_id": deck.song_id}

    async def pause(self, side: DeckSide) -> dict[str, Any]:
        deck = self._deck_a if side == DeckSide.A else self._deck_b
        deck.playing = False
        await self._state.update_deck(side, playing=False)
        await self._session.record("play_paused", deck=side.value)
        return {"ok": True}

    async def stop(self, side: DeckSide) -> dict[str, Any]:
        deck = self._deck_a if side == DeckSide.A else self._deck_b
        deck.playing = False
        deck.reset()
        await self._state.update_deck(side, playing=False, position_sec=0.0)
        await self._session.record("play_stopped", deck=side.value)
        return {"ok": True}

    # ── Crossfade ───────────────────────────────────────────────────────

    async def crossfade(self, style: str, duration_sec: float,
                        from_deck: DeckSide, to_deck: DeckSide) -> dict[str, Any]:
        """Start a stem-aware crossfade transition."""
        if self._xfade_active:
            return {"ok": False, "error": "crossfade already in progress"}

        self._xfade_active = True
        self._xfade_style = style
        self._xfade_duration_samples = int(duration_sec * SAMPLE_RATE)
        self._xfade_elapsed = 0
        self._xfade_from = from_deck
        self._xfade_to = to_deck

        # Start the incoming deck
        to = self._deck_b if to_deck == DeckSide.B else self._deck_a
        to.reset()
        to.playing = True

        await self._state.update_deck(to_deck, playing=True)
        await self._session.record("crossfade_start", style=style,
                                   from_deck=from_deck.value, to_deck=to_deck.value)
        logger.info("crossfade start: %s %.1fs %s→%s", style, duration_sec,
                    from_deck.value, to_deck.value)
        return {"ok": True, "style": style, "duration_sec": duration_sec}

    def _finish_xfade(self):
        """Complete the crossfade: stop outgoing deck, reset state."""
        self._xfade_active = False
        from_deck = self._deck_a if self._xfade_from == DeckSide.A else self._deck_b
        from_deck.playing = False
        logger.info("crossfade complete: %s→%s", self._xfade_from.value if self._xfade_from else "?",
                    self._xfade_to.value if self._xfade_to else "?")

    async def set_xfade_curves(self, curves: list[dict]):
        """Set the curve list for the next crossfade (from TransitionPlan)."""
        self._xfade_curves = curves

    # ── FX ──────────────────────────────────────────────────────────────

    async def trigger(self, fx_id: int, side: DeckSide) -> dict[str, Any]:
        """Trigger a stem FX: 7=bass kill, 8=vocal mute, 9=drum solo."""
        deck = self._deck_a if side == DeckSide.A else self._deck_b
        if fx_id == 7:  # bass kill
            if "bass" in deck.stems:
                deck.stems["bass"].muted = not deck.stems["bass"].muted
        elif fx_id == 8:  # vocal mute
            if "vocals" in deck.stems:
                deck.stems["vocals"].muted = not deck.stems["vocals"].muted
        elif fx_id == 9:  # drum solo
            for name, buf in deck.stems.items():
                buf.muted = (name != "drums")

        await self._session.record("key_press", fx_id=fx_id, deck=side.value)
        return {"ok": True, "fx_id": fx_id}

    # ── Health / State ──────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "running": self._running,
            "sounddevice": _HAS_SOUNDDEVICE,
            "sample_rate": SAMPLE_RATE,
            "block_size": BLOCK_SIZE,
            "underrun_count": self._underrun_count,
            "xfade_active": self._xfade_active,
        }

    async def state(self) -> dict[str, Any]:
        return await self.health()


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════

_audio_engine: AudioEngine | None = None


def get_audio_engine() -> AudioEngine:
    global _audio_engine
    if _audio_engine is None:
        _audio_engine = AudioEngine()
    return _audio_engine
