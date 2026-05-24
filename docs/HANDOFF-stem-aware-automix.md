# HarBeat Stem-Aware Automix — HANDOFF v3

**Date:** 2026-05-23
**Scope:** Two-tier Automix system (non-stem + stem-aware), 10 transition presets, scoring engine, decision rules, A/B comparison tool

---

## 1. Architecture Overview

```
Jetson (offline)                          RK3588 (real-time)
┌─────────────────────┐                   ┌──────────────────────┐
│ analysis.json       │ ──manifest.json──→ │ sync-worker          │
│ stems/{v,d,b,o}.wav │                   │ cache/{sid}/*.wav    │
│ transition_plan.json│ ─────────────────→ │ engine.py executes   │
│                     │                   │ curves in callback   │
└─────────────────────┘                   └──────────────────────┘
```

**Key principle:** Jetson does ML (analysis + demucs); RK3588 only executes pre-computed transition plans. No ML on RK.

---

## 2. Transition Plan Data Structure

**File:** `app/modules/playlists/stem_automix.py` — `TransitionPlan`

```json
{
  "from_song_id": "101",
  "to_song_id": "102",
  "mode": "non_stem | stem_aware",
  "preset": "bass_swap",
  "start_bar": 0,
  "duration_bars": 8,
  "bpm_from": 128.0,
  "bpm_to": 128.0,
  "tempo_strategy": "none | sync_to_from | sync_to_to | tempo_blend",
  "curves": [
    {
      "target": "A.bass",
      "param": "gain",
      "points": [[0.0, 1.0], [0.4, 0.0], [1.0, 0.0]],
      "shape": "s_curve"
    }
  ]
}
```

**All timing is in bars (4 beats each).** RK3588 converts to seconds using `bpm_from` at runtime.

### AutomationCurve fields

| Field | Type | Values |
|-------|------|--------|
| `target` | enum | `A.vocals`, `A.drums`, `A.bass`, `A.other`, `B.*`, `master` |
| `param` | enum | `gain`, `low_eq`, `mid_eq`, `high_eq`, `highpass`, `lowpass`, `echo_send`, `reverb_send`, `mute` |
| `points` | list | `[[time_frac, value], ...]` — time ∈ [0, 1] |
| `shape` | enum | `linear`, `equal_power`, `exponential`, `s_curve` |

---

## 3. Two-Tier Automix System

### Tier 1: Non-Stem Automix (Spotify Mix style)

- **Input:** Two full audio tracks + BPM + beatgrid + downbeat + key + energy + phrase_map + cue_points
- **Available immediately** — no stems needed
- **Actions:** beatmatched crossfade, EQ curves, filter sweeps, echo out, riser, tempo blend, cut, slam, power, fade, rise, blend, wave, melt
- **Implementation:** Each preset has a `_fallback` function that produces curves targeting `master` (full track)

### Tier 2: Stem-Aware Automix (djay Neural Mix / Serato Stems style)

- **Input:** Original + 4 stems (vocals, drums, bass, other) per track
- **Available after** Jetson completes background stem separation
- **Actions:** Per-stem gain control, bass swap, vocal handoff, drum bridging, acapella overlay
- **Auto-upgrade:** When stems become `ready`, subsequent transitions automatically use stem-aware mode

---

## 4. 10 Transition Presets

### Stem-Aware Presets (9)

| # | Preset | Best For | Core Logic | Key Constraint |
|---|--------|----------|------------|----------------|
| 1 | `bass_swap` | Dance, house, hip-hop | A drums hold → B drums enter; A bass exits before B bass enters at midpoint | No dual bass at full level |
| 2 | `vocal_handoff` | Two vocal tracks | A vocals echo out at phrase boundary; B vocals enter after safe gap | Avoids vocal overlap |
| 3 | `drum_bridge` | B intro weak, A drums stable | A drums sustain rhythm; B bass/melody enter gradually; A drums exit when B drums land | A drums must be loopable |
| 4 | `acapella_overlay` | Clean A vocal + compatible B instrumental | A vocals over B instrumental; B vocals enter late | key_distance ≤ 1 Camelot step |
| 5 | `instrumental_under_vocal` | A vocal section, B clean intro | B instrumental enters under A; A vocals echo out; B vocals stay muted initially | B.vocals muted until safe |
| 6 | `breakdown_drop` | A breakdown/outro → B drop/chorus | Build tension via HPF sweep + echo; B full stems at drop downbeat; master -6dB headroom | A must have clean outro |
| 7 | `loop_bridge` | Stable drum loop on A or B | Loop A.drums as bridge; B layers in; loop exits at phrase boundary | A.drums loopable |
| 8 | `echo_freeze` | Key clash, vocal conflict, hard to match | Short transition (1-4 bars): A vocal/snare echo freeze; B enters clean at downbeat | No long overlap |
| 9 | `hard_cut` | High energy, same BPM, slam style | Instant switch at phrase boundary with 1-beat echo tail on A | phrase boundary alignment |

### Non-Stem Fallback (1)

| # | Preset | Logic |
|---|--------|-------|
| 10 | `fallback_crossfade` | Equal-power full-track crossfade. **Never fails.** |

### Preset Fallback Map

When stems are unavailable, stem-aware presets auto-downgrade:

| Stem-Aware | Fallback Behavior |
|------------|-------------------|
| `bass_swap` | EQ-only low-frequency crossover (low_eq curve on master) |
| `vocal_handoff` | Fast crossfade with echo send on outgoing master |
| `drum_bridge` | Extended crossfade + HPF sweep on outgoing |
| `acapella_overlay` | B enters low under A, then A fades |
| `instrumental_under_vocal` | B enters low, A fades with echo tail |
| `breakdown_drop` | HPF sweep + cut to B at drop point |
| `loop_bridge` | Extended overlap favoring B low entry |
| `echo_freeze` | Short crossfade with heavy echo |
| `hard_cut` | Instant master switch with echo tail |
| `fallback_crossfade` | (always non-stem) |

---

## 5. Scoring System

**File:** `app/modules/playlists/stem_automix.py` — `score_transition_candidates()`

### Scoring Dimensions (13 fields)

| Field | Range | Meaning |
|-------|-------|---------|
| `bpm_distance` | 0–1 | 0=same BPM, 1=very different |
| `beatgrid_confidence` | 0–1 | Both tracks have ≥8 beat points? |
| `downbeat_confidence` | 0–1 | Both tracks have ≥4 downbeats? |
| `key_distance` | 0–12 | Camelot steps: 0=same, 1=relative/neighbor |
| `phrase_match_score` | 0–1 | Both tracks have phrase maps? |
| `energy_delta` | 0–1 | 0=same energy level, 1=opposite |
| `vocal_overlap_risk` | 0–1 | Product of vocal densities × 1.5 |
| `bass_conflict_risk` | 0–1 | Product of bass energies × 1.4 |
| `drum_bridge_score` | 0–1 | A drums loopable + B intro clean? |
| `stem_quality_score` | 0–1 | min(stem quality of both tracks) |
| `separation_artifact_risk` | 0–1 | 1 - stem_quality_score |
| `intro_outro_cleanliness` | 0–1 | Both ends have clean sections? |
| `transition_confidence` | 0–1 | Weighted composite (see below) |

### Confidence Weights

```
confidence = 0.20*(1-bpm_distance) + 0.15*beatgrid + 0.10*downbeat
           + 0.15*(1-key_dist/12) + 0.10*phrase + 0.10*(1-energy_delta)
           + 0.05*(1-artifact_risk) + 0.05*drum_bridge
           + 0.05*intro_outro + 0.05*min(1, 2*stem_quality)
```

---

## 6. Decision Rules (Preset Selection)

**File:** `app/modules/playlists/stem_automix.py` — `select_best_preset()`

Priority order:

```
1. confidence < 0.25                → hard_cut (safest)
2. stem_quality < 0.4               → non-stem only (best non-stem preset)
3. bass_conflict > 0.5              → bass_swap
4. vocal_overlap > 0.55             → vocal_handoff or echo_freeze
5. intro_outro > 0.6 + energy_delta → breakdown_drop
6. drum_bridge > 0.35               → drum_bridge
7. key_compatible + low_vocal       → acapella_overlay
8. vocal_density > 0.4 + clean_B    → instrumental_under_vocal
9. has_drum_loop                    → loop_bridge
10. confidence < 0.35               → echo_freeze or hard_cut
11. default                         → bass_swap
```

---

## 7. Curve Engine

**File:** `app/modules/playlists/stem_automix.py` — `build_curve()`

Four interpolation shapes:

| Shape | Formula | Use Case |
|-------|---------|----------|
| `linear` | Straight interpolation | Cuts, mutes, precise timing |
| `equal_power` | cos²(πt/2) / sin²(πt/2) | Crossfades (constant power) |
| `exponential` | log-linear interpolation | Filter cutoff sweeps (perceptual linearity) |
| `s_curve` | smoothstep(gain) = 3g² - 2g³ | Vocal fade, bass swap (smooth, natural) |

---

## 8. RK3588 Execution Format

The engine reads `TransitionPlan.curves` and applies each `AutomationCurve` in the audio callback:

```
For each callback block:
  progress = current_sample / total_transition_samples  # ∈ [0, 1]
  For each curve in plan.curves:
    value = interpolate(curve.points, progress, curve.shape)
    Apply value to curve.target with curve.param
  Sum all stem/eq contributions → output buffer
```

### Parameter Application

| `param` | How to Apply |
|---------|-------------|
| `gain` | Multiply stem/full audio by value |
| `low_eq` | Set deck EQ low-shelf (dB) |
| `mid_eq` | Set deck EQ peak (dB) |
| `high_eq` | Set deck EQ high-shelf (dB) |
| `highpass` | Set Biquad HPF cutoff (Hz) |
| `lowpass` | Set Biquad LPF cutoff (Hz) |
| `echo_send` | Mix delayed signal scaled by value |
| `reverb_send` | Mix reverb scaled by value |
| `mute` | Bypass stem when value > 0.5 |

### EQ Parameter Ranges

- `low_eq`: -12 to +12 dB (80Hz low-shelf)
- `mid_eq`: -12 to +12 dB (1kHz peak, Q=0.9)
- `high_eq`: -12 to +12 dB (8kHz high-shelf)
- `highpass`: 20–400 Hz
- `lowpass`: 200–18000 Hz

---

## 9. Files Created/Modified

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `app/modules/playlists/stem_automix.py` | ~960 | Core module: data models, curve engine, 10 presets + fallbacks, scoring, decision engine, offline renderer, high-level API |
| `scripts/export_ab_comparison.py` | 230 | A/B comparison: exports non_stem.wav and stem_aware.wav for the same track pair |
| `tests/test_stem_automix.py` | 380 | 12 test classes covering all 8 required scenarios + serialization + parametrized preset validation |

### Existing Files (unchanged)

- `app/modules/playlists/transition_planner.py` — Existing non-stem planner (TrackFeature, score_transition, plan_phrase_transition)
- `app/modules/playlists/offline_renderer.py` — Existing offline renderer (render_offline_mix with basic stem rules)
- `app/modules/playlists/schemas.py` — Existing API schemas (DjTransitionPlanItem, DjOfflineMixRequest)
- `audio-engine/engine.py` — RK3588 engine (tiered playback from HANDOFF-v2)

---

## 10. A/B Comparison Tool

```bash
# With stems (compares both modes)
python scripts/export_ab_comparison.py \
  --song-a music/song_a.wav \
  --song-b music/song_b.wav \
  --stems-a output/stems/htdemucs/song_a/ \
  --stems-b output/stems/htdemucs/song_b/ \
  --bpm-a 128 --bpm-b 128 --key-a 8A --key-b 9A \
  --output-dir ./ab_output/

# Without stems (validates fallback works)
python scripts/export_ab_comparison.py \
  --song-a music/song_a.wav \
  --song-b music/song_b.wav \
  --output-dir ./ab_output/

# Force a specific preset
python scripts/export_ab_comparison.py \
  --song-a music/song_a.wav --song-b music/song_b.wav \
  --force-preset breakdown_drop
```

Outputs:
- `non_stem.wav` — Non-stem Automix version
- `stem_aware.wav` — Stem-aware Automix version (if stems provided)
- `plan_comparison.json` — Both transition plans for inspection
- `scores.json` — Full scoring breakdown

---

## 11. Test Coverage

**Run:** `pytest tests/test_stem_automix.py -v`

| # | Test Class | What it Tests |
|---|------------|---------------|
| 1 | `TestCurveEngine` | All 4 curve shapes (linear, equal_power, s_curve, exponential) |
| 2 | `TestNoStems` | All presets return non_stem mode; fallback_crossfade always works |
| 3 | `TestStemsAvailable` | Stems → stem_aware mode; all presets produce valid curves |
| 4 | `TestPartialStems` | One track missing stems → auto-downgrade |
| 5 | `TestDifferentBPM` | Moderate/large BPM differences scored correctly |
| 6 | `TestKeyIncompatible` | Key clash blocks acapella_overlay selection |
| 7 | `TestDualVocal` | High vocal density → vocal_handoff/echo_freeze |
| 8 | `TestBassConflict` | High bass energy → bass_swap |
| 9 | `TestLowConfidence` | Low info → hard_cut or echo_freeze |
| 10 | `TestSerialization` | TransitionPlan JSON roundtrip |
| 11 | `TestAllPresets` | Parametrized: every preset has curves, monotonic times, valid value ranges |
| 12 | `TestBuildAutomixTransition` | High-level API: auto-preset, force-preset, tempo strategy |

---

## 12. Integration Points

### With existing `generate_dj_mix_plan()` (service.py)

To upgrade the existing mix plan generator to use stem-aware transitions:

```python
from app.modules.playlists.stem_automix import (
    TrackContext, build_automix_transition, TransitionPlan
)

# Build context per track from LibrarySong
ctx = TrackContext(
    song_id=song.id,
    bpm=song.bpm,
    camelot_key=song.camelot_key,
    energy=song.energy,
    duration_sec=song.duration,
    beat_points=song.beat_points,
    downbeats=song.downbeats,
    phrase_map=song.phrase_map,
    cue_points=song.cue_points,
    has_stems=song.stem_status == "ready",
    stem_quality_score=0.85 if song.stem_status == "ready" else 0.0,
)

# Generate plan with auto preset selection
plan = build_automix_transition(ctx_a, ctx_b)

# Serialize for RK3588
plan_json = plan.to_dict()
```

### With existing `render_offline_mix()` (offline_renderer.py)

The new `render_transition_plan()` in `stem_automix.py` can be used as a drop-in replacement when you have `TransitionPlan` objects instead of `DjTransitionPlanItem` objects.

### With RK3588 `engine.py`

The existing engine already handles per-stem gain via `_read_deck_styled()` and EQ/filter via `_apply_style_effects()`. To consume the new `TransitionPlan` format directly:

1. Parse `curves` into gain arrays per stem per block
2. Apply `low_eq/mid_eq/high_eq` as `Deck.set_eq()` calls
3. Apply `highpass/lowpass` as `Biquad.set_hpf/set_lpf()` calls
4. Apply `echo_send` as echo buffer mix
5. Apply `mute` as stem bypass

---

## 13. Known Limitations

1. **Offline renderer (`render_transition_plan`)**: EQ/filter curves (low_eq, highpass, lowpass) are skipped — they need biquad implementation. Currently the renderer only applies gain curves.
2. **Echo renderer**: Echo send is simplified to gain-only in the offline path. Full echo requires a delay line implementation matching the RK3588 engine's `_echo_process()`.
3. **Loop bridge preset**: Assumes `A.drums` is loopable but doesn't validate this programmatically — it's a suggestion in the transition plan for the RK engine to execute.
4. **Vocal density estimation**: Currently set manually. Future: auto-estimate from stem RMS analysis.
5. **Bass energy estimation**: Same as vocal density — manual for now.
6. **`non_stem_curves()`**: Currently returns `fallback_crossfade` for all non-stem modes. Should use the preset-specific `_fallback_fn` instead for richer non-stem transitions.
7. **Stem quality scoring**: Hardcoded to 0.85 when stems exist. Future: compute from separation artifact analysis.

---

## 14. Next Steps

1. **Integrate into `generate_dj_mix_plan()`** — Replace `DjTransitionPlanItem` with `TransitionPlan` in the mix plan output
2. **Add stem quality estimation** — Analyze stem RMS, bleed, artifacts
3. **Implement EQ/filter in offline renderer** — Port Biquad from `dsp.py` to the Jetson offline renderer
4. **Add echo delay line to offline renderer** — Match RK3588's `_echo_process()`
5. **Implement RK3588 `TransitionPlan` executor** — Parse the new JSON format in the engine callback
6. **Deploy Jetson-side RQ worker** — Stems pipeline (from HANDOFF-v2)
7. **Benchmark with real stems** — Run A/B comparison on actual separated tracks
