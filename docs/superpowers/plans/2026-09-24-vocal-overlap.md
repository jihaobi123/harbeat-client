# Vocal Overlap Implementation Plan

**Goal:** Test an aligned, gain-weighted vocal score on the accepted music and twelve new tracks while retaining the formal V3.1 release.
**Architecture:** Frozen V3 candidates establish a material anchor; an independent wrapper replaces the vocal score for eligible A timings. The existing dynamic EQ and transport execute the selected plan. A separate corpus builder and listening page provide traceable comparisons.
**Tech Stack:** TypeScript, React, WebAudio, Vitest, Python, existing NAS reports and Jetson static relay.

- [x] Write `web/src/vocal-overlap/score.test.ts` for staggered/simultaneous activity, exact integration, edge versus middle weighting, rate mapping and malformed evidence. Run it red before adding `score.ts`.
- [x] Implement `score.ts` with interval union/intersection and the antiderivative `2*t*t/D - 4*t*t*t/(3*D*D)`. Keep weight normalization `2*D/3` and V3 padding 0.3 source seconds.
- [x] Write `planner.test.ts` for material anchoring, unchanged non-vocal score terms, full-duration preservation, missing evidence, dynamic EQ reuse and baseline immutability. Run red, then implement `planner.ts` as a wrapper; leave the release planner unchanged.
- [x] Build `VocalOverlapLab.tsx`, an isolated entry/config and dedicated feedback key. Show old/new cue times, score components and mapped vocal evidence. Reuse `LiveTransport`, source audition and completed-session checks. Add accurate experiment policy metadata to transport logging without changing DSP scheduling.
- [ ] Extend the corpus from NAS with a separate `scripts/build_vocal_overlap_corpus.py`, source hashes, deterministic diverse selection and exclusion audit. Preserve old track records. Test selection and preservation before rendering assets.
- [ ] Generate a fixed old/new pair-position matrix and independent example cases in `corpus.test.ts`. Save coverage and per-plan changes, verify the original twenty records and accepted feedback cases.
- [ ] Run focused tests, full source tests with `--cache=false`, type checks, experiment and official production builds. Review changed files and resolve findings.
- [ ] Serve the independent experiment and check real browser playback, comparison consistency, live request and feedback. Add only an isolated static page; keep the formal entry and previous versions intact. Record verified URLs, counts and remaining limitations.

The user has approved the experiment. Execute within that scope, using a separate corpus worker and an independent review where helpful. Keep selection and preparation separate from the audio-score implementation.

Progress: the 20-track fixed matrix contains 1,900 requests, 727 executable comparisons and one changed cue. All 20 original cases are preserved (19 executable; their selected cues remain unchanged). The source suite passes 216 tests with the frozen corpus and eighteen accepted feedback fixtures enabled; TypeScript and both builds pass. Five corpus-builder tests pass. Review findings about source binding and trace metadata were fixed with failing regression tests first. Six additional source-verified songs are rendering; twelve was a target, not an eligibility relaxation.
