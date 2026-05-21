"""音频引擎：双 deck + MixPlan 自动 crossfade + 9 键加花。"""

from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import BLOCK_SIZE, CACHE_DIR, CYPHER_HOME, REQUIRE_STEMS_FOR_PLAY, SAMPLE_RATE, resolve_audio_device
from mix_plan import NormalizedPlan, Transition, normalize_mix_plan

logger = logging.getLogger(__name__)

SAMPLES_DIR = CYPHER_HOME / "samples"
REQUIRED_STEMS = ("vocals", "drums", "bass", "other")
SAMPLE_FILES = {
    1: "01_ha.wav",
    2: "02_scratch.wav",
    3: "03_horn.wav",
    4: "04_drum_loop.wav",
    5: "05_bass_loop.wav",
    6: "06_hat_loop.wav",
}
# 叠到主轨上的增益（2/4/5 偏小声时加大）
SAMPLE_GAIN = {1: 1.0, 2: 1.5, 3: 1.0, 4: 2.0, 5: 2.0, 6: 1.2}
PRELOAD_BEFORE_SEC = 3.0


class SongCacheError(Exception):
    def __init__(self, message: str, code: int = 409) -> None:
        super().__init__(message)
        self.code = code


def _song_dir(song_id: int | str) -> Path:
    return CACHE_DIR / str(song_id)


def check_song_cache(song_id: int | str, require_stems: bool = False) -> Path:
    song_dir = _song_dir(song_id)
    original = song_dir / "original.wav"
    if not original.is_file():
        raise SongCacheError(f"缺少 original.wav: {original}", code=409)
    if require_stems:
        missing = [n for n in REQUIRED_STEMS if not (song_dir / f"{n}.wav").is_file()]
        if missing:
            raise SongCacheError(f"缺少 stem: {missing}", code=409)
    return original


def _load_wav_stereo(path: Path) -> np.ndarray:
    data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != SAMPLE_RATE:
        n_out = int(len(data) * SAMPLE_RATE / sr)
        x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        out = np.empty((n_out, 2), dtype=np.float32)
        for ch in range(2):
            out[:, ch] = np.interp(x_new, x_old, data[:, ch])
        data = out
    return data


def _read_segment(buf: np.ndarray, pos: int, frames: int) -> tuple[np.ndarray, int]:
    end = pos + frames
    chunk = buf[pos:end]
    new_pos = end
    if len(chunk) < frames:
        chunk = np.vstack([chunk, np.zeros((frames - len(chunk), 2), dtype=np.float32)])
    return chunk, new_pos


class Deck:
    __slots__ = ("audio", "pos", "song_id", "stems")

    def __init__(self) -> None:
        self.audio: np.ndarray | None = None
        self.pos = 0
        self.song_id: int | str | None = None
        self.stems: dict[str, np.ndarray] = {}

    @property
    def pos_sec(self) -> float:
        return self.pos / SAMPLE_RATE if self.audio is not None else 0.0

    def clear(self) -> None:
        self.audio = None
        self.pos = 0
        self.song_id = None
        self.stems = {}

    def load(self, song_id: int | str, start_at_sec: float = 0.0) -> float:
        path = check_song_cache(song_id, require_stems=REQUIRE_STEMS_FOR_PLAY)
        self.audio = _load_wav_stereo(path)
        start_frame = int(max(0.0, start_at_sec) * SAMPLE_RATE)
        self.pos = min(start_frame, max(0, len(self.audio) - 1))
        self.song_id = song_id
        self.stems = {}
        for name in REQUIRED_STEMS:
            stem_path = _song_dir(song_id) / f"{name}.wav"
            if stem_path.is_file():
                self.stems[name] = _load_wav_stereo(stem_path)
        return len(self.audio) / SAMPLE_RATE

    def read(self, frames: int) -> np.ndarray:
        if self.audio is None:
            return np.zeros((frames, 2), dtype=np.float32)
        chunk, self.pos = _read_segment(self.audio, self.pos, frames)
        return chunk


class AudioEngineMVP:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.deck_a = Deck()
        self.deck_b = Deck()
        self._active = "a"
        self._plan: NormalizedPlan | None = None
        self._plan_enabled = False
        self._transition_index = 0
        self._in_transition = False
        self._fade_frames_done = 0
        self._fade_total_frames = 0
        self._active_tr: Transition | None = None
        self._next_preloaded = False
        self._playing = False
        self._paused = False
        self._stream: sd.OutputStream | None = None
        self.samples: dict[int, np.ndarray] = {}
        self._one_shot_keys: list[tuple[int, list]] = []  # (key, [buf, pos])
        self.loops: dict[int, list] = {}
        self.stem_fx: tuple | None = None
        self._lpf_state = np.zeros(2, dtype=np.float32)
        self._xrun_count = 0
        self._load_samples()

    @property
    def active_deck(self) -> Deck:
        return self.deck_a if self._active == "a" else self.deck_b

    @property
    def inactive_deck(self) -> Deck:
        return self.deck_b if self._active == "a" else self.deck_a

    def _swap_decks(self) -> None:
        self._active = "b" if self._active == "a" else "a"
        self.inactive_deck.clear()
        self._in_transition = False
        self._fade_frames_done = 0
        self._active_tr = None
        self._next_preloaded = False
        self._transition_index += 1

    def _load_samples(self) -> None:
        for key, fname in SAMPLE_FILES.items():
            path = SAMPLES_DIR / fname
            if path.is_file():
                self.samples[key] = _load_wav_stereo(path)

    @staticmethod
    def _resolve_device() -> int | str | None:
        import os
        return resolve_audio_device(os.environ.get("CYPHER_AUDIO_DEVICE"))

    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return
        device = self._resolve_device()
        self._stream = sd.OutputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=2,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=self._callback,
        )
        self._stream.start()
        try:
            idx = device if isinstance(device, int) else sd.default.device[1]
            dev_name = sd.query_devices(idx).get("name", "?")
        except Exception:
            dev_name = str(device)
        logger.info("output stream started device=%s name=%s", device, dev_name)

    def _scheduled_transition(self) -> Transition | None:
        if not self._plan or self._transition_index >= len(self._plan.transitions):
            return None
        return self._plan.transitions[self._transition_index]

    def _next_song_id(self) -> int | str | None:
        tr = self._scheduled_transition()
        return tr.to_song_id if tr else None

    def _next_transition_in_sec(self) -> float | None:
        tr = self._scheduled_transition()
        if not tr or self.active_deck.song_id != tr.from_song_id:
            return None
        return max(0.0, tr.from_at_sec - self.active_deck.pos_sec)

    def get_state(self) -> dict:
        with self._lock:
            return {
                "playing": self._playing and not self._paused,
                "paused": self._paused,
                "current_song_id": self.active_deck.song_id,
                "position_sec": round(self.active_deck.pos_sec, 3),
                "next_song_id": self._next_song_id(),
                "next_transition_in_sec": self._next_transition_in_sec(),
                "in_transition": self._in_transition,
                "active_loops": sorted(self.loops.keys()),
                "active_stem_fx": self.stem_fx[0] if self.stem_fx else None,
                "audio_xrun_count": self._xrun_count,
            }

    def load_plan(self, mix_plan: dict) -> None:
        with self._lock:
            self._plan = normalize_mix_plan(mix_plan)
            self._plan_enabled = bool(self._plan.tracks)
            self._transition_index = 0
            self._in_transition = False
            self._next_preloaded = False
        logger.info(
            "mix_plan loaded: tracks=%s transitions=%d",
            self._plan.tracks if self._plan else [],
            len(self._plan.transitions) if self._plan else 0,
        )

    def play(self, song_id: int | str, start_at_sec: float = 0.0) -> dict:
        with self._lock:
            self._ensure_stream()
            self.deck_b.clear()
            self._active = "a"
            dur = self.deck_a.load(song_id, start_at_sec)
            self._playing = True
            self._paused = False
            self._in_transition = False
            self._transition_index = 0
            self._next_preloaded = False
            self._one_shot_keys.clear()
            self.stem_fx = None
            if self._plan and self._plan.tracks and song_id in self._plan.tracks:
                self._plan_enabled = True
                self._transition_index = self._plan.tracks.index(song_id)
                if self._transition_index < len(self._plan.transitions):
                    pass
                else:
                    self._transition_index = len(self._plan.transitions)
            else:
                self._plan_enabled = False
        logger.info("playing song_id=%s from %.2fs", song_id, start_at_sec)
        return {"song_id": song_id, "position_sec": start_at_sec, "duration_sec": dur}

    def pause(self) -> dict:
        with self._lock:
            self._paused = True
        return {"paused": True}

    def resume(self) -> dict:
        with self._lock:
            if self.active_deck.audio is None:
                raise SongCacheError("没有正在加载的曲目", code=400)
            self._paused = False
            self._playing = True
        return {"paused": False}

    def seek(self, sec: float) -> dict:
        with self._lock:
            if self.active_deck.audio is None:
                raise SongCacheError("没有正在加载的曲目", code=400)
            frame = int(max(0.0, sec) * SAMPLE_RATE)
            self.active_deck.pos = min(frame, max(0, len(self.active_deck.audio) - 1))
        return {"position_sec": sec}

    def next_track(self) -> dict:
        """手动切下一首：立即开始 crossfade（或硬切）。"""
        with self._lock:
            tr = self._scheduled_transition()
            if tr and self.active_deck.song_id == tr.from_song_id:
                self._begin_transition(tr)
                return {"action": "crossfade", "to_song_id": tr.to_song_id}
            if self._plan and self._plan.tracks:
                idx = self._plan.tracks.index(self.active_deck.song_id) if self.active_deck.song_id in self._plan.tracks else -1
                if idx >= 0 and idx + 1 < len(self._plan.tracks):
                    nxt = self._plan.tracks[idx + 1]
                    self._begin_transition(
                        Transition(
                            from_song_id=self.active_deck.song_id or 0,
                            to_song_id=nxt,
                            from_at_sec=self.active_deck.pos_sec,
                            to_at_sec=0.0,
                            fade_sec=8.0,
                        )
                    )
                    return {"action": "crossfade", "to_song_id": nxt}
            self.stop()
        return {"action": "stop", "note": "no_next_in_plan"}

    def _begin_transition(self, tr: Transition) -> None:
        try:
            self.inactive_deck.load(tr.to_song_id, tr.to_at_sec)
        except SongCacheError as exc:
            logger.error("transition load failed: %s", exc)
            return
        self._active_tr = tr
        self._fade_total_frames = int(tr.fade_sec * SAMPLE_RATE)
        self._fade_frames_done = 0
        self._in_transition = True
        self._next_preloaded = True
        logger.info(
            "crossfade start %s -> %s (%.1fs)",
            tr.from_song_id,
            tr.to_song_id,
            tr.fade_sec,
        )

    def _maybe_preload_and_transition(self) -> None:
        if not self._plan_enabled or not self._plan or self._in_transition:
            return
        tr = self._scheduled_transition()
        if not tr or self.active_deck.song_id != tr.from_song_id:
            return
        pos_sec = self.active_deck.pos_sec
        if not self._next_preloaded and pos_sec >= tr.from_at_sec - PRELOAD_BEFORE_SEC:
            try:
                self.inactive_deck.load(tr.to_song_id, tr.to_at_sec)
                self._next_preloaded = True
                logger.info("preloaded song_id=%s for transition", tr.to_song_id)
            except SongCacheError as exc:
                logger.warning("preload failed: %s", exc)
        if pos_sec >= tr.from_at_sec:
            if not self._next_preloaded:
                self._begin_transition(tr)
            else:
                self._active_tr = tr
                self._fade_total_frames = int(tr.fade_sec * SAMPLE_RATE)
                self._fade_frames_done = 0
                self._in_transition = True
                logger.info("crossfade start %s -> %s", tr.from_song_id, tr.to_song_id)

    @staticmethod
    def _fade_gains(progress: float, curve: str) -> tuple[float, float]:
        x = min(1.0, max(0.0, progress))
        if curve == "linear":
            return 1.0 - x, x
        return math.cos(x * math.pi / 2), math.sin(x * math.pi / 2)

    def trigger(self, key: int) -> dict:
        with self._lock:
            if key == 0:
                if self._paused:
                    self._paused = False
                    self._playing = True
                    action = "resume"
                else:
                    self._paused = True
                    action = "pause"
                return {"key": 0, "action": action}
            if key in (1, 2, 3):
                buf = self.samples.get(key)
                if buf is None:
                    return {"key": key, "error": "sample_missing"}
                self._one_shot_keys.append((key, [buf, 0]))
                return {"key": key, "action": "one_shot"}
            if key in (4, 5, 6):
                if key in self.loops:
                    del self.loops[key]
                    return {"key": key, "action": "loop_off"}
                buf = self.samples.get(key)
                if buf is None:
                    return {"key": key, "error": "sample_missing"}
                self.loops[key] = [buf, 0]
                return {"key": key, "action": "loop_on"}
            if key in (7, 8, 9):
                if not self.active_deck.stems:
                    return {"key": key, "error": "stems_not_loaded"}
                kinds = {7: "mute_vocals", 8: "solo_drums", 9: "lpf"}
                self.stem_fx = (kinds[key], time.time() + 2.0)
                if key == 9:
                    self._lpf_state[:] = 0
                return {"key": key, "action": kinds[key]}
        return {"key": key, "error": "invalid_key"}

    def stop(self) -> None:
        with self._lock:
            self._playing = False
            self._paused = False
            self.deck_a.clear()
            self.deck_b.clear()
            self._in_transition = False
            self._plan_enabled = False
            self._one_shot_keys.clear()
            self.loops.clear()
            self.stem_fx = None

    def _mix_loops(self, frames: int) -> np.ndarray:
        mix = np.zeros((frames, 2), dtype=np.float32)
        for key, layer in self.loops.items():
            buf, pos = layer
            chunk, pos = _read_segment(buf, pos % len(buf), frames)
            layer[1] = pos % len(buf)
            mix += chunk * SAMPLE_GAIN.get(key, 1.0)
        return mix

    def _mix_one_shots(self, frames: int) -> np.ndarray:
        mix = np.zeros((frames, 2), dtype=np.float32)
        still: list[tuple[int, list]] = []
        for key, layer in self._one_shot_keys:
            buf, pos = layer
            if pos >= len(buf):
                continue
            chunk, new_pos = _read_segment(buf, pos, frames)
            layer[1] = new_pos
            mix += chunk * SAMPLE_GAIN.get(key, 1.0)
            if new_pos < len(buf):
                still.append((key, layer))
        self._one_shot_keys = still
        return mix

    def _apply_stem_fx(self, main: np.ndarray, deck: Deck, frames: int) -> np.ndarray:
        if not self.stem_fx:
            return main
        kind, t_end = self.stem_fx
        if time.time() > t_end:
            self.stem_fx = None
            return main
        pos = deck.pos - frames
        if kind == "mute_vocals" and "vocals" in deck.stems:
            v = deck.stems["vocals"][pos : pos + frames]
            if len(v) == frames:
                return main - v
        if kind == "solo_drums" and "drums" in deck.stems:
            d = deck.stems["drums"][pos : pos + frames]
            if len(d) == frames:
                return d
        if kind == "lpf":
            out = np.empty_like(main)
            for i in range(frames):
                self._lpf_state = self._lpf_state + 0.15 * (main[i] - self._lpf_state)
                out[i] = self._lpf_state
            return out
        return main

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            self._xrun_count += 1
            logger.warning("sounddevice status: %s", status)
        with self._lock:
            if not self._playing or self._paused or self.active_deck.audio is None:
                outdata.fill(0)
                return

            if self._in_transition and self._active_tr:
                tr = self._active_tr
                a = self.active_deck.read(frames)
                b = self.inactive_deck.read(frames)
                progress = self._fade_frames_done / max(1, self._fade_total_frames)
                ga, gb = self._fade_gains(progress, tr.fade_curve)
                main = a * ga + b * gb
                self._fade_frames_done += frames
                if self._fade_frames_done >= self._fade_total_frames:
                    self._swap_decks()
            else:
                self._maybe_preload_and_transition()
                main = self.active_deck.read(frames)
                if self.active_deck.audio is not None and self.active_deck.pos >= len(self.active_deck.audio):
                    self._playing = False

            deck_for_fx = self.active_deck
            main = self._apply_stem_fx(main, deck_for_fx, frames)
            main = main + self._mix_loops(frames) + self._mix_one_shots(frames)
            outdata[:] = np.clip(main, -1.0, 1.0)

    def shutdown(self) -> None:
        with self._lock:
            self.stop()
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None


engine = AudioEngineMVP()
