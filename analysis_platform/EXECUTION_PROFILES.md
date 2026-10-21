# Device execution preprocessing

This extension keeps existing reports and NAS sources immutable. It exports new
source-bound sidecars, then optionally reusable song chunks for device mixing.
It never creates a pair-specific mixed WAV and does not run a new GPU model.

## Run

Use the existing isolated analysis environment (`analysis_platform/requirements.txt`).
It already pins NumPy 2.2.6, SciPy 1.15.3, librosa 0.11.0 and SoundFile 0.13.1.
The extension itself uses NumPy, SciPy and SoundFile. Beat This! and All-In-One
adapters remain in `services/preprocessing/app/modules/library/analysis.py`;
their model agreement is explicitly unknown unless separately evaluated.
On 2026-10-21 the isolated Jetson CPU exporter verified NumPy 2.2.6,
SciPy 1.15.3, librosa 0.11.0 and SoundFile 0.13.1. No new GPU model was
installed for this exporter. BeatThis/All-In-One package distributions were
not present in that CPU environment; separate existing model runtimes are
not evidence that those optional adapters ran for these exported profiles.

```sh
python -m analysis_platform.device_export --library /path/to/published-catalog \
  --output /mnt/nas/harbeat/preprocess/device-execution-v1 --profiles-only
python -m analysis_platform.device_export --library /path/to/published-catalog \
  --output /mnt/nas/harbeat/preprocess/device-execution-v1 --track-id TRACK_ID
python -m pytest -q tests/test_execution_profiles.py tests/test_metric_mix.py
```

`--library` contains `library.json` and its referenced per-track detail JSON.
`--nas` and `--reports` override the NAS defaults. A selected track may be
exported later for a reservation, without recomputing any pair transition.
Concurrent exporters hold a per-track filesystem lock and reload the current
index under that lock. A reservation can enter between background tracks;
completed rows from other exporters are preserved.

`analysis_platform.execution_publisher` is the optional cloud preparation queue.
It polls newly published tracks every 180 seconds, synchronizes only a compact
source catalog to the isolated Jetson CPU exporter, and copies lightweight
profiles back. Put requested reservation track IDs in the private queue file:

```json
{"trackIds":["track-d2d58531421de0eb9690"]}
```

The default queue is `/srv/harbeat-listen/execution-state/requests.json`; write
it atomically. The queue can contain known published IDs only. Explicit set
requests run before the six default audition tracks. A separate low-priority
CPU job fills the whole profile catalog in the background and yields its lock
between songs. Publication verifies object hashes and
source bindings before the ready flag. Pending transfer/capacity is reported
in private `status.json`, while original playback can continue. Cloud objects
are capped at 2 GiB with at least 3 GiB free disk retained. The daemon does not
restart or recover imports/GPU workers. Example service configuration is in
`deploy/analysis-platform/harbeat-execution-publisher.service`; install its code
at `/srv/harbeat-listen/execution-code` and its output under the queue root.
Expose only `execution-state/public` (including its `objects` directory), never the
queue, catalog, SSH settings or private status file.
For first publication while a larger CPU batch is still running, use
`python -m analysis_platform.execution_publisher --existing-only --once`.
This publishes completed immutable assets without waiting for another export.

## Protocol and evidence

`index.json` uses `harbeat.execution-library.v1`. Every profile binds track ID,
run ID, original master hash, report hash and verified immutable NAS manifest.
`profiles/<hash>.json` contains four stem energy/activity/transient timelines
at 125 ms; bass and other include local normalized pitch-class power. Silence
has unknown chroma. Drum spectral-flux peaks include frequency band, observed
beat index, within-beat phase, nearest sixteenth subdivision and timing residual.
These are onset bands, not instrument labels or a calibrated groove score.

Per-bar interval regularity is labeled as a heuristic. Complete 8/16-bar spans
are candidate evidence; musical phrase confidence and model agreement remain
unknown. Existing human-activity/VAD and cue safety rules remain authoritative.

`tracks/<id>.json` uses `harbeat.execution-track.v1`. Its stems contain aligned
16-second source chunks, with exact integer source frame bounds and common
source origin zero. `objects/<hash>.flac` is PCM 24-bit at the original sample
rate and stereo channel count. Float sources are quantized with maximum
half-LSB amplitude error; out-of-range float sources are rejected rather than
clipped. Each object's actual encoded bytes are SHA-256 checked. The source
fingerprint remains separately available and never means the re-encoded bytes.
No paths to private NAS storage are included in public objects.
The master can have a different sample rate only when integer cross-products
prove exactly equal source duration. `masterSampleGrid` records this rational
mapping; both master and stems are decoded into the shared device audio rate.
Even a one-sample unexplained duration difference remains rejected.

`metric_mix.strategy.strategy` validates the existing cue plan and joins the
two bound profiles. It returns `harbeat.execution-strategy.v1` with the old
provisional method thresholds, explicit source mapping and no rendered output
statistics. The device still needs pitch-preserving processing, sample-clock
execution and peak protection. Profile-only vocal handover stays disabled until
the existing finer waveform tail/quiet guard is satisfied locally.

## Publication and disk budget

Publish JSON under `/listen/execution/` and encoded immutable objects under
`/listen/execution-media/<hash>.flac`. Copy only selected track objects and
their manifests to the cloud; keep the complete canonical objects on NAS.
An index entry with `assetsReady: false` is profile evidence, not a promise
that mobile audio is available. A cloud publisher must advertise `assetsReady`
only after all referenced assets have arrived and hashes have been checked.
One catalog's four stems can exceed the cloud's available disk space.

The known stale report binding for `track-080bca25199811cdd57d` is explicitly
excluded until a new source-bound publication fixes it. Missing evidence and
other validation failures appear in `index.json.excluded`; they never become
perfect compatibility scores.

## Execution acceptance snapshot, 2026-10-21

The isolated Mac test environment passed 25 tests; the actual Jetson isolated
analysis environment passed the same 25 tests in 3.57 seconds. The suite covers
silent/unknown evidence, local pitch and sub-beat events, exact source-rate
mapping, source/report mismatch, corrupt object repair, stale ready retirement,
finite numeric limits and two simultaneous exporter processes preserving both
index rows.

At 16:29 CST the cloud publisher had 25 source-bound profiles and all six pilot
tracks fully verified and downloadable: HIPHOP, Make It Right, Attention,
All Falls Down, GRILLZ and Sorry. Their encoded stem chunks total 349,081,523
bytes, reused across pairs. Sorry verifies exact rational duration equality
between its 48 kHz master and 44.1 kHz stems. The publisher service is enabled;
remaining catalog profiles fill in a separate CPU job. This snapshot does not
claim full-catalog completion or APK/device audio acceptance.

Observed isolated-vocal activity, chroma and drum events are analysis evidence.
Complete 8/16-bar spans are available as candidates, with musical-phrase
confidence still unknown. No new long-overlap rule is automatically approved
by this CPU export, and no pair-specific rendered WAV is required by it.
