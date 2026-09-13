# Audio Runtime

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

This module contains the currently deployed RK dual-deck audio engine and Unix
socket command layer, extracted as a package. Internal imports are the only
runtime code changes from the source copy.

For default-render transitions it owns:

- predecoding the transition render and target resume deck;
- validating v2/v7 or v2/v9 metadata;
- scheduling against the active deck's local sample clock;
- triggering the render at the planned Track1 point;
- resuming Track2 without zero padding;
- idempotent scheduling for a repeated pair.

It does not plan or render transitions, download assets, expose mobile HTTP,
or map physical keys. The extracted package has not replaced the RK systemd
service.

## Test

```powershell
$env:PYTHONPATH = "modules/audio-runtime/src"
py -m pytest -q modules/audio-runtime/tests
```

The tests substitute a no-device `sounddevice` implementation and write only
temporary WAV fixtures. No physical audio output is opened.
