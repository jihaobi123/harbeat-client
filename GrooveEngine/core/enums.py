"""Enumerations used across GrooveEngine."""

from __future__ import annotations

from enum import Enum


class PhraseType(str, Enum):
    """High-level musical phrase classes produced by analyzers."""

    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    BUILD = "build"
    DROP = "drop"
    OUTRO = "outro"
    UNKNOWN = "unknown"


class FXType(str, Enum):
    """Automation target categories handled by the mixer."""

    VOLUME = "volume"
    LOW_EQ = "low_eq"
    MID_EQ = "mid_eq"
    HIGH_EQ = "high_eq"
    HIGH_PASS = "high_pass"
    DELAY_MIX = "delay_mix"
    DELAY_FEEDBACK = "delay_feedback"
    REVERB_MIX = "reverb_mix"
    NOISE_LEVEL = "noise_level"


class TransitionType(str, Enum):
    """Available transition strategies."""

    CLEAN_BLEND = "clean_blend"
    ECHO_OUT = "echo_out"
    RISER = "riser"
    CUT_SWAP = "cut_swap"
    TRIPLET_SWAP = "triplet_swap"
    MELODIC_RESET = "melodic_reset"


class DeckState(str, Enum):
    """Playback state for a single deck."""

    STOPPED = "stopped"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"
