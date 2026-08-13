# Functional module registry

This registry tracks independently extracted modules. `accepted` means the
module passed a fresh-clone test and immutable tag check. It does not mean the
module has replaced production code.

| Module | Version | Branch | Fresh-clone tested implementation | Tests | Status | Production integration |
|---|---|---|---|---:|---|---|
| `observability-e2e` | `0.1.0` | `module/observability-e2e` | `53e8736961a0cd8251a6c3f8c7ad5f016e8b2b02` | 7 | tested, pushed, accepted | Read-only tools; no runtime replacement |
| `device-runtime` | `0.1.0` | `module/device-runtime` | `523d0053c145a9e70541505308f44a555bcd742e` | 20 | tested, pushed, accepted | Adapter and dual-read migration still required |
| `library-catalog` | `0.1.0` | `module/library-catalog` | `56d92b37a61bb9ed606d94f9f254ca575ba567db` | 8 | tested, pushed, accepted | Authenticated mobile replay still required |
| `audio-preprocess` | `0.1.0` | `module/audio-preprocess` | `237ee91b7336613ff1fae54c0567c78261c8f19a` | 7 | tested, pushed, accepted | 43/43 real Jetson payloads pass gate; production replacement not applied |
| `stem-separation` | `0.1.0` | `module/stem-separation` | `e9e3f515ea80dbb6a78ba92a995c66ba3bae281a` | 5 | tested, pushed, accepted | 42/43 songs have four stems; one remains unprocessed |
| `sequence-planner` | `0.1.0` | `module/sequence-planner` | `f54e38dfaad09e586d8d52fe3d95cdaa0f3650ae` | 5 | tested, pushed, accepted | 43 input, 30 default-compatible output in 168ms; production replacement not applied |
| `transition-planner` | `0.1.0` | `module/transition-planner` | `b276cff9193cd13b46e304a28232958c51f9f1d4` | 4 | tested, pushed, accepted | Four plan entry points match current production planner; Jetson production replacement not applied |
| `transition-renderer` | `0.1.0` | `module/transition-renderer` | `f903c5b22bb9d79f5f911b831558809fcd3253ca` | 3 | tested, pushed, accepted | v7 fast-cut and v9 normal WAV/meta paths pass; Jetson replacement not applied |
| `asset-sync` | `0.1.0` | `module/asset-sync` | `d8a8c5a3aeca3154e14466c459573a0e562d6e5d` | 6 | tested, pushed, accepted | Manifest, cache, atomic download, cancellation and priority sync paths pass; RK SSH probe blocked by legacy KEX |
| `transition-orchestrator` | `0.1.0` | `module/transition-orchestrator` | `423a65e9b620ba4b54741edfb2a481bf9ee566ac` | 5 | tested, pushed, accepted | Pure plan/manifest validation, priority sync request and task state machine; production replacement not applied |
| `audio-runtime` | `0.1.0` | `module/audio-runtime` | pending | 22 | extracted, local runtime tested | Real RK dual-deck engine, render prepare/schedule/sample-clock trigger/resume and socket contract; systemd replacement not applied |

## Acceptance rules

- Every accepted commit must be reachable from its module branch and tag.
- Tests must pass from a fresh clone of the remote branch.
- Deployment probes must be read-only until a module-specific integration gate
  is approved.
- Existing production files and environments remain protected until all core
  modules pass a fresh-environment end-to-end replay.
