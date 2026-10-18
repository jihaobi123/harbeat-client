# Individual Vocal Handover Implementation Plan

> Execute inline using executing-plans; obtain requesting-code-review independent review of the new comparison before delivery.

**Goal:** Deliver the remaining individual vocal-handover auditions with the true original fade as reference and no echo.

**Architecture:** Preregister frozen existing-policy candidates, run source-bound endpoint evidence, prepare up to three passing source-shared cases, and use a separate blind page and persistence namespace. Old experiments and unrelated working changes are preserved.

**Tech Stack:** Existing Python/Essentia/YAMNet/pYIN/ffmpeg on Jetson; TypeScript/React/Vite/WebAudio locally.

- [x] Freeze the prior accepted anchor and one plan per other eligible shortlist source before new inference; save selection, hashes and exact cue provenance.
- [x] Prepare and run model/pitch observations in a new NAS experiment directory. Verify coverage-v2 reports; retain every rejection without cue replacement. Select the first two additional passing distinct sources in frozen order.
- [x] Bind NAS manifests/source hashes, render nine shared clips per pair, and build a separate pack with source-bound selected ends and a complete candidate audit. Keep original endpoints, rate, EQ, bass and incoming-vocal rules.
- [x] Write regression tests demonstrating that reference uses natural rest curves, treatment changes only outgoing vocal/accompaniment curves, incoming voice/bass remain equal, no FX source loads, and durable logs/early votes persist. Run red before implementation.
- [x] Implement the new policy/player/UI by adapting the existing endpoint page and isolated echo log/clock fixes. Use independent DB/round/pack schemas, all-case initial-choice gate for reveal, standalone config on5197, and visible skipped-case explanations.
- [x] Run appropriate Python/TypeScript regressions, typecheck/build, source/PCM audits and independent review; resolve important findings.
- [x] Actually play every arm in practice, verify render observations and frozen invariants, early voting, saved history after reload/export, zero playback errors, and blank formal round. Save evidence/screenshot, open the deliverable, and commit only scoped files.

## Preparation results

Five new candidates were frozen before model inference, selection SHA0d88eb45943d78cf3f2e4647ef1e0ca64b993312ba6a725785fcc3c6df1a54d6. Each uses a single existing-policy plan from the prior shortlist. WANNABE → Tonight and GOOD BOY → Snake Gang passed. Shoot Your Shot → Feeling for You, I Like → Feeling for You and Luv(sic.) Part3 → 中国风？(已售) were rejected for incoming activity; no cue substitutions.

The accepted Doin’ It → Talgo anchor is bound to coverage-v2 pack SHA2f31c53d3797b2f6b23967a035b3ae861fe5e66429734943a122d6b79fe12348. Its timing, plan/EQ, bass, relay, endpoint, provenance and nine assets match the earlier delivered echo formal snapshot233c61d0. Explicit anchor binding was recorded after new-candidate inference began, retaining that timing caveat; it did not depend on those new results. Packaging checks exact historical pack and case equality, then validates fresh coverage-v2 observations independently.

Nine isolated source contexts received actual YAMNet/voice-instrumental inference and pYIN/envelope analysis. The original context request and observation audit are retained. WANNABE reached actual source EOF at191.242061s before the requested194.18s; only the observation end was corrected to decoded EOF, with the frozen185.213061–189.18cue unchanged. No silence was padded. Final model inference was rerun on all nine contexts before pitch and fresh reports. Observed coverage still spans the guarded handover.

Independent review found one important anchor-binding gap, fixed with a failing-then-passing drift regression. Re-review found no further important code issue. Local packaging uses the coverage-v2 anchor directory, not the older v1 pack.

27/27served source asset hashes and decoded frame counts passed.45Python tests and106related TypeScript tests passed, including27new TypeScript tests; typecheck and standalone Vite build passed. Build only reported stale Browserslist data. All inputs keep their frozen original plans; generated source clips carry no effect layer.

## Browser acceptance

Practice round4d87aa05-c030-4e4b-ac50-6f11a2397c7e completed all six arms with36on-time render observations, no playback failures or browser errors/warnings. All frozen plans/EQ/bass/assets/incoming-vocal curves and relative native takeover times match; natural/relay accompaniment and outgoing-vocal curves differ as designed. Early votes, solo vocal Play/Pause, archive and reload/export passed. Practice choices are excluded. Blank formal round0d0abe4b-3203-4f22-a943-769dc9e1a740 remains with zero starts/heard/choices/reveals. Common limiter reached minimum0.9398021 in GOOD BOY relay (~0.54dB attenuation); all other arms1. This is an observed output-chain difference, not a loudness-equivalence claim. Formal listener review is still pending.

## Formal listener results — 2026-10-18

Round0d0abe4b-3203-4f22-a943-769dc9e1a740 completed all three initial blind choices. Doin’ It → Talgo:A/relay; WANNABE → Tonight:B/natural; GOOD BOY → Snake Gang:B/relay. Both versions of all three cases had rendered the protected-end position and original native takeover before the first vote, including the earlier GOOD BOY relay pass before its repeat. No complete-clip requirement is imposed. Practice round4d87aa05 is excluded. Raw export and coverage analysis are retained under the vocal-handover work directory, with hashes in evidence.

Two relay preferences and one natural preference establish mixed case-specific usefulness. There are no tie or neither choices, no reported symptoms or notes, and no basis to label an artifact, incomplete lyric or exact cause. The preferred relay cases have7.895/10.116soverlaps and2.938/4.099sof outgoing voice after early bed transfer; natural-preferred WANNABE has3.967soverlap and1.204sof voice after bed transfer. Available handover space is a hypothesis for further replication, not a duration threshold or causal conclusion. GOOD BOY relay mild limiter attenuation and unmatched perceived loudness remain limitations.

This prepared round's listener choices are complete and archived. Keep original defaults; no universal activation, automatic threshold, new effect or combined-method experiment was added when reading these results.
