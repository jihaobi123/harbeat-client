# Audio Runtime

> 本目录已同步远端后续实现；不等于已接入当前第二版。部署职责与采用状态以 [当前模块清单](../REGISTRY.md) 为准。
> 本模块的旧手机/预渲染合同不是新 APK 接口要求。

Version `0.2.0` adds a pure command-contract layer before the real RK engine.
Prepare, schedule and immediate playback now share strict pair/song/time
validation. The real-time callback, sample clock and sounddevice path are not
rewritten in this version.

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
