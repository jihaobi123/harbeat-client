# Transition Orchestrator

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

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
