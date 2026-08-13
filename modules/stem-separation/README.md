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
