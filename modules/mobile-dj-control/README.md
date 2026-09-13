# Mobile DJ Control

> **第一版实现（含后续维护版本），仅保留供评估。第二版不一定需要，是否复用必须由对应负责人确认。**
> **第二版采用状态：待确认。** 未确认前，不列为必做功能，不默认接入或部署，不以其旧接口约束新 APK。
> 这里的“第一版”指产品代际，不是把包版本改为 1.0；版本来源及职责见 [当前模块清单](../REGISTRY.md)。

Version `0.2.0` adds a pure task lifecycle with explicit transition identity,
pair stability, legal state changes and pending TTL. It does not use a global
UI lock. Fast, energy and style continue to share one execution request and
differ only in target selection and trigger metadata.

This pure Dart module extracts the mobile contract that was previously buried
inside `dj_control_page.dart`.

Fast cut, confirmed energy cut, and confirmed style cut all produce the same
orchestration request. Their only execution differences are the trigger and
the already-selected target song. Energy/style preview remains selection-only
and cannot render, sync, prepare, or schedule anything.

The module also owns typed RK task parsing, pending-operation serialization,
and playback confirmation. Flutter widgets, HTTP clients, polling, local
storage, and queue mutation remain adapters outside this module.

## Test

```powershell
dart run modules/mobile-dj-control/tests/mobile_dj_control_test.dart
```
