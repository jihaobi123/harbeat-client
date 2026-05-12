"""Background scheduler that pre-renders upcoming transitions so they are ready
before the playhead reaches the handoff point."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from typing import Any, Callable

import numpy as np

from core.datatypes import TrackMetadata, TransitionPlan, TransitionWindowScore
from core.enums import TransitionType
from logic.strategies import STRATEGY_REGISTRY


class RenderJobState(str, Enum):
    QUEUED = "queued"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"


@dataclass(slots=True)
class RenderJob:
    """A single pre-render job for one transition."""

    track_a_id: str
    track_b_id: str
    strategy: TransitionType
    score_breakdown: TransitionWindowScore | None = None

    state: RenderJobState = RenderJobState.QUEUED
    result_audio: np.ndarray | None = None
    plan: TransitionPlan | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None

    @property
    def ready(self) -> bool:
        return self.state == RenderJobState.READY and self.result_audio is not None


@dataclass(slots=True)
class RenderScheduler:
    """Manages a background thread that renders upcoming transitions.

    The scheduler keeps N transitions pre-rendered ahead of the current playback
    position so the engine never has to wait for a render.
    """

    lookahead_count: int = 2
    sample_rate: int = 44100

    _pending: list[RenderJob] = field(default_factory=list)
    _thread: threading.Thread | None = field(default=None, init=False)
    _running: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # Callback: given track_id, return TrackMetadata.  Set by the controller.
    metadata_lookup: Callable[[str], TrackMetadata] | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._render_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def enqueue(self, job: RenderJob) -> None:
        with self._lock:
            existing = [j for j in self._pending
                        if j.track_a_id == job.track_a_id
                        and j.track_b_id == job.track_b_id
                        and j.strategy == job.strategy]
            if existing:
                return
            self._pending.append(job)

    def dequeue_ready(self, track_a_id: str, track_b_id: str,
                      strategy: TransitionType | None = None) -> RenderJob | None:
        with self._lock:
            for job in self._pending:
                if (job.track_a_id == track_a_id and job.track_b_id == track_b_id
                        and job.ready):
                    if strategy is None or job.strategy == strategy:
                        self._pending.remove(job)
                        return job
        return None

    def cancel_for_track(self, track_a_id: str) -> None:
        with self._lock:
            self._pending = [j for j in self._pending
                             if j.track_a_id != track_a_id
                             and j.state != RenderJobState.RENDERING]

    def _render_loop(self) -> None:
        from audio.offline_renderer import OfflineDualDeckRenderer
        renderer = OfflineDualDeckRenderer(sample_rate=self.sample_rate)

        while self._running:
            job: RenderJob | None = None
            with self._lock:
                for j in self._pending:
                    if j.state == RenderJobState.QUEUED:
                        j.state = RenderJobState.RENDERING
                        job = j
                        break

            if job is None:
                time.sleep(0.1)
                continue

            try:
                self._execute_render(renderer, job)
            except Exception as exc:
                with self._lock:
                    job.state = RenderJobState.FAILED
                    job.error = str(exc)

    def _execute_render(self, renderer: Any, job: RenderJob) -> None:
        if self.metadata_lookup is None:
            raise RuntimeError("RenderScheduler.metadata_lookup not set")

        md_a = self.metadata_lookup(job.track_a_id)
        md_b = self.metadata_lookup(job.track_b_id)

        if job.score_breakdown is not None:
            plan = TransitionPlan(
                mix_start_time=0.0,
                overlap_duration_beats=job.score_breakdown.overlap_beats,
                target_bpm=job.score_breakdown.target_bpm,
                phase_offset_beats=job.score_breakdown.phase_offset_beats,
                alignment_confidence=job.score_breakdown.alignment_confidence,
                handoff_profile=job.score_breakdown.handoff_profile,
                strategy=job.strategy,
                track_a_exit_bar=job.score_breakdown.track_a_exit_bar,
                track_b_entry_bar=job.score_breakdown.track_b_entry_bar,
                automation=[],
                score_breakdown=job.score_breakdown,
            )
            plan.automation = STRATEGY_REGISTRY[job.strategy].build_automation(plan)
        else:
            from logic.brain import TransitionPlanner
            planner = TransitionPlanner()
            candidates = planner.top_candidates(md_a, md_b, limit=5)
            match = next((c for c in candidates if c.strategy == job.strategy), None)
            if match is None:
                match = candidates[0]
            plan = TransitionPlan(
                mix_start_time=0.0,
                overlap_duration_beats=match.overlap_beats,
                target_bpm=match.target_bpm,
                phase_offset_beats=match.phase_offset_beats,
                alignment_confidence=match.alignment_confidence,
                handoff_profile=match.handoff_profile,
                strategy=match.strategy,
                track_a_exit_bar=match.track_a_exit_bar,
                track_b_entry_bar=match.track_b_entry_bar,
                automation=[],
                score_breakdown=match,
            )
            plan.automation = STRATEGY_REGISTRY[match.strategy].build_automation(plan)

        import soundfile as sf
        audio_a, _ = sf.read(md_a.path, always_2d=True, dtype="float32")
        audio_b, _ = sf.read(md_b.path, always_2d=True, dtype="float32")

        result = renderer.render_transition(
            audio_a, md_a, md_a.title, plan, audio_b, md_b, md_b.title
        )

        with self._lock:
            job.result_audio = result.audio
            job.plan = plan
            job.state = RenderJobState.READY
            job.completed_at = time.monotonic()
