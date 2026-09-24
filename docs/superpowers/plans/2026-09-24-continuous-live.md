# Continuous Live Implementation Plan

**Goal:** Provide continuous playback and in-session control across all 157 songs, with honest readiness states and the accepted vocal-overlap mix.
**Architecture:** NAS preparation emits an index and immutable per-track details/media. A segmented native-source scheduler extends the existing transport without changing legacy playback. A separate listening page manages the next-song selection, preloading and continuous handoffs.
**Tech Stack:** Python, FFmpeg, React, TypeScript, WebAudio, existing media registry, Vitest and Playwright.

- [ ] Corpus preparation: create `scripts/build_continuous_library.py` and `tests/test_continuous_library.py`. Test all-entry accounting, full duration, source binding, label separation, contiguous segment bounds, recipe deduplication and resume behavior before implementation. Audit the 157 records, benchmark rendering, then produce all native segments and compatible entry assets in a new NAS directory. Keep old source and release files intact.
- [x] Audio scheduler: create `web/src/continuous/segments.ts` and tests, add optional `audioSegments` to `Track`, and integrate full-song sources into `web/src/realtime/transport.ts`. Write failing regressions for late seeks, segment boundaries, pause, stop/seek races, memory pins, buffer deadlines and legacy scheduling first. Preserve the existing transition graph, EQ and planner.
- [x] Continuous page: create `web/src/continuous/ContinuousLive.tsx`, controller/catalog helpers, CSS, entry HTML and Vite config. Test metadata loading, stale selections, current-song continuity, repeated handoffs and catalog filters. The page keeps all 157 entries visible, lazy-loads details, uses `planVocalOverlap`, prepares the selected next song and exposes playback/volume/progress controls.
- [ ] Integration: validate actual corpus contracts, run the new tests and full source suite with the accepted reference fixtures. Verify full durations, existing algorithms, source identities and retained failed/unavailable entries. Review concurrency and memory behavior independently.
- [ ] Browser and release: build the independent page, verify a local preview, publish verified data/page files, and run public browser checks for segment crossing, multiple handoffs, selection changes, pause/seek/volume and feedback preservation. Save publication hashes, coverage and exact limitations.

Execution uses separate bounded workers for corpus preparation and audio scheduling while the main worker builds the page and integrates the results. The available execution skill explicitly recommends subagent work; its named subagent-specific companion is not installed, so use the provided collaboration tools and review each result before release.


## 2026-09-24 implementation checkpoint

- Corpus code, source inventory, read-only benchmark and regression tests are complete. All 157 identities were accounted for; no new full-song assets have been generated yet.
- Audio scheduler and continuous page are implemented. Full source suite: 252 passed, 10 optional corpus-dependent tests skipped. Python corpus suites: 15 passed. TypeScript and continuous/vocal-overlap/V3.1 builds pass.
- Independent review identified and resolved: stale third-song preparation after handoff, automatic continuation failing permanently after a transient cue miss, exhausted filter state not recovering when filters expand, and nullable optional genre data excluding valid songs.
- Browser checked all 157 inventory records (84 KPOP, 8 EDM, 65 reference), manual-style filtering, search, unavailable states and mobile width. Playback verification uses the previous 26 published fixtures; it does not establish the new full corpus as ready.
- Remote staging was rejected by automatic approval review: source transfer and remote write were not explicitly authorized. A user question is pending for uploading the preparer to the existing HarBeat server, processing all 157, and publishing the separate page. No remote write was attempted after that rejection.
- Remaining after authorization: stage the reviewed preparer into the new NAS directory, audit bindings, benchmark one actual output, run the complete resumable batch, validate ready/unavailable counts and source hashes, browser-test full-song boundaries and multiple handoffs, publish only the new page and data, and verify the public URL while retaining old page hashes.

Final local browser regression also passed a locked third-song queue and re-preparation after takeover, paused seek/resume, volume, real overlap, and old-feedback key preservation. Some fresh-network runs exceeded the shortened legacy fixture before preload completed; final queue regression held playback paused during preload, then performed the actual mix on the audio clock. New full-song assets still require browser validation after generation.
