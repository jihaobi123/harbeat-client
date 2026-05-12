"""Online DJ controller — the brain of real-time continuous mix playback.

State machine:
    IDLE → PREPARING → PLAYING ↔ MANUAL ↔ TRANSITIONING ↔ FADE_RESCUE

The controller coordinates DeckManager (A/B alternation), RenderScheduler
(background pre-render), and ReadyChecker (safety fallback).  Its main loop
runs in a background thread and fills a ring-buffer consumed by the audio
callback, guaranteeing glitch-free output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
import threading
import time
from typing import Any

import numpy as np

from core.datatypes import (
    AutomationLane,
    AutomationPoint,
    MixCommand,
    TrackMetadata,
    TransitionPlan,
    TransitionWindowScore,
)
from core.enums import DeckState, FXType, TransitionType
from engine.deck_manager import DeckManager, DeckSlot, LiveDeck
from engine.ready_checker import FallbackReason, ReadyChecker
from engine.render_scheduler import RenderJob, RenderJobState, RenderScheduler


# ══════════════════════════════════════════════════════════════════════
# Ring buffer
# ══════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class _RingBuffer:
    capacity_frames: int
    channels: int
    buffer: np.ndarray = field(init=False)
    write_index: int = field(default=0, init=False)
    read_index: int = field(default=0, init=False)
    available_frames: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.buffer = np.zeros((self.capacity_frames, self.channels), dtype=np.float32)

    def write(self, frames: np.ndarray) -> None:
        for frame in frames:
            self.buffer[self.write_index] = frame
            self.write_index = (self.write_index + 1) % self.capacity_frames
            if self.available_frames < self.capacity_frames:
                self.available_frames += 1
            else:
                self.read_index = (self.read_index + 1) % self.capacity_frames

    def read(self, frame_count: int) -> np.ndarray:
        output = np.zeros((frame_count, self.channels), dtype=np.float32)
        to_read = min(frame_count, self.available_frames)
        for i in range(to_read):
            output[i] = self.buffer[self.read_index]
            self.read_index = (self.read_index + 1) % self.capacity_frames
        self.available_frames -= to_read
        return output

    def clear(self) -> None:
        self.write_index = 0
        self.read_index = 0
        self.available_frames = 0


# ══════════════════════════════════════════════════════════════════════
# Playback mode
# ══════════════════════════════════════════════════════════════════════

class PlaybackMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    FADE_RESCUE = "fade_rescue"


# ══════════════════════════════════════════════════════════════════════
# Transition state
# ══════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class _CrossfadeState:
    active: bool = False
    start_frame: int = 0
    total_frames: int = 0
    gain_a: float = 1.0
    gain_b: float = 0.0
    strategy: TransitionType = TransitionType.CUT_SWAP
    automation: list[AutomationLane] = field(default_factory=list)
    fade_reason: FallbackReason = FallbackReason.NONE


# ══════════════════════════════════════════════════════════════════════
# Controller
# ══════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class OnlineDJController:
    """Real-time dual-deck DJ controller with pre-render pipeline.

    Usage::

        ctrl = OnlineDJController(sample_rate=44100, block_size=1024)
        ctrl.load_playlist(track_metadata_list)
        ctrl.start()
        ctrl.press_manual(strategy)  # immediate transition with chosen strategy
        ctrl.press_pause()
        ctrl.stop()
    """

    sample_rate: int = 44100
    block_size: int = 1024

    _decks: DeckManager = field(default_factory=DeckManager)
    _scheduler: RenderScheduler = field(default_factory=RenderScheduler)
    _checker: ReadyChecker = field(default_factory=ReadyChecker)
    _output: _RingBuffer = field(init=False)
    _crossfade: _CrossfadeState = field(default_factory=_CrossfadeState)

    _playlist: list[TrackMetadata] = field(default_factory=list)
    _current_index: int = 0
    _next_index: int = 1

    mode: PlaybackMode = PlaybackMode.AUTO
    paused: bool = True
    _running: bool = False
    _render_thread: threading.Thread | None = field(default=None, init=False)

    # Manual trigger request from the UI (set by press_manual, consumed by render loop)
    _manual_pending: bool = False
    _manual_strategy: TransitionType | None = None

    _stream: Any = None

    # User-facing info about the most recent transition decision
    last_transition_strategy: str = ""
    last_fade_reason: str = ""

    def __post_init__(self) -> None:
        self._output = _RingBuffer(
            capacity_frames=self.sample_rate * 8, channels=2,
        )
        self._decks = DeckManager(sample_rate=self.sample_rate, block_size=self.block_size)
        self._scheduler = RenderScheduler(sample_rate=self.sample_rate, lookahead_count=2)
        self._checker = ReadyChecker()

    # ── public API ──────────────────────────────────────────────────

    def load_playlist(self, tracks: list[TrackMetadata]) -> None:
        if len(tracks) < 1:
            raise ValueError("Need at least one track")
        self._playlist = list(tracks)
        self._current_index = 0
        self._next_index = min(1, len(tracks) - 1)

    def start(self, blocking: bool = False) -> None:
        if self._running:
            return
        if not self._playlist:
            raise RuntimeError("No playlist loaded")

        self._running = True
        self.paused = False

        self._decks.deck_a.load(self._playlist[0])
        self._decks.deck_a.play()

        if len(self._playlist) > 1:
            self._decks.deck_b.load(self._playlist[1])
            self._decks.deck_b.stop()

        self._enqueue_pre_renders()
        self._scheduler.start()

        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()

        import sounddevice as sd
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=2,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

        if blocking:
            while self._running:
                time.sleep(0.1)

    def stop(self) -> None:
        self._running = False
        self._scheduler.stop()
        if self._render_thread and self._render_thread.is_alive():
            self._render_thread.join(timeout=2.0)
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def press_manual(self, strategy: TransitionType | None = None) -> None:
        """User pressed MANUAL — trigger an immediate transition to the next track.

        If *strategy* is None the best auto-scored strategy is used.
        This is the primary manual cut button.
        """
        self.mode = PlaybackMode.MANUAL
        self._manual_pending = True
        self._manual_strategy = strategy
        self._checker.record_manual_switch()

    def press_pause(self) -> None:
        self.paused = True
        self._decks.pause_both()

    def press_resume(self) -> None:
        self.paused = False
        self._decks.play_both()

    @property
    def current_track(self) -> TrackMetadata | None:
        if 0 <= self._current_index < len(self._playlist):
            return self._playlist[self._current_index]
        return None

    @property
    def next_track(self) -> TrackMetadata | None:
        if 0 <= self._next_index < len(self._playlist):
            return self._playlist[self._next_index]
        return None

    def status_snapshot(self) -> dict:
        active = self._decks.active_deck
        idle = self._decks.idle_deck
        fade_reason = self._crossfade.fade_reason.value if self._crossfade.active else "none"
        return {
            "mode": self.mode.value,
            "paused": self.paused,
            "current_track_index": self._current_index,
            "active_deck": self._decks._active.value,
            "active_track": active.metadata.title if active.metadata else None,
            "active_playhead_seconds": active.status.playhead_seconds,
            "active_playhead_beats": active.status.playhead_beats,
            "active_seconds_remaining": active.seconds_remaining,
            "idle_deck": self._decks._idle.value,
            "idle_track": idle.metadata.title if idle.metadata else None,
            "idle_loaded": idle.loaded,
            "crossfade_active": self._crossfade.active,
            "crossfade_strategy": self._crossfade.strategy.value if self._crossfade.active else None,
            "fade_reason": fade_reason,
            "manual_override_strategy": self._manual_strategy.value if self._manual_strategy else None,
            "manual_pending": self._manual_pending,
            "fallback_risk": self._checker.rapid_switch_count >= self._checker.rapid_switch_threshold,
            "last_transition_strategy": self.last_transition_strategy,
            "last_fade_reason": self.last_fade_reason,
        }

    # ── internal logic ──────────────────────────────────────────────

    def _audio_callback(self, outdata: np.ndarray, frames: int, _time_info: object, _status: object) -> None:
        outdata[:] = self._output.read(frames)

    def _render_loop(self) -> None:
        """Main loop: read deck blocks, apply crossfade, feed output buffer.

        Two triggers start a transition:
        1. AUTO: active deck has < 2 seconds of audio remaining
        2. MANUAL: user pressed the MANUAL button (self._manual_pending)
        """
        auto_detect_frames = int(self.sample_rate * 2.0)

        while self._running:
            if self.paused:
                time.sleep(0.05)
                continue

            block_a, block_b = self._decks.read_frames(self.block_size)
            mixed = self._mix_blocks(block_a, block_b)
            self._output.write(mixed)

            # Trigger check (only if not already crossfading)
            if not self._crossfade.active:
                should_transition = False

                # Manual trigger takes priority
                if self._manual_pending:
                    should_transition = True
                # Auto trigger when deck nears end
                elif self._decks.active_deck.frames_remaining < auto_detect_frames:
                    should_transition = True

                if should_transition:
                    self._begin_transition()

            # Advance crossfade
            if self._crossfade.active:
                self._crossfade.start_frame += self.block_size
                if self._crossfade.start_frame >= self._crossfade.total_frames:
                    self._finish_transition()

            # Prevent runaway buffer
            if self._output.available_frames > self.block_size * 6:
                time.sleep(self.block_size / self.sample_rate / 2)

    def _mix_blocks(self, block_a: np.ndarray, block_b: np.ndarray) -> np.ndarray:
        cs = self._crossfade
        if not cs.active:
            return block_a

        progress = min(cs.start_frame / max(cs.total_frames, 1), 1.0)
        gain_a = self._interp_volume("A", progress)
        gain_b = self._interp_volume("B", progress)
        return (block_a * gain_a + block_b * gain_b).astype(np.float32, copy=False)

    def _interp_volume(self, deck: str, progress: float) -> float:
        """Read volume from automation lanes, falling back to linear crossfade."""
        if not self._crossfade.automation:
            return (1.0 - progress) if deck == "A" else progress

        for lane in self._crossfade.automation:
            for pt in lane.points:
                if pt.deck == deck and pt.fx_type == FXType.VOLUME:
                    pts = sorted(lane.points, key=lambda p: p.beat_offset)
                    vols = [p.value for p in pts if p.deck == deck]
                    offsets = [p.beat_offset / max(pts[-1].beat_offset, 1) for p in pts if p.deck == deck]
                    if vols and offsets:
                        return float(np.interp(progress, offsets, vols))

        return (1.0 - progress) if deck == "A" else progress

    def _begin_transition(self) -> None:
        """Start crossfade from active deck to idle deck.

        Strategy resolution order:
        1. Manual trigger with explicit strategy → use that
        2. Manual trigger without strategy → auto-score best
        3. Auto trigger → auto-score best

        If pre-rendered audio is not ready or buffer is low → FADE_RESCUE
        """
        idle = self._decks.idle_deck
        if not idle.loaded:
            self._manual_pending = False
            return

        # ── Resolve strategy ───────────────────────────────────
        if self._manual_pending and self._manual_strategy is not None:
            strategy = self._manual_strategy
            was_manual = True
        else:
            strategy = self._determine_auto_strategy()
            was_manual = self._manual_pending

        # ── Check readiness ────────────────────────────────────
        render_ready = self._is_transition_ready(strategy)
        buffer_ok = self._output.available_frames > self.block_size * 2

        can_use, fallback_reason, _ = self._checker.check(
            render_ready=render_ready,
            buffer_healthy=buffer_ok,
            deck_has_audio=idle.loaded,
        )

        if not can_use:
            strategy = TransitionType.CUT_SWAP
            self.mode = PlaybackMode.FADE_RESCUE
        elif was_manual:
            self.mode = PlaybackMode.MANUAL
        else:
            self.mode = PlaybackMode.AUTO

        # ── Compute crossfade params ────────────────────────────
        overlap_beats = 4.0 if not can_use else 8.0
        total_frames = self._beats_to_frames(overlap_beats)

        cs = self._crossfade
        cs.active = True
        cs.start_frame = 0
        cs.total_frames = max(total_frames, self.sample_rate // 4)
        cs.gain_a = 1.0
        cs.gain_b = 0.0
        cs.strategy = strategy
        cs.fade_reason = fallback_reason

        if not can_use:
            cs.automation = self._checker.build_fade_automation(overlap_beats)
        else:
            cs.automation = []  # linear crossfade

        self.last_transition_strategy = strategy.value
        self.last_fade_reason = fallback_reason.value

        idle.play()
        self._decks.active_deck.play()  # ensure active keeps going
        self._manual_pending = False
        self._manual_strategy = None

    def _finish_transition(self) -> None:
        """Complete handoff: stop old deck, swap roles, load next track."""
        self._decks.active_deck.stop()

        self._decks.swap()
        self._crossfade.active = False
        self._crossfade.gain_a = 1.0
        self._crossfade.gain_b = 0.0

        self._current_index = self._next_index
        self._next_index = min(self._next_index + 1, len(self._playlist) - 1)

        if self._next_index < len(self._playlist) and self._next_index != self._current_index:
            self._decks.load_idle(self._playlist[self._next_index])

        self._enqueue_pre_renders()
        self._manual_strategy = None
        self._manual_pending = False
        self.mode = PlaybackMode.AUTO

    def _determine_auto_strategy(self) -> TransitionType:
        from logic.brain import TransitionPlanner
        planner = TransitionPlanner()
        a = self._playlist[self._current_index]
        b = self._playlist[self._next_index]
        best = planner.top_candidates(a, b, limit=1)
        return best[0].strategy if best else TransitionType.CUT_SWAP

    def _is_transition_ready(self, strategy: TransitionType) -> bool:
        a_id = self._playlist[self._current_index].track_id
        b_id = self._playlist[self._next_index].track_id
        job = self._scheduler.dequeue_ready(a_id, b_id, strategy=strategy)
        return job is not None

    def _enqueue_pre_renders(self) -> None:
        from logic.brain import TransitionPlanner
        planner = TransitionPlanner()

        for i in range(self._current_index, min(len(self._playlist) - 1, self._current_index + 3)):
            a = self._playlist[i]
            b = self._playlist[i + 1]
            candidates = planner.top_candidates(a, b, limit=3)
            for cand in candidates[:2]:
                job = RenderJob(
                    track_a_id=a.track_id,
                    track_b_id=b.track_id,
                    strategy=cand.strategy,
                    score_breakdown=cand,
                )
                self._scheduler.enqueue(job)

    def _beats_to_frames(self, beats: float) -> int:
        bpm = 120.0
        if 0 <= self._current_index < len(self._playlist):
            bpm = self._playlist[self._current_index].beatgrid.bpm
        beats_per_second = bpm / 60.0
        return int(beats / max(beats_per_second, 0.5) * self.sample_rate)
