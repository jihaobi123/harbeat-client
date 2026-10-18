# Rhythm Bridge Implementation Plan

> Execute inline with executing-plans; independent review at completion.

**Goal:** Deliver three independent natural-drum bridge A/B auditions.

**Architecture:** Fixed original masters plus signed drum correction through identical original EQ. Existing local player, blind-record and persistence pattern, isolated namespaces and assets.

**Tech Stack:** Python/ffmpeg/NAS; TypeScript/WebAudio/React/Vite.

- [x] Add failing `web/src/rhythm-bridge/policy.test.ts`: original master gains equal, drum ownership sums1, A holds to final bar, only drum changes, invalid boundaries reject. Run `web/node_modules/.bin/vitest run web/src/rhythm-bridge/policy.test.ts`; implement `bridgeCurves` with complementary final-bar fades and correction union knots.
- [x] Freeze three existing plans and source drum hashes in work/rhythm-bridge-20261018/selection.json. Implement scripts/render_rhythm_bridge.py using render_melody_yield.stretch_pair and strict published manifest/report verification, emit18hashed stereo clips plus per-bar natural drum RMS. Skip quiet/unavailable sources; never move cues.
- [x] Adapt existing standalone graph/player/rounds/UI into web/src/rhythm-bridge, new5200Vite entry. Keep original EQ, source lengths, native takeover, limiter and output gain. Change layers to Master/Drums and log both bridge-start and native takeover. New database/schema, early choices and first-choice persistence.
- [x] Run policy/transport/rounds and renderer tests, typecheck and standalone build. Independently review changes. Actual browser practice plays both arms of all cases, verify on-time markers and output stats; practice early choice then archive, reload/export blank formal round, preserve previous records, screenshot and scoped commit.

## Delivery verification before human listening

66TypeScript tests (21new),11Python tests (9new), typecheck and standalone build pass. No important/critical independent review findings after frozen manifest binding; minor copy corrected and forged source rejection tests added.18actual decoded asset frame counts/hashes pass. Six actual browser plays complete, each with five on-time render markers and minimum limiter gain1; no console errors/warnings. Early practice vote accepted before any complete play. Practice cd6afdbb-7b0e-4d75-bf82-79bf31d6a7da excluded and archived; blank formal 335b4639-46b0-4276-a213-de6788e0b6cb survived refresh/export with all prior player logs.14preexisting tracked modifications retain their hashes. Source/selection/raw exports/screenshot preserved in work/rhythm-bridge-20261018; formal listener results pending, no quality trigger or production rollout.

## Listener results archived

Formal335b4639-46b0-4276-a213-de6788e0b6cb: Attention→HIPHOP prefers bridge; Meant To Be→HIPHOP and All Falls Down→GRILLZ prefer original. All first blind votes are B, with independent concealed mappings resulting in1bridge/2original. Both native takeovers were observed before each vote, regardless of full-play heard flags. Third original stopped about0.48safter takeover, limiting later-tail conclusions. No reveal, symptoms or notes; practice excluded. User overall impression is a slight benefit above no added effect, less satisfying than the previous effect (not explicitly named); preserve separately from case votes and do not claim controlled cross-effect ranking. Stable outgoing drum energy versus declining tails is a replication hypothesis, not a rule; retain original default. Current independent round is complete; no next technique or combination implemented in this feedback review.
