# HarBeat Functional Modules

This directory is the unified source tree for the 13 independently extracted
HarBeat functional modules.

## Version status

- Baseline version: `functional-modules/v0.1.0`
- Unified branch: `delivery/functional-module-extraction-20260813`
- Per-module branches: `module/<module-name>`
- Per-module immutable tags: `module/<module-name>/v0.1.0`
- Production status: extracted and independently tested; not yet wired in as
  the production runtime

Version `0.1.0` is a behavior-preserving baseline. It intentionally keeps the
currently verified behavior, including documented compatibility code. Clean
implementations must be released as later versions and must not rewrite this
baseline tag.

## Product function map

| Module | Product function | Runtime owner |
|---|---|---|
| `observability-e2e` | Cross-device tests, trace collection and diagnostics | Development/QA |
| `device-runtime` | Mobile-to-RK connection, identity and playback state | Mobile + RK |
| `library-catalog` | Library, playlist, song identity and asset manifests | Jetson + mobile |
| `audio-preprocess` | Beat, phrase, energy and transition-candidate analysis | Jetson |
| `stem-separation` | Demucs vocals/drums/bass/other separation | Jetson |
| `sequence-planner` | Automatic song ordering and energy curves | Jetson |
| `transition-planner` | Exit/entry selection and alignment for all transitions | Jetson |
| `transition-renderer` | Generate transition WAV and metadata | Jetson |
| `asset-sync` | Download and verify songs and transition packages | RK |
| `transition-orchestrator` | Sync/prepare/schedule task state machine | RK |
| `audio-runtime` | Real playback, dual decks and scheduled transition execution | RK |
| `mobile-dj-control` | Fast/energy/style cut intent and task recovery | Mobile |
| `physical-input` | Hardware keys, SFX and volume routing | RK |

## Start here

1. Read `modules/REGISTRY.md` for the accepted commit of every module.
2. Read the module's `MODULE.yaml` for inputs, outputs, dependencies and
   deployment boundary.
3. Read the module's `README.md` before changing its implementation.
4. Run the module health check before and after each change.
5. Run all module tests with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_functional_modules.ps1
```

Full developer handover:
`docs/functional_modules_v0_1_developer_handover_20260813.md`.

Clean-version execution rules:
`docs/functional_modules_clean_final_execution_plan_20260813.md`.

## Clone patterns

Clone the complete baseline:

```powershell
git clone https://github.com/jihaobi123/harbeat-client.git
cd harbeat-client
git checkout functional-modules/v0.1.0
```

Work on one module only:

```powershell
git clone --branch module/stem-separation `
  https://github.com/jihaobi123/harbeat-client.git harbeat-stem-separation
cd harbeat-stem-separation
git checkout module/stem-separation/v0.1.0
```

The repository remains a monorepo. A module branch limits the supported change
surface; it is not a separate repository or a production microservice image.

## Non-negotiable rules

- Never commit songs, stems, render WAV files, databases, model weights,
  credentials, device backups or production caches.
- Do not delete deployed source files merely because equivalent code exists in
  `modules/`.
- Do not silently fall back when a required versioned contract is missing.
- Keep planning, rendering, synchronization, orchestration and playback as
  separate responsibilities.
- Any clean rewrite must prove behavior parity against `v0.1.0` before it can
  replace production code.
