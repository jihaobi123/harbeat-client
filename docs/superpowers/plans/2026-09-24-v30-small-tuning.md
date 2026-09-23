# V3.0 Small Tuning Implementation Plan

**Goal:** Preserve V3 playback behavior while testing only local boundary calibration and EQ coefficients.
**Architecture:** Original V3 catalog/planner → optional bounded cue adjustment → unchanged gain/wet paths with optional dynamic EQ → independent 2×2 lab.
**Tech Stack:** TypeScript, React, WebAudio, Vitest, existing Jetson static relay.

- [x] Add failing tests in `web/src/v30/tuning.test.ts`: same B/window/asset/duration; shift bounded to next bar and original budget; missing evidence/no improvement retains baseline; fixed/dynamic share cue; no phrase hold.
- [x] Implement source-bound assessment and bounded candidate selection in `web/src/v30/planner.ts`; attach original/updated measurements and unchanged-variable manifest.
- [x] Add failing `web/src/v30/tuning.test.ts` tests for spectrum-dependent bounded/slew-limited controls, midpoint sensitivity, missing energy and no change to gains. Implement `eq.ts` around V3 fixed coefficients, not phrase automation.
- [x] Add optional `v30Eq` coefficients to Plan and schedule them in original transport branch; verify V3 gain/wet/dry schedules remain identical and extra EQ clocks cancel correctly. Trace actual EQ and calibration evidence.
- [x] Build independent `V30Lab`, preserving old catalogs and feedback; assemble original20-track catalog + hash-bound alignment with gzip snapshots. Render all available original cases and explain retained cues.
- [x] Validate corpus invariants; run regression tests, review using requesting-code-review, deploy isolated page and main link. Browser-test actual paired EQ, live request, feedback persistence and audio events. Push code/docs and retain original V3 link.

Acceptance tests are structural invariants plus real browser execution; no automatic metric is treated as proof of perceptual preference. User authorization covers implementation/deployment; do not ask again.

Validation: 183 source tests passed; real corpus check ran separately (157 fixed-pair positions plus 1,900 pair/position probes). Four-arm browser replay and a user-triggered live transition completed with unchanged overlap; feedback eligibility, persistence, main entry, and old HTML fingerprints verified. GitHub publication follows the validated implementation.
