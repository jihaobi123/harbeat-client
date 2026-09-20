# V3: exact replay of the colleague's delivered mix

The user preferred the colleague's audible result and requested its logic be retained. V3 replays the colleague's selected six-song decisions and executes the original rendering function bodies, without any V2 route scoring, 100 BPM normalization, per-song gain policy or FIR EQ.

## Reproduction

```
.venv-lab/bin/python mixing/recipes/render_demo_v3.py --sources /path/to/sources.json --output /path/to/result
# Historical review-page recipe and its required artifacts: see mixing/README.md
```

Inputs: the hash-pinned original renderer and plan under `mixing/vendor/colleague_demo_v1`, plus six local originals mapped from the V1 frozen source list. Original renderer SHA-256: `8cf342e72a688ccde658cf402866f63f3cc7fe8eafd7fc70857cc32d6185069a`. The original authorship is retained. The loader selects only rendering function definitions, constants and the annotations future import, avoiding missing planner dependencies. The function bodies remain unchanged; a wrapper logs audio command arguments.

The missing original planner dependencies mean the 720-route search is not rerun. Original chosen order, section anchors, incoming rates at full precision, and vocal flags come from the delivered plan. Overlap is recovered from incoming source milliseconds divided by that full-precision rate, rather than using rounded display values. The renderer's own millisecond formatting and its original limiter are retained.

## Audio policy

- Closer → Bring Back The Summer → Paris → Clear → What Lovers Do → Don't Say.
- Incoming intro at A BPM / B BPM; body at its original rate.
- Original FFmpeg linear crossfade, bass/treble shelves, final-half-bar wet-to-dry recovery.
- Incoming bass -7 dB at 140 Hz and treble +1.2 dB at 3600 Hz. Outgoing bass -9 dB and treble -1.4 dB.
- Original optional 1200 Hz mid cut -5 dB; all five delivered vocal decisions are false.
- Every segment gain 0.76; final mix limiter limit 0.96 with level=false; final seven-second fade.
- Original 16-bit WAV stages, 44.1 kHz stereo, MP3 libmp3lame 320 kbps.

## Verified result

The newly rendered MP3 is byte-for-byte identical to the colleague's original file:

`d87180977de7494bf3e2e4e2640049bd50c712fb4d25c8fffe6861eb93182a41`

Decoded audio also matches exactly: 18,971,667 stereo frames, 430.196531 seconds. All five transition timestamps returned by the original renderer have zero difference from the delivered record. MP3 integrated loudness -10.57 LUFS, true peak +1.93 dBTP, exactly as in the reference. These values were measured, with no extra normalization or true-peak attenuation applied to the artifact.

18 related tests passed (V3, V2 and render suites). Browser checks cover both full players, five snippets, exclusive playback, five decision-log cards and mobile overflow. Source originals, V1, V2 and prior analysis remain unchanged. Structural uncertainty is retained; reproduction success does not certify semantic boundaries or human musical quality.

Artifacts: `outputs/demo-render-v3/listen`, including newly rendered WAV/MP3, five clips, original reference, frozen plan, recorded commands, comparison JSON, checksum manifest and two standalone pages. `work` holds intermediate WAVs and decoded numerical comparisons, outside the published directory.

## Publication

https://8.136.120.255/analysis-lab-static/demo-3-20260920/index.html

Published 16 checksum-verified files through the existing Jetson static service and cloud relay, without restarting or changing the backend. Public checks passed: page 200, MP3/WAV byte range 206, playback of both full versions and all five clips, mutually exclusive players, five log cards, mobile layout, no browser errors or failed responses. See `outputs/demo-render-v3/release-validation.json`.
