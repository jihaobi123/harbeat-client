# Transition Renderer

> 历史抽取基线（2026-08-13），不是当前 V2 的已部署模块。下文的部署位置、合同和验收记录属于历史版本。
> 新开发先看 [V2 模块处置表](../../docs/repository/module-decisions.md) 与 [部署位置](../../docs/repository/deployment-map.md)，不要直接据此替换正式实现。

This module is the standalone local-window renderer extracted from the
deployed Jetson path. It reads only the required regions of the two source
audio files, aligns drum/onset phase, optionally applies a small overlap-only
tempo stretch, separates low/mid/high bands, applies deterministic curves,
matches local energy, searches the resume point, and writes WAV plus metadata.

The normal automatic path uses `three_band_default_v9_fast_phase_window`.
The verified manual fast-cut path uses
`three_band_default_v7_standalone_curve_no_energy_floor`. The renderer does
not choose songs, plan points, download files, or control RK playback.

## Test

```powershell
$env:PYTHONPATH = "modules/transition-renderer/src"
py -m pytest -q modules/transition-renderer/tests
```
