# Transition Orchestrator

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

## Test

```powershell
$env:PYTHONPATH = "modules/transition-orchestrator/src"
py -m pytest -q modules/transition-orchestrator/tests
```
