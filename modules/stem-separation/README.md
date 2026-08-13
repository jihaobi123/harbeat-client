# Stem Separation

Version `0.2.0` keeps the v0.1 separation behavior and adds an injected Demucs
runner, atomic publication of canonical stem files, typed process errors, and
a standalone CLI. Core tests do not launch Demucs.

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

## Standalone use

```powershell
$env:PYTHONPATH = "modules/stem-separation/src"
py -m harbeat_stem_separation input.wav D:\harbeat\stems
```

The command prints one JSON result and exits with `0` only when all four stems
are present and non-empty.

On Jetson/Linux, use `python -m harbeat_stem_separation` with the deployment
virtual environment.

## Tests

```powershell
py -m unittest discover modules/stem-separation/tests -v
```
