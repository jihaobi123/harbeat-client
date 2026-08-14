# Legacy Core Behavior Reconstruction Specification

Date: 2026-08-15
Scope: information required to reproduce the legacy core after deleting its source

This document records behavior and deployment facts, not legacy source code. It
contains no passwords, API keys, or database connection values.

## 1. Device Roles

| Device | Legacy responsibility | Data it must retain |
|---|---|---|
| Jetson | PostgreSQL-facing catalog and analysis; raw audio analysis; Demucs separation; transition planning; WAV/meta rendering | NAS originals, v2 analysis rows, stems, model assets, CUDA/FFmpeg, PostgreSQL access |
| RK3588 | audio device, cached original/render assets, prepare/schedule, playback and physical input adapter | ALSA card configuration, FFmpeg, audio runtime assets, cache layout |
| Phone | UI and control requests | no core algorithm or analysis state |

The legacy phone-to-RK resource pipeline is deliberately not part of this
reconstruction. It is the deferred v2 backend boundary.

## 2. Raw-Audio Analysis Behavior

The old Jetson analysis accepted an original audio path and optional title and
artist metadata. It produced BPM, duration, beat points, downbeats, phrase map,
energy curve, loudness/groove information, key and Camelot key, plus DJ feature
profiles. The intended engines were:

| Feature | Legacy engine/behavior |
|---|---|
| BPM and beat/downbeat | Essentia rhythm extraction (`essentia_rhythmextractor2013`) |
| Key and mode | Essentia key profile; Camelot conversion |
| Loudness | pyloudnorm plus measured RMS/loudness windows |
| Additional spectral features | librosa/numpy/soundfile |
| Full fallback behavior | present in the old app, but the clean acceptance path rejects fallback |

The clean replacement preserves the algorithm snapshot from the old
`analysis.py` and adds a standalone pipeline. A valid result requires non-empty
beat points, downbeats, phrase map and energy windows, numeric BPM/duration,
Camelot key, and engine provenance.

## 3. v2 Candidate Generation

The structural stage consumes beat/downbeat/phrase boundaries and produces
beat, bar, phrase and phrase-change boundaries plus Track1 exit and Track2
entry candidates.

Candidate metadata includes local RMS, entry/exit RMS, vocal sparsity,
drum strength/stability, immediate punch, handoff readiness, tail RMS and a
combined score. The required source marker is
`dj_structure_precomputed_window_v2`.

The fast-cut planner uses the current playback cursor plus the requested live
window. It selects a Track1 exit candidate inside the window and a Track2 entry
candidate from persisted v2 data. It does not scan the entire audio file during
planning and it must fail typed when v2 data is missing. Energy/style selection
chooses the target song outside this core planner; once selected, it uses the
same planning and render contract.

## 4. Transition and Render Contract

The planner returns a renderer-neutral plan containing pair id, mode, from/to
positions, alignment, resume position and default-mix metadata. Manual fast cut
requires:

```text
audio_feature_source = dj_structure_precomputed_window_v2
renderer = three_band_default_v7_standalone_curve_no_energy_floor
fallback = false
degraded = false
```

The renderer reads local windows from both source files, aligns beat/onset
phase, applies overlap-only tempo correction when needed, mixes low/mid/high
bands with deterministic curves, searches the resume position, then writes a
WAV and JSON metadata. It does not choose songs, download assets, or control
RK.

Expected render metadata includes `from_at_sec`, `to_at_sec`, `resume_at_sec`,
renderer version, source marker, sample rate, frame count, timing and cache
paths. Repeated rendering of the same pair must produce identical WAV bytes.

## 5. Legacy Facts Worth Preserving

- Jetson legacy source: `/home/mark/harbeat`, Git HEAD
  `79f288deb5f86081c7ba0d85432f7bb783abb05d`.
- RK legacy source: `/home/cat/cypher`, Git HEAD
  `f9c6797ad7738a06f10f73133cacb5b9dc9c5850`.
- Legacy venvs: `/home/mark/venvs/harbeat` and `/home/cat/venvs/edge`.
- Legacy source and venvs are not runtime prerequisites for clean core.
- Pre-delete file snapshot: `D:\work\harbeat-device-backups\20260815-core-preservation`.
- Snapshot manifest: `sha256-manifest.json`, 299 files, 3,914,548 bytes.
- PostgreSQL/NAS/stem/v2 data are retained; secrets are migrated to
  `/etc/harbeat/secrets/runtime.env` with root-only permissions.
- Locked htdemucs artifact: `955717e8-8726e21a.th`, SHA256
  `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.

## 6. Deletion Map

After clean-core acceptance, delete only legacy business runtime material:

| Delete | Keep |
|---|---|
| `/home/mark/harbeat` | `/opt/harbeat/releases/core-v0.5.0` and `current` |
| `/home/mark/venvs/harbeat` | Python system runtime, CUDA, FFmpeg, drivers |
| `/home/cat/cypher` | `/opt/harbeat/releases/core-v0.5.0` and ALSA/audio restore |
| `/home/cat/venvs/edge` | PostgreSQL, NAS mounts, originals, stems, v2 data |
| old business units, targets and caches | `/etc/harbeat`, `/var/lib/harbeat`, model assets and manifests |

Do not delete `.cache/torch` until the NAS model artifact hash has been checked.
Do not delete PostgreSQL or NAS data as part of source cleanup.

