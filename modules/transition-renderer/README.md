# Transition Renderer

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
