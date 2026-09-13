# Mobile DJ Control

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

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
