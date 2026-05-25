#!/usr/bin/env python3
"""
Jetson → stem_automix: Score all track pairs, select optimal presets,
generate TransitionPlans, and deploy to RK3588.

Usage:
    python3 scripts/jetson_stem_scoring.py [--execute]
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.playlists.stem_automix import (
    TrackContext, TransitionPreset, TransitionMode,
    score_transition_candidates, select_best_preset,
    build_automix_transition, TempoStrategy,
)

RK_BASE = "http://192.168.5.17:9000"

PRESET_CN = {
    "bass_swap": "贝斯交换",
    "vocal_handoff": "人声交接",
    "drum_bridge": "鼓组桥接",
    "acapella_overlay": "Acapella叠加",
    "instrumental_under_vocal": "器乐垫人声",
    "breakdown_drop": "Breakdown切入",
    "loop_bridge": "Loop桥接",
    "echo_freeze": "回声冻结",
    "hard_cut": "硬切",
    "fallback_crossfade": "保底淡化",
}


def load_analysis(path="data/jetson_analysis.json"):
    with open(path) as f:
        raw = json.load(f)

    ctx_map = {}
    for tid, d in raw.items():
        ctx = TrackContext(
            song_id=d["song_id"],
            bpm=d["bpm"],
            camelot_key=d["camelot_key"],
            key_name=d.get("key"),
            energy=d["energy"],
            duration_sec=d["duration_sec"],
            beat_points=d.get("beat_points", []),
            downbeats=d.get("downbeats", []),
            phrase_map=d.get("phrase_map", []),
            cue_points=[],
            has_stems=d["has_stems"],
            stem_quality_score=d["stem_quality_score"],
            vocal_density=d["vocal_density"],
            bass_energy=d["bass_energy"],
            intro_is_clean=d["intro_is_clean"],
            outro_is_clean=d["outro_is_clean"],
            has_drum_loop=d["has_drum_loop"],
        )
        ctx_map[tid] = ctx
    return ctx_map


def score_all_pairs(ctx_map):
    """Score all directed pairs (A→B) and return ranked results."""
    track_ids = sorted(ctx_map.keys())
    results = []

    for from_id in track_ids:
        for to_id in track_ids:
            if from_id == to_id:
                continue
            ctx_a = ctx_map[from_id]
            ctx_b = ctx_map[to_id]
            scores = score_transition_candidates(ctx_a, ctx_b)
            preset, mode, _ = select_best_preset(ctx_a, ctx_b, scores)

            # Compute BPM ratio quality
            bpm_a, bpm_b = ctx_a.bpm or 120, ctx_b.bpm or 120
            ratio = bpm_b / bpm_a if bpm_a > 0 else 1
            candidates = [ratio, ratio/2, ratio*2]
            best_ratio = min(candidates, key=lambda r: abs(1-r))
            bpm_quality = "perfect" if abs(1-best_ratio) < 0.03 else (
                "good" if abs(1-best_ratio) < 0.06 else (
                "ok" if abs(1-best_ratio) < 0.10 else "bad"))

            results.append({
                "from": from_id,
                "to": to_id,
                "from_bpm": bpm_a,
                "to_bpm": bpm_b,
                "bpm_quality": bpm_quality,
                "camelot_dist": scores.key_distance,
                "preset": preset.value,
                "preset_cn": PRESET_CN.get(preset.value, preset.value),
                "mode": mode.value,
                "confidence": round(scores.transition_confidence, 3),
                "bpm_dist": round(scores.bpm_distance, 3),
                "vocal_risk": round(scores.vocal_overlap_risk, 3),
                "bass_risk": round(scores.bass_conflict_risk, 3),
                "drum_bridge": round(scores.drum_bridge_score, 3),
                "energy_delta": round(scores.energy_delta, 3),
            })

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def print_matrix(results, track_ids):
    """Print transition quality matrix."""
    sorted_ids = sorted(track_ids)

    # Header
    print(f"\n{'─'*80}")
    print("  TRANSITION QUALITY MATRIX (confidence + optimal preset)")
    print(f"{'─'*80}")
    header = f"  {'From↓ To→':10s}"
    for tid in sorted_ids:
        header += f" {tid:>8s}"
    print(header)
    print(f"  {'─'*10}{'─'*9 * len(sorted_ids)}")

    # Build lookup
    lookup = {}
    for r in results:
        lookup[(r["from"], r["to"])] = r

    for from_id in sorted_ids:
        row = f"  {from_id:>8s}  "
        for to_id in sorted_ids:
            if from_id == to_id:
                row += f" {'─':>8s}"
            else:
                r = lookup.get((from_id, to_id))
                if r:
                    quality_char = {"perfect":"★","good":"●","ok":"○","bad":"△"}.get(r["bpm_quality"],"?")
                    row += f" {quality_char}{r['confidence']:.2f}"
                else:
                    row += "   ?    "
        print(row)

    print(f"  ★=BPM perfect  ●=good  ○=ok  △=bad")
    print()


def print_top_transitions(results, top_n=15):
    """Print the best transition pairs."""
    print(f"\n{'─'*80}")
    print(f"  TOP {top_n} TRANSITIONS (ranked by confidence)")
    print(f"{'─'*80}")
    print(f"  {'Rank':>4}  {'From':>6} → {'To':>6}  {'Conf':>6}  {'Preset':>24}  {'CN':>12}  {'Mode':>11}  {'BPM':>15}  {'Key':>6}  {'Vocal':>6}")
    print(f"  {'─'*80}")

    for i, r in enumerate(results[:top_n], 1):
        bpm_str = f"{r['from_bpm']:.0f}→{r['to_bpm']:.0f} ({r['bpm_quality']})"
        print(f"  {i:>4}  {r['from']:>6} → {r['to']:>6}  {r['confidence']:>6.3f}  {r['preset']:>24}  {r['preset_cn']:>12}  {r['mode']:>11}  {bpm_str:>15}  {r['camelot_dist']:>4}d  {r['vocal_risk']:>5.2f}")
    print()


def rk_post(path, body):
    url = f"{RK_BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def rk_state():
    url = f"{RK_BASE}/state"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def rk_health():
    url = f"{RK_BASE}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def execute_mix_sequence(ctx_map, sequence, results_lookup):
    """Execute a sequence of crossfades on RK3588 using optimal presets."""

    print(f"\n{'='*60}")
    print("  DEPLOYING TO RK3588")
    print(f"{'='*60}")

    health = rk_health()
    if not health.get("ok"):
        print(f"  RK not reachable: {health}")
        return

    state = rk_state()
    current_song = state.get("current_song_id")
    print(f"  RK online | Current: Song {current_song} | Playing: {state.get('playing')}")

    # Map RK song IDs to our track IDs
    # Our analysis uses "100"-"108", RK uses int song IDs
    rk_current = str(current_song) if current_song else None

    for i in range(len(sequence) - 1):
        from_id = sequence[i]
        to_id = sequence[i + 1]
        r = results_lookup.get((from_id, to_id))
        if not r:
            continue

        # Calculate crossfade duration from BPM
        ctx_b = ctx_map[to_id]
        bars = 8
        bpm = r["from_bpm"]
        fade_sec = round(bars * 4 * 60.0 / max(bpm, 1.0), 1)

        # Map preset to RK xfade style
        style_map = {
            "bass_swap": "bass_swap",
            "vocal_handoff": "echo_out",
            "drum_bridge": "smooth",
            "acapella_overlay": "smooth",
            "instrumental_under_vocal": "smooth",
            "breakdown_drop": "filter",
            "loop_bridge": "filter",
            "echo_freeze": "echo_out",
            "hard_cut": "cut",
            "fallback_crossfade": "smooth",
        }
        rk_style = style_map.get(r["preset"], "smooth")

        print(f"\n  [{i+1}/{len(sequence)-1}] {from_id} → {to_id}")
        print(f"    Preset: {r['preset_cn']} ({r['preset']})")
        print(f"    Confidence: {r['confidence']:.3f} | Mode: {r['mode']}")
        print(f"    RK style: {rk_style} | Fade: {fade_sec:.1f}s | BPM: {r['from_bpm']:.0f}→{r['to_bpm']:.0f}")

        # Execute on RK
        result = rk_post("/xfade", {
            "to_song_id": int(to_id),
            "fade_sec": fade_sec,
            "style": rk_style,
            "to_at_sec": 0.0,
        })

        if result.get("ok"):
            print(f"    ✓ Executed")
        else:
            err = result.get("detail", result.get("error", "unknown"))
            print(f"    ✗ Failed: {err}")

        time.sleep(8)

    # Final state
    state = rk_state()
    print(f"\n  Final: Song {state.get('current_song_id')} | pos={state.get('position_sec',0):.1f}s")


# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default="data/jetson_analysis.json")
    ap.add_argument("--execute", action="store_true",
                    help="Deploy and execute optimal mix sequence on RK3588")
    args = ap.parse_args()

    # 1. Load analysis
    print("Loading analysis...")
    ctx_map = load_analysis(args.analysis)
    track_ids = sorted(ctx_map.keys())
    print(f"  {len(track_ids)} tracks: {', '.join(track_ids)}")

    # 2. Score all pairs
    print(f"\nScoring all {len(track_ids) * (len(track_ids)-1)} pairs...")
    t0 = time.time()
    results = score_all_pairs(ctx_map)
    print(f"  Done in {time.time()-t0:.1f}s")

    # 3. Matrix
    print_matrix(results, track_ids)

    # 4. Top transitions
    print_top_transitions(results, top_n=15)

    # 5. Save results
    out = {
        "analysis_path": args.analysis,
        "track_ids": track_ids,
        "total_pairs": len(results),
        "transitions": results,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/transition_scores.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"  Scores saved → data/transition_scores.json")

    # 6. Execute on RK if requested
    if args.execute:
        # Build optimal sequence through all 7 tracks
        # Greedy: start from current song, always pick best next
        lookup = {(r["from"], r["to"]): r for r in results}

        # If we can determine current song from RK, use it; else start at 100
        state = rk_state()
        start = str(state.get("current_song_id", "100"))
        if start not in track_ids:
            start = "100"
        print(f"\n  Starting sequence from: {start}")

        # Greedy path through all tracks
        remaining = set(track_ids) - {start}
        sequence = [start]
        current = start
        while remaining:
            # Find best transition from current to any remaining track
            best = None
            best_conf = -1
            for nxt in remaining:
                r = lookup.get((current, nxt))
                if r and r["confidence"] > best_conf:
                    best_conf = r["confidence"]
                    best = nxt
            if best is None:
                best = remaining.pop()
            else:
                remaining.discard(best)
            sequence.append(best)
            current = best

        print(f"  Optimal sequence: {' → '.join(sequence)}")

        execute_mix_sequence(ctx_map, sequence, lookup)
