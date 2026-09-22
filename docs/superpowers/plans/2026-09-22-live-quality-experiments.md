# V3 Live single-variable quality experiments

User approved execution of independent vocal, boundary, horizon, EQ, material and duration trials. Execute inline using test-driven-development; baseline deployed files remain frozen.

Architecture: retain the pinned 279b65d planner for candidate generation; apply one scoring delta per ranking experiment. A separate browser experiment page runs plans through the existing Web Audio engine with all selected assets loaded before comparison playback. Do not add local style/energy filtering. Fixed-cue trials isolate EQ depth, B source excerpt, and overlap length. No production or frozen page is replaced.

- [x] Tests first: baseline parity; one-field policy differences; horizon does not alter waiting penalty scale; ranking score decomposition agrees; fixed-cue EQ/material/length invariants; cancellation during loading.
- [x] Add pinned baseline planner/decision and experiment policies with documented provenance.
- [x] Add controlled replay to LiveTransport, isolated from ordinary playback; full experiment/source/plan/clock logs and export.
- [x] Add comparison page: sequential trials, parameters, baseline vs experiment plans, real-time A/B playback, listening feedback and baseline link.
- [x] Prepare one exact-length two-bar B tail asset for a four-to-two-bar trial, source hash verified. Fixed case Big Girls → Cold; compare same A exit and B takeover.
- [x] Run synthetic and real-catalog comparisons; build; test controlled audio output if browser infrastructure permits, otherwise explicitly record limitation.
- [x] Publish independent static release and audit results, verify all source assets and frozen baseline hashes; commit and push code. Report outcomes without claiming objective metrics establish listening superiority.

Validation: 77 checks passed before the additional controlled-log presentation test; the new test passed separately. Seven browser runs completed (six variants plus fixed EQ reference), with 21 linked audio-thread observations and persisted full session. Feedback unlocked after both EQ arms completed. Desktop and 390px mobile layouts inspected; no horizontal overflow. First QA timeout was a 60-second total test limit including full FLAC downloads; recheck separated observed loading from execution. No DSP fix was needed.
