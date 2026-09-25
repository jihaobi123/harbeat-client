# Vocal-led accompaniment bridge — test release

Public entry: https://8.136.120.255/analysis-lab-static/vocal-bridge-20260925/index.html

This is a six-case short audition, not the production automatic playlist player. The user authorized a test of outgoing vocals over the incoming song's intro/interlude. Production `/listen/`, candidate selection, the accepted aligned/gain-weighted vocal-overlap score, and its full progressive transition are unchanged.

## Audio behavior

Both arms use identical excerpts and tempo mapping. The reference reproduces the existing full-length linear deck fade and V30 dynamic EQ, including A's 20 ms EQ activation and B's last-half-bar dry restoration. B remains at its matched tempo until the preview ends; native-speed restoration is deliberately outside this experiment.

The bridge crossfades accompaniment during the first 40% of the overlap. A's separated voice remains at the original level through its detected end plus 150 ms, then fades out by the exit. B's voice is fully restored by that exit, before its detected first entrance. Each overlap is followed by ten seconds of B.

The live graph is `master * bed + vocal * (voice - bed)`. This equals `accompaniment * bed + vocal * voice`, where accompaniment is the residual master minus separated vocals. Equal bed/voice gains reconstruct the master exactly. All four nodes share the same AudioContext schedule; master/vocal nodes for each deck start on the same timestamp. Pause suspends this clock. Stop/replacement cancels downloads and invalidates stale asynchronous starts.

Only excerpts are prepared offline. Master and vocal channels are merged into one four-channel atempo operation before splitting, preserving shared time-stretch decisions. Float WAV preserves peaks above 1 without source clipping. Both arms use the existing 0.76 deck scale and the same 5 ms lookahead peak protection; user volume is after this protection. This is not a perceptually loudness-matched blind comparison.

## Eligibility and fixed cases

A/B reports and stem fingerprints must bind to the exact analyzed track. Every measured beat throughout the overlap must pass the existing 65 ms gate. B must have no detected voice during the whole entry window with guard margins, followed by a meaningful detected entrance 0.15–2 seconds later. A must contain at least two seconds of voice and finish its last detected vocal 0.5–3 seconds before exit. Tempo ratios are restricted to 0.94–1.06.

| A | B | B entry (source sec) | overlap (sec) | B rate |
|---|---|---:|---:|---:|
| Energy | DDU-DU DDU-DU (Korean Ver.) | 8.820 | 13.700 | 1.000000 |
| Movie Star | HOT | 42.560 | 8.580 | 1.000000 |
| 꽃 (FLOWER) | After LIKE | 54.200 | 7.691 | 0.996000 |
| Yensa | Big Flexa | 75.151 | 8.507 | 0.999115 |
| Nevada | The Spectre | 78.760 | 7.824 | 0.958589 |
| Leave Me Alone | Tonight | 53.200 | 7.860 | 1.000000 |

VAD and structural labels are estimates; quiet passages within a model-labeled chorus are described as vocal-free passages rather than certified interludes. Separation artifacts, undetected vocals, lyrical phrase truncation and harmonic mismatch remain listening questions. No key filter is claimed.

## Reproduction and deployment

Frozen inputs and manifests live on NAS at `/mnt/nas/harbeat/data/experiments/vocal-bridge-20260925/`: `selection.json`, `rendered.json`, `cases.json`. The complete selection byte hash is `28c5c75e8ccd0a214e759a33f8487449b3df81d66e040dfe1fc79ecbf272b9a5`.

Render on Jetson with Python, NumPy and FFmpeg:

```sh
python3 scripts/render_vocal_bridge.py \
  --selection /mnt/nas/harbeat/data/experiments/vocal-bridge-20260925/selection.json \
  --nas /mnt/nas/harbeat/preprocess \
  --reports /mnt/nas/harbeat/data/analysis-platform/reports \
  --output /path/to/new/staging
```

Bundle `scripts/build_vocal_bridge_manifest.ts` with the existing web esbuild installation, then run the bundle with three arguments: frozen selection path, renderer output `rendered.json`, output `cases.json`. The builder reruns timing/vocal checks and refuses a renderer hash different from the current selection bytes. Changing cue positions, rates or source/report fingerprints requires a new render.

Run `npm run build:vocal-bridge` from `web`. Copy the generated HTML as `index.html`, `assets/`, the existing `v3-clock.js`, verified `cases.json`, and rendered `audio/` into a new experiment directory. Do not overwrite the production symlink or library.

The current public files live at `/home/mark/harbeat-analysis-platform/web/dist/vocal-bridge-20260925/` on Jetson, served through the existing cloud static proxy. The 24 excerpts total 135,703,872 bytes. NAS retains the original songs, analysis and frozen selection; Jetson holds this public excerpt cache. The cloud's 5.2 GiB free space was unchanged. Rollback is removing this experiment directory only; no service restart or production rollback is needed.

## Verification

- Existing frontend suite: 295 passing tests, 12 existing external-fixture skips, then the added selection-binding regression passed (296 total passing coverage).
- Nine new frontend tests cover eligibility, automation, residual identity, shared clocks, pause/resume, cancelled preparation, replacement and stale selection rejection. Two renderer tests verify joint-stretch channel relationships, exact frame counts and source path/hash rejection.
- Type checking and independent experiment build pass. Independent review's stale-render binding finding was fixed and rechecked.
- Re-rendered all 24 assets into a separate staging directory with selection binding: every asset matched the first render byte for byte. Removed the duplicate staging directory after comparison.
- Public HTML, JS, CSS, worklet and manifest match local release hashes. The complete production HTML/JS/CSS/worklet and `library.json` hashes match the preceding release.
- Desktop and 390 px mobile screenshots inspected; no horizontal overflow. Browser playback verification results are recorded in the release evidence, including all audio-thread transition events and source schedules. Audio-clock/peak checks verify execution, not musical preference.

All six cases completed both arms publicly (12 complete plays), with no browser errors and all 36 audio-thread observations on time. Cumulative protected peak was 0.960; cumulative minimum protection gain was 0.807 (about 1.86 dB attenuation). These extrema are session-wide, not per-arm measurements.
