"""音频引擎：双 deck + MixPlan 自动 crossfade + 9 键加花。"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import BLOCK_SIZE, CACHE_DIR, CYPHER_HOME, REQUIRE_STEMS_FOR_PLAY, SAMPLE_RATE, resolve_audio_device
from dsp import Biquad
from mix_plan import NormalizedPlan, Transition, normalize_mix_plan

# Import professional DJ transition engine
import sys
sys.path.insert(0, '/tmp')
from dj_transition_engine import get_transition_envelopes, BUILDERS

logger = logging.getLogger(__name__)

SAMPLES_DIR = CYPHER_HOME / "samples"
REQUIRED_STEMS = ("vocals", "drums", "bass", "other")
STEM_AWARE_STYLES = {
    # 专业 DJ 转场（需要 stems）
    "smooth",
    "bass_swap",
    "echo_out",
    "echo_freeze",
    "filter",
    "slam",
    # 自定义转场（需要 stems）
    "drum_swap",
    "vocal_ducking",
    "vocal_handoff",
    "instrumental_only",
    "vocal_solo_intro",
}

# Prefetch 缓存：App/edge-agent 可提前调 engine.prefetch(song_id) 把 wav+stems 预解码进
# 这里；Deck.load() 用到该 song_id 时直接 pop 出 numpy 数组，避免按键时才走磁
# 盘 IO（50-200ms 锁顿）。这是复刻 Spotify Mix 「按键即响」响应的关键：predecoded PCM。
_PREFETCH_CACHE: dict[str, dict] = {}
_PREFETCH_LOCK = threading.Lock()
_PREFETCH_MAX = 4  # 最多同时备 4 首
# 5 个常见 DJ 加花音效（2026-05 更新）。文件需预先放在 ~/cypher/samples/ 下。
# 名字使用加花上下文词，后续替换素材只需覆盖同名 wav。
SAMPLE_FILES = {
    1: "air_horn.wav",            # 喇叭 长鸣
    2: "air_horn_burst.wav",      # 喇叭 三连
    3: "snare_crack.wav",         # 嚓声 Snare
    4: "beat_juggle_stutter.wav", # Beat Juggle
    5: "bass_drop.wav",           # Bass Drop
    6: "vinyl_stop.wav",          # 黑胶刹停
}
# 叠到主轨上的增益
SAMPLE_GAIN = {1: 1.4, 2: 1.4, 3: 1.4, 4: 1.2, 5: 1.6, 6: 1.3}
PRELOAD_BEFORE_SEC = 30.0
BEATMATCH_MAX_SHIFT = 0.06
BEATMATCH_MIN_SHIFT = 0.005
BEATMATCH_CACHE_MAX_FILES = 20


class SongCacheError(Exception):
    def __init__(self, message: str, code: int = 409) -> None:
        super().__init__(message)
        self.code = code


def _song_dir(song_id: int | str) -> Path:
    return CACHE_DIR / str(song_id)



_ORIGINAL_EXTS = ("wav", "mp3", "flac", "m4a", "ogg", "opus", "aac")


def _find_original_path(song_dir: Path) -> Path | None:
    """Locate cached original audio in any supported extension."""
    for ext in _ORIGINAL_EXTS:
        p = song_dir / f"original.{ext}"
        if p.is_file():
            return p
    return None


def check_song_cache(song_id: int | str, require_stems: bool = False) -> Path:
    song_dir = _song_dir(song_id)
    original = _find_original_path(song_dir)
    if original is None:
        raise SongCacheError(f"缺少 original.*: {song_dir}", code=409)
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
    __slots__ = (
        "audio", "pos", "song_id", "stems", "gain",
        # 3-band EQ：80Hz low-shelf / 1kHz peak / 8kHz high-shelf
        "eq_low_db", "eq_mid_db", "eq_hi_db",
        "_eq_lo", "_eq_mid", "_eq_hi",
    )

    def __init__(self) -> None:
        self.audio: np.ndarray | None = None
        self.pos = 0
        self.song_id: int | str | None = None
        self.stems: dict[str, np.ndarray] = {}
        # 响度归一线性增益（10^(dB/20)）。默认 1.0 = 不改。
        self.gain: float = 1.0
        # DJ 风 3-band EQ：各 band 纯 gain 参数（dB）+ 各一段 Biquad。默认 0 dB = bypass。
        self.eq_low_db: float = 0.0
        self.eq_mid_db: float = 0.0
        self.eq_hi_db: float = 0.0
        self._eq_lo: Biquad = Biquad()
        self._eq_mid: Biquad = Biquad()
        self._eq_hi: Biquad = Biquad()

    @property
    def pos_sec(self) -> float:
        return self.pos / SAMPLE_RATE if self.audio is not None else 0.0

    def clear(self) -> None:
        self.audio = None
        self.pos = 0
        self.song_id = None
        self.stems = {}
        self.gain = 1.0
        # EQ 参数 + 状态都重置，给下一首一个干净起点
        self.eq_low_db = 0.0
        self.eq_mid_db = 0.0
        self.eq_hi_db = 0.0
        for bq in (self._eq_lo, self._eq_mid, self._eq_hi):
            bq.reset()
            bq.set_bypass(True)

    def set_eq(self, low_db: float, mid_db: float, hi_db: float,
               sr: float = float(SAMPLE_RATE)) -> tuple[float, float, float]:
        """设置 3-band EQ（限幅 ±12 dB）。返回实际被采纳的 (low, mid, hi)。

        任一 band = 0 dB 时该段跳过 process（bypass），省下 CPU。
        """
        low_db = max(-12.0, min(12.0, float(low_db)))
        mid_db = max(-12.0, min(12.0, float(mid_db)))
        hi_db = max(-12.0, min(12.0, float(hi_db)))
        self.eq_low_db = low_db
        self.eq_mid_db = mid_db
        self.eq_hi_db = hi_db
        if abs(low_db) < 0.05:
            self._eq_lo.set_bypass(True)
        else:
            self._eq_lo.set_lowshelf(sr, 80.0, low_db, q=0.707)
        if abs(mid_db) < 0.05:
            self._eq_mid.set_bypass(True)
        else:
            self._eq_mid.set_peak(sr, 1000.0, mid_db, q=0.9)
        if abs(hi_db) < 0.05:
            self._eq_hi.set_bypass(True)
        else:
            self._eq_hi.set_highshelf(sr, 8000.0, hi_db, q=0.707)
        return low_db, mid_db, hi_db

    def apply_eq(self, chunk: np.ndarray) -> np.ndarray:
        """依次过 low-shelf -> peak -> high-shelf。bypass 路径 0 成本。"""
        chunk = self._eq_lo.process(chunk)
        chunk = self._eq_mid.process(chunk)
        chunk = self._eq_hi.process(chunk)
        return chunk

    def eq_values(self) -> tuple[float, float, float]:
        return self.eq_low_db, self.eq_mid_db, self.eq_hi_db

    def copy_eq_from(self, other: "Deck") -> None:
        self.set_eq(other.eq_low_db, other.eq_mid_db, other.eq_hi_db)

    def set_gain_db(self, db: float | None) -> None:
        if db is None:
            self.gain = 1.0
            return
        # 限幅 ±8dB
        db = max(-8.0, min(8.0, float(db)))
        self.gain = float(10.0 ** (db / 20.0))

    def load(
        self,
        song_id: int | str,
        start_at_sec: float = 0.0,
        load_stems: bool = True,
        audio_path: Path | None = None,
    ) -> float:
        key = str(song_id)
        cached: dict | None = None
        if audio_path is None:
            with _PREFETCH_LOCK:
                if key in _PREFETCH_CACHE:
                    cached = _PREFETCH_CACHE.pop(key)
        if cached is not None and audio_path is None:
            self.audio = cached["audio"]
            self.stems = cached["stems"]
            logger.info("deck.load hit prefetch cache: %s (remain=%d)", song_id, len(_PREFETCH_CACHE))
        else:
            path = audio_path or check_song_cache(song_id, require_stems=REQUIRE_STEMS_FOR_PLAY and load_stems)
            self.audio = _load_wav_stereo(path)
            self.stems = {}
            if load_stems and audio_path is None:
                for name in REQUIRED_STEMS:
                    stem_path = _song_dir(song_id) / f"{name}.wav"
                    if stem_path.is_file():
                        self.stems[name] = _load_wav_stereo(stem_path)
        start_frame = int(max(0.0, start_at_sec) * SAMPLE_RATE)
        self.pos = min(start_frame, max(0, len(self.audio) - 1))
        self.song_id = song_id
        return len(self.audio) / SAMPLE_RATE

    def read(self, frames: int) -> np.ndarray:
        if self.audio is None:
            return np.zeros((frames, 2), dtype=np.float32)
        chunk, self.pos = _read_segment(self.audio, self.pos, frames)
        if self.gain != 1.0:
            chunk = chunk * self.gain
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
        self._preload_requested: str | None = None
        self._playing = False
        self._paused = False
        self._stream: sd.OutputStream | None = None
        self.samples: dict[int, np.ndarray] = {}
        self._one_shot_keys: list[tuple[int, list]] = []  # (key, [buf, pos])
        self.loops: dict[int, list] = {}
        self.stem_fx: tuple | None = None
        # 持久 stem solo（None = 关闭，取值 'vocals'/'drums'/'bass'/'other'）
        # 与 stem_fx 不同：stem_fx 是 2 秒短效，stem_solo 一直生效直到关闭。
        self._stem_solo: str | None = None
        self._lpf_biquad: Biquad = Biquad()
        self._xrun_count = 0
        # ---- Sprint 1: 简易 look-ahead 峰值限制器 ----
        # 一块回调内：用块内峰值预测目标增益，配合 prev_gain 做立即-attack / 慢-release，
        # 并在块首做线性 ramp 避免 click。LUFS 已经把整体响度对齐 -14 LUFS，
        # 限制器只负责堵住串场瞬态过冲。
        self._lim_threshold: float = 0.95
        self._lim_gain: float = 1.0
        # 200ms 释放时间 -> 每 2048 样本块衰减系数 exp(-blocksize / (release_sec * sr))
        self._lim_release_coef: float = float(np.exp(-2048.0 / (0.2 * SAMPLE_RATE)))
        # ---- Sprint 2: 过渡风格 FX 状态 ----
        # 每个 deck 一段 biquad（LPF / HPF，按风格切换），系数每个 callback 重设。
        self._fx_filter_a: Biquad = Biquad()
        self._fx_filter_b: Biquad = Biquad()
        # echo: 250ms 单 tap 延迟 + 反馈，缓冲 0.6 sec 留余量
        self._echo_delay_samples: int = int(0.25 * SAMPLE_RATE)
        self._echo_buf_len: int = int(0.6 * SAMPLE_RATE)
        self._echo_buf: np.ndarray = np.zeros((self._echo_buf_len, 2), dtype=np.float32)
        self._echo_pos: int = 0  # write pointer
        self._echo_feedback: float = 0.45
        self._echo_wet: float = 0.7
        self._load_samples()
        self._cleanup_beatmatch_cache()

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
        self._preload_requested = None
        self._transition_index += 1
        # 过渡结束：重置 FX 状态，避免下次进入时听到残响 / 启动 click
        self._fx_filter_a.reset()
        self._fx_filter_a.set_bypass(True)
        self._fx_filter_b.reset()
        self._fx_filter_b.set_bypass(True)
        self._echo_buf.fill(0.0)
        self._echo_pos = 0

    def _load_samples(self) -> None:
        for key, fname in SAMPLE_FILES.items():
            path = SAMPLES_DIR / fname
            if path.is_file():
                self.samples[key] = _load_wav_stereo(path)

    @staticmethod
    def _cleanup_beatmatch_cache() -> None:
        """清理旧的 beatmatch 预渲染文件，只保留最近 N 个。"""
        if not CACHE_DIR.exists():
            return
        pattern = "original.rb.*.wav"
        files: list[Path] = []
        for song_dir in CACHE_DIR.iterdir():
            if not song_dir.is_dir():
                continue
            for f in song_dir.glob(pattern):
                if f.is_file():
                    files.append(f)
        if len(files) <= BEATMATCH_CACHE_MAX_FILES:
            return
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[BEATMATCH_CACHE_MAX_FILES:]:
            try:
                old.unlink()
                logger.info("beatmatch cache evict: %s", old)
            except OSError:
                pass
        logger.info("beatmatch cache cleaned: %d kept, %d removed", min(len(files), BEATMATCH_CACHE_MAX_FILES), max(0, len(files) - BEATMATCH_CACHE_MAX_FILES))

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
                "active_stem_solo": self._stem_solo,
                "audio_xrun_count": self._xrun_count,
                "playback_tier": self._playback_tier(),
            }

    def _stems_available(self, deck: Deck | None = None) -> bool:
        """Check if a deck (or both) has all 4 stems loaded."""
        if deck is not None:
            return all(name in deck.stems for name in REQUIRED_STEMS)
        a_ok = all(name in self.deck_a.stems for name in REQUIRED_STEMS)
        b_ok = all(name in self.deck_b.stems for name in REQUIRED_STEMS)
        return a_ok and b_ok

    def _playback_tier(self) -> str:
        """Return current playback capability tier.

        Tier 1 (basic):      Single deck play, no Automix capability.
        Tier 2 (non-stem):   Automix with beatmatch crossfade, EQ, filter, echo, cut, slam.
        Tier 3 (stem-aware): Automix with bass swap, vocal ducking, drum swap.
        """
        if self._stems_available():
            return "stem_aware"
        if self._stems_available(self.active_deck):
            return "stem_aware"
        if self._in_transition and self._stems_available(self.inactive_deck):
            return "stem_aware"
        if not self._plan_enabled or not self._plan:
            return "basic"
        return "non_stem"

    def _resolve_style(self, requested_style: str) -> str:
        """Auto-downgrade stem-aware styles when stems are unavailable."""
        if requested_style in STEM_AWARE_STYLES and not self._stems_available():
            fallback_map = {
                "bass_swap": "filter",
                "vocal_ducking": "blend",
                "drum_swap": "power",
                "vocal_handoff": "blend",
                "instrumental_only": "filter",
                "vocal_solo_intro": "echo_out",
            }
            fallback = fallback_map.get(requested_style, "smooth")
            logger.info(
                "style downgrade: %s -> %s (stems unavailable)",
                requested_style, fallback,
            )
            return fallback
        return requested_style

    def _transition_handoff_ratio(self, tr: Transition) -> float:
        """Return the beat-aligned vocal handoff point for vocal_handoff."""
        if tr.vocal_handoff_ratio is not None:
            return min(0.68, max(0.32, float(tr.vocal_handoff_ratio)))
        if tr.phase_anchor_sec is not None and tr.fade_sec > 0:
            return min(0.68, max(0.32, (float(tr.phase_anchor_sec) - tr.to_at_sec) / tr.fade_sec))
        meta = self._plan.track_meta.get(str(tr.to_song_id), {}) if self._plan else {}
        beats = meta.get("beats") or []
        lo, hi, target = 0.32, 0.62, 0.45
        candidates = []
        for beat in beats:
            try:
                ratio = (float(beat) - tr.to_at_sec) / max(0.001, tr.fade_sec)
            except (TypeError, ValueError):
                continue
            if lo <= ratio <= hi:
                candidates.append(ratio)
        if candidates:
            return min(candidates, key=lambda r: abs(r - target))
        if tr.to_beat_interval_sec and tr.to_beat_interval_sec > 0:
            target_sec = target * tr.fade_sec
            snapped = round(target_sec / tr.to_beat_interval_sec) * tr.to_beat_interval_sec
            return min(hi, max(lo, snapped / max(0.001, tr.fade_sec)))
        return target

    def load_plan(self, mix_plan: dict) -> None:
        with self._lock:
            self._plan = normalize_mix_plan(mix_plan)
            self._plan_enabled = bool(self._plan.tracks)
            self._transition_index = 0
            self._in_transition = False
            self._next_preloaded = False
            self._preload_requested = None
        logger.info(
            "mix_plan loaded: tracks=%s transitions=%d",
            self._plan.tracks if self._plan else [],
            len(self._plan.transitions) if self._plan else 0,
        )
        # 后台预热 beatmatch 渲染，避免在实时 preload 时等 rubberband
        if self._plan and self._plan.transitions:
            for tr in self._plan.transitions:
                threading.Thread(
                    target=self._beatmatched_audio_path,
                    args=(tr,),
                    kwargs={"render": True},
                    daemon=True,
                    name=f"beatmatch-warm-{tr.to_song_id}",
                ).start()

    def play(self, song_id: int | str, start_at_sec: float = 0.0) -> dict:
        deck = Deck()
        with self._lock:
            deck.copy_eq_from(self.deck_a)
        dur = deck.load(song_id, start_at_sec)
        self._apply_loudness_gain(deck, song_id)
        with self._lock:
            self._ensure_stream()
            self._active = "a"
            self.deck_a = deck
            self.deck_b.clear()
            self._playing = True
            self._paused = False
            self._in_transition = False
            self._transition_index = 0
            self._next_preloaded = False
            self._preload_requested = None
            self._one_shot_keys.clear()
            self.stem_fx = None
            # /play 是“硬切”，重置持久 stem_solo 避免上一首的供菜多到下一首。
            self._stem_solo = None
            # /play 不会恢复残留的 mix plan。只有 edge-agent 通过
            # load_plan 明确启动的 session 才启用 plan 自动调度。
            # edge-agent 用显式 /xfade 切歌，不依赖 plan 的自动过渡。
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
                pass
            elif self._plan and self._plan.tracks:
                idx = self._plan.tracks.index(self.active_deck.song_id) if self.active_deck.song_id in self._plan.tracks else -1
                if idx >= 0 and idx + 1 < len(self._plan.tracks):
                    nxt = self._plan.tracks[idx + 1]
                    tr = Transition(
                        from_song_id=self.active_deck.song_id or 0,
                        to_song_id=nxt,
                        from_at_sec=self.active_deck.pos_sec,
                        to_at_sec=0.0,
                        fade_sec=8.0,
                    )
                else:
                    tr = None
            else:
                tr = None
            if tr is None:
                self.stop()
                return {"action": "stop", "note": "no_next_in_plan"}
        self.manual_transition(
            tr.to_song_id,
            fade_sec=tr.fade_sec,
            to_at_sec=tr.to_at_sec,
            style=tr.style,
        )
        return {"action": "crossfade", "to_song_id": tr.to_song_id}

    def manual_transition(
        self,
        to_song_id: int | str,
        fade_sec: float = 4.0,
        to_at_sec: float = 0.0,
        style: str = "smooth",
    ) -> dict:
        """越过 plan 调度直接对任意歌曲做 crossfade。

        用于 App 端“能量切歌 / 风格切歌 / 手动下一首”，复刻网页版
        SeamlessPlayer 的无缝衰接效果。调用前需确保目标歌的 wav 已在
        ~/cypher/cache/{song_id}/original.wav，否则会抛 SongCacheError。
        style: 7 种 DJ 切歌风格，默认 smooth。
        """
        with self._lock:
            if self.active_deck.audio is None:
                raise SongCacheError("audio-engine 未在播放，不能 crossfade，请先 /play", code=400)
            # 如果 plan 已自动触发过渡 (via _maybe_preload_and_transition)，
            # 先清理掉，避免两个过渡抢同一对 Deck 导致 ALSA underrun。
            if self._in_transition:
                self._in_transition = False
                self._fade_frames_done = 0
                self._active_tr = None
                self._next_preloaded = False
                self._preload_requested = None
            tr = Transition(
                from_song_id=self.active_deck.song_id or 0,
                to_song_id=to_song_id,
                from_at_sec=self.active_deck.pos_sec,
                to_at_sec=float(max(0.0, to_at_sec)),
                fade_sec=float(max(0.05, fade_sec)),
                style=str(style or "smooth"),
            )
            inactive_eq = self.inactive_deck.eq_values()

        deck = Deck()
        deck.set_eq(*inactive_eq)
        want_stems = style in STEM_AWARE_STYLES
        # Beatmatched original renders cannot carry stems. Until we render
        # beatmatched stems as a bundle, stem-aware styles must load source
        # stems and leave tempo handling to cue selection.
        audio_path = None if want_stems else self._beatmatched_audio_path(tr, render=False)
        deck.load(to_song_id, to_at_sec, load_stems=want_stems, audio_path=audio_path)
        self._apply_loudness_gain(deck, to_song_id)

        with self._lock:
            if self.active_deck.audio is None:
                raise SongCacheError("audio-engine 未在播放，不能 crossfade，请先 /play", code=400)
            # 如果 plan 已自动触发过渡 (via _maybe_preload_and_transition)，
            # 先清理掉，避免两个过渡抢同一对 Deck 导致 ALSA underrun。
            if self._in_transition:
                self._in_transition = False
                self._fade_frames_done = 0
                self._active_tr = None
                self._next_preloaded = False
                self._preload_requested = None
            tr = Transition(
                from_song_id=self.active_deck.song_id or 0,
                to_song_id=to_song_id,
                from_at_sec=self.active_deck.pos_sec,
                to_at_sec=float(max(0.0, to_at_sec)),
                fade_sec=float(max(0.05, fade_sec)),
                style=str(style or "smooth"),
            )
            # 跳出 plan 调度，避免 crossfade 结束后又被 plan transition 覆盖
            self._plan_enabled = False
            self._install_inactive_deck(deck)
            self._start_transition_locked(tr)
        return {
            "action": "crossfade",
            "to_song_id": to_song_id,
            "fade_sec": tr.fade_sec,
            "to_at_sec": tr.to_at_sec,
            "style": tr.style,
        }

    def _install_inactive_deck(self, deck: Deck) -> None:
        if self._active == "a":
            self.deck_b = deck
        else:
            self.deck_a = deck

    def _start_transition_locked(self, tr: Transition) -> None:
        self._active_tr = tr
        self._fade_total_frames = int(tr.fade_sec * SAMPLE_RATE)
        self._fade_frames_done = 0
        self._in_transition = True
        self._next_preloaded = True
        self._preload_requested = None
        self._fx_filter_a.reset()
        self._fx_filter_a.set_bypass(True)
        self._fx_filter_b.reset()
        self._fx_filter_b.set_bypass(True)
        self._echo_buf.fill(0.0)
        self._echo_pos = 0
        logger.info(
            "crossfade start %s -> %s (%.1fs)",
            tr.from_song_id,
            tr.to_song_id,
            tr.fade_sec,
        )

    def set_stem_solo(self, stem: str | None) -> dict:
        """持久 stem solo：只让某个 stem 出声，None = 恢复全轨。不影响 crossfade。"""
        with self._lock:
            if stem is not None and stem not in REQUIRED_STEMS:
                raise SongCacheError(f"invalid stem: {stem}", code=400)
            if stem is not None and stem not in self.active_deck.stems:
                raise SongCacheError(f"stem '{stem}' 未加载（该歌可能缺少分离音轨）", code=409)
            self._stem_solo = stem
        logger.info("stem_solo set to %s", stem)
        return {"stem": stem}

    def prefetch(self, song_ids: list[int | str]) -> dict:
        """提前把候选歌曲的 wav+stems 解码到内存，让按键切歌不再走磁盘 IO。

        非阻塞：每首歌起一个 daemon 线程读 5 个 wav，结果放到 _PREFETCH_CACHE。
        缓存命中后 Deck.load() 直接 pop 出 numpy 数组（~微秒）而不是 sf.read（~百毫秒）。
        """
        scheduled: list[str] = []
        already: list[str] = []
        for sid in song_ids:
            key = str(sid)
            with _PREFETCH_LOCK:
                if key in _PREFETCH_CACHE:
                    already.append(key)
                    continue
            threading.Thread(
                target=self._do_prefetch,
                args=(sid,),
                daemon=True,
                name=f"prefetch-{key}",
            ).start()
            scheduled.append(key)
        return {"scheduled": scheduled, "already": already, "cache_size": len(_PREFETCH_CACHE)}

    def _do_prefetch(self, song_id: int | str) -> None:
        key = str(song_id)
        try:
            t0 = time.time()
            path = check_song_cache(song_id, require_stems=False)
            audio = _load_wav_stereo(path)
            stems: dict[str, np.ndarray] = {}
            for name in REQUIRED_STEMS:
                stem_path = _song_dir(song_id) / f"{name}.wav"
                if stem_path.is_file():
                    stems[name] = _load_wav_stereo(stem_path)
            with _PREFETCH_LOCK:
                # LRU：超出上限丢最早项
                while len(_PREFETCH_CACHE) >= _PREFETCH_MAX:
                    drop = next(iter(_PREFETCH_CACHE))
                    _PREFETCH_CACHE.pop(drop)
                    logger.info("prefetch LRU drop: %s", drop)
                _PREFETCH_CACHE[key] = {"audio": audio, "stems": stems}
            dt = (time.time() - t0) * 1000
            logger.info("prefetch ok: %s in %.0fms (cache=%d)", song_id, dt, len(_PREFETCH_CACHE))
        except Exception as e:
            logger.warning("prefetch failed for %s: %s", song_id, e)

    def _apply_loudness_gain(self, deck: Deck, song_id: int | str) -> None:
        """从 plan.track_meta 取 replay_gain_db 并套到 deck 上。"""
        if not self._plan:
            deck.set_gain_db(None)
            return
        meta = self._plan.track_meta.get(str(song_id))
        if not meta:
            deck.set_gain_db(None)
            return
        deck.set_gain_db(meta.get("replay_gain_db"))

    @staticmethod
    def _beatmatch_time_ratio(tr: Transition) -> float | None:
        """Rubberband time ratio for B so its tempo matches A."""
        ratio: float | None = None
        if tr.from_beat_interval_sec and tr.to_beat_interval_sec:
            if tr.from_beat_interval_sec > 0 and tr.to_beat_interval_sec > 0:
                # tempo_B / tempo_A == interval_A / interval_B.
                ratio = tr.from_beat_interval_sec / tr.to_beat_interval_sec
        elif tr.tempo_ratio and tr.tempo_ratio > 0:
            # Fallback for P2 plans that already provide tempo_B / tempo_A.
            ratio = tr.tempo_ratio
        if ratio is None:
            return None
        if abs(ratio - 1.0) < BEATMATCH_MIN_SHIFT:
            return None
        if abs(ratio - 1.0) > BEATMATCH_MAX_SHIFT:
            logger.info("beatmatch skip: ratio %.4f outside ±%.0f%%", ratio, BEATMATCH_MAX_SHIFT * 100)
            return None
        return float(ratio)

    def _align_beat_phase(self, tr: Transition) -> float | None:
        """返回节拍对齐后的 to_at_sec，或 None 表示无法对齐。

        找到 A 下一拍，遍历 B beats 中落在预测位附近的拍，选第一个能
        给出非负且偏移 ≤0.25s 的结果。
        """
        if not self._plan:
            return None
        a_meta = self._plan.track_meta.get(str(tr.from_song_id))
        b_meta = self._plan.track_meta.get(str(tr.to_song_id))
        if not a_meta or not b_meta:
            return None
        a_beats = a_meta.get("beats")
        b_beats = b_meta.get("beats")
        if not a_beats or not b_beats:
            return None
        ratio = self._beatmatch_time_ratio(tr) or 1.0

        a_pos = self.active_deck.pos_sec
        a_next = None
        for b in a_beats:
            if b > a_pos + 0.01:
                a_next = b
                break
        if a_next is None:
            return None

        dt_a = a_next - a_pos
        b_predicted = tr.to_at_sec + dt_a * ratio

        # 找 B beats 中离预测位 ≤0.35s 的候选拍，按距离排序
        candidates = []
        for b in b_beats:
            d = abs(b - b_predicted)
            if d <= 0.35:
                candidates.append((d, b))
        candidates.sort()

        for _, b_target in candidates:
            to_start = b_target - dt_a * ratio
            if to_start < 0:
                continue
            shift = abs(to_start - tr.to_at_sec)
            if shift <= 0.25:
                return max(0.0, to_start)
        return None

    def _beatmatched_audio_path(self, tr: Transition, *, render: bool) -> Path | None:
        ratio = self._beatmatch_time_ratio(tr)
        if ratio is None:
            return None
        song_dir = _song_dir(tr.to_song_id)
        src = _find_original_path(song_dir)
        if src is None:
            return None
        tag = f"{ratio:.5f}".replace(".", "p")
        out = song_dir / f"original.rb.{tag}.wav"
        if out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
            return out
        if not render:
            return None

        rubberband = shutil.which("rubberband")
        if not rubberband:
            logger.warning("beatmatch skip: rubberband CLI not found")
            return None

        # 只渲染前 60 秒，大幅减少 rubberband 耗时（长曲从 80s → ~20s）
        trim_src = src
        trim_tmp = None
        try:
            info = sf.info(str(src))
            if info.duration > 65:
                trim_tmp = src.with_name(src.name.replace(".wav", ".trim60.wav"))
                if not trim_tmp.is_file() or trim_tmp.stat().st_mtime < src.stat().st_mtime:
                    ffmpeg = shutil.which("ffmpeg")
                    if ffmpeg:
                        subprocess.run(
                            [ffmpeg, "-y", "-t", "60", "-i", str(src),
                             "-c:a", "pcm_f32le", "-ar", str(info.samplerate), str(trim_tmp)],
                            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                        )
                if trim_tmp.is_file():
                    trim_src = trim_tmp
        except Exception:
            pass

        tmp = out.with_suffix(out.suffix + ".tmp")
        cmd = [rubberband, "--ignore-clipping", "-t", f"{ratio:.6f}", str(trim_src), str(tmp)]
        t0 = time.time()
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
            tmp.replace(out)
            if trim_tmp is not None:
                try:
                    trim_tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            logger.info(
                "beatmatch render ok: song_id=%s ratio=%.4f in %.0fms",
                tr.to_song_id,
                ratio,
                (time.time() - t0) * 1000,
            )
            AudioEngineMVP._cleanup_beatmatch_cache()
            return out
        except Exception as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            if trim_tmp is not None:
                try:
                    trim_tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            logger.warning("beatmatch render failed for %s: %s", tr.to_song_id, exc)
            return None

    def _begin_transition(self, tr: Transition) -> None:
        if self.inactive_deck.song_id != tr.to_song_id:
            try:
                want_stems = (tr.style or "smooth") in STEM_AWARE_STYLES
                audio_path = None if want_stems else self._beatmatched_audio_path(tr, render=False)
                self.inactive_deck.load(tr.to_song_id, tr.to_at_sec, load_stems=want_stems, audio_path=audio_path)
            except SongCacheError as exc:
                logger.error("transition load failed: %s", exc)
                return
            self._apply_loudness_gain(self.inactive_deck, tr.to_song_id)
        self._apply_beat_align(tr)
        self._start_transition_locked(tr)

    def _apply_beat_align(self, tr: Transition) -> None:
        """节拍对齐微调：找到 A 下一拍和 B 最近拍，微调 inactive deck 位置。"""
        aligned = self._align_beat_phase(tr)
        if aligned is None:
            return
        offset_frames = int((aligned - tr.to_at_sec) * SAMPLE_RATE)
        if offset_frames == 0:
            return
        deck = self.inactive_deck
        if deck.audio is None:
            return
        new_pos = deck.pos + offset_frames
        max_pos = max(0, len(deck.audio) - 1)
        if 0 <= new_pos <= max_pos:
            deck.pos = new_pos
            logger.info(
                "beatmatch phase align: song_id=%s offset=%.1fms",
                tr.to_song_id, offset_frames * 1000 / SAMPLE_RATE,
            )

    def _request_transition_preload(self, tr: Transition) -> None:
        key = str(tr.to_song_id)
        if self._preload_requested == key:
            return
        self._preload_requested = key
        inactive_eq = self.inactive_deck.eq_values()
        threading.Thread(
            target=self._do_transition_preload,
            args=(tr, inactive_eq),
            daemon=True,
            name=f"transition-preload-{key}",
        ).start()

    def _do_transition_preload(
        self,
        tr: Transition,
        inactive_eq: tuple[float, float, float],
    ) -> None:
        key = str(tr.to_song_id)
        try:
            t0 = time.time()
            deck = Deck()
            deck.set_eq(*inactive_eq)
            # Load stems if this is a stem-aware transition style
            want_stems = (tr.style or "smooth") in STEM_AWARE_STYLES
            audio_path = None if want_stems else self._beatmatched_audio_path(tr, render=False)
            deck.load(tr.to_song_id, tr.to_at_sec, load_stems=want_stems, audio_path=audio_path)
            self._apply_loudness_gain(deck, tr.to_song_id)
            with self._lock:
                current = self._scheduled_transition()
                if (
                    not self._plan_enabled
                    or self._in_transition
                    or current is None
                    or current.to_song_id != tr.to_song_id
                    or self.active_deck.song_id != tr.from_song_id
                ):
                    if self._preload_requested == key:
                        self._preload_requested = None
                    return
                self._install_inactive_deck(deck)
                self._next_preloaded = True
                self._preload_requested = None
            dt = (time.time() - t0) * 1000
            logger.info("preloaded song_id=%s for transition in %.0fms", tr.to_song_id, dt)
        except Exception as exc:
            logger.warning("preload failed for %s: %s", tr.to_song_id, exc)
            with self._lock:
                if self._preload_requested == key:
                    self._preload_requested = None

    def _maybe_preload_and_transition(self) -> None:
        if not self._plan_enabled or not self._plan or self._in_transition:
            return
        tr = self._scheduled_transition()
        if not tr or self.active_deck.song_id != tr.from_song_id:
            return
        pos_sec = self.active_deck.pos_sec
        if not self._next_preloaded and pos_sec >= tr.from_at_sec - PRELOAD_BEFORE_SEC:
            self._request_transition_preload(tr)
        if pos_sec >= tr.from_at_sec:
            if not self._next_preloaded:
                # 如果到了转场点但预加载未完成，等待最多 2 秒
                if pos_sec < tr.from_at_sec + 2.0:
                    self._request_transition_preload(tr)
                else:
                    # 超时，强制转场
                    self._begin_transition(tr)
            else:
                self._begin_transition(tr)

    @staticmethod
    def _fade_gains(progress: float, curve: str) -> tuple[float, float]:
        x = min(1.0, max(0.0, progress))
        if curve == "linear":
            return 1.0 - x, x
        return math.cos(x * math.pi / 2), math.sin(x * math.pi / 2)

    @staticmethod
    def _sin_ramp(progress: float, start: float, duration: float) -> float:
        t = min(1.0, max(0.0, (progress - start) / max(0.001, duration)))
        return math.sin(t * math.pi / 2)

    @staticmethod
    def _style_envelopes(
        style: str,
        progress: float,
        *,
        vocal_handoff_ratio: float = 0.45,
    ) -> tuple[dict, dict]:
        """返回两个 deck 的 stem 增益表，键名 ∈ vocals/drums/bass/other 或 'full'。

        实现 DJ / Spotify Mix 风格的纯 gain 包络：
        - smooth/power: 整轨等功率 cos/sin
        - bass_swap/filter/echo_out: 包络 + _apply_style_effects 里的 biquad/echo
        - cut: 0.05 比例点硬切
        - slam: 前段保留 A，短暂静默后 B 硬进（不依赖 stems）
        - fade/blend/rise/wave/melt: Spotify Mix 风格 preset 映射
        """
        x = min(1.0, max(0.0, progress))
        cos_x = math.cos(x * math.pi / 2)
        sin_x = math.sin(x * math.pi / 2)
        if style == "fade":
            return {"full": 1.0 - x}, {"full": x}
        if style == "blend":
            return {"full": cos_x}, {"full": sin_x}
        if style == "rise":
            return {"full": cos_x ** 1.15}, {"full": sin_x ** 0.75}
        if style == "wave":
            pulse = 0.92 + 0.08 * math.sin(2.0 * math.pi * x * 4.0)
            return {"full": cos_x * pulse}, {"full": sin_x * (2.0 - pulse)}
        if style == "melt":
            return {"full": cos_x ** 1.6}, {"full": sin_x ** 0.9}
        if style == "power":
            return {"full": cos_x ** 1.2}, {"full": sin_x ** 0.7}
        if style == "cut":
            return ({"full": 1.0 if x < 0.05 else 0.0},
                    {"full": 0.0 if x < 0.05 else 1.0})
        if style == "slam":
            if x < 0.68:
                return {"full": 1.0 - 0.25 * (x / 0.68)}, {"full": 0.0}
            if x < 0.78:
                return {"full": 0.0}, {"full": 0.0}
            return {"full": 0.0}, {"full": 1.0}
        if style == "echo_freeze":
            if x < 0.36:
                a_g = 1.0
            elif x < 0.58:
                a_g = math.cos((x - 0.36) / 0.22 * math.pi / 2)
            else:
                a_g = 0.0
            if x < 0.46:
                b_g = 0.0
            else:
                b_g = math.sin((x - 0.46) / 0.54 * math.pi / 2)
            return {"full": a_g}, {"full": b_g}
        if style == "bass_swap":
            # True stem-aware: swap bass stems between decks
            return (
                {"vocals": cos_x, "drums": cos_x, "bass": cos_x ** 4.0, "other": cos_x},
                {"vocals": sin_x, "drums": sin_x, "bass": sin_x ** 0.25, "other": sin_x},
            )
        if style == "drum_swap":
            # B drums enter softly, A drums fade normally
            return (
                {"vocals": cos_x, "drums": cos_x, "bass": cos_x, "other": cos_x},
                {"vocals": sin_x, "drums": sin_x ** 0.33, "bass": sin_x, "other": sin_x},
            )
        if style == "vocal_ducking":
            # Duck A vocals during transition, B vocals fade in gently
            return (
                {"vocals": cos_x ** 2.5, "drums": cos_x, "bass": cos_x, "other": cos_x},
                {"vocals": sin_x ** 0.5, "drums": sin_x, "bass": sin_x, "other": sin_x},
            )
        if style == "vocal_handoff":
            # Fixed vocal_handoff: smooth vocal crossfade + continuous instrumental bed
            #
            # Key improvements:
            # 1. A non-vocals fade out gradually across the FULL transition (not just 40%)
            # 2. B instrumental bed starts earlier and builds smoothly
            # 3. Vocal crossfade is tight (3% window) but happens over a continuous bed
            # 4. No energy holes or sudden silence
            #
            # Timeline:
            # - 0-18%: A full, B drums start fading in
            # - 18-45%: A fading, B instrumental building
            # - 45% (handoff): Vocal ownership changes (tight crossfade)
            # - 45-100%: A continues fading, B takes over

            xn = min(1.0, max(0.0, x))
            handoff = min(0.58, max(0.38, float(vocal_handoff_ratio)))
            cross = 0.03  # micro-crossfade window for vocals

            # ── A side ──
            # Non-vocals: slow fade across FULL transition (not just 40%)
            # Use cos curve for smooth energy decay
            a_nv = math.cos(xn * math.pi / 2)  # 0% -> 100%: 1.0 -> 0.0

            # Vocals: tight crossfade around handoff point
            av0 = handoff - cross / 2
            av1 = handoff + cross / 2
            if xn < av0:
                a_v = 1.0
            elif xn < av1:
                a_v = math.cos((xn - av0) / (av1 - av0) * math.pi / 2)
            else:
                a_v = 0.0

            # ── B side ──
            # Drums: start early, build smoothly
            b_d = AudioEngineMVP._sin_ramp(xn, 0.12, 0.30)  # Start at 12%, ramp over 30%

            # Bass: enter after drums are established
            b_b = AudioEngineMVP._sin_ramp(xn, 0.22, 0.28)  # Start at 22%, ramp over 28%

            # Other: texture bed, start early
            b_o = AudioEngineMVP._sin_ramp(xn, 0.15, 0.30)  # Start at 15%, ramp over 30%

            # Vocals: tight crossfade matching A vocal fade
            if xn < av0:
                b_v = 0.0
            elif xn < av1:
                b_v = math.sin((xn - av0) / (av1 - av0) * math.pi / 2)
            else:
                b_v = 1.0

            return (
                {"vocals": a_v,  "drums": a_nv, "bass": a_nv, "other": a_nv},
                {"vocals": b_v,  "drums": b_d,  "bass": b_b,  "other": b_o},
            )
        if style == "instrumental_only":
            # Keep the transition instrumental: both vocal stems muted during the
            # overlap, drums/bass/other do a clean equal-power handoff.
            return (
                {"vocals": 0.0, "drums": cos_x, "bass": cos_x ** 1.7, "other": cos_x},
                {"vocals": 0.0, "drums": sin_x, "bass": sin_x ** 0.7, "other": sin_x},
            )
        if style == "vocal_solo_intro":
            # A vocal rides over B instrumental bed; B vocal stays muted until
            # the transition finishes and normal deck playback takes over.
            if x < 0.72:
                a_v = 1.0
            else:
                a_v = math.cos((x - 0.72) / 0.28 * math.pi / 2)
            a_nv = math.cos(min(1.0, x / 0.35) * math.pi / 2)
            b_inst = math.sin(min(1.0, max(0.0, (x - 0.18) / 0.52)) * math.pi / 2)
            b_bass = math.sin(min(1.0, max(0.0, (x - 0.42) / 0.35)) * math.pi / 2)
            return (
                {"vocals": a_v, "drums": a_nv, "bass": a_nv, "other": a_nv},
                {"vocals": 0.0, "drums": b_inst, "bass": b_bass, "other": b_inst},
            )
        if style == "echo_out":
            return {"full": cos_x ** 1.5}, {"full": sin_x}
        if style == "filter":
            return {"full": cos_x}, {"full": sin_x}
        # default smooth
        return {"full": cos_x}, {"full": sin_x}

    def _read_deck_styled(self, deck: Deck, frames: int, gains: dict) -> np.ndarray:
        """按 stem gain 表从 deck 读一块。gains 同时出现 stem 键和 'full' 时，
        如果 deck 有完整 4 个 stem 则走分豁路径；否则退化到整轨增益。"""
        if deck.audio is None:
            return np.zeros((frames, 2), dtype=np.float32)
        pos = deck.pos
        # 全轨路径：只有 'full' 或 deck 没加载 stem
        if "full" in gains or not deck.stems:
            chunk, deck.pos = _read_segment(deck.audio, pos, frames)
            g = float(gains.get("full", max(gains.values()) if gains else 1.0))
            return chunk * (g * deck.gain)
        # 分 stem 路径
        out = np.zeros((frames, 2), dtype=np.float32)
        new_pos = pos
        any_read = False
        for name in REQUIRED_STEMS:
            g = float(gains.get(name, 0.0))
            if g == 0.0:
                continue
            buf = deck.stems.get(name)
            if buf is None:
                continue
            chunk, new_pos = _read_segment(buf, pos, frames)
            out += chunk * g
            any_read = True
        if not any_read:
            # 所需 stem 都不在，退化到全轨
            chunk, new_pos = _read_segment(deck.audio, pos, frames)
            out = chunk * float(max(gains.values()) if gains else 0.0)
        deck.pos = new_pos
        if deck.gain != 1.0:
            out *= deck.gain
        return out

    def set_deck_eq(self, deck_id: str, low_db: float = 0.0,
                    mid_db: float = 0.0, hi_db: float = 0.0) -> dict:
        """DJ 风 3-band EQ。deck_id ∈ {'a', 'b', 'active', 'inactive'}。
        每个 band 限幅 ±12 dB；返回实际被采纳的值。"""
        with self._lock:
            did = (deck_id or "").lower()
            if did == "a":
                deck = self.deck_a
            elif did == "b":
                deck = self.deck_b
            elif did == "active":
                deck = self.active_deck
            elif did == "inactive":
                deck = self.inactive_deck
            else:
                return {"ok": False, "error": "invalid_deck_id", "deck": deck_id}
            lo, mi, hi = deck.set_eq(low_db, mid_db, hi_db)
            return {
                "ok": True,
                "deck": "a" if deck is self.deck_a else "b",
                "low_db": lo,
                "mid_db": mi,
                "hi_db": hi,
            }

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
            if key in (1, 2, 3, 4, 5, 6):
                buf = self.samples.get(key)
                if buf is None:
                    return {"key": key, "error": "sample_missing"}
                self._one_shot_keys.append((key, [buf, 0]))
                return {"key": key, "action": "one_shot"}
            if key in (7, 8, 9):
                if not self.active_deck.stems:
                    return {"key": key, "error": "stems_not_loaded"}
                kinds = {7: "mute_vocals", 8: "solo_drums", 9: "lpf"}
                self.stem_fx = (kinds[key], time.time() + 2.0)
                if key == 9:
                    self._lpf_biquad.reset()
                    self._lpf_biquad.set_lpf(float(SAMPLE_RATE), 1000.0, q=0.707)
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
            self._stem_solo = None

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
            return self._lpf_biquad.process(main)
        return main

    def _read_with_solo(self, deck: Deck, frames: int) -> np.ndarray:
        """按当前 stem_solo 设置读取一个 deck 的音频。没有 solo 或 stem 缺失时走 deck.audio。"""
        if deck.audio is None:
            return np.zeros((frames, 2), dtype=np.float32)
        solo = self._stem_solo
        if solo and solo in deck.stems:
            buf = deck.stems[solo]
        else:
            buf = deck.audio
        chunk, deck.pos = _read_segment(buf, deck.pos, frames)
        if deck.gain != 1.0:
            chunk = chunk * deck.gain
        return chunk

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
                progress = self._fade_frames_done / max(1, self._fade_total_frames)
                style = self._resolve_style(tr.style or "smooth")
                if style in ("smooth", "blend"):
                    a = self._read_with_solo(self.active_deck, frames)
                    a = self.active_deck.apply_eq(a)
                    b = self._read_with_solo(self.inactive_deck, frames)
                    b = self.inactive_deck.apply_eq(b)
                    ga, gb = self._fade_gains(progress, tr.fade_curve)
                    main = a * ga + b * gb
                else:
                    handoff_ratio = self._transition_handoff_ratio(tr) if style == "vocal_handoff" else 0.45
                    sa, sb = self._style_envelopes(
                        style,
                        progress,
                        vocal_handoff_ratio=handoff_ratio,
                    )
                    a = self._read_deck_styled(self.active_deck, frames, sa)
                    a = self.active_deck.apply_eq(a)
                    b = self._read_deck_styled(self.inactive_deck, frames, sb)
                    b = self.inactive_deck.apply_eq(b)
                    a, b = self._apply_style_effects(style, progress, a, b, frames)
                    main = a + b
                self._fade_frames_done += frames
                if self._fade_frames_done >= self._fade_total_frames:
                    self._swap_decks()
            else:
                self._maybe_preload_and_transition()
                main = self._read_with_solo(self.active_deck, frames)
                main = self.active_deck.apply_eq(main)
                if self.active_deck.audio is not None and self.active_deck.pos >= len(self.active_deck.audio):
                    # 播放到结尾时，尝试强制转场而不是直接停止
                    tr = self._scheduled_transition()
                    if tr and self._plan_enabled and not self._in_transition:
                        # 强制开始转场，即使预加载未完成
                        try:
                            want_stems = (tr.style or "smooth") in STEM_AWARE_STYLES
                            self.inactive_deck.load(tr.to_song_id, tr.to_at_sec, load_stems=want_stems)
                            self._apply_loudness_gain(self.inactive_deck, tr.to_song_id)
                            self._start_transition_locked(tr)
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).warning("Force transition failed: %s", e)
                            self._playing = False
                            self._plan_enabled = False
                    else:
                        self._playing = False
                        self._plan_enabled = False

            deck_for_fx = self.active_deck
            main = self._apply_stem_fx(main, deck_for_fx, frames)
            main = main + self._mix_loops(frames) + self._mix_one_shots(frames)
            outdata[:] = self._apply_limiter(main, frames)

    def _apply_style_effects(self, style: str, progress: float,
                             a: np.ndarray, b: np.ndarray,
                             frames: int) -> tuple[np.ndarray, np.ndarray]:
        """在 stem-gain 之后、求和之前，按风格对 A / B 信号施加真滤波 / 延迟效果。

        - bass_swap: A 渐进 HPF (20→200Hz，在 50% 之后才接管低频屏蔽)
                     B 渐进 LPF (低频→宽带，前半段只放低频)
        - filter:    A LPF 18kHz → 200Hz；B LPF 200Hz → 18kHz（对称扫频）
        - echo_out:  A 信号送入 0.25s 反馈 echo（0.45 反馈, 0.7 wet）
        - rise:      A/B 做高通交接，形成上扬进入感
        - melt:      A echo + 下沉 LPF，B 从暗到亮打开
        其他风格保持原样（纯 stem gain 已经够）。
        """
        x = min(1.0, max(0.0, progress))
        sr = float(SAMPLE_RATE)

        if style == "bass_swap":
            # A: HPF cutoff sweeps 20 -> 220 Hz，截掉 A 的低频，让 B 的低频接管
            fc_a = 20.0 + 200.0 * x
            self._fx_filter_a.set_hpf(sr, fc_a, q=0.707)
            a = self._fx_filter_a.process(a)
            # B: LPF cutoff sweeps 160 -> 16000 Hz，B 一开始只是低频，后慢慢全频
            fc_b = 160.0 + (16000.0 - 160.0) * x
            self._fx_filter_b.set_lpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "filter":
            # A: LPF 18kHz -> 200Hz (log sweep 听感更线性)
            fc_a = 18000.0 * ((200.0 / 18000.0) ** x)
            self._fx_filter_a.set_lpf(sr, fc_a, q=0.707)
            a = self._fx_filter_a.process(a)
            # B: LPF 200Hz -> 18kHz
            fc_b = 200.0 * ((18000.0 / 200.0) ** x)
            self._fx_filter_b.set_lpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "rise":
            # A 越来越薄，B 从电话感逐渐打开成全频。
            fc_a = 30.0 + 1100.0 * x
            self._fx_filter_a.set_hpf(sr, fc_a, q=0.707)
            a = self._fx_filter_a.process(a)
            fc_b = 1200.0 * ((30.0 / 1200.0) ** x)
            self._fx_filter_b.set_hpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "melt":
            a = self._echo_process(a, frames)
            fc_a = 18000.0 * ((450.0 / 18000.0) ** x)
            self._fx_filter_a.set_lpf(sr, fc_a, q=0.707)
            a = self._fx_filter_a.process(a)
            fc_b = 650.0 * ((18000.0 / 650.0) ** x)
            self._fx_filter_b.set_lpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "echo_out":
            # A 信号 -> 反馈延迟（写入 buffer），随后从 buffer 读出叠加回主路
            # 由于 delay (11025) > frames (2048)，写入与读取区不重叠，可直接矢量化
            a = self._echo_process(a, frames)
            return a, b

        if style == "echo_freeze":
            # Short safety transition: freeze/echo A while B enters late. This
            # is useful for tense key, wide BPM, or unavoidable vocal overlap.
            a = self._echo_process(a, frames)
            fc_b = 900.0 * ((40.0 / 900.0) ** x)
            self._fx_filter_b.set_hpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "vocal_ducking":
            # A vocals already ducked by gain envelope; add light reverb tail via echo
            a = self._echo_process(a, frames)
            return a, b

        if style == "vocal_handoff":
            # Dry vocal handoff. A vocal gets no echo (echo smears sound like
            # stutter when delay is short). B opens with gentle HPF: 800→30Hz.
            fc_b = 800.0 * ((30.0 / 800.0) ** x)
            self._fx_filter_b.set_hpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "instrumental_only":
            # Clear a little low-end space on A while B takes the groove.
            fc_a = 30.0 + 180.0 * x
            self._fx_filter_a.set_hpf(sr, fc_a, q=0.707)
            a = self._fx_filter_a.process(a)
            return a, b

        if style == "vocal_solo_intro":
            # A vocal gets a small echo tail; B instrumental opens from thin to full.
            a = self._echo_process(a, frames)
            fc_b = 1000.0 * ((35.0 / 1000.0) ** x)
            self._fx_filter_b.set_hpf(sr, fc_b, q=0.707)
            b = self._fx_filter_b.process(b)
            return a, b

        if style == "drum_swap":
            # B drum soft entry already handled by gain envelope
            # Add slight HPF on A to clear rhythmic space
            fc_a = 60.0 + 180.0 * x
            self._fx_filter_a.set_hpf(sr, fc_a, q=0.707)
            a = self._fx_filter_a.process(a)
            return a, b

        return a, b

    def _echo_process(
        self,
        a: np.ndarray,
        frames: int,
        *,
        feedback: float | None = None,
        wet: float | None = None,
    ) -> np.ndarray:
        """对 A 信号做 0.25s 反馈延迟，wet 叠加回原信号。"""
        L = self._echo_buf_len
        delay = self._echo_delay_samples
        wp = self._echo_pos
        rp = (wp - delay) % L
        fb = self._echo_feedback if feedback is None else float(feedback)
        wet_gain = self._echo_wet if wet is None else float(wet)

        # 读取 delayed 信号（可能跨边界）
        if rp + frames <= L:
            delayed = self._echo_buf[rp : rp + frames].copy()
        else:
            first = L - rp
            delayed = np.concatenate(
                [self._echo_buf[rp:], self._echo_buf[: frames - first]],
                axis=0,
            )

        # 写入：当前 A + 反馈 * 历史延迟信号
        write_chunk = a + fb * delayed
        if wp + frames <= L:
            self._echo_buf[wp : wp + frames] = write_chunk
        else:
            first = L - wp
            self._echo_buf[wp:] = write_chunk[:first]
            self._echo_buf[: frames - first] = write_chunk[first:]

        self._echo_pos = (wp + frames) % L
        return a + wet_gain * delayed

    def _apply_limiter(self, main: np.ndarray, frames: int) -> np.ndarray:
        """块级 look-ahead 峰值限制器。
        - 测当前块峰值 → 目标增益 = threshold / peak（clip 到 ≤1）
        - target < prev_gain：立即 attack（gain 直接落到 target）
        - target >= prev_gain：按 release_coef 慢慢回到 1.0
        - 块首前 64 个样本对 prev_gain → 新 gain 做线性 ramp，避免阶跃 click
        """
        peak = float(np.max(np.abs(main))) if main.size else 0.0
        if peak > self._lim_threshold:
            target = self._lim_threshold / peak
        else:
            target = 1.0
        prev = self._lim_gain
        if target < prev:
            new_gain = target  # 立即压下
        else:
            # 释放：朝 target（通常是 1.0）平滑靠拢
            new_gain = target + (prev - target) * self._lim_release_coef
        # 块内 ramp
        ramp_len = min(64, frames)
        if ramp_len > 0 and abs(new_gain - prev) > 1e-6:
            ramp = np.linspace(prev, new_gain, ramp_len, dtype=np.float32)
            main[:ramp_len] *= ramp[:, None]
            if frames > ramp_len:
                main[ramp_len:] *= new_gain
        else:
            main *= new_gain
        self._lim_gain = new_gain
        # 兜底硬限幅
        np.clip(main, -1.0, 1.0, out=main)
        return main

    def shutdown(self) -> None:
        with self._lock:
            self.stop()
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.abort()
                stream.close()
            except Exception:
                pass


engine = AudioEngineMVP()
