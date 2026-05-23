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
from dsp import Biquad
from mix_plan import NormalizedPlan, Transition, normalize_mix_plan

logger = logging.getLogger(__name__)

SAMPLES_DIR = CYPHER_HOME / "samples"
REQUIRED_STEMS = ("vocals", "drums", "bass", "other")

# Prefetch 缓存：App/edge-agent 可提前调 engine.prefetch(song_id) 把 wav+stems 预解码进
# 这里；Deck.load() 用到该 song_id 时直接 pop 出 numpy 数组，避免按键时才走磁
# 盘 IO（50-200ms 锁顿）。这是复刻 Spotify Mix 「按键即响」响应的关键：predecoded PCM。
_PREFETCH_CACHE: dict[str, dict] = {}
_PREFETCH_LOCK = threading.Lock()
_PREFETCH_MAX = 4  # 最多同时备 4 首
# 5 个常见 DJ 加花音效（2026-05 更新）。文件需预先放在 ~/cypher/samples/ 下。
# 名字使用加花上下文词，后续替换素材只需覆盖同名 wav。
SAMPLE_FILES = {
    1: "scratch.wav",   # 揓碟
    2: "air_horn.wav",  # 气笛 / 喜剧喜剧喜
    3: "spinback.wav", # 倒带
    4: "siren.wav",    # 警报
    5: "whoosh.wav",   # 嘏 / riser
}
# 叠到主轨上的增益
SAMPLE_GAIN = {1: 1.2, 2: 1.8, 3: 1.4, 4: 1.6, 5: 1.4}
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
    __slots__ = ("audio", "pos", "song_id", "stems", "gain")

    def __init__(self) -> None:
        self.audio: np.ndarray | None = None
        self.pos = 0
        self.song_id: int | str | None = None
        self.stems: dict[str, np.ndarray] = {}
        # 响度归一线性增益（10^(dB/20)）。默认 1.0 = 不改。
        self.gain: float = 1.0

    @property
    def pos_sec(self) -> float:
        return self.pos / SAMPLE_RATE if self.audio is not None else 0.0

    def clear(self) -> None:
        self.audio = None
        self.pos = 0
        self.song_id = None
        self.stems = {}
        self.gain = 1.0

    def set_gain_db(self, db: float | None) -> None:
        if db is None:
            self.gain = 1.0
            return
        # 限幅 ±8dB
        db = max(-8.0, min(8.0, float(db)))
        self.gain = float(10.0 ** (db / 20.0))

    def load(self, song_id: int | str, start_at_sec: float = 0.0) -> float:
        key = str(song_id)
        cached: dict | None = None
        with _PREFETCH_LOCK:
            if key in _PREFETCH_CACHE:
                cached = _PREFETCH_CACHE.pop(key)
        if cached is not None:
            self.audio = cached["audio"]
            self.stems = cached["stems"]
            logger.info("deck.load hit prefetch cache: %s (remain=%d)", song_id, len(_PREFETCH_CACHE))
        else:
            path = check_song_cache(song_id, require_stems=REQUIRE_STEMS_FOR_PLAY)
            self.audio = _load_wav_stereo(path)
            self.stems = {}
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
        self._lpf_state = np.zeros(2, dtype=np.float32)
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
            self._apply_loudness_gain(self.deck_a, song_id)
            self._playing = True
            self._paused = False
            self._in_transition = False
            self._transition_index = 0
            self._next_preloaded = False
            self._one_shot_keys.clear()
            self.stem_fx = None
            # /play 是“硬切”，重置持久 stem_solo 避免上一首的供菜多到下一首。
            self._stem_solo = None
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
            self._begin_transition(tr)
        return {
            "action": "crossfade",
            "to_song_id": to_song_id,
            "fade_sec": tr.fade_sec,
            "to_at_sec": tr.to_at_sec,
            "style": tr.style,
        }

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

    def _begin_transition(self, tr: Transition) -> None:
        try:
            self.inactive_deck.load(tr.to_song_id, tr.to_at_sec)
        except SongCacheError as exc:
            logger.error("transition load failed: %s", exc)
            return
        self._apply_loudness_gain(self.inactive_deck, tr.to_song_id)
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
                self._apply_loudness_gain(self.inactive_deck, tr.to_song_id)
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

    @staticmethod
    def _style_envelopes(style: str, progress: float) -> tuple[dict, dict]:
        """返回两个 deck 的 stem 增益表，键名 ∈ vocals/drums/bass/other 或 'full'。

        实现 7 种 DJ 风格的纯 gain 近似（不用实时 biquad/reverb）：
        - smooth/power: 整轨等功率 cos/sin
        - bass_swap: bass 在 50% 点互换，其他 stem 等功率
        - echo_out: A 各 stem 快深幢府（vocals 略留以价 echo 残响），B 正常
        - filter: 以 stem 粗粒度近似低频扫频（A 先去 bass、后去 drums，B 反向）
        - cut: 0.05 比例点硬切
        - slam: 前 70% 卸 vocals 留 drums〃0.7-0.8 静默。后段 B 全开
        """
        x = min(1.0, max(0.0, progress))
        cos_x = math.cos(x * math.pi / 2)
        sin_x = math.sin(x * math.pi / 2)
        if style == "power":
            return {"full": cos_x ** 1.2}, {"full": sin_x ** 0.7}
        if style == "cut":
            return ({"full": 1.0 if x < 0.05 else 0.0},
                    {"full": 0.0 if x < 0.05 else 1.0})
        if style == "slam":
            if x < 0.7:
                t = x / 0.7
                return ({"vocals": 1.0 - t, "other": 1.0 - t * 0.5,
                         "drums": 1.0, "bass": 1.0 - t * 0.3},
                        {"full": 0.0})
            if x < 0.8:
                return {"full": 0.0}, {"full": 0.0}
            return {"full": 0.0}, {"full": 1.0}
        if style == "bass_swap":
            if x < 0.5:
                return ({"vocals": cos_x, "drums": cos_x,
                         "bass": 1.0 - x * 2, "other": cos_x},
                        {"vocals": sin_x, "drums": sin_x,
                         "bass": 0.0, "other": sin_x})
            return ({"vocals": cos_x, "drums": cos_x,
                     "bass": 0.0, "other": cos_x},
                    {"vocals": sin_x, "drums": sin_x,
                     "bass": (x - 0.5) * 2, "other": sin_x})
        if style == "echo_out":
            return ({"vocals": cos_x ** 1.5,
                     "drums": cos_x ** 3,
                     "bass": cos_x ** 3,
                     "other": cos_x ** 2},
                    {"full": sin_x})
        if style == "filter":
            return ({"vocals": cos_x ** 0.7,
                     "drums": cos_x ** 2,
                     "bass": cos_x ** 3,
                     "other": cos_x ** 1.2},
                    {"vocals": sin_x ** 1.5,
                     "drums": sin_x ** 0.8,
                     "bass": sin_x ** 0.6,
                     "other": sin_x})
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
            out = np.empty_like(main)
            for i in range(frames):
                self._lpf_state = self._lpf_state + 0.15 * (main[i] - self._lpf_state)
                out[i] = self._lpf_state
            return out
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
                style = tr.style or "smooth"
                if style not in ("smooth", "power") and (
                    not self.active_deck.stems or not self.inactive_deck.stems
                ):
                    style = "smooth"  # 缺 stem 时退化
                if style == "smooth":
                    a = self._read_with_solo(self.active_deck, frames)
                    b = self._read_with_solo(self.inactive_deck, frames)
                    ga, gb = self._fade_gains(progress, tr.fade_curve)
                    main = a * ga + b * gb
                else:
                    sa, sb = self._style_envelopes(style, progress)
                    a = self._read_deck_styled(self.active_deck, frames, sa)
                    b = self._read_deck_styled(self.inactive_deck, frames, sb)
                    a, b = self._apply_style_effects(style, progress, a, b, frames)
                    main = a + b
                self._fade_frames_done += frames
                if self._fade_frames_done >= self._fade_total_frames:
                    self._swap_decks()
            else:
                self._maybe_preload_and_transition()
                main = self._read_with_solo(self.active_deck, frames)
                if self.active_deck.audio is not None and self.active_deck.pos >= len(self.active_deck.audio):
                    self._playing = False

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

        if style == "echo_out":
            # A 信号 -> 反馈延迟（写入 buffer），随后从 buffer 读出叠加回主路
            # 由于 delay (11025) > frames (2048)，写入与读取区不重叠，可直接矢量化
            a = self._echo_process(a, frames)
            return a, b

        return a, b

    def _echo_process(self, a: np.ndarray, frames: int) -> np.ndarray:
        """对 A 信号做 0.25s 反馈延迟，wet 叠加回原信号。"""
        L = self._echo_buf_len
        delay = self._echo_delay_samples
        wp = self._echo_pos
        rp = (wp - delay) % L

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
        write_chunk = a + self._echo_feedback * delayed
        if wp + frames <= L:
            self._echo_buf[wp : wp + frames] = write_chunk
        else:
            first = L - wp
            self._echo_buf[wp:] = write_chunk[:first]
            self._echo_buf[: frames - first] = write_chunk[first:]

        self._echo_pos = (wp + frames) % L
        return a + self._echo_wet * delayed

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
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None


engine = AudioEngineMVP()
