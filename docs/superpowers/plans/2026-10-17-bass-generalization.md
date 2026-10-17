# Bass coverage and EQ comparison implementation plan

Execute inline with the approved six-case, three-arm design. Preserve all unrelated edits and previous audition pages.

**Goal:** Five new eligible fixed pairs plus the old anchor, randomized reference/stem/EQ listening and honest coverage evidence.

**Architecture:** Full source-bound public catalog snapshot; deterministic predeclared source slots and unchanged safe-plan gates. Shared four-channel master/bass source renderer. Independent three-arm player using original EQ and a constant-setting additional low shelf. Balanced blind assignment and durable first-choice records.

- [ ] Snapshot all current detail JSON and verify catalog identities. Implement `scripts/prepare_bass_generalization.ts` using original automatic planner, source gates, harmonic ranking, bass timing and EQ. Freeze six plans and record candidate/skip counts; no listening-based selection.
- [ ] RED/GREEN tests for `web/src/bass-generalization/policy.ts`: three modes, invariant non-bass curves, zero added EQ outside EQ arm, fixed 140Hz/18dB recipe, exact frozen markers, invalid timing. RED/GREEN balanced assignment and blind-record lifecycle tests in `rounds.test.ts`.
- [ ] Reuse `render_bass_swap.py` on the frozen multi-case selection, with original source hash/frame checks. Copy only short assets; verify hashes and source frames, record actual bass energy and skipped sources. Keep original anchor source plan/hash exact.
- [ ] RED/GREEN tests and implementation of independent `transport.ts`: same original plan/EQ/non-bass gains, extra low shelf zero in non-EQ arms, shared sources/clock, original native takeover, replacement/abort safety, complete logs.
- [ ] Build `BassCoverageLab.tsx`, `main.tsx`, `style.css`, standalone HTML/Vite config (localhost5190). Balanced A/B/C mapping, complete-listening gate, first blind choice, reveal, symptoms, round history/export and new round. Before reveal, no technique names or phase hints. Preserve initial blind vote after edits.
- [ ] Run appropriate regressions, renderer tests, TypeScript and isolated build. Independent review, actual browser playback of every delivered arm; verify plans/gains/EQ settings and timed events in exported logs. Verify reveal/first-choice/history/export and create fresh blind user round. Save evidence and screenshot; commit only this experiment, no production deployment.
