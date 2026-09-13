# Audio Runtime

> **第一版实现（含后续维护版本），仅保留供评估。第二版不一定需要，是否复用必须由对应负责人确认。**
> **第二版采用状态：待确认。** 未确认前，不列为必做功能，不默认接入或部署，不以其旧接口约束新 APK。
> 这里的“第一版”指产品代际，不是把包版本改为 1.0；版本来源及职责见 [当前模块清单](../REGISTRY.md)。

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
