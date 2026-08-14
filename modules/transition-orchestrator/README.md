# Transition Orchestrator

Version `0.3.0` adds the clean control-plane operation contract on top of the
typed task states introduced in `0.2.0`. Repeating the same request returns
the existing operation; reusing the same request ID for different content is
a structured conflict and never overwrites state.

This module is the protocol boundary for a manual transition. It validates a
plan and its pair manifest, creates the priority sync request, accepts one
operation idempotently, and records the state machine used by the RK edge
agent.

The module deliberately has no network, filesystem, audio, or device code.
Callers provide current playback and clock values, then pass the generated
sync request to `asset-sync` and the validated plan to the device runtime.

Supported operation states:

```text
accepted -> syncing -> cache_ready -> prepared -> scheduled
accepted -> prewarmed
accepted -> failed | expired | cancelled
```

The clean operation lifecycle is separate from the compatibility task contract:

```text
accepted -> source_snapshot -> planned -> rendered_or_reused
         -> target_audio_ready -> pair_synced -> prepared -> scheduled
         -> executing -> resumed
```

`auto`, `fast`, `energy`, and `style` share this lifecycle. Energy and style
require an already confirmed target song; fast and auto may defer target
selection to the server executor. Persistence and HTTP remain adapters.

## Test

```powershell
$env:PYTHONPATH = "modules/transition-orchestrator/src"
py -m pytest -q modules/transition-orchestrator/tests
```
