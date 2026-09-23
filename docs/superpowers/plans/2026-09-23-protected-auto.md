# Automatic protected mixing implementation plan

Goal: execute real browser mixes without mandatory human checkboxes, while keeping geometry and measured vocal-gap checks. This corrects the user-rejected manual-only release; user authorized implementation inline. Keep manual mode and frozen V3 accessible.

Design: retain manual guard planner defaults. Add a distinct acoustic evidence admission path, never fabricate Reviews. Derive source-bound quiet intervals from existing 50 ms vocal RMS, threshold -32 dBFS, minimum 200 ms. These are experimental acoustic proxies, not semantic phrase truth. A exits at a small-bar-aligned point after the model section end, allowing at most two bars / four seconds to finish its vocal tail, never before the segment end. Require 50 ms quiet margins and <=65 ms grid shift. B uses actual original silent windows (1/2/4 bars), within one section, quiet through entry and 100 ms after body takeover. If absent, do not mark a track eligible.

- [x] Add failing tests for evidence-based admission without human reviews, stale hashes, loud/short gaps, early exit, cross-section entry and no fallback.
- [x] Prepare a separate automatic catalog from source-bound reports; generate entry assets only from quiet original material; retain rejected measurements.
- [x] Implement independent automatic gate plus source hash/range validation. Preserve manual mode behavior. Distinguish acoustic checks and human verification in every log.
- [x] Add automatic mix UI with feasible pair selection and one-click actual WebAudio transition; preload A/B/head before playback. Include full-start and transition audition, planned/actual events, and exact source evidence.
- [x] Verify at least two real distinct pair transitions in browser; all unit regressions; publish current entry with manual.html fallback, push branch. State coverage and acoustic limitations explicitly.
