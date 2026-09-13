# Transition Renderer

> **第一版实现（含后续维护版本），仅保留供评估。第二版不一定需要，是否复用必须由对应负责人确认。**
> **第二版采用状态：待确认。** 未确认前，不列为必做功能，不默认接入或部署，不以其旧接口约束新 APK。
> 这里的“第一版”指产品代际，不是把包版本改为 1.0；版本来源及职责见 [当前模块清单](../REGISTRY.md)。

Version `0.2.0` adds an explicit renderer policy registry. Declared unknown
renderer versions are rejected instead of silently becoming v9. The v7 and v9
DSP implementations and generated-audio behavior are intentionally unchanged.

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
