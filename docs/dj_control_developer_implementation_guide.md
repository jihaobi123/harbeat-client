# HarBeat DJ Control Developer Guide

This document describes the currently deployed DJ Control implementation across
the mobile app, Jetson backend, and RK3588 edge runtime.

## Runtime Status

Current verified deployment targets:

- Mobile package: `com.uhi.monitorplusflutter.gstore`, `versionName=1.4.9`, `versionCode=35`
- Jetson backend: `root@100.87.142.21:/home/mark/harbeat`
- RK3588 runtime: `cat@192.168.43.7:/home/cat/cypher`

Health checks:

```bash
ssh root@100.87.142.21 "curl -fsS http://127.0.0.1:8000/health"
curl http://192.168.43.7:9000/state
adb devices
```

Verified runtime snapshot on 2026-06-20:

- Mobile ADB device: `130ddcca`, app id `com.uhi.monitorplusflutter.gstore`, `versionName=1.4.9`, `versionCode=35`
- Jetson service: `harbeat-api` is active at `/home/mark/harbeat`, health endpoint returns `status=ok`
- RK3588 services: `cypher-audio-engine` and `cypher-edge-agent` are active at `/home/cat/cypher`
- RK3588 state endpoint: `http://127.0.0.1:9000/state`; do not use `8080` for runtime state checks
- The deployed Jetson hashes matched the local source for `dance_style.py`, `cut_strategy.py`, `eq_transition_strategy.py`, `auto_mixer/strategy_selector.py`, `auto_mixer/mixing_strategies.py`, and `spotify_mix/section_matcher.py`
- The deployed RK hashes matched the local source for `audio-engine/engine.py`, `edge-agent/main.py`, and `sync-worker/main.py`

## High-Level Flow

The three cut modes only decide the target song and timing. The actual audio
handoff is centralized:

```text
Mobile cut action
  -> Jetson /api/dj/cut/plan or /api/dj/transitions/plan
  -> section_match transition planning
  -> AutoMixer five-strategy EQ-band plan
  -> mobile sends transition_plan to RK edge-agent /xfade
  -> edge-agent forwards xfade_eq_band_mix
  -> RK audio-engine manual_eq_band_mix()
```

Normal successful execution should show:

```text
transition_mode = section_match
execution_mode = eq_band_mix
style / playback_tier = eq_band_mix
degraded = false
```

## Five EQ-Band Strategies

The package strategies live in:

- `app/modules/dj_control/auto_mixer/strategy_selector.py`
- `app/modules/dj_control/auto_mixer/mixing_strategies.py`
- `app/modules/dj_control/eq_transition_strategy.py`

Strategy selection:

```text
1 standard_blend: similar energy and compatible features
2 energy_lift: incoming song energy is much higher
3 energy_drop: incoming song energy is much lower
4 tempo_compat: BPM difference is large
5 cross_style: low/mid/high frequency distribution differs strongly
```

`mixing_strategies.py` converts the original five strategy curves into RK-ready
low/mid/high dB automation. RK executes the plan against original MP3/PCM audio.
Stems are not required for frequency mixing.

Important runtime choice:

- Fixed `-6 dB` master headroom has been removed.
- Jetson now emits `safety.headroom_db = 0`.
- RK `eq_band_mix` now mixes with `main = a + b` to match the offline
  `auto_dj_mix.py` renderer more closely.

## Section Matching

The section matcher is in:

- `app/modules/dj_control/spotify_mix/section_matcher.py`
- `app/modules/dj_control/spotify_mix/beat_bar_points.py`
- `app/modules/dj_control/spotify_mix/section_scorer.py`

Despite the historical folder name, this is local MP3 analysis and does not use
Spotify APIs.

Point selection priority:

```text
1. Stem-enhanced transition point data, if present
2. MP3 beat/bar analysis from original audio
3. Existing phrase_map fallback
```

The exact overlap window is scored for:

- Double-vocal conflict
- One-sided vocal allowance
- Exit point too close to the end
- Downbeat snapping
- Section compatibility

Human-sensible rule: vocals are allowed, but double vocals are penalized or
rejected.

## Cut Modes

### Fast Cut

Mobile sends a standard cut request. Jetson chooses the next song and a fast
cut point with `cut_strategy.plan_cut("fast_cut")`.

Before execution, mobile requests or ensures a section-match transition for:

```text
current song -> selected next song
```

Then it sends that `eq_band_mix` transition plan to RK.

### Energy Cut

Mobile calls:

```text
POST /api/dj/cut/plan
intent = target_energy_bucket
```

Jetson uses `plan_target_energy_cut()` to choose the candidate. It weights:

- Target section energy
- Whole-song energy
- Current style compatibility
- BPM compatibility
- Cache status
- Transition window safety

If a chosen entry segment does not create double-vocal overlap, Jetson overrides
the section-match `to_at_sec` with that segment entry.

Mobile executes the returned `prepared_transition`.

### Style Cut

Mobile calls:

```text
POST /api/dj/cut/plan
intent = target_dance_style
```

Jetson uses `plan_target_style_cut()` and reads:

- `dance_style_scores`
- `genre_profile.style_evidence_v1`
- `manual_primary_style`

The current deployed styles are:

```text
breaking, hiphop, jazz, popping, locking, house, krump, waacking
```

After target selection, Jetson attaches a `prepared_transition` using the same
section-match plus five-strategy EQ-band path.

## Mobile Responsibilities

Main files:

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/api_client.dart`
- `mobile/lib/src/edge_agent_client.dart`
- `mobile/lib/src/sync_worker_client.dart`

Key functions:

- `_planSectionMatchTransition()`: requests Jetson `transition_mode=section_match`
- `_assertRealSectionMatchPlan()`: rejects fake/fallback plans
- `_edgeXfadeFromPlan()`: sends `transition_mode=eq_band_mix` and full
  `transition_plan` to RK
- `_v32FadeSec()`: preserves the strategy duration and enforces a minimum for
  EQ-band plans

The UI shows recent execution details:

- RK actual tier
- Prepared plan debug
- Last executed plan debug

## Jetson Responsibilities

Main files:

- `app/modules/dj_control/router.py`
- `app/modules/dj_control/cut_strategy.py`
- `app/modules/dj_control/eq_transition_strategy.py`
- `app/modules/dj_control/auto_mixer/*`
- `app/modules/dj_control/spotify_mix/*`
- `app/modules/library/analysis_vocal_patch_gpu.py`

Data used by the current runtime:

```text
source_path / original MP3
bpm
energy
beat_points
downbeats
phrase_map
vocal_events as {start,end,confidence}
music_features.dj.low_ratio / mid_ratio / high_ratio
dance_style_scores
genre_profile.style_evidence_v1
```

Optional enhancement fields:

```text
energy_curve
transition_windows
stem_activity_windows
bass_risk_windows
bpm_curve
stem_quality_profile
```

The runtime can operate without stems. Stem-derived data is only a better cut
point source when it exists.

## RK3588 Responsibilities

Main files:

- `cypher-integration/rk3588-edge/edge-agent/main.py`
- `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py`
- `cypher-integration/rk3588-edge/audio-engine/socket_server.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`
- `cypher-integration/rk3588-edge/sync-worker/main.py`

Edge-agent behavior:

- `/xfade` receives mobile requests.
- If `transition_mode=eq_band_mix` and `transition_plan` exists, it forwards
  `xfade_eq_band_mix`.
- Ordinary xfade is only a degraded fallback, and should be surfaced as degraded.

Audio-engine behavior:

- `manual_eq_band_mix()` loads the target original audio.
- The callback evaluates deck A/B low/mid/high automation per audio block.
- The output is `main = a + b` for EQ-band plans.
- The engine rejects self-transition.

## Library Data Snapshot

Current checked library size: `23` songs.

Available for all 23:

```text
BPM
energy
beat_points
downbeats
phrase_map
low/mid/high ratio
dance_style_scores
```

Mostly missing optional fields:

```text
energy_curve
transition_windows
stem_activity_windows
stem_activity
bass_risk_windows
bpm_curve
dj_hot_cues
```

Known stale item:

- `Do For Love - 2Pac` still has old `enter/exit` vocal marker data instead of
  range-format `{start,end,confidence}`.

Recommended data maintenance order:

```text
1. Backfill vocal_events range format for stale songs.
2. Backfill MP3 band features if new songs are imported.
3. Add energy_curve / transition_windows for better section selection.
4. Add stem_activity_windows only when stem analysis is intentionally enabled.
```

Useful scripts:

- `scripts/backfill_vocal_events.py`
- `scripts/backfill_mp3_band_features.py`
- `scripts/backfill_complete_analysis.py`

## Adding A New Style

To add another style:

1. Add it to `STYLE_PROFILES` in `dance_style.py`.
2. Add a fingerprint in `STYLE_FINGERPRINTS`.
3. Add tag signals in `STYLE_TAG_SIGNALS`.
4. Add reference tags in `style_reference_profiles.py`.
5. Add taxonomy tags in `style_taxonomy.py`.
6. Add it to the style reserve default list in `cut_strategy.py`.
7. Add a mobile button if the style should be directly selectable.
8. Backfill `dance_style_scores` or `style_evidence_v1` for existing songs.

## Deployment Commands

Jetson:

```bash
scp app/modules/dj_control/<file>.py root@100.87.142.21:/tmp/
ssh root@100.87.142.21 "cp /tmp/<file>.py /home/mark/harbeat/app/modules/dj_control/<file>.py"
ssh root@100.87.142.21 "systemctl restart harbeat-api"
```

RK:

```bash
scp cypher-integration/rk3588-edge/audio-engine/engine.py cat@192.168.43.7:/tmp/engine.py
ssh cat@192.168.43.7 "cp /tmp/engine.py /home/cat/cypher/audio-engine/engine.py"
ssh cat@192.168.43.7 "printf 'temppwd\n' | sudo -S systemctl restart cypher-audio-engine"
```

Mobile:

```bash
cd mobile
flutter analyze
flutter build apk --debug
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

## Verification Checklist

```bash
# Jetson
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/dj/styles

# RK
curl http://192.168.43.7:9000/state

# Mobile
adb devices
adb shell dumpsys package com.uhi.monitorplusflutter.gstore | grep versionName
```

During a real transition, confirm:

```text
transition_mode=section_match
execution_mode=eq_band_mix
strategy_num in 1..5
degraded=false
actual tier eq_band_mix
```
