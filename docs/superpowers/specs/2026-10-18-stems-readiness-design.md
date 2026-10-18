# Stems readiness and vocal/bed handover design

The user authorized auditing preprocessing and implementing supported techniques sequentially, one effect per audition. Existing frozen pairs and prior formal bass choices remain authoritative. This iteration implements only the first supported controlled treatment; subsequent techniques remain a listening sequence rather than simultaneous effects.

## Audit and decision
Audit live NAS published manifests, success/pointer hashes, asset presence, analysis availability and the 148 frozen audition report bindings. Distinguish computed/published data from validated semantic or perceptual evidence. No models or published data are changed.

Four stems and measured timing support isolated gain and FX experiments. VAD/RMS activity does not certify lyrical phrase boundaries; section labels do not certify vocal-free windows; global key and beat-level RMS do not certify local harmony/groove. Drum subgroup assets must be checked in actual manifests, independently of old preview asset selection.

## First treatment
Freeze all 12 previously auditioned plans. Admit only a case with bound A/B vocal evidence, no B detected vocal during entry plus 300ms before and150ms after, at least2s A detected activity, A last vocal ending0.5–3s before original exit and after55% overlap. Require existing measured beat gate. Select distinct sources deterministically; preserve all eligible cases up to3 and report shortfall. Existing inputs yield one candidate, Attention→HIPHOP; this is a technique smoke comparison, not generalization.

Reference uses the listener-selected bass strategy, original rest and vocal fades. Treatment transfers drum/melodic residual accompaniment over first40% of the existing overlap, keeps A vocal at1 through its last detected end+150ms, then fades it to0 by original exit. B vocal keeps original gain; no new vocal overlap is permitted. Both keep original bass curves, EQ, wet/dry, source clips, cue boundaries, speed mapping and native B takeover. The whole intended arrangement is the variable; this cannot isolate whether a preference comes from holding vocals versus moving accompaniment earlier.

Audio graph per side: master*bed + bass*(frozenBass-bed) + vocals*(voice-bed). Reference collapses vocal correction to0. Joint six-channel master/bass/vocal WSOLA extraction on each side preserves shared phase decisions; all stereo tracks must have exact timeline lengths. No per-arm normalization. New assets bind selection/report/manifest/master/bass/vocal hashes.

## Audition and validation
Independent page on5193, isolated IndexedDB. Natural/relay A/B mapping, early choices and immutable heard snapshots, actual render onset, alternating recommended order across rounds, complete logs, practice and formal reveal gating. Reuse the verified drum trial architecture in a separate namespace, including cancellation and render observations. No method/eligibility hints before reveal. User-facing wording says detected vocal end, never promises a complete lyrical phrase.

Tests verify frozen bass, original reference identity, new voice/bed envelopes, vocal guards and rejection, single-case persistence/reveal, shared timeline lengths and player cancellation. Verify all generated hashes and source bindings; actual playback both arms in practice, reload and export, archive practice and leave a clean formal round. Document limitations and unmet preprocessing requirements. No production deployment.
