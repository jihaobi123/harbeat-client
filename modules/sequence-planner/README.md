# Sequence Planner

This module only orders songs. It does not choose transition points, render
audio, sync assets, or control RK playback.

## Current deployed behavior

`default` uses greedy pair chaining:

```text
total = 0.42 * BPM compatibility
      + 0.34 * Camelot/key compatibility
      + 0.14 * whole-track energy similarity
      + 0.10 * bass similarity
```

Other presets assign each unused song to the closest slot on a named energy
curve. The implementation is behavior-compatible with the Jetson files whose
SHA256 is recorded in `deploy/provenance-20260813.json`.

## Deliberate boundary

The planner consumes persisted summaries. It must not decode audio in the live
request and must not call `/render`, `/sync`, or RK endpoints.

## Tests

```powershell
py -m unittest discover modules/sequence-planner/tests -v
```
