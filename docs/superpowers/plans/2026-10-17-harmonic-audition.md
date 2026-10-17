# Harmonic audition implementation plan

> Execute inline, task by task, preserving the user's existing changes. Use test-driven development for ranking logic. The approved result is an isolated audition, with no live ranking deployment.

**Goal:** Deliver three playable comparisons that change only next-track ranking through an explicit experimental harmonic preference.

**Architecture:** Read immutable public track snapshots and the audited NAS key metadata. Generate safe transition plans with the current automatic planner, freeze the best plan for each destination, and compare baseline ranking against a bounded harmonic bonus. Replay both choices through the existing LiveTransport, with the same frozen per-pair plans and shared audio cache.

**Tech stack:** TypeScript, Vitest, React/Vite and the existing Web Audio transport.

## Task 1 — Pure ranking with evidence gates

Files: create `web/src/harmonic-key/ranking.ts` and `ranking.test.ts`.

- [ ] Write failing tests using this input shape:

```ts
type KeyEvidence={camelot:string;needsReview:boolean;masterSha256:string;runId:string}
type Candidate<T>={id:string;score:number;plan:T;key?:KeyEvidence;masterSha256:string;runId:string}
```

Tests must cover 12A/1A neighbors, 8A/8B relatives, rejection of diagonal 8A/9B, malformed and missing keys, exact source binding, and the following unchanged-ranking invariant:

```ts
expect(rankFrozen(from,candidates,false).map(x=>x.id)).toEqual(candidates.map(x=>x.id))
expect(JSON.stringify(candidates)).toBe(before)
```

- [ ] Run `npm test -- src/harmonic-key/ranking.test.ts` and verify the missing implementation causes failure.
- [ ] Implement strict Camelot parsing, source checks and `rankFrozen`. Same key bonus 0.08; same-mode neighbors or same-number opposite modes bonus 0.064; otherwise zero. Pending-review keys score zero unless the isolated experiment explicitly allows provisional evidence. Preserve original score and plan references; stable original order breaks ties.
- [ ] Run the tests and commit the two files.

## Task 2 — Build a reproducible frozen comparison pack

Files: create `web/scripts/build-harmonic-pack.ts`. Audit inputs remain in workspace `work/harmonic-key-20261017/`.

- [ ] Fetch the current public catalog and choose a bounded cohort around 90–110 BPM from the verified key audit, preserving collection diversity. Save each fetched public detail locally for reproducibility.
- [ ] Use `planAutomaticQuality` with each fixed source, the same candidate pool and one fixed source position. Build EQ for surviving candidates, retain the highest-ranked frozen plan per destination, and require the baseline winner to equal the existing planner's winner.
- [ ] Apply only `rankFrozen` to those plans. Save three cases: two changed choices if available and one unchanged choice. Each case records candidate IDs, original scores, added bonuses and full frozen plans. Never force a change by altering a score or key.
- [ ] Assert strict evidence mode produces the baseline for all provisional-only inputs and that plan hashes do not change across ranking arms.
- [ ] Write `web/public/harmonic-key-data.json` and an audit manifest. Use absolute `/listen/` media URLs via the local development proxy; retain no private NAS paths in the public pack.

## Task 3 — Audition page using the existing transport

Files: create `web/harmonic-key.html`, `web/vite.harmonic-key.config.ts`, `web/src/harmonic-key/main.tsx`, `HarmonicKeyLab.tsx`, `harmonic-key.css`.

- [ ] Present three cases, two clearly named audition buttons, one stop button, a local preference form and feedback export. Explain provisional labels and the change in destination song in plain Chinese.
- [ ] Construct LiveTransport with the existing AudioBufferPool, autoNext=false and prewarm=false. The custom planner returns the selected immutable frozen plan only for its matching source/destination. Start four seconds before its transition, prepare required assets, request that exact destination, and stop eight seconds after takeover.
- [ ] Reuse `v3-clock.js` from existing public assets. Cancel timers, stop and dispose transports on case/arm changes or unmount. Use an operation revision to reject stale asynchronous loads.
- [ ] Configure Vite to proxy `/listen/` to the existing HTTPS site with certificate verification enabled. Build only the separate harmonic entry into `dist-harmonic-key`.

## Task 4 — Verify and deliver

- [ ] Run ranking tests together with existing automatic quality, local beat and vocal overlap tests.
- [ ] Build the new entry with `npx vite build --config vite.harmonic-key.config.ts` and run TypeScript checks.
- [ ] Open the local page, play each case's two arms, verify actual progress and frozen plan IDs, stop, switch cases and submit/export one reversible local preference.
- [ ] Save proof and report current limitations. Commit only new harmonic experiment files and these design documents. Leave the existing live player and all unrelated working changes intact.
