# Vocal overlap cue experiment

This experiment replaces the vocal-conflict term in the accepted V3.1 ranking. The formal reference remains `audio-v3.1.0` (`2ba6c8f`). Its page and historical feedback are preserved.

## What changes

The original planner first selects B and its entry material. The experiment keeps that song, source range, audio asset, tempo rate and complete overlap duration. It then compares the original eligible A timings for that material. The 18-second request budget, beat constraints, waiting term, section bonus, full linear crossfade and dynamic EQ algorithm stay the same.

V3 subtracts `0.3 * A_vocal_fraction * B_vocal_fraction`. The experiment uses the same VAD intervals and 300 ms source-time padding, merges their unions and maps B into playback time with `(source_time - B_entry) / rate`. It intersects the two activity timelines and weights each simultaneous interval by `4*x*(1-x)`, where `x` is progress through the existing crossfade. The integral is divided by `2*duration/3`, keeping the penalty in [0, 0.3]. Continuous vocals on both tracks still receive the full penalty.

The curve measures the overlap of the deck gains. It does not measure actual vocal loudness, recognize lyrics or prove that a musical phrase is complete. The B mapping uses the nominal time-stretch rate; local timing changes inside the rendered atempo asset are not measured separately. Moving A changes the evidence used by the unchanged dynamic EQ algorithm, so EQ coefficients can differ between cue choices.

The runtime checks report and source identity, VAD time origin, track/run IDs, successful source binding checks and every VAD row against its preprocessing snapshot. Unknown, malformed or mismatched evidence produces an explicit unavailable result. The log records the old term, new term, mapped intervals, source row numbers, material anchor, candidate count and selected shift.

## Music and cases

The twenty accepted tracks retain their original metadata, windows and assets. Old windows may gain new variants keyed only by the six added A tracks. The original variants remain unchanged.

Six new songs passed the existing genre and preprocessing criteria:

| Track | Measured BPM | Source VAD coverage |
| --- | ---: | ---: |
| Soul Of Freedom | 94.0 | 74.5% |
| Rump Shaker | 103.4 | 93.1% |
| Wylin' | 73.1 | 83.3% |
| Victory Lap Five | 136.4 | 94.9% |
| DSK | 85.0 | 82.4% |
| Prayer Vox feat. Vivian Chen ~infused by Caccini 「Ave Maria」~ | 93.9 | 69.7% |

The initial expansion target was twelve additions. The audit retained six eligible songs rather than loosening the evidence requirements: 32 other model-labelled Hip-Hop records lacked canonical core analysis, and one had a tempo/grid inconsistency. Genre labels are model candidates. Selection uses source uniqueness, tempo and vocal coverage, before calculating experimental scores. Each preview covers at most the first 150 seconds of its source.

Fixed cases retain unavailable requests. New music gets a fixed old-to-new and new-to-old pairing at 30 seconds. The wider matrix checks every ordered pair at 15, 30, 45, 60 and 80 seconds. Changed-cue examples are labelled as selected demonstrations and are excluded from any claim about independent listening preference.

## Listening and feedback

Build with `npm run build:vocal-overlap` in `web`. The page has controlled comparisons, live requests, original-source audition, a mapped vocal timeline and request-linked audio observations. It shares the existing transport and PCM cache. Feedback uses `harbeat-vocal-overlap-feedback-v1`, with exact case, arm, session, request and plan IDs. A controlled audition must finish through eight seconds after takeover before feedback is enabled.

The local preview is served by the delivered `serve-local.cjs` on port 4317. It serves the new page locally, reads existing public audio from HarBeat, and caches missing new audio from the private NAS through read-only SSH. Every new audio read is checked against its catalog size and SHA256. Its remote source is restricted to this experiment's immutable FLAC filenames. No UI or new music is published remotely by this server. The official-page link returns to the original remote origin, where previous browser feedback remains available.

Remote publication remains pending explicit user authorization after automatic approval review rejected uploading the experiment UI. The intended separate page directory is `vocal-overlap-20260924`; the formal index and previous versions must remain intact.

## Validation

- The frozen twenty-track matrix has 1,900 requests, 727 executable comparisons and one changed cue. Of the original twenty cases, nineteen remain executable and none changes its cue.
- The expanded 26-track matrix has 3,250 requests: 1,326 executable comparisons, 1,924 unavailable under the existing constraints, and the same single changed cue. The twelve new fixed cases include eleven executable comparisons and one unavailable request; none changes its cue. All original track projections remain identical. Planner time at the 95th percentile was 2.67 ms on this machine; this is a local measurement, not a timing guarantee.
- In the changed example, 24K Magic (1) to Clap Clap at 80 seconds, A moves 2.24 seconds later. The same B asset keeps its 4.485986-second overlap. The new proxy decreases from 58.7% to 27.4%; this is not a listening preference result.
- 217 source tests pass with the expanded matrix, frozen corpus and eighteen accepted feedback reconstructions enabled; nine unrelated opt-in fixtures are skipped. TypeScript checks and experiment/formal builds pass. Five Python corpus-builder tests pass.
- An isolated browser on the expanded local page completed both arms of the changed example, the MOMMAE to Soul Of Freedom fixed audition, and a live request with that new song. All three audio-thread events were observed for each transition. Existing eighteen feedback records remained unchanged, three new test ratings persisted separately, and desktop/mobile checks reported no page errors or failed requests. These observations do not measure speaker or Bluetooth latency. Details are in `expanded-local-browser-proof.json` and the corresponding session exports.

All 823 new single-song assets passed size and SHA256 verification on the private NAS. The local package contains the six native previews and uses verified read-only caching for remaining clips. Expanded coverage and per-request results are in `coverage-matrix.json`.
