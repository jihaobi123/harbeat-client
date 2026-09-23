# Multiple listening cases implementation plan

Goal: expand each approved single-variable experiment to 12 source-visible listening cases without altering the V3 baseline.
Architecture: deterministic case catalog plus generalized fixedTrial; independent source-verified tail assets; case-aware UI and feedback identity.
Tech: TypeScript/React/Vitest, FFmpeg on Jetson, existing static publish path.
Execute inline under the user's existing authorization.

- [x] Add failing tests for diverse directed pairs, same-case invariants, deterministic ranking cases, and feedback identity.
- [x] Implement case selection and generalize fixedTrial with backward-compatible legacy case.
- [x] Prepare exact tail assets on Jetson from hash-verified masters; preserve source provenance.
- [x] Add case picker, per-case coverage/feedback status and visible changed/unchanged result. Clear stale feedback on case changes.
- [x] Test every case against real catalog, build, check browser selection and selected playback cases.
- [x] Deploy independent release, preserve previous page and baseline, update docs and push GitHub branch.

Validation: 80 unit/integration checks passed; 12 real tail assets passed source/time invariants. Browser checked all 72 case bindings, then played four arms over FREE BRO → Big Girls, RATATA → Cold, and No Me Tocas → Crazy Love. Twelve audio-thread events observed, full logs persisted, feedback unlock and case isolation verified; mobile layout has no horizontal overflow. These are execution checks, not listening preferences.
