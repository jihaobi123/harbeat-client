# Stems Readiness and Vocal Bed Implementation Plan

> Execute inline using executing-plans; request an independent code review before final release.

**Goal:** Audit actual preprocessing readiness and deliver the first supported, controlled vocal/bed handover audition.

**Architecture:** Read-only readiness audit; deterministic selection from frozen pairs and formal bass preferences; joint-stretch source clips; residual stem mixer; isolated durable blind page.

**Tech Stack:** Python/numpy/ffmpeg, TypeScript/React/Vite/Web Audio, existing NAS reports.

- [x] Finish live manifest/report audit and record measured counts, binding failures, validation limitations and data gaps by technique.
- [x] Write failing policy and eligibility tests, including activity-versus-phrase distinction, unchanged bass and reference, no incoming vocal, bounded exit; implement minimal policy.
- [x] Select from the original12 plans without moving cues. Bind and render master/bass/vocal shared clips using existing stretch_layers; probe/hash all assets and verify selection matches formal feedback.
- [x] Create independent vocal-bed player/UI from verified drum-loop patterns; adapt names and guards, single-case support, isolated DB, extra voice/bed logs and markers. Keep previous trial files unchanged. Test cancellation, first audible start, formulas, native handoff, votes/history/exports.
- [x] Run appropriate regression tests, typecheck and isolated build; obtain independent review and fix findings.
- [x] Actually play all arms in practice, verify on-time markers and fixed conditions, reload persistence, preserve practice history, leave empty formal round. Save screenshot/evidence and commit exact scoped paths.

The sequence continues with melody, bass, rhythm, stem FX, vocal chopping and multi-track arrangement only after the relevant data gate and per-effect listening review. Existing bass/drum experiments count as prior evidence; no claim all seven are newly implemented here.
