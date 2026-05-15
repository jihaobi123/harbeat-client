"""Keyword-based voice command matching with priority disambiguation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

VoiceIntent = str


@dataclass
class KeywordEntry:
    keywords: list[str]
    intent: str
    priority: int


KEYWORD_TABLE: list[KeywordEntry] = [
    KeywordEntry(["let's go", "lets go", "let us go", "dj", "play", "start", "开始", "播放"], "play", 50),
    KeywordEntry(["pause", "暂停", "暂停一下", "停一下"], "pause", 90),
    KeywordEntry(["stop"], "pause", 95),
    KeywordEntry(["hold on", "hold"], "hold", 80),
    KeywordEntry(["release", "松开", "继续"], "release", 80),
    KeywordEntry(["next", "下一首", "切歌", "skip"], "next", 70),
    KeywordEntry(["lift energy", "liftenergy", "升能量", "能量上升", "推高"], "lift_energy", 70),
    KeywordEntry(["drop the beat", "drop beat", "drop energy", "dropenergy", "降能量", "压下去"], "drop_energy", 70),
    KeywordEntry(["popping", "poping", "hiphop", "hip hop", "hip-hop", "breaking", "break in"], "switch_style", 60),
    KeywordEntry([
        "loop 30", "loop thirty", "loop last 30", "loop last thirty",
        "循环 30", "循环三十", "循环前30秒", "循环前三十秒", "前30秒循环", "回到30秒前",
    ], "loop_last_30s", 75),
    KeywordEntry([
        "loop off", "exit loop", "stop loop", "no loop",
        "退出循环", "关闭循环", "取消循环", "停止循环",
    ], "loop_off", 78),
    KeywordEntry(["紧急停止", "emergency stop", "emergency", "急停", "kill", "cut", "关掉"], "emergency_stop", 100),
]

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
    text = str(text).strip().lower()
    text = text.replace("'", "")
    text = text.replace("-", " ")
    text = " ".join(text.split())
    return text


def match_intent(text: str, language_hint: str = "auto") -> Tuple[str, float, list[str], Optional[dict]]:
    if not text or not text.strip():
        return ("noop", 0.0, [], None)

    normalized = _normalize(text)
    best_intent = "noop"
    best_priority = -1
    best_keywords: list[str] = []
    best_match_count = 0

    for entry in KEYWORD_TABLE:
        matched = [kw for kw in entry.keywords if _normalize(kw) in normalized or normalized in _normalize(kw)]
        if not matched:
            continue
        if entry.priority > best_priority or (entry.priority == best_priority and len(matched) > best_match_count):
            best_intent = entry.intent
            best_priority = entry.priority
            best_keywords = matched
            best_match_count = len(matched)

    payload: Optional[dict] = None
    if best_intent == "switch_style":
        for kw, style in _STYLE_DETECTION.items():
            if _normalize(kw) in normalized:
                payload = {"style": style}
                break
        payload = payload or {"style": "auto"}

    if best_intent == "noop":
        return (best_intent, 0.0, [], None)

    total_kw = next((len(e.keywords) for e in KEYWORD_TABLE if e.intent == best_intent and e.priority == best_priority), max(len(best_keywords), 1))
    confidence = min(1.0, best_match_count / max(total_kw, 1))
    return (best_intent, confidence, best_keywords, payload)


def build_mix_command(intent: str, payload: Optional[dict] = None) -> dict:
    mapping: Dict[str, dict] = {
        "play": {"command": "play", "payload": {}},
        "pause": {"command": "pause", "payload": {}},
        "hold": {"command": "pause", "payload": {"hold": True}},
        "release": {"command": "play", "payload": {"release": True}},
        "next": {"command": "next", "payload": {}},
        "lift_energy": {"command": "none", "payload": {"energy": "higher"}},
        "drop_energy": {"command": "none", "payload": {"energy": "lower"}},
        "switch_style": {"command": "none", "payload": payload or {"style": "auto"}},
        "loop_last_30s": {"command": "loop", "payload": {"action": "last_seconds", "seconds": 30}},
        "loop_off": {"command": "loop", "payload": {"action": "off"}},
        "emergency_stop": {"command": "stop", "payload": {"emergency": True}},
        "noop": {"command": "none", "payload": {}},
    }
    return mapping.get(intent, mapping["noop"])
