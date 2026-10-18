# Vocal-only echo implementation plan

> Execute inline with executing-plans. Obtain requesting-code-review independent review before delivery.

**Goal:** Deliver the next controlled stems technique, a finite vocal-only echo exit, and complete observation-review browser acceptance.

**Architecture:** Fresh source-bound v2 observations → guarded effect-window sidecar → deterministic wet-only clip → unchanged dry stems player plus one wet layer → isolated blind audition.

**Tech Stack:** Python/numpy/scipy/soundfile, React/Vite/WebAudio, existing round persistence and source validators.

- [x] Finish existing review-page playback/save/reload/export acceptance; preserve unreviewed outcomes, existing notes and old listener records.
- [x] Create tests/test_stem_effects.py first: finite source-window/gap/rate/B-onset guards and impulse/zero/repeat/edge PCM behavior. Implement analysis_platform/stem_effects.py. Protect inputs from mutation.
- [x] Create scripts/prepare_vocal_echo.py to verify coverage-v2 source reports, all nine hashes and actual decoded A dimensions; save a hashed FX sidecar and finite wet asset. Reject mismatched or unsafe cases before publishing. Do not overwrite prior packs.
- [x] Create web/src/vocal-echo/{policy,transport,rounds,VocalEchoLab,main,style} with tests before behavior changes. Base both arms on existing detected-end policy; add a fourth A filter path and wet-only source. Keep original B three paths and all nine dry source schedules. Use identical assets and dry automation in both arms.
- [x] Create standalone web/vocal-echo.html and vite.vocal-echo.config.ts on5196; copy both reused vocal-endpoints audio and new wet audio for standalone build. Independent harbeat.vocal-echo.v1 records include fixed effect and input hashes.
- [x] Run targeted Python/TypeScript and relevant regressions, typecheck/build. Review independently and fix important findings.
- [x] Actually play both arms in practice, verify wet onset/end and original takeover markers, early voting, stop, solo wet playback, reload/export; preserve QA history and leave blank formal round. Save evidence/screenshot and scoped commit, excluding pre-existing dirty files.

Roadmap order after this listening checkpoint: replicate successful vocal/bass/rhythm techniques; partial drum/percussion bridge with subgroup alignment/bleed evidence; half/double-time relationship with phrase-grid validation; short scratch/stop/direct-cut variants; lyric slicing and multi-song arrangements after manual cue/role annotations. Each receives a separate controlled audition before automatic activation.

## Implementation checkpoints

- Existing review page served all six source-audio hashes correctly; Doin’ It tail-position playback, save, reload and export succeeded in the in-app browser. All annotations remain unreviewed/unknown with no numerical human boundaries; temporary QA notes were removed. This is UI acceptance only.
- New effect window and wet-only clip generated from fresh coverage-v2 reports. Nine original assets and all frozen dry plan fields compare exactly. Decoded wet support9.84905–10.83587s, conservatively guarded through10.87587s on the clip clock; source end262.86413s is before original exit263.883s. Isolated wet peak0.221621; no normalization.
- Independent review fixed cumulative worklet statistics by adding an isolated per-play stereo meter resetting at scheduled onset. Browser development refresh also exposed reused log-bucket identity; immutable per-player record IDs now preserve previous buckets, with regression coverage. These changes apply only to the new experiment.
-39Python tests passed (8newFX +31existing endpoint coverage/source tests).27newTypeScript tests passed; final relevant suite214tests, typecheck and standalone build passed. Current listen comparison remains one functional sample, not general effectiveness evidence.

Final browser acceptance: round f5405731-7204-474c-a1b4-10ba7c7f6efe completed both arms with16on-time markers, identical dry treatment/assets and wet gains0/1. Fresh stereo meters reported peak0.832888 and minimum limiter gain1 in both plays; no perceived-loudness claim. Two reloads and export preserved all records. Blank formal round 233c61d0-446c-410b-a078-acfb5d59204f remains. Evidence: docs/evidence/vocal-echo-20261018.json. Local servers:5194(session44391),5196(session89145).

Dependency note: the FX preparation script uses the existing, pre-existing coverage-v2 working changes (verified_analysis/guarded handover API). Those files were hash-preserved and deliberately excluded from this scoped commit; synchronizing the source to another machine requires retaining those prerequisite changes as well as generated audio.
