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

## Acceptance rules

- Every accepted commit must be reachable from its module branch and tag.
- Tests must pass from a fresh clone of the remote branch.
- Deployment probes must be read-only until a module-specific integration gate
  is approved.
- Existing production files and environments remain protected until all core
  modules pass a fresh-environment end-to-end replay.
