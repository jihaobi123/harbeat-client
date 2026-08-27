# Stem Separation

This module owns offline Demucs separation and validation of the four stem
files. It is intentionally separate from RK real-time `stem_solo` and
`stem_curves`, which belong to `stem-runtime`.

## Output contract

The only complete result is a mapping containing all four names:

```text
vocals -> vocals.wav
drums  -> drums.wav
bass   -> bass.wav
other  -> other.wav
```

Partial output is a failure for stem-aware playback. The caller may decide to
use a non-stem render, but this module never silently claims that a partial
separation is complete.

## Drum analysis

When `drums.wav` is available, `analyze_stem_files` also returns
`drum_analysis` with:

- model-derived Kick, Snare, Hi-hat, Tom, and Cymbal event candidates when a
  dedicated worker is configured;
- confidence-gated Kick, Snare, and Hi-hat spectral candidates as an explicit
  fallback when the model worker is unavailable;
- a 2-second density curve;
- a downbeat-aligned 16-step dominant pattern and stability score;
- fill candidates, per-class confidence, and quality flags.

Pass `bpm`, `beat_points`, and `downbeats` from the rhythm pipeline. Without a
beat grid, event detection remains available but pattern output is explicitly
marked for review. The result reports `selected_engine`, `detector_mode`, and
`engine_routes`, so callers can distinguish mature-model output from spectral
fallback. Neither route may be advertised as a real-song accuracy figure
before annotated-set validation.

The application pipeline persists v3 facts in
`music_features.pre_style_features` and the separate 21-style result in
`music_features.high_frequency_styles`. See
`docs/pre_style_feature_analysis_backend_deployment.md` for model-worker
contracts, licensing constraints, feature semantics, and acceptance commands.

## Runtime behavior preserved from Jetson

- Reuse existing `htdemucs/<source-stem-name>/*.wav` files.
- Invoke the deployment interpreter with `python -m demucs -n htdemucs`.
- Use an ASCII-safe temporary input when a source path is not safe for the
  model runner, then copy verified outputs to the canonical stem directory.
- Validate all four files after the process exits.

The model cache and audio files are deployment assets. They are not committed
to Git.

## Tests

```powershell
py -m unittest discover modules/stem-separation/tests -v
```

The application-level regression tests are:

```bash
PYTHONPATH=. pytest -q app/tests/test_drum_analysis.py app/tests/test_stem_analysis.py
```
