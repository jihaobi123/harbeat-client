# Asset Sync

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
