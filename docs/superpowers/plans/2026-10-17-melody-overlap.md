# Melody overlap audition implementation plan

> Execute inline with executing-plans, task by task; the user approved the concrete design. Preserve all unrelated working changes.

**Goal:** Three fixed-pair comparisons altering only the melody/bass layer gain envelope.

**Architecture:** Freeze first-round harmonic variant plans. Prepare report-bound short master/vocal/drum excerpts with shared six-channel tempo processing, preserving original B takeover/native speed. Use identical per-layer EQ chains, reference drum/vocal gains, and algebraic residual reconstruction. New local page and separate transport; no production changes.

**Tech stack:** TypeScript/Vitest, React/Vite, Python/NumPy/FFmpeg on Jetson, existing audio cache and output limiter.

## 1. Policy and reconstruction

- [x] Create `web/src/melody-overlap/policy.test.ts`; RED tests require final verified source bar, reject malformed/nonfinite/outside cues and freeze input. Verify reference vocal/drum curves identical in both arms and master gain/correction gains algebraically reconstruct reference audio at every sampled time.
- [x] Implement `policy.ts`: `curves(pre,duration,shortStart,mode)` returns A/B layer points. Reference gain is original linear crossfade. Short mode keeps A melody until shortStart, then fades A out and B in by takeover. Vocals/drums always reference curves. `correction(layer,bed)` combines union knot times.
- [x] Use `npm test -- src/melody-overlap/policy.test.ts`; expect RED then all green.

## 2. Frozen selection and source renderer

- [x] Create `scripts/prepare_melody_overlap.ts`; read existing harmonic pack, freeze variant plan, select last complete A bar using existing bars/beat gate, copy source provenance and vocal conflict evidence. No rescoring or alternate cue selection. Save input to workspace `work/melody-overlap-20261017/selection.json`.
- [x] Create `scripts/test_melody_overlap_renderer.py` then `render_melody_overlap.py`. RED tests assert exact interchannel alignment/length, H=master-vocals-drums reconstruction, source SHA rejection, and finite output. Use one six-channel atempo operation per entry; write separate stereo short assets. Prepare A pre+overlap, B entry at original rate, B body eight seconds at native speed. Never mix songs offline.
- [x] Read source-bound NAS manifests, verify track/run/master SHA and all stem hashes. Render in Jetson temporary output and copy only short assets to ignored `web/melody-audio/`. Record real layer RMS during overlap as sample evidence, not a conflict diagnosis. Skip ineligible cases and report count.

## 3. Independent player and page

- [x] Create `web/src/melody-overlap/transport.test.ts` using a fake AudioContext only for scheduling boundaries and cancellation. Require identical case/plan/EQ/voice/drum evidence for both modes, single clock, B entry/native handoff at same frozen time, no sources after stop during loading.
- [x] Implement `transport.ts`: reuse AudioCache/pool, v3-clock limiter, scheduleV30Eq, referenceCurves and stemGainPoints. Each layer uses identical EQ/wet-dry timeline, with post-filter master/correction gains. Use .76 reference scale, 4ms native body edge, source-bound logged plan. Stop after eight seconds of B body. Abort obsolete loads, dispose on unmount, collect complete/failed/aborted session logs.
- [x] Create standalone `melody-overlap.html`, `vite.melody-overlap.config.ts`, `main.tsx`, `MelodyOverlapLab.tsx`, `style.css`. Three cases, reference/short buttons, stop, exact fixed plan summary, provisional separation notice, local preference/export, reversible test vote. Do not alter harmonic audition or production files.

## 4. Verify and deliver

- [x] Run policy/player/renderer tests plus harmonic, automatic quality, beat alignment, vocal scoring and existing transport regressions. Run TypeScript and isolated Vite build.
- [x] Use CUA browser to play both arms of every eligible case to completion; verify scheduled plan, voice/drum points and EQ equality from exported logs. Test stop, replacement, load cancellation and local feedback export/undo. Save screenshot.
- [x] Independent code review via requesting-code-review skill; fix important findings, preserve user dirty changes. Record checks in `docs/evidence/melody-overlap-20261017.json`, commit only this experiment. Leave local page open for user audition; no production deployment or claims of subjective improvement.

Implementation notes: the existing 65 ms local beat gate remains authoritative. All Falls Down’s observed final bar ends 30 ms before its frozen exit, within that existing tolerance; the exit itself is retained exactly. Short overlap begins at the recorded final-bar start. Assets above unity use float WAV, other clips use FLAC; neither arm is normalized separately. Shared multi-channel WSOLA can have a different texture from the previous single-master entry; both arms of this experiment share those same rendered assets. Limiter minimum statistics are lifetime values, not per-arm loudness evidence.

## Final verification

134 TypeScript tests passed; the optional corpus test was skipped. Five renderer tests passed on both local and Jetson runtimes. TypeScript and the isolated build passed. All 27 copied stereo 44.1 kHz assets matched recorded bytes, frames and SHA-256; seven preserve above-unity samples as float WAV and twenty use FLAC. Total assets: 53,455,141 bytes.

CUA browser exported six complete sessions with 18 audio observations and zero late observations. For each pair, original plan and EQ matched the frozen pack exactly, voice/drum points matched across arms, and each session finished after its expected duration. Stop/replacement, load cancellation (unit), feedback save, note edit, export, undo and case-switch persistence were checked. No browser warnings/errors; no subjective sound-quality judgment was made. Independent review found no remaining critical or important issues.

Local proof: workspace `work/melody-overlap-20261017/{qa-result.json,browser-playback-export.json,melody-overlap.png,selection.json,pack.json,source-inventory.json}`. Audition URL: `http://127.0.0.1:5188/melody-overlap.html`. Production defaults and previous harmonic audition remain unchanged.
