# Stage E mobile-to-RK contract and switch plan

Date: 2026-08-14

## Decision

The clean RK edge service is a transport adapter. It must not contain song
selection, transition planning, rendering, DSP, cache download, or physical
key policy. Those responsibilities remain in their extracted modules.

Production ports `9000` and `9100` stay unchanged until the spare-port mobile
E2E gate passes. The old environment remains read-only reference material and
is not copied into the clean release.

```text
production_ready = false
cleanup_authorized = false
```

## Contract audit

The audit compares the deployed mobile calls, production RK OpenAPI, and the
clean module command contracts.

| Interface group | Mobile use | Clean owner | Decision |
|---|---|---|---|
| `/state` and aliases | Progress, current song, transition reconciliation | `audio-runtime` through edge adapter | Required |
| `/play`, `/pause`, `/resume`, `/seek` | Library and DJ transport | `audio-runtime` | Required |
| `/stem_solo` | Song detail stem audition | `audio-runtime` | Required |
| `/trigger` | App emulation of physical sample keys | `audio-runtime` | Required |
| `/xfade` | Existing non-render transition path | `audio-runtime` | Required until mobile migration removes it |
| `/prefetch`, `/cache/validate` | Decode and cache validation | `audio-runtime` | Required |
| `/autoplay/default/start` | Start normal automatic playback | `audio-runtime` | Required |
| `/autoplay/default/prefetch` | Predecode queue and render pairs | `audio-runtime` | Required |
| `/autoplay/default/render` | Execute a prepared automatic render | `audio-runtime` | Required |
| `/autoplay/default/render/orchestrate` | Fast, energy and style cut after target selection | `transition-orchestrator` + `asset-sync` + `audio-runtime` | Required |
| Orchestration GET/DELETE | Mobile polling, recovery and cancellation | edge adapter task store | Required |
| Sync `/sync`, `/status`, `/cache/check` | Song and pair transfer | `asset-sync` | Required on port 19100/then 9100 |
| Direct render prepare/schedule endpoints | Compatibility and diagnostic scripts | `audio-runtime` | Keep during Stage E |
| `/next`, `/prewarm_beatmatch`, `/load_plan` | Legacy or diagnostic flow | clean modules | Keep during Stage E, remove only after telemetry proves unused |
| `/live/override`, `/live/intent` | Separate live-deck screen, absent from production RK OpenAPI | No valid RK owner yet | Do not silently emulate; defer as a separate feature |
| `/beat_reinforce` | Client method exists but no deployed call; engine reports unsupported | None | Explicitly unsupported, candidate for removal |
| Pairing aliases and session event flush | Not part of the four acceptance workflows | Device/runtime service | Defer |
| Realtime EQ/filter/loudness HTTP routes | No active mobile call in audited workflows | `audio-runtime` has commands | Add only when a real UI contract is accepted |

## Clean request path

Normal transport:

```text
mobile HTTP -> clean edge adapter -> audio-runtime Unix socket -> audio device
```

Fast, energy and style transition after target selection:

```text
mobile POST orchestration
  -> validate v2/v7 plan and pair manifest
  -> read current audio sample-clock state
  -> asset-sync priority pair download when absent
  -> audio-runtime prepare_default_render
  -> verify source song and remaining lead again
  -> audio-runtime schedule_default_render
  -> persist scheduled task
  -> reconcile executed state from audio-runtime
```

The three manual modes differ only in target-song selection and `trigger`.
They use the same pair sync, prepare and schedule path.

## Isolation rules

- `state_root` is private service state.
- `asset_root/cache` is the only shared song/render cache.
- Edge never reads a legacy cache path.
- Sync and audio services receive the same `asset_root` as `CYPHER_HOME`.
- Transition tasks are atomically persisted under the clean edge state root.
- A repeated transition ID with identical content reuses the task.
- A repeated transition ID with different content returns HTTP 409.
- Production ports are not rebound during spare-port validation.

## Direct execution order

1. Run all clean adapter and 13-module tests.
2. Stage the clean packages and configs into a new RK release directory.
3. Start edge on port 19000 against the current audio/sync protocol, without
   changing production ports. Then replace sync and audio one at a time; the
   fully clean stack uses ports 19000/19100 and a dedicated socket.
4. Run route contract, cache, prepare, schedule and idempotency probes.
5. Build a test APK whose RK/sync endpoints use the spare ports.
6. Run real mobile playback and automatic transition 5/5.
7. Run fast cut 5/5, then energy cut 5/5, then style cut 5/5.
8. Test repeat taps, hotspot interruption, process restart and damaged cache.
9. Switch one production service at a time with a rollback command recorded.
10. Run the same E2E gate again on production ports.

## Delivery gate

Stage E passes only when all of the following are evidenced:

- Mobile transport state remains continuous and does not freeze during work.
- Automatic, fast, energy and style transitions each pass 5/5.
- Fast cut ready time is at most 12 seconds and transition starts within 15 seconds.
- Trigger error is at most 100 ms and no accepted plan is degraded or fallback.
- Failed manual work leaves automatic playback usable.
- Repeated taps create one effective schedule.
- Weak-hotspot recovery does not require changing the RK address.
- Spare-port activate and rollback both succeed.

Passing this document does not authorize old-environment cleanup. Stage F,
physical input, empty-image rebuild and a full rollback rehearsal remain
mandatory.
