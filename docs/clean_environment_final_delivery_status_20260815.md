# HarBeat Clean Environment Delivery

Date: 2026-08-15
Branch: `rewrite/clean-core-operation-v0.4`
Release: `core-v0.4.2`

## Final Result

The two requested steps are complete:

1. Cleanup: temporary build outputs, temporary device staging inputs, stale Jetson NAS mount behavior, and legacy runtime autostart were handled safely.
2. Execution: PostgreSQL/NAS recovery gates, clean wheel installation, hardware checks, core transition acceptance, activation/rollback drills, and legacy runtime isolation passed.

The result is a clean, installed, isolated core environment. It is not declared production-ready because the phone resource pipeline and full three-device product E2E are intentionally deferred to v2.

## Delivered Gates

| Gate | Result |
|---|---|
| PostgreSQL dump and isolated restore | Passed; 13 tables and exact row counts match |
| Library and v2 coverage | 43/43 songs, 43/43 v2, Track1/Track2 candidates present |
| NAS source coverage | 43/43 original files |
| Declared stem coverage | 168/168 files; 1 song has no stem manifest and is recorded for backfill |
| Internal wheels | 12/12 installed on both devices |
| Jetson third-party wheels | 65 Linux ARM64 CPython 3.10 wheels; incompatible Windows wheels rejected |
| RK third-party wheels | 21 Linux ARM64 wheels |
| Jetson CUDA/Demucs | CUDA Orin, Torch, torchaudio, Demucs smoke passed |
| RK audio | ES8388 card 2, 11 audio devices, FFmpeg 6.1 and monotonic clock passed; legacy socket is absent as expected after isolation |
| Core planner | 20/20 deterministic plans |
| Core renderer | 5/5 WAV outputs; identical WAV SHA256 |
| Activation/rollback | 3 cycles passed on Jetson and RK |
| Legacy runtime after reboot | Inactive and disabled; old source/venv retained |
| NAS after reboot | Automount waits for network and mounts on first access |
| 2026-08-15 final device recheck | Both releases resolve to `core-v0.4.2`; Jetson PostgreSQL/NAS/CUDA and RK card 2/FFmpeg/12 wheel imports passed |

Core acceptance output:

```text
audio_feature_source=dj_structure_precomputed_window_v2
renderer_version=three_band_default_v7_standalone_curve_no_energy_floor
fallback=false
degraded=false
from_at_sec=11.029
to_at_sec=27.494
resume_at_sec=33.992
```

Cold render was 27.92 seconds on the first uncached run. Subsequent runs were 0.23-0.79 seconds with OS file cache. This is an offline core-render measurement, not a 15-second phone-to-RK SLA. Resource pull, prewarm, weak-hotspot recovery, scheduling and full auto/fast/energy/style E2E remain v2 scope.

## Device Responsibilities

| Device | Current clean responsibility |
|---|---|
| Phone | Not connected to the clean runtime in this release; v2 control/resource pipeline |
| Jetson | Core planner, v7 renderer, CUDA/Demucs environment, PostgreSQL/NAS access |
| RK3588 | Audio hardware/runtime dependencies and future prepare/schedule integration |

Clean release paths on both devices:

```text
/opt/harbeat/releases/core-v0.4.2
/opt/harbeat/current -> /opt/harbeat/releases/core-v0.4.2
/etc/harbeat
/var/lib/harbeat
/srv/harbeat-assets
```

## Evidence

- Stage B: `deploy/clean-environment/evidence/stage-b/data-backup-acceptance-20260815.json`
- Stage D: `deploy/clean-environment/evidence/stage-d/clean-release-deployment-acceptance-20260815.json`
- Stage E: `deploy/clean-environment/evidence/stage-e/core-transition-acceptance-20260815.json`
- Stage F: `deploy/clean-environment/evidence/stage-f/legacy-runtime-isolation-20260815.json`
- Final device recheck: `deploy/clean-environment/evidence/stage-f/final-device-recheck-20260815.json`
- Restore procedure: `docs/clean_environment_data_restore_procedure_20260815.md`
- External WAV/meta, plan, database dump, NAS manifests and service snapshots: `D:\work\harbeat-device-backups\20260814`

## Rollback

The old source, venv, systemd unit files and recovery bundles remain available. Re-enable only the required old service after confirming the clean release is not being used:

```bash
sudo systemctl enable --now harbeat-api
sudo systemctl enable --now cypher.target
```

The old files were not permanently deleted. Intermediate external wheelhouse directories `locked-v2` and `locked-v3` are classified as delete candidates, while `locked-v4` is the canonical Jetson wheelhouse. Permanent deletion remains a separate approval gate.

## Release Status

```text
core_transition_algorithm_accepted=true
resource_pipeline_v2_required=true
legacy_r5_feature_acceptance_deferred=true
production_ready=false
legacy_runtime_quarantine_authorized=true
legacy_runtime_disable_authorized=true
legacy_files_delete_authorized=false
cleanup_authorized=false
```
