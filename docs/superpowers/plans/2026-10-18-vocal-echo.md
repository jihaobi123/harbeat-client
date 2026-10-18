# Vocal-only echo implementation plan

> Execute inline with executing-plans. Obtain requesting-code-review independent review before delivery.

**Goal:** Deliver the next controlled stems technique, a finite vocal-only echo exit, and complete observation-review browser acceptance.

**Architecture:** Fresh source-bound v2 observations → guarded effect-window sidecar → deterministic wet-only clip → unchanged dry stems player plus one wet layer → isolated blind audition.

**Tech Stack:** Python/numpy/scipy/soundfile, React/Vite/WebAudio, existing round persistence and source validators.

- [ ] Finish existing review-page playback/save/reload/export acceptance; preserve unreviewed outcomes, existing notes and old listener records.
- [ ] Create tests/test_stem_effects.py first: finite source-window/gap/rate/B-onset guards and impulse/zero/repeat/edge PCM behavior. Implement analysis_platform/stem_effects.py. Protect inputs from mutation.
- [ ] Create scripts/prepare_vocal_echo.py to verify coverage-v2 source reports, all nine hashes and actual decoded A dimensions; save a hashed FX sidecar and finite wet asset. Reject mismatched or unsafe cases before publishing. Do not overwrite prior packs.
- [ ] Create web/src/vocal-echo/{policy,transport,rounds,VocalEchoLab,main,style} with tests before behavior changes. Base both arms on existing detected-end policy; add a fourth A filter path and wet-only source. Keep original B three paths and all nine dry source schedules. Use identical assets and dry automation in both arms.
- [ ] Create standalone web/vocal-echo.html and vite.vocal-echo.config.ts on5196; copy both reused vocal-endpoints audio and new wet audio for standalone build. Independent harbeat.vocal-echo.v1 records include fixed effect and input hashes.
- [ ] Run targeted Python/TypeScript and relevant regressions, typecheck/build. Review independently and fix important findings.
- [ ] Actually play both arms in practice, verify wet onset/end and original takeover markers, early voting, stop, solo wet playback, reload/export; preserve QA history and leave blank formal round. Save evidence/screenshot and scoped commit, excluding pre-existing dirty files.

Roadmap order after this listening checkpoint: replicate successful vocal/bass/rhythm techniques; partial drum/percussion bridge with subgroup alignment/bleed evidence; half/double-time relationship with phrase-grid validation; short scratch/stop/direct-cut variants; lyric slicing and multi-song arrangements after manual cue/role annotations. Each receives a separate controlled audition before automatic activation.
