# V3.1 visual realtime candidate implementation plan

> Execute inline in the current isolated feature checkout. User requested implementation and selected same-family twenty-track coverage. Preserve unrelated diagnostics and all published baseline releases.

**Goal:** Explain protected vs ordinary V3 through music timelines, enable actual mid-song protected requests, and expand controlled listening to about twenty Hip-Hop-family songs.

**Architecture:** Existing guardPlan and LiveTransport remain audio policy/DSP authorities. A pure visual model maps original sections/vocals/cues onto source and render timelines. A new V31Lab composes live controls, paired trials, ratings and readable history. A reproducible corpus builder selects by preprocessing evidence, produces isolated media and coverage manifests; no blanket policy fallback.

**Tech Stack:** React/TypeScript, SVG, WebAudio, Vitest; Python/FFmpeg on Jetson, existing NAS/Alibaba routing.

- [x] Inventory latest unique reports and necessary source assets; retain selection/exclusion reasons. Select twenty including original six if identities exist, using style family and analysis availability before checking mix feasibility.
- [x] Add failing tests for corpus selection identity/deduplication and bounded asset enumeration; implement preparation module/script with report/master/stem binding, inherited guard candidates, immutable recipes, existing-source caching, per-track errors and progress.
- [x] Test pure timeline mapping: B head is stretched, B body resumes native time, A ends at handoff; section/vocal intersections are clipped; union overlap never double-counted; missing data stays unknown. Implement visual model and SVG source/render timelines.
- [x] Add a default-collapsed raw evidence view, prominent plain-language explanations, A/B difference metrics and original-source audition controls.
- [x] Test fixed comparison skip-wait playback preserves selected plan and original request position; implement optional audition offset only. Default existing comparison behavior remains unchanged.
- [x] Implement independent V31 entry/config and live UI: start/pause/seek, next target selection while A plays, explicit preload, protected dynamic request, cancellation, pending plan and audio-clock progress. No automatic energy/style controls.
- [x] Add deterministic multi-song paired cases at common source trigger positions, list no-window cases, and browser-local listening ratings with export. Keep full report/decision/execution logs.
- [x] Run corpus build on Jetson, verify all selected sources/assets and candidate coverage, publish new candidate release without overwriting accepted versions.
- [x] Run unit/regression and real-corpus checks, actual browser transitions for multiple new songs, mobile layout, source/timeline inspection, shared analysis-platform logs and cold-load behavior. Report exactly what is and is not validated.
- [x] Publish code and concise usage/coverage documentation on GitHub; open V3.1 candidate page. Formal promotion awaits user's extended listening decision.

Validation: 150 web tests passed (6 optional fixture suites skipped); 3 Python selection tests passed; 3,287 real-data requests checked; 2,720 referenced audio hashes verified. Browser completed three paired auditions and one actual mid-song request on two new pairs, including stop-during-initialisation, fixed pair preservation, source-only inspection and mobile overflow checks. Human preference remains to be collected.
