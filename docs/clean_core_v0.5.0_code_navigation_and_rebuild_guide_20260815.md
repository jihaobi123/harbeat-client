# Clean Core v0.5.0 Code Navigation and Rebuild Guide

Date: 2026-08-15
Branch: `rewrite/clean-core-operation-v0.4`

## 1. What Is Delivered

The clean release contains 12 independently installable Python wheels. Source,
package metadata, tests and deployment locks are in this repository; target
wheelhouses are external artifacts with SHA256 manifests.

| Module | Package | Responsibility | Device |
|---|---|---|---|
| asset-sync | `harbeat-asset-sync` | asset manifest, download verification, atomic sync | Jetson/RK boundary |
| audio-preprocess | `harbeat-audio-preprocess` | raw MP3 analysis and `dj_structure_v2` candidates | Jetson |
| audio-runtime | `harbeat-audio-runtime` | deck state, DSP envelopes, default-render playback contract | RK |
| device-runtime | `harbeat-device-runtime` | endpoint, connection, session and operation state | device boundary |
| library-catalog | `harbeat-library-catalog` | song identity, catalog models and repository ports | Jetson |
| observability-e2e | `harbeat-observability-e2e` | trace/journal contracts across mobile/Jetson/RK | all |
| physical-input | `harbeat-physical-input` | entity buttons, key/action routing and trigger encoding | RK |
| sequence-planner | `harbeat-sequence-planner` | playlist sequence and compatibility constraints | Jetson |
| stem-separation | `harbeat-stem-separation` | offline Demucs four-stem separation and validation | Jetson |
| transition-orchestrator | `harbeat-transition-orchestrator` | operation lifecycle, manifest validation, executor ports | boundary |
| transition-planner | `harbeat-transition-planner` | default/fast/energy/style plan shapes and candidate rules | Jetson |
| transition-renderer | `harbeat-transition-renderer` | deterministic local-window WAV/meta rendering | Jetson |

Energy and style song ranking is outside transition planning. After a target
song is selected, both use the same transition plan and render path as fast cut.

## 2. Audio Analysis

Core source:

```text
modules/audio-preprocess/src/harbeat_audio_preprocess/base_analysis.py
modules/audio-preprocess/src/harbeat_audio_preprocess/pipeline.py
modules/audio-preprocess/src/harbeat_audio_preprocess/dj_structure_v2.py
modules/audio-preprocess/src/harbeat_audio_preprocess/service.py
```

The raw algorithm snapshot is `base_analysis.py`; `pipeline.py` is the clean
composition and validation boundary. Run on Jetson:

```bash
/opt/harbeat/current/venv/bin/harbeat-analyze-audio \
  /srv/harbeat-assets/music-files/shared/song.mp3 \
  --output /var/lib/harbeat/analysis/song.json \
  --require-essentia
```

The base package requires numpy. Jetson supplies the `analysis` extra from the
locked ARM64 wheelhouse: Essentia, librosa, pyloudnorm and soundfile. RK can
import the package without these analysis libraries.

## 3. Stem Separation

```bash
/opt/harbeat/current/venv/bin/python -m harbeat_stem_separation \
  ORIGINAL_AUDIO OUTPUT_ROOT \
  --model-repo /srv/harbeat-assets/models/demucs \
  --timeout-sec 120
```

The model directory must contain `htdemucs.yaml` and the locked
`955717e8-8726e21a.th`. The CLI publishes only complete vocals/drums/bass/other
sets and uses atomic file publication.

## 4. Planner and Renderer

```text
modules/transition-planner/src/harbeat_transition_planner/
modules/transition-renderer/src/harbeat_transition_renderer/
deploy/clean-environment/tools/validate_core_transition.py
```

`plan_fast_cut_transition` requires persisted v2 candidates and a live cursor
window. `plan_target_energy_transition` and `plan_target_style_transition`
share the same transition shape after target selection. The renderer writes
the WAV/meta pair into the configured pair cache. It never performs network
sync or RK control.

## 5. Dependencies and Rebuild

Locked files:

```text
deploy/clean-environment/locks/jetson.python.lock
deploy/clean-environment/locks/jetson.third-party-wheelhouse.json
deploy/clean-environment/locks/rk3588.python.lock
deploy/clean-environment/locks/rk3588.third-party-wheelhouse.json
```

Build internal wheels:

```powershell
& deploy/clean-environment/build-wheels.ps1 `
  -Output D:\artifacts\wheelhouse-core-v0.5.0 `
  -Release 0.5.0
```

Install with `deploy/clean-environment/tools/install_clean_release.sh` into an
empty `/opt/harbeat/releases/core-vX.Y.Z` directory. It requires exactly 12
internal wheels, a target third-party wheelhouse, both manifests and a passing
`pip check`. Never install from a legacy source tree or venv.

## 6. Acceptance Gates

- all module and deployment tests pass in per-module isolation;
- Jetson: Python 3.10/aarch64, 12 imports, CUDA/Orin, Demucs and NAS pass;
- RK: Python 3.10/aarch64, 12 imports, ALSA ES8388, FFmpeg and monotonic clock pass;
- raw audio analysis uses Essentia with no fallback on multiple real songs;
- planner is deterministic for 20 repeated runs;
- renderer produces 5 decodable outputs with identical WAV SHA256;
- missing v2, missing audio and unsupported renderer fail typed;
- explicit htdemucs model repository produces four real stems.

The clean core acceptance does not claim phone UI, hotspot resource pulling,
or full automatic/fast/energy/style product E2E. Those belong to the next
backend architecture and can consume these module contracts.

