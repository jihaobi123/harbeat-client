# Standalone Vocal Echo Implementation Plan

> Execute inline using executing-plans; requesting-code-review at integration.

**Goal:** Three fixed original-versus-vocal-only echo auditions, without protected handover.

**Architecture:** Verified existing contexts/clips → finite original-gain vocal send → unchanged original dry graph plus wet toggle → isolated5201blind page.

**Tech Stack:** Python/numpy/scipy/soundfile; TypeScript/WebAudio/React/Vite.

- [x] Add failing policy and render tests. Assert dry equals original natural treatment, independent bass rejected, wet toggle only; gain before delay, finite support, input unchanged. Run `vitest run web/src/vocal-echo-solo/policy.test.ts` and `pytest tests/test_vocal_echo_solo.py` before implementation.
- [x] Implement `scripts/prepare_vocal_echo_solo.py`: bind source pack/analysis hashes from frozen-input, run verified_analysis, compare original embedded contexts/endpoints/source metadata, hash/decode all nine dry assets, apply `plan_vocal_echo`, original fade weighting before `render_vocal_echo`; emit wet-only hashes/support and explicit rejection audit. Preserve all dry bytes and plan fields.
- [x] New `web/src/vocal-echo-solo` policy/player/rounds/UI, entry/config5201. Adapt existing ten-source echo graph, replace protected dry policy with natural original; record send/wet/native markers and source gain policy. Independent storage/schema; allow early choice, preserve first choice and historic logs.
- [x] Targeted/related regressions, typecheck/build, independent review; actual both arms all accepted cases in practice. Confirm original dry equality and wet0/1, eight on-time markers, peak/limiter stats, early choice, refresh/export history; leave blank formal and screenshot, update evidence/roadmap and commit only current files.

## Delivery acceptance; listener preference pending

28new TypeScript tests,107related frontend and22Python tests pass (5new). Typecheck/standalone build pass. Independent review found and verified correction of live post-EQ wet cutoff and censored A-gap wording; no remaining important/critical findings. All27dry hashes and original plan/vocal fields equal parent;3finite wet assets verified. Final practice 8f75c994-964c-4a06-ab90-3c1032d4a017 completed six plays with8on-time render markers each, unchanged dry curves/assets/EQ/plan, wet0/1 only, and minimum limiter gain1. Actual stop/replay and early choice passed. Pre-fix practice remains separately archived and excluded. Fresh blank formal 73f1842c-e818-408e-95d3-e69edf43cc5e survived refresh/export with all history/player logs. No console errors/warnings.14existing tracked modifications retain hashes. Raw inputs/exports/audit/screenshot retained in work/vocal-echo-solo-20261018. No listener outcome, quality trigger or combination claimed.

## Listener review complete

Formal73f1842c-e818-408e-95d3-e69edf43cc5e: Doin’ It→Talgo chose B/original; WANNABE→Tonight tie; GOOD BOY→Snake Gang chose A/original. Total2original/1tie/0echo/0neither. Both wet-support windows and native takeover markers were heard before each initial vote across earlier plays; do not require whole-clip completion or ignore earlier complete replays. Doin’ It echo native takeover was only32msbefore vote; GOOD BOY original stopped~0.297safter takeover, limiting later-tail conclusions. No symptoms, notes or reveal. Practice rounds excluded. No beneficial trigger established for this fixed original-gain three-tap setting; retain original defaults and do not silently combine this effect with prior preferred treatments. This does not test all echo timings/strengths or vocal FX.
