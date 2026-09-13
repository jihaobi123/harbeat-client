# Asset Sync

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

This module is the deployed RK sync-worker extracted as an independent
component. It expands song and default-mix manifests, downloads only declared
assets, validates size and SHA256 when supplied, writes through `.part` files,
publishes atomically, records sidecars and timings, and reuses valid cache
entries. Pair caches are invalidated when renderer/planner metadata no longer
matches the manifest.

The worker supports priority replacement of rolling sync and cancellation for
a user-triggered manual transition. It does not select songs, render audio, or
control the RK audio engine.

## Test

```powershell
$env:PYTHONPATH = "modules/asset-sync/src"
py -m pytest -q modules/asset-sync/tests
```
