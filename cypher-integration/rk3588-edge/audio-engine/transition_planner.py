"""
Transition Planner: 输入 N 首歌的分析数据 → 逐对候选窗口评分 → 生成完整 DJ Mix Plan。

用法:
    from transition_planner import plan_mix
    plan = plan_mix(songs, stems_available=True)

CLI:
    python transition_planner.py songs.json
"""

from __future__ import annotations

import logging
from typing import Any

from strategy_selector import select_preset, STEM_AWARE_PRESETS

logger = logging.getLogger(__name__)

# ── 候选窗口生成 ─────────────────────────────────────────────────

# 出歌候选：标签 + 最小剩余秒数
EXIT_CANDIDATES = [
    ("Outro", 4),
    ("Bridge", 6),
    ("Breakdown", 6),
    ("Chorus", 8),
    ("Hook", 8),
    ("Verse", 10),
    ("Build", 10),
]
ENTRY_CANDIDATES = [
    ("Intro", 4),
    ("Verse", 8),
    ("Build", 8),
    ("PreChorus", 8),
    ("Breakdown", 8),
    ("Chorus", 12),
    ("Hook", 12),
]


def _collect_candidates(song: dict, candidates: list[tuple[str, float]], is_exit: bool) -> list[dict]:
    """从 cues / sections 中收集所有匹配标签的候选窗口。

    Returns: [{"start": float, "end": float, "label": str, "source": str}, ...]
    """
    cues = song.get("cues") or []
    sections = song.get("sections") or song.get("segments") or []
    duration = float(song.get("duration", 0) or 0)
    results = []

    for label, min_remain in candidates:
        # 先试 sections
        for sec in sections:
            if sec.get("label", "").lower() == label.lower():
                start = float(sec.get("start", 0))
                end = float(sec.get("end", start + 16))
                if is_exit:
                    if end > start + 3 and start > 2 and end < duration - min_remain:
                        results.append({"start": start, "end": min(end, duration - 1),
                                        "label": label, "source": "sections"})
                else:
                    if end > start + 3 and end < duration - 2:
                        results.append({"start": start, "end": min(end, duration - 1),
                                        "label": label, "source": "sections"})

        # 再试 cues
        for cue in cues:
            if cue.get("label", "").lower() == label.lower():
                t = float(cue.get("time", 0))
                if is_exit:
                    if 4 < t < duration - min_remain:
                        end = t + 16
                        for nc in cues:
                            nt = float(nc.get("time", 0))
                            if nt > t + 4:
                                end = min(nt, t + 32)
                                break
                        results.append({"start": t, "end": min(end, duration - 1),
                                        "label": label, "source": "cues"})
                else:
                    if t < duration - 8:
                        end = t + 16
                        for nc in cues:
                            nt = float(nc.get("time", 0))
                            if nt > t + 4:
                                end = min(nt, t + 32)
                                break
                        results.append({"start": t, "end": min(end, duration - 1),
                                        "label": label, "source": "cues"})

    return results


def _fallback_exit(song: dict) -> dict:
    duration = float(song.get("duration", 0) or 0)
    cues = song.get("cues") or []
    if cues:
        late = [c for c in cues if float(c.get("time", 0)) > duration * 0.5]
        if late:
            t = float(late[-1].get("time", 0))
            return {"start": t, "end": min(t + 16, duration - 1), "label": "Auto-End", "source": "fallback"}
    start = max(0, duration - 24)
    return {"start": start, "end": max(start + 8, duration - 1), "label": "Auto-End", "source": "duration"}


def _fallback_entry(song: dict) -> dict:
    cues = song.get("cues") or []
    if cues:
        return {"start": float(cues[0].get("time", 0)), "label": cues[0].get("label", "Start"), "source": "fallback"}
    return {"start": 0.0, "label": "Start", "source": "fallback"}


def _generate_window_pairs(a: dict, b: dict, prefer_exit: float | None,
                           prefer_entry: float | None) -> list[dict]:
    """生成候选 (exit, entry) 窗口对。"""
    pairs = []

    # 用户指定 → 只用这一对，不混入自动候选
    if prefer_exit is not None and prefer_entry is not None:
        return [{"exit": {"start": prefer_exit, "end": prefer_exit + 20, "label": "Manual", "source": "manual"},
                  "entry": {"start": prefer_entry, "label": "Manual", "source": "manual"},
                  "source": "manual"}]

    # 自动候选
    exits = _collect_candidates(a, EXIT_CANDIDATES, is_exit=True)
    entries = _collect_candidates(b, ENTRY_CANDIDATES, is_exit=False)

    if not exits:
        exits = [_fallback_exit(a)]
    if not entries:
        entries = [_fallback_entry(b)]

    # 生成所有组合（限制数量）
    for ex in exits[:4]:
        for en in entries[:4]:
            pairs.append({"exit": ex, "entry": en, "source": "auto"})

    return pairs


# ── 过渡时长 ─────────────────────────────────────────────────────

def _suggest_fade_sec(selected: str, bpm_quality: str, key_quality: str, double_vocal: float) -> float:
    if selected in ("cut", "slam"):
        return 0.5
    if selected == "echo_freeze":
        return max(4.0, min(8.0, 6.0 + double_vocal * 6))
    if selected == "vocal_handoff":
        return max(12.0, min(24.0, 16.0 + double_vocal * 8))
    if selected == "bass_swap":
        return max(8.0, min(20.0, 12.0))
    if selected == "vocal_solo_intro":
        return max(10.0, min(22.0, 14.0))
    if bpm_quality in ("wide", "risky"):
        return 8.0
    if key_quality == "tense":
        return 6.0
    return 8.0


def _suggest_vocal_handoff_ratio(song_b: dict, b_in_cue: float, fade_sec: float, double_vocal: float) -> float:
    """Pick a vocal cut point from B's beat grid and vocal density.

    Higher double-vocal risk moves the target earlier, then the beat grid snaps
    it back to an actual beat in the transition window.
    """
    target = 0.50 - min(0.12, max(0.0, double_vocal) * 0.10)
    lo, hi = 0.32, 0.62
    beats = song_b.get("beats") or song_b.get("beat_points") or []
    candidates = []
    for beat in beats:
        try:
            ratio = (float(beat) - b_in_cue) / max(0.001, fade_sec)
        except (TypeError, ValueError):
            continue
        if lo <= ratio <= hi:
            candidates.append(ratio)
    if candidates:
        return round(min(candidates, key=lambda r: abs(r - target)), 4)

    bpm = float(song_b.get("bpm", 0) or 0)
    if bpm > 0:
        interval = 60.0 / bpm
        target_sec = target * fade_sec
        snapped = round(target_sec / interval) * interval
        return round(max(lo, min(hi, snapped / max(0.001, fade_sec))), 4)
    return round(max(lo, min(hi, target)), 4)


# ── 主入口 ───────────────────────────────────────────────────────

def plan_mix(
    songs: list[dict],
    *,
    stems_available: bool = True,
    prefer_exits: dict[str, float] | None = None,
    prefer_entries: dict[str, float] | None = None,
) -> dict:
    """输入 N 首歌的分析数据，返回完整 Mix Plan。

    每首歌需包含: song_id, bpm, camelot, energy, duration。
    可选: cues, sections, stem_activity_windows。

    Returns: {plan_id, tracks, transitions, analyses, summary}
    """
    if len(songs) < 2:
        return {"error": "至少需要 2 首歌", "tracks": [], "transitions": [], "analyses": [], "summary": ""}

    prefer_exits = prefer_exits or {}
    prefer_entries = prefer_entries or {}

    tracks = []
    transitions = []
    analyses = []

    for i, song in enumerate(songs):
        sid = str(song.get("song_id", song.get("id", f"track_{i}")))
        bpm = float(song.get("bpm", 0) or 0)
        beats = song.get("beats") or song.get("beat_points") or []
        tracks.append({
            "song_id": sid,
            "order": i,
            "title": song.get("title", ""),
            "artist": song.get("artist", ""),
            "bpm": bpm,
            "beats": beats[:20] if beats else [],
            "duration": float(song.get("duration", 0) or 0),
        })

    for i in range(len(songs) - 1):
        a, b = songs[i], songs[i + 1]
        sid_a = tracks[i]["song_id"]
        sid_b = tracks[i + 1]["song_id"]

        # 生成候选窗口对
        pairs = _generate_window_pairs(a, b, prefer_exits.get(sid_a), prefer_entries.get(sid_b))

        # 对每个候选对运行 selector，选最高分
        best_pair_result = None
        best_score = -1.0
        all_candidates = []

        for pair in pairs:
            ex = pair["exit"]
            en = pair["entry"]
            a_out_start = float(ex["start"])
            a_out_end = float(ex["end"])
            b_in_cue = float(en["start"])

            result = select_preset(a, b, a_out_start, a_out_end, b_in_cue, stems_available)

            all_candidates.append({
                "exit": ex,
                "entry": en,
                "source": pair["source"],
                "selected": result["selected"],
                "score": result["score"],
                "top3": [(r["preset"], r["score"]) for r in result["rankings"][:3]],
            })

            if result["score"] > best_score:
                best_score = result["score"]
                best_pair_result = {"exit": ex, "entry": en, "result": result, "source": pair["source"]}

        # 取最优
        if best_pair_result is None:
            best_pair_result = {"exit": {"start": 0, "end": 16, "label": "Fallback", "source": "fallback"},
                                "entry": {"start": 0, "label": "Fallback", "source": "fallback"},
                                "result": all_candidates[0].get("result", {}),
                                "source": "fallback"}

        result = best_pair_result["result"]
        risks = result.get("risks", {})
        compat = result.get("compatibility", {})
        fade_sec = _suggest_fade_sec(
            result["selected"],
            compat.get("bpm_quality", "ok"),
            compat.get("camelot_quality", "ok"),
            risks.get("double_vocal_risk", 0),
        )

        transition = {
            "from_song": sid_a,
            "to_song": sid_b,
            "from_at_sec": round(float(best_pair_result["exit"]["start"]), 3),
            "to_at_sec": round(float(best_pair_result["entry"]["start"]), 3),
            "fade_sec": round(fade_sec, 3),
            "style": result["selected"],
            "from_beat_interval_sec": round(60.0 / a.get("bpm", 120), 6) if a.get("bpm") else None,
            "to_beat_interval_sec": round(60.0 / b.get("bpm", 120), 6) if b.get("bpm") else None,
        }
        if result["selected"] == "vocal_handoff":
            transition["vocal_handoff_ratio"] = _suggest_vocal_handoff_ratio(
                b,
                float(best_pair_result["entry"]["start"]),
                fade_sec,
                risks.get("double_vocal_risk", 0),
            )
        transitions.append(transition)

        analyses.append({
            "pair_index": i,
            "from": sid_a,
            "to": sid_b,
            "selected_window": best_pair_result["exit"],
            "selected_entry": best_pair_result["entry"],
            "selector_result": result,
            "candidates_evaluated": len(all_candidates),
            "all_candidates": all_candidates,
        })

    # 摘要
    lines = [f"🎧 Mix Plan: {len(songs)} tracks, {len(transitions)} transitions"]
    for i, tr in enumerate(transitions):
        an = analyses[i]["selector_result"]
        ex = analyses[i]["selected_window"]
        en = analyses[i]["selected_entry"]
        lines.append(
            f"  {i+1}. {tracks[i].get('title',tracks[i]['song_id'])[:24]} "
            f"→ {tracks[i+1].get('title',tracks[i+1]['song_id'])[:24]}"
        )
        lines.append(f"      {tr['style']} (score={an['score']:.2f}, {tr['fade_sec']:.1f}s)")
        lines.append(f"      exit: {ex['label']}@{ex['start']:.1f}s  →  entry: {en['label']}@{en['start']:.1f}s")

    return {
        "plan_id": f"auto-{abs(hash(tuple(t['song_id'] for t in tracks)))}",
        "tracks": tracks,
        "transitions": transitions,
        "analyses": analyses,
        "summary": "\n".join(lines),
    }


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) < 2:
        print("Usage: python transition_planner.py <songs.json>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        songs = json.load(f)
    plan = plan_mix(songs)
    print(plan["summary"])
    print()
    # 打印每对的 Top 3 候选
    for an in plan.get("analyses", []):
        print(f"\nPair {an['pair_index']}: {an['from'][:8]}... → {an['to'][:8]}...")
        print(f"  Evaluated {an['candidates_evaluated']} window pairs")
        for c in an.get("all_candidates", [])[:5]:
            print(f"    exit={c['exit']['label']}@{c['exit']['start']:.1f}s "
                  f"entry={c['entry']['label']}@{c['entry']['start']:.1f}s "
                  f"→ {c['selected']} ({c['score']:.3f})")
