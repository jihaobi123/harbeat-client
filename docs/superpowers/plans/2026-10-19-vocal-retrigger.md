# Vocal Retrigger Implementation Plan

**Goal:** Prepare one source-review-gated original-versus-one-shot audition at5207; document two fixed-cue skips.
**Architecture:** Existing source-bound endpoint candidates and cached master/vocal clips; finite original-gain capture; unchanged dry graph plus optional one-shot; isolated blind store with cue review.
**Tech Stack:** Python NumPy/soundfile, React/TypeScript/WebAudio, fixed Vite preview, NAS provenance.

- [x] Read5206feedback, obtain missing third human choice, archive2filter/1original with coverage/checkbox limits.
- [x] Write failing planner/capture tests: whole selected endpoint candidate (not full VAD activity),300msquiet support, source hashes, finite one-shot and unchanged originals; implement minimal planner/capture.
- [x] Recheck frozen endpoint files via verified_analysis; plan all3fixed cases, retain skips and extract only eligible unchanged six dry clips plus exact cue/replay assets. Reverify NAS report/manifest/source hashes.
- [x] Add policy/graph/player: reference original dry gain/EQ; same sources/timing, optional one-shot at nativehandoff only; rendered-onset/end required, cancel/retry.
- [x] Add round review status/history, review-at-vote snapshots, blocking until complete, unchanged early voting after review. Invalid/revoked review stops playback; never fake a formal human judgment.
- [x] Build independent5207page with context/sample review, blind arms, exact provenance and skip explanations; practice isolation, history/export/reload.
- [x] Tests/typecheck/build, independent review/repair, real browser current-parameter practice both arms, cue gate/revoke/earlyvote/cancel/export/archive checks; blank formal left for human.
- [x] Save evidence/status/finite completion queue, scope commit and deliver page/screenshot. Final cross-technique catalogue follows remaining listener rounds, not inferred from practice.
