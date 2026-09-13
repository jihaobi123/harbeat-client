# Asset Sync

> **第一版实现（含后续维护版本），仅保留供评估。第二版不一定需要，是否复用必须由对应负责人确认。**
> **第二版采用状态：待确认。** 未确认前，不列为必做功能，不默认接入或部署，不以其旧接口约束新 APK。
> 这里的“第一版”指产品代际，不是把包版本改为 1.0；版本来源及职责见 [当前模块清单](../REGISTRY.md)。

Version `0.2.0` extracts cache validation and atomic publication into a pure
core used by the current worker. HTTP, curl and FastAPI remain transport
adapters; weak-network retry behavior is intentionally unchanged in this
refactor.

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
