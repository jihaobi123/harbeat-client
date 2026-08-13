# Audio Preprocess

Version `0.2.0` adds a persistence-neutral `PreprocessService`. Analysis output
is validated before an `AnalysisRepository` can save it. The v0.1 song-object
mutation entry point remains for production compatibility; candidate scoring
math is intentionally unchanged in this refactor.

This module preserves the deployed offline song-analysis capability. Its first
independently accepted implementation is `dj_structure_v2`, the candidate data
used by the default transition and fast-cut planners.

## Current deployed pipeline

1. Decode original audio and compute BPM, key, beats, downbeats, phrases,
   energy, loudness, groove, and transition windows.
2. Optionally enrich analysis from separated stems. Stem separation itself is
   owned by `stem-separation`, not this module.
3. Compute DJ fingerprint and style evidence.
4. Compute `dj_structure_v2` candidate boundaries and local handoff features.
5. Persist the versioned payload in `LibrarySong.music_features`.

## Extraction boundary

`src/harbeat_audio_preprocess/dj_structure_v2.py` is a copy of the source that
was running on Jetson on 2026-08-13. Its SHA256 is recorded in the provenance
manifest. Algorithm changes must be made after behavior-compatible extraction,
not during the copy.

## Quality gate

Every analyzed row must contain:

- `version = dj_structure_v2`
- non-empty `track1_exit_candidates`
- non-empty `track2_entry_candidates`
- candidate `audio_feature_source = dj_structure_precomputed_window_v2`
- finite times and normalized score fields

Missing or invalid data is reported explicitly. Runtime planners must not hide
it with a silent fallback.

## Tests

```powershell
py -m unittest discover modules/audio-preprocess/tests -v
```

The full audio parity test runs on Jetson because it needs the production
librosa/Essentia environment and catalog audio. Unit tests use synthetic
candidate payloads and pure helper calls.
