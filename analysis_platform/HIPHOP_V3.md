# NAS Hip-Hop six-song mix — confirmed V3 audio policy

The user's confirmed Future Bass V3 baseline is archived locally under `deliverables/HarBeat-V3-20260920-confirmed` and on NAS at `/mnt/nas/harbeat/mix-releases/v3-20260920-confirmed`. Its reference MP3 SHA-256 remains `d87180977de7494bf3e2e4e2640049bd50c712fb4d25c8fffe6861eb93182a41`.

## Inputs and selection

Read the existing NAS report index and latest reports without modifying analysis. The snapshot contains 241 distinct audio identity records (including alternate versions); five genre results were failed/null, not treated as predictions. The published candidate list contains 49 directory-song IDs with either an existing manual Hip-Hop label or a top-1 Discogs400 parent of Hip Hop. Labels and model scores stay separate.

The six selected tracks all have top-1 model parent Hip Hop and published SongFormer intro/chorus plus ready, run-bound Silero vocal intervals:

1. FREE BRO — Bandmanrill — 149.4 BPM — Grime
2. Big Girls — IShowSpeed — 142.9 BPM — Trap
3. RATATA — Skrillex, Missy Elliott, Mr. Oizo — 125 BPM — Trap
4. Cold — Stormzy — 137 BPM — Grime
5. No Me Tocas — Lazuli — 130 BPM — Trap
6. Crazy Love — Tion Wayne, LeoStayTrill, MJ Cole — 136.4 BPM — Grime

Come Up was excluded: nominal 146.3 BPM versus a median recorded bar interval corresponding to 160 BPM (>5% disagreement). Older classic Hip-Hop library records remain in the catalog list but were not promoted from coarse drop/phrase labels into confirmed chorus boundaries. Model scores are raw outputs, not accuracy probabilities.

Original audio bytes match manifest master SHA-256; report snapshots match their transfer hashes. Vocal records match track ID, analysis run ID and the published vocal asset SHA. Original source labels, flags and files remain unchanged.

## Policy and missing dependencies

`analysis_platform/colleague_policy.py` executes the hash-pinned colleague script's original section selection, transition cases, vocal-window rules, and transition score functions. Its missing `phrase_mix.snap_to_bar` helper is explicitly adapted to nearest/floor/ceil **recorded** `bars_ms` values, without V2 fitting or extrapolation. Cue duration, key and drum helper functions come from the earlier user-supplied HarBeat V4 package; their hashes are logged. This is not a claim to have recovered the missing planner environment.

The script evaluates all 720 routes with the original start/trend/edge formula. Routes requiring unavailable intro tail bar anchors or overlap exceeding the first chorus are excluded. Two routes remain executable for these six inputs. The highest-scoring executable route is frozen, and all rankings and rejected pairs are downloadable. Degraded drum evidence keeps the colleague's weight of 0.17, with degradation exposed rather than removed or presented as calibrated.

Audio is produced by the unchanged render functions verified in the original V3 reproduction: intro-only A/B tempo matching, original body tempo, fixed 0.76 gain, original shelf EQ and optional 1200 Hz mid cut, original limiter, final seven-second fade. All five transitions trigger the original both-window vocal condition; this is not V2's strict simultaneous-intersection policy. No V2 fixed-100-BPM or local-loudness gain policy is used.

## Run and artifacts

```
/tmp/harbeat-analysis-runtime/bin/python scripts/render_hiphop_v3.py --plan-only
/tmp/harbeat-analysis-runtime/bin/python scripts/render_hiphop_v3.py
/tmp/harbeat-analysis-runtime/bin/python scripts/build_hiphop_v3_review.py
```

Input snapshot: `outputs/hiphop-v3/inputs`.
Output: `outputs/hiphop-v3/listen` (full WAV/MP3, five snippets, three pages, frozen plan, full route ranking, execution commands, selection CSV/JSON, six report snapshots, hashes).

The new mix lasts 260.944762 seconds. MP3 measured -11.81 LUFS and +0.13 dBTP; no extra normalization was introduced. Maximum difference between theoretical source-duration plan and the renderer's measured segment-length timeline is 96.155 ms. These records explicitly do not claim per-filter event instrumentation, limiter-latency compensation or browser sound-card telemetry.

22 related tests passed, including a real audio check of the original mid-duck branch and exact dry-body restoration. Local browser tests played the full mix and five snippets, checked exclusive playback, five logs, 49 catalog rows, filtering and mobile overflow. The selected boundary semantics remain unconfirmed. There is no colleague reference audio for this new set; byte-identity verification applies only to the preserved Future Bass baseline.

## Published and archived

https://8.136.120.255/analysis-lab-static/hiphop-v3-20260920/index.html

Public playback verified for all six players, all five transition logs, 49 catalog rows, filtering and mobile layout, with no page errors/failed responses. Anonymous HTML returned 200 and MP3/WAV range requests 206. NAS archive: `/mnt/nas/harbeat/mix-releases/hiphop-v3-20260920`, containing audio/logs, recipe and input snapshots with archive checksums. No service restart or authentication changes.
