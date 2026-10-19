# First combination audition implementation plan

> **For agentic workers:** Use executing-plans inline for this authorized continuation. Use checkbox steps for progress.

**Goal:** Deliver Attention/HIPHOP original, previously preferred bass handoff, and identical bass handoff plus one other-stem filter as a blind three-arm audition.

**Architecture:** New isolated combination-step-one modules reuse existing bass/filter curve generators, EQ, cache and durable persistence. All master/bass clips stay identical to5190; only Aother is borrowed from5206, whose Aparent master is bit-identical. Differing B renders are excluded. Original and single have zero other-filter correction; combined adds exactly5206filter correction.

**Tech Stack:** React/TypeScript, WebAudio, Vite, Vitest, Python soundfile/hash audit, existing CUA browser.

### Task1: Freeze material and parameters

- [x] Verify `filterCase.plan === bassCase.plan` and `filterCase.vocalConflict === bassCase.vocalConflict`, equal pre/post/BPM, fresh NAS source fingerprints where available, all six cached asset hashes/decoded lengths. Write `work/combination-step-one-20261019/pack.json` and preparation audit; no source edits.
- [x] Retain raw parent pack hashes and prior listener-analysis hashes. Bind exact source clocks, original parameter objects, timing, filter, audio and playback code hashes into the new pack fingerprint.

### Task2: Test and implement bounded combination playback

- [x] Create `web/src/combination-step-one/policy.test.ts`: original/single share zero filter; single/combined bass curves identical; original reference curves preserved; mutation and unsupported-mode rejection.
- [x] Run `web/node_modules/.bin/vitest run src/combination-step-one/policy.test.ts` from web and observe new behavior absent.
- [x] Implement `policy.ts` by calling `bassCurves` and `filterPlan`; expose only `original|single|combined`. Implement `graph.ts` as master plus bass correction plus optional filtered-minus-dry other, all under original EQ and timing, initialized silent gains.
- [x] Adapt isolated `transport.ts` from existing melody-filter player: six required assets, original source durations, three valid modes, rendered start/end gates, stop/retry, immutable source logs, nine markers.
- [x] Test equal source clocks/voice reference envelopes and stale/cancelled completion handling using the existing transport harness with six assets and three modes. Run scoped tests.

### Task3: Test and implement tri-arm durable audition

- [x] Create rounds tests: A/B/C is a permutation of original/single/combined; vote allowed before any completion; first vote immutable across changes; practice isolation; mapping/fingerprint validation fails closed; source change archives prior round.
- [x] Observe new tests fail before implementation. Adapt `rounds.ts` from melody-filter with three arms and strict valid choice checks.
- [x] Add `CombinationLab.tsx`, `main.tsx`, `style.css`, HTML entry and Vite config on5210. Keep persistence/export/history/stop/retry, add symptom version selection. Reveal requires first choice, not full playback.

### Task4: Verify and deliver

- [x] Run scoped and relevant inherited tests, TypeScript check and Vite build. Verify local assets via hashes; protect all14existing dirty files.
- [x] Through a dedicated audit page, render real OfflineAudioContext outputs: baseline compatibility, combined-minus-single equals only the filter correction within numeric tolerance; compare peaks/RMS and exact identical tails. Export report.
- [x] Run built preview; use visible browser to complete all three practice arms, verify markers/errors/limits, early vote/stop/reload/export. Archive practice, leave blank formal round, mark deliverable tabs and open audition.
- [x] Request independent code review, fix material findings, write `docs/evidence/combination-step-one-20261019.json`, update status/roadmap, commit only scoped files and report usable listening URL. Do not activate production or judge subjective winner.

Source-audit adjustment: identical plan does not imply identical cached rendering.5206Bmaster differs from5190Bmaster; final pack uses all5190masters plus its two active bass excerpts and only5206Aother. Aparent master sample comparison is exactly zero. Six shared assets and nine markers per complete play. Fresh NAS SSH closed; preserve earlier source binding and freshly rehash cached assets, with no new NAS-proof claim.

Completed:56related/14scopedtests,tsc/build,independent review,real offline differential proof,and3complete browser plays/27on-time markers. Formal7d8afe74-0307-4bff-ab90-9fddfdabc9fbblank after reload. Practice isolated. No subjective winner claimed.
