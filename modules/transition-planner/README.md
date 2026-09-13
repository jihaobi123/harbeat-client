# Transition Planner

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

This is the independently testable planning layer extracted from the deployed
Jetson DJ control path. It keeps the same four plan entry points used by the
current backend:

- `plan_default_transition`: ordinary automatic handoff
- `plan_fast_cut_transition`: live Track1 exit window plus persisted v2 Track2 candidates
- `plan_target_energy_transition`: selected target song with stable-section energy constraint
- `plan_target_style_transition`: selected target song with style contrast metadata

Energy and style selection happen outside this module. Once a target song is
chosen, both paths use this module for the same exit, entry, beat alignment,
and default-render metadata logic.

The module is intentionally renderer- and device-neutral. A caller must pass
the returned plan to a renderer/sync/orchestration module. It never calls an
HTTP endpoint, decodes audio during normal precomputed planning, or controls
RK playback.

## Test

```powershell
$env:PYTHONPATH = "modules/transition-planner/src"
py -m unittest discover modules/transition-planner/tests -v
```
