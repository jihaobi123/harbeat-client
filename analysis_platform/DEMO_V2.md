# DEMO V2 audition and calibration

Approved scope: combine exhaustive six-track ordering, mapped audible-window vocal checks and attenuation-only low-band handling while keeping one immutable plan as the source of renderer and execution logs. This is a separate six-song audition; no production preprocessing replacement or authentication change.

## Run

Use the existing six hash-verified reports in `outputs/demo-render-v1/reports`, original paths from the frozen V1 plan, and the colleague plan in `outputs/colleague-demo-review-20260920`. The runtime needs numpy, scipy, soundfile, librosa, and FFmpeg on PATH.

```sh
/tmp/harbeat-analysis-runtime/bin/python scripts/render_demo_v2.py --plan-only
/tmp/harbeat-analysis-runtime/bin/python scripts/render_demo_v2.py
/tmp/harbeat-analysis-runtime/bin/python scripts/build_demo_v2_review.py
```

Outputs live in `outputs/demo-render-v2/listen`. Existing V1 and source reports are not edited. `plan.json` drives all gains and EQ. `execution.json` records applied DSP sample positions. `routes.json` retains all 720 rankings and 30 directional pair plans; fixed-gain consolidation for the winning route is explicit. The new low-band code is optional, so V1 plans keep their previous behavior.

## Acoustic comparison limits

There are no independent human annotations. Source audio SHA is checked. The comparison measures detected-transient proximity in each candidate intro/chorus, with 50 ms proximity windows. It does not measure ground-truth beat/downbeat/section accuracy. The colleague archive omits `snap_to_bar` and its raw input grid; its delivered endpoint plus nominal BPM reconstructs the constant-tempo proxy used for comparison. Early/late and full-span diagnostics are retained separately from the role-specific decision.

A timing-evidence winner requires at least 16 compared ticks, an eight-percentage-point coverage advantage and at least 10 ms improvement in capped mean distance. Clear and What Lovers Do favor the platform candidate in the chorus comparison; the other four are inconclusive. Current reproducible V1 grids remain selected. This does not certify bar phase or semantic section names.

Adjacent log-mel feature changes suggest review positions only. No section label is assigned from these features, no 30/11-bar phrase is coerced to a conventional length, and no original report is overwritten. Original, platform-click and colleague-click excerpts share the same source samples; the click references are candidates, not ground truth. Manual review starts unchecked, is stored only in the browser under the frozen plan ID, and can be exported with source fingerprints. Exports are not automatically applied to the server.

## V2 policy

- Target 100 BPM throughout each song; no tempo jump at the intro/body boundary.
- Rank routes by tempo distance, branch cost, mapped padded vocal intersection, and a modest Camelot heuristic. Degraded drum groups have zero weight. Ready drum inputs use the `kick`, `snare_clap`, `hihat` schema.
- Vocal unknown remains an error. In audible playback coordinates, pad intervals 0.3 seconds, require each side to cover at least 0.5 seconds and 5% of the window, plus at least 0.3 seconds of intersection. Raw intersection is also logged. Mid attenuation is -5 dB at 250–4000 Hz if triggered; all five selected transitions in this audition stay below the full trigger criteria.
- B low band at 140 Hz is -7 dB, restored over the final half-bar. A low band gradually reaches -9 dB during its exit. No positive EQ boost. Complementary FIR returns exactly to dry at zero attenuation.
- Local loudness and sample peaks set conservative trims; one fixed trim per song. Measure WAV and encoded MP3 true peaks after rendering.

## Validation

102 related tests passed (existing dependency warnings retained). The real render lasts 422.4 seconds. MP3 integrated loudness is -16.84 LUFS, true peak -2.02 dBTP. Sample event deviations are at most one sample. Independent bounded review found and prompted correction of the `snare_clap` schema mismatch; degraded six-song routing is unaffected. V1 WAV checksum is unchanged. Browser validation covers main playback, all 18 review boundary cards, candidate reference selection, unchecked defaults, browser persistence, six-track export and responsive pages.

## Published audition

Published separately on 2026-09-20 through the existing Jetson static service and Alibaba Cloud relay:

- https://8.136.120.255/analysis-lab-static/demo-2-20260920/index.html
- https://8.136.120.255/analysis-lab-static/demo-2-20260920/calibration-review.html
- https://8.136.120.255/analysis-lab-static/demo-2-20260920/decision-log.html

All 69 manifest entries were verified before atomic publication. Anonymous page GET returned 200 and MP3 byte-range GET returned 206. Public browser checks confirmed 422.4-second full playback metadata, both calibration click variants, 18 initially unconfirmed boundary cards, six-track review export, five transition logs, and no page errors or failed responses. Desktop and mobile layouts passed overflow checks. Results: `outputs/demo-render-v2/public-browser-validation.json`. No backend restart was needed.
