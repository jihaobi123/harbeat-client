# Vocal Endpoint Implementation Plan

> Execute inline using executing-plans and obtain requesting-code-review independent review.

**Goal:** Use existing open projects to produce auditable vocal endpoint candidates and one controlled vocal-handover comparison.

**Architecture:** Source-bound isolated-vocal contexts → official YAMNet and existingSilero → pYIN/envelope → gap/tail candidate policy → frozen baseline/current cue comparison. Independent durable browser UI.

**Tech Stack:** TensorFlow/Essentia CPU isolated model environment, librosa pYIN, numpy/scipy, ffmpeg, React/Vite/WebAudio.

- [ ] Verify official projects/weights and source contexts; record runtime/provenance and model limitations.
- [ ] Write failing endpoint policy tests, implement seed/breath/tail/gap logic and deterministic candidate/rejection evidence.
- [ ] Run actual models on3outgoing contexts plus incoming control; verify times and input hashes; select only cue-compatible confident-enough audition candidates and report all failures.
- [ ] Implement isolated baseline-versus-detected-end player and blind UI. Reuse unchanged clips, bass, EQ, bed curves, cues and native takeover. Add readable reveal evidence and isolated vocal playback.
- [ ] Appropriate tests/typecheck/build and independent review; fix important findings.
- [ ] Actually play both arms in practice, check render markers, early choice and reload/export; preserve practice history, leave empty formal round, save screenshot/evidence and scoped commit.
