"""Keyword-based voice command matching with priority disambiguation.

Supports Chinese + English keywords for each DJ control intent.
When multiple intents match, the one with highest priority wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

VoiceIntent = str  # "play" | "pause" | "hold" | ...


@dataclass
class KeywordEntry:
    keywords: list[str]
    intent: str
    priority: int  # higher = wins when overlapping
    style_payload: Optional[str] = None  # for SwitchStyle


# ── Master keyword table (v1, from approved specification) ───────────

KEYWORD_TABLE: list[KeywordEntry] = [
    # ── Emergency (highest priority — always overrides) ──
    KeywordEntry(
        keywords=["紧急停止", "emergency", "急停", "cut", "kill", "关掉"],
        intent="emergency_stop",
        priority=11,
    ),

    # ── Play ──
    KeywordEntry(
        keywords=["play", "播放", "开始", "start", "go", "走",
                   "lets go", "let's go", "let us go",
                   "dj", "DJ", "drop the beat", "drop beat"],
        intent="play",
        priority=10,
    ),

    # ── Pause ──
    KeywordEntry(
        keywords=["pause", "暂停", "暂停一下", "停一下", "stop", "停"],
        intent="pause",
        priority=10,
    ),

    # ── Next ──
    KeywordEntry(
        keywords=["next", "下一首", "切歌", "skip", "跳过"],
        intent="next",
        priority=10,
    ),

    # ── Hold ──
    KeywordEntry(
        keywords=["hold on", "hold", "保持", "定住", "freeze", "锁住"],
        intent="hold",
        priority=9,
    ),

    # ── Release ──
    KeywordEntry(
        keywords=["release", "释放", "松开", "继续", "resume", "unfreeze"],
        intent="release",
        priority=9,
    ),

    # ── Lift Energy ──
    KeywordEntry(
        keywords=["升能量", "能量上升", "lift", "lift energy",
                   "build up", "拉起来", "推高"],
        intent="lift_energy",
        priority=8,
    ),

    # ── Drop Energy ──
    KeywordEntry(
        keywords=["降能量", "能量下降", "drop energy", "cool down",
                   "压下去", "放低"],
        intent="drop_energy",
        priority=8,
    ),

    # ── Switch Style ──
    KeywordEntry(
        keywords=["切风格", "换风格", "switch style", "change style", "换曲风",
                   "popping", "poping", "hiphop", "hip hop", "hip-hop",
                   "breaking", "break in"],
        intent="switch_style",
        priority=7,
    ),
]

# Style detection rules embedded in switch_style keywords
_STYLE_DETECTION: Dict[str, str] = {
    "popping": "popping",
    "poping": "popping",
    "hiphop": "hiphop",
    "hip hop": "hiphop",
    "hip-hop": "hiphop",
    "breaking": "breaking",
    "break in": "breaking",
}


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return " ".join(str(text).strip().lower().split())


def match_intent(
    text: str,
    language_hint: str = "auto",
) -> Tuple[str, float, list[str], Optional[dict]]:
    """Match raw transcribed text to a voice intent.

    Returns (intent, confidence, matched_keywords, command_payload).

    Priority-based disambiguation:
    - When multiple intents match, highest priority wins.
    - Same priority → more matched keywords → first in table.
    - EmergencyStop (priority 11) always overrides everything else.
    - NoOp is the fallback when nothing matches.
    """
    if not text or not text.strip():
        return ("noop", 0.0, [], None)

    normalized = _normalize(text)

    # Collect all matches
    best_intent = "noop"
    best_priority = -1
    best_keywords: list[str] = []
    best_payload: Optional[dict] = None
    best_match_count = 0

    for entry in KEYWORD_TABLE:
        matched: list[str] = []
        for kw in entry.keywords:
            if _normalize(kw) in normalized or normalized in _normalize(kw):
                matched.append(kw)

        if not matched:
            continue

        match_count = len(matched)
        # Tie-breaking: priority > match count > table order (implicit)
        if entry.priority > best_priority:
            best_intent = entry.intent
            best_priority = entry.priority
            best_keywords = matched
            best_payload = None
            best_match_count = match_count
        elif entry.priority == best_priority and match_count > best_match_count:
            best_intent = entry.intent
            best_keywords = matched
            best_payload = None
            best_match_count = match_count

    # Build payload for SwitchStyle
    if best_intent == "switch_style":
        for kw, style in _STYLE_DETECTION.items():
            if _normalize(kw) in normalized:
                best_payload = {"style": style}
                break

    # Confidence = fraction of keywords in this entry matched
    if best_intent != "noop":
        total_kw = max(
            next(
                (len(e.keywords)
                 for e in KEYWORD_TABLE
                 if e.intent == best_intent and e.priority == best_priority),
                len(best_keywords),
            ),
            1,
        )
        confidence = min(1.0, best_match_count / total_kw)
    else:
        confidence = 0.0

    return (best_intent, confidence, best_keywords, best_payload)


def build_mix_command(intent: str, payload: Optional[dict] = None) -> dict:
    """Map a voice intent to a MixCommand that GrooveEngine can consume.

    Returns a dict with ``command`` and ``payload`` keys, matching the
    MixCommand dataclass shape.
    """
    intent_to_command: Dict[str, dict] = {
        "play": {"command": "play", "payload": {}},
        "pause": {"command": "pause", "payload": {}},
        "hold": {"command": "pause", "payload": {"hold": True}},
        "release": {"command": "play", "payload": {"release": True}},
        "next": {"command": "next", "payload": {}},
        "lift_energy": {"command": "none", "payload": {"energy": "up"}},
        "drop_energy": {"command": "none", "payload": {"energy": "down"}},
        "switch_style": {
            "command": "none",
            "payload": payload or {"style": "auto"},
        },
        "emergency_stop": {"command": "stop", "payload": {"emergency": True}},
        "noop": {"command": "none", "payload": {}},
    }
    return intent_to_command.get(intent, intent_to_command["noop"])
