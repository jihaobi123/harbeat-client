# First combination audition implementation plan

> **For agentic workers:** Use executing-plans inline for this authorized continuation. Use checkbox steps for progress.

**Goal:** Deliver Attention/HIPHOP original, previously preferred bass handoff, and identical bass handoff plus one other-stem filter as a blind three-arm audition.

**Architecture:** New isolated combination-step-one modules reuse existing bass/filter curve generators, EQ, cache and durable persistence. Master/other clips stay identical to5206; bass corrections use frozen5190same-clock clips. Original and single have zero other-filter correction; combined adds exactly5206filter correction.

**Tech Stack:** React/TypeScript, WebAudio, Vite, Vitest, Python soundfile/hash audit, existing CUA browser.

### Task1: Freeze material and parameters

- [ ] Verify `filterCase.plan === bassCase.plan` and `filterCase.vocalConflict === bassCase.vocalConflict`, equal pre/post/BPM, fresh NAS source fingerprints where available, all eight cached asset hashes/decoded lengths. Write `work/combination-step-one-20261019/pack.json` and preparation audit; no source edits.
- [ ] Retain raw parent pack hashes and prior listener-analysis hashes. Bind exact source clocks, original parameter objects, timing, filter, audio and playback code hashes into the new pack fingerprint.

### Task2: Test and implement bounded combination playback

- [ ] Create `web/src/combination-step-one/policy.test.ts`: original/single share zero filter; single/combined bass curves identical; original reference curves preserved; mutation and unsupported-mode rejection.
- [ ] Run `web/node_modules/.bin/vitest run src/combination-step-one/policy.test.ts` from web and observe new behavior absent.
- [ ] Implement `policy.ts` by calling `bassCurves` and `filterPlan`; expose only `original|single|combined`. Implement `graph.ts` as master plus bass correction plus optional filtered-minus-dry other, all under original EQ and timing, initialized silent gains.
- [ ] Adapt isolated `transport.ts` from existing melody-filter player: eight required assets, original source durations, three valid modes, rendered start/end gates, stop/retry, immutable source logs, six markers.
- [ ] Test equal source clocks/voice reference envelopes and stale/cancelled completion handling using the existing transport harness with eight assets and three modes. Run scoped tests.

### Task3: Test and implement tri-arm durable audition

- [ ] Create rounds tests: A/B/C is a permutation of original/single/combined; vote allowed before any completion; first vote immutable across changes; practice isolation; mapping/fingerprint validation fails closed; source change archives prior round.
- [ ] Observe new tests fail before implementation. Adapt `rounds.ts` from melody-filter with three arms and strict valid choice checks.
- [ ] Add `CombinationLab.tsx`, `main.tsx`, `style.css`, HTML entry and Vite config on5210. Keep persistence/export/history/stop/retry, add symptom version selection. Reveal requires first choice, not full playback.

### Task4: Verify and deliver

- [ ] Run scoped and relevant inherited tests, TypeScript check and Vite build. Verify local assets via hashes; protect all14existing dirty files.
- [ ] Through a dedicated audit page, render real OfflineAudioContext outputs: baseline compatibility, combined-minus-single equals only the filter correction within numeric tolerance; compare peaks/RMS and exact identical tails. Export report.
- [ ] Run built preview; use visible browser to complete all three practice arms, verify markers/errors/limits, early vote/stop/reload/export. Archive practice, leave blank formal round, mark deliverable tabs and open audition.
- [ ] Request independent code review, fix material findings, write `docs/evidence/combination-step-one-20261019.json`, update status/roadmap, commit only scoped files and report usable listening URL. Do not activate production or judge subjective winner.
