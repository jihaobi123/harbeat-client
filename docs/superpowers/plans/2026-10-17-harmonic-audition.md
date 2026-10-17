# Harmonic audition implementation plan

> Execute inline, task by task, preserving the user's existing changes. Use test-driven development for ranking logic. The approved result is an isolated audition, with no live ranking deployment.

**Goal:** Deliver three playable comparisons that change only next-track ranking through an explicit experimental harmonic preference.

**Architecture:** Read immutable public track snapshots and the audited NAS key metadata. Generate safe transition plans with the current automatic planner, freeze the best plan for each destination, and compare baseline ranking against a bounded harmonic bonus. Replay both choices through the existing LiveTransport, with the same frozen per-pair plans and shared audio cache.

**Tech stack:** TypeScript, Vitest, React/Vite and the existing Web Audio transport.

## Task 1 — Pure ranking with evidence gates

Files: create `web/src/harmonic-key/ranking.ts` and `ranking.test.ts`.

- [x] Write failing tests using this input shape:

```ts
type KeyEvidence={camelot:string;needsReview:boolean;verified:boolean;masterSha256:string;runId:string}
type Candidate<T>={id:string;score:number;plan:T;key?:KeyEvidence;masterSha256:string;runId:string}
```

Tests must cover 12A/1A neighbors, 8A/8B relatives, rejection of diagonal 8A/9B, malformed and missing keys, exact source binding, and the following unchanged-ranking invariant:

```ts
expect(rankFrozen(from,candidates,false).map(x=>x.id)).toEqual(candidates.map(x=>x.id))
expect(JSON.stringify(candidates)).toBe(before)
```

- [x] Run `npm test -- src/harmonic-key/ranking.test.ts` and verify the missing implementation causes failure.
- [x] Implement strict Camelot parsing, source checks and `rankFrozen`. Same key bonus 0.08; same-mode neighbors or same-number opposite modes bonus 0.064; otherwise zero. Pending-review keys score zero unless the isolated experiment explicitly allows provisional evidence. Preserve original score and plan references; stable original order breaks ties.
- [x] Run the tests and commit the two files.

## Task 2 — Build a reproducible frozen comparison pack

Files: create `web/scripts/build-harmonic-pack.ts`. Audit inputs remain in workspace `work/harmonic-key-20261017/`.

- [x] Fetch the current public catalog and choose a bounded cohort around 90–110 BPM from the verified key audit, preserving collection diversity. Save each fetched public detail locally for reproducibility.
- [x] Use `planAutomaticQuality` with each fixed source, the same candidate pool and one fixed source position. Build EQ for surviving candidates, retain the highest-ranked frozen plan per destination, and require the baseline winner to equal the existing planner's winner.
- [x] Apply only `rankFrozen` to those plans. Save three cases: two changed choices if available and one unchanged choice. Each case records candidate IDs, original scores, added bonuses and full frozen plans. Never force a change by altering a score or key.
- [x] Assert strict evidence mode produces the baseline for all provisional-only inputs and that plan hashes do not change across ranking arms.
- [x] Write isolated `web/harmonic-key-data.json` (outside the shared public build) and an audit manifest. Use absolute `/listen/` media URLs via the local development proxy; retain no private NAS paths in the public pack.

## Task 3 — Audition page using the existing transport

Files: create `web/harmonic-key.html`, `web/vite.harmonic-key.config.ts`, `web/src/harmonic-key/main.tsx`, `HarmonicKeyLab.tsx`, `harmonic-key.css`.

- [x] Present three cases, two clearly named audition buttons, one stop button, a local preference form and feedback export. Explain provisional labels and the change in destination song in plain Chinese.
- [x] Construct LiveTransport with the existing AudioBufferPool, autoNext=false and prewarm=false. Use the existing controlled `playComparison` method with the selected immutable frozen plan. Start four seconds before its transition, prepare the actual source/takeover segments, schedule that exact destination, and stop eight seconds after takeover.
- [x] Reuse `v3-clock.js` from existing public assets. Cancel timers, stop and dispose transports on case/arm changes or unmount. Use an operation revision to reject stale asynchronous loads.
- [x] Configure Vite to proxy `/listen/` to the existing HTTPS site with certificate verification enabled. Build only the separate harmonic entry into `dist-harmonic-key`.

## Task 4 — Verify and deliver

- [x] Run ranking tests together with existing automatic quality, local beat and vocal overlap tests.
- [x] Build the new entry with `npx vite build --config vite.harmonic-key.config.ts` and run TypeScript checks.
- [x] Open the local page, play each case's two arms, verify actual progress and frozen plan IDs, stop, switch cases and submit/export one reversible local preference.
- [x] Save proof and report current limitations. Commit only new harmonic experiment files and these design documents. Leave the existing live player and all unrelated working changes intact.

## Implementation findings

- The 148 source-bound key records all require review. The deployment has no validation report for this model route; a confidence cap of 0.79 is not validated accuracy. Strict mode preserves baseline ranking. Provisional labels are permitted only in this clearly marked local audition.
- Two cases change destination (Meant To Be and Attention); All Falls Down retains the same destination. Each destination retains its original highest-ranked plan, EQ and timing.
- Late transition points exposed an existing controlled-player preload defect: it always loaded the first 150-second native chunk. The comparison now preloads the actual source and takeover chunks. An integration regression verifies real LiveTransport scheduling after 150 seconds.
- Browser testing found completion attribution could follow a mutable arm reference during React batching. Completion is now bound to the session’s captured case and arm, and disposing detaches its callback first. Full-round export retains all audition sessions.

## Final verification

116 tests passed; one optional corpus test skipped. TypeScript and isolated build passed. Browser exported six distinct completed comparison sessions, each with one original frozen plan, one handoff and one completion; all six scheduled plans exactly matched the pack. Stop, case switch, reversible feedback save/export and undo were verified. No browser warnings/errors. QA does not assess subjective sound quality.

Proof: workspace `work/harmonic-key-20261017/qa-result.json`, `browser-playback-export.json`, and `harmonic-audition.png`. The generated pack/build remain local ignored artifacts. Minor follow-ups: generator fallback when fewer than two changed cases exist; richer feedback-export metadata. Neither affects this fixed pack.
