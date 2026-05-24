"""Strategy selector — wraps stem_automix scoring for RK3588 edge agent.

Decides:
  - Which TransitionPreset to use for a track pair
  - Whether to use stem-aware or non-stem mode
  - Which playback_tier the transition supports

All scoring logic is delegated to app.modules.playlists.stem_automix.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import PlaybackTier

logger = logging.getLogger(__name__)


@dataclass
class SelectionResult:
    preset: str
    mode: str           # "non_stem" | "stem_aware"
    confidence: float
    tier: str           # PlaybackTier value
    scores: dict[str, float] = field(default_factory=dict)
    plan: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


class StrategySelector:
    """Selects the best transition strategy for a track pair.

    Uses the full scoring/decision engine from stem_automix.
    Falls back gracefully when stem_automix is unavailable (minimal RK3588 image).
    """

    def __init__(self):
        self._available = False
        try:
            from app.modules.playlists.stem_automix import (
                TrackContext,
                TransitionPreset,
                TransitionMode,
                build_automix_transition,
                score_transition_candidates,
                select_best_preset,
            )
            self._TrackContext = TrackContext
            self._TransitionPreset = TransitionPreset
            self._TransitionMode = TransitionMode
            self._build_automix_transition = build_automix_transition
            self._score_transition_candidates = score_transition_candidates
            self._select_best_preset = select_best_preset
            self._available = True
            logger.info("strategy_selector: stem_automix engine loaded")
        except ImportError:
            logger.warning("strategy_selector: stem_automix unavailable — using basic fallback")

    def select(
        self,
        from_track: dict[str, Any],
        to_track: dict[str, Any],
        duration_bars: int = 8,
        force_preset: str | None = None,
    ) -> SelectionResult:
        """Select the best transition preset for a track pair.

        Args:
            from_track: Track A metadata dict (from manifest.analysis).
            to_track: Track B metadata dict.
            duration_bars: Transition length in bars.
            force_preset: Override auto-selection with a specific preset name.

        Returns:
            SelectionResult with preset, mode, confidence, tier, and plan.
        """
        if not self._available:
            return self._basic_fallback(from_track, to_track, duration_bars)

        # Build TrackContext from manifest analysis dicts
        ctx_a = self._ctx_from_manifest(from_track)
        ctx_b = self._ctx_from_manifest(to_track)

        try:
            scores = self._score_transition_candidates(ctx_a, ctx_b)

            if force_preset:
                try:
                    preset = self._TransitionPreset(force_preset)
                except ValueError:
                    logger.warning("unknown preset '%s', falling back to auto", force_preset)
                    preset, mode, scores = self._select_best_preset(ctx_a, ctx_b, scores)
                else:
                    mode = self._TransitionMode.stem_aware if (
                        ctx_a.has_stems and ctx_b.has_stems and scores.stem_quality_score >= 0.4
                    ) else self._TransitionMode.non_stem
            else:
                preset, mode, scores = self._select_best_preset(ctx_a, ctx_b, scores)

            plan = self._build_automix_transition(
                ctx_a, ctx_b,
                force_preset=preset,
                duration_bars=duration_bars,
            )

            tier = PlaybackTier.stem_aware if mode == self._TransitionMode.stem_aware else PlaybackTier.non_stem
            return SelectionResult(
                preset=preset.value,
                mode=mode.value,
                confidence=scores.transition_confidence,
                tier=tier.value,
                scores=scores.to_dict(),
                plan=plan.to_dict(),
            )
        except Exception as exc:
            logger.exception("strategy_selector: scoring failed: %s", exc)
            return self._basic_fallback(from_track, to_track, duration_bars)

    def _ctx_from_manifest(self, track: dict[str, Any]):
        """Build TrackContext from manifest analysis data."""
        analysis = track.get("analysis", {})
        quality = track.get("qualityFlags", {})
        stems_dict = track.get("files", {}).get("stems", {})

        has_stems = quality.get("has_stems", bool(stems_dict))
        stem_quality = 0.85 if has_stems else 0.0

        return self._TrackContext(
            song_id=str(track.get("songId") or track.get("librarySongId", "unknown")),
            bpm=float(analysis.get("bpm", 0)) or None,
            camelot_key=analysis.get("camelot_key") or analysis.get("camelotKey"),
            energy=analysis.get("energy"),
            duration_sec=float(track.get("durationSec", 240)),
            beat_points=list(analysis.get("beat_points", [])),
            downbeats=list(analysis.get("downbeats", [])),
            phrase_map=list(analysis.get("phrase_map", [])),
            cue_points=list(analysis.get("cue_points", [])),
            has_stems=has_stems,
            stem_quality_score=stem_quality,
            vocal_density=0.5,
            bass_energy=0.5,
            intro_is_clean=has_stems,
            outro_is_clean=has_stems,
            has_drum_loop=has_stems,
        )

    def _basic_fallback(
        self, from_track: dict[str, Any], to_track: dict[str, Any], duration_bars: int,
    ) -> SelectionResult:
        """Minimal fallback when stem_automix is unavailable."""
        return SelectionResult(
            preset="fallback_crossfade",
            mode="non_stem",
            confidence=0.3,
            tier=PlaybackTier.basic.value,
            warnings=["stem_automix engine unavailable — using basic crossfade"],
        )
