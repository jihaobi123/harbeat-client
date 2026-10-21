# JSON strategies from Jetson

The gateway adds `POST /plans` and `GET /plans/{id}` beneath the existing public
`/listen/smart-api/` prefix. Existing `/jobs` endpoints and rendered auditions
remain available. A plan job verifies NAS source files and asks the fixed Node
planner for controls and a method decision. It returns JSON without rendering or
transferring a finished mix WAV. The phone applies the controls to its verified
local source assets.

## API

`POST /plans` accepts exactly `{from,to,windowId,start}`. It requires the configured
listening Origin, an 8 KiB maximum body, public mix-ready tracks and the existing
source-bound `validated_plan` checks. It returns `202 {id,status:"queued"}`.
Duplicate queued jobs reuse their slot; a valid completed job returns
the complete, unmodified ready decision JSON (including its canonical fingerprint). A single strategy worker has three outstanding
slots, independently of the legacy render queue. Queue saturation returns 429.
An unconfigured engine returns 503 and does not enqueue work.

`GET /plans/{id}` returns queued/running/failed status or the unchanged Node
`harbeat.jetson-mix-plan.v1` result. It verifies current source identities and the
configured planner fingerprint before returning a completed plan. Invalid IDs,
expired versions or changed source bindings return 404. Failures use a fixed
public message; SSH diagnostics and trusted job metadata stay under
`METRIC_MIX_ROOT/plans/private/` with mode 0600.

The successful JSON retains Node's source proofs, exact cue geometry, controls,
metrics, decision, EQ, restore point, required stems and optional drum-prelude
approval. The original method must remain eligible as an approved fallback.
Python validates the fixed worker/engine boundary, source fingerprints, geometry
and public fields. The phone validates `analysisSha256` using the same TypeScript
canonical JSON implementation as the Node producer; Python does not reserialize
floating-point values to recreate that checksum.

## Configuration

Deploy the same `metric_mix` modules and `analysis_platform/jetson_plan.py` to cloud
and Jetson, preserving their Python code fingerprints. Install the root-built
`jetson-plan.cjs` bundle on Jetson, then set its actual SHA-256 on the cloud service.

| Variable | Location | Default / requirement |
| --- | --- | --- |
| `HARBEAT_PLAN_ENGINE_SHA256` | cloud | Required lowercase SHA-256 of the fixed Node bundle |
| `HARBEAT_PLAN_CLOUD_EXECUTION_ROOT` | cloud | `/srv/harbeat-listen/execution-current`; current index and verified profile bindings participate in cache identity |
| `HARBEAT_PLAN_REMOTE` | cloud | `mark@100.87.142.21` |
| `HARBEAT_PLAN_REMOTE_CODE` | cloud | `/home/mark/harbeat-metric-mix` |
| `HARBEAT_PLAN_REMOTE_PY` | cloud | `/home/mark/harbeat-analysis-venv/bin/python` |
| `HARBEAT_PLAN_CLI` | Jetson runner | `/home/mark/harbeat-device-execution/jetson-plan.cjs` |
| `HARBEAT_PLAN_NODE` | Jetson runner | `/usr/local/bin/node` (deployed Node 22); must support the supplied bundle |
| `HARBEAT_PLAN_EXECUTION_ROOT` | Jetson runner | `/mnt/nas/harbeat/preprocess/device-execution-v1` |

Cloud environment variables do not automatically reach a remote SSH process.
Use the documented defaults, or configure the Jetson runner's environment through
its fixed deployment wrapper. Paths and executable settings are deployment
configuration; none is accepted from a public request. No new GPU model or import
worker restart is required. Releasing these modules changes `worker_version`, so
cloud and Jetson must be switched together to keep legacy render jobs compatible.

The runner reads the existing NAS master/stem assets with `source_assets`, and
verifies the execution index and profile hashes. A profile-only export is valid;
cloud audio-segment publication is a separate device capability check. Each raw
window is 44.1 kHz stereo interleaved little-endian float32 in an invocation-private
temporary directory. Main B PCM begins at its existing entry point and includes
only the existing 8 ms continuation and optional 350 ms stretch padding.

The optional prelude uses the three complete adjacent A bars before the main cue,
with one bar to fade B drums in and two bars to hold. Its B source begins at
`bStart - leadSeconds * rate`; negative or incomplete source coverage disables
the prelude. This is an audition-only candidate. It does not move the main cue or
automatically enable drum layers during ordinary playback.
The existing 65 ms phase tolerance also applies to locating those A bars. Their
observed duration determines the lead while the original main-cue offset is kept;
the main start/end are never snapped to a nominal bar boundary. Node still checks
the full B prelude against its observed beat grid.

Only an internal `--audition-output` invocation also supplies `pcm.body`: eight
seconds of the native-rate B master beginning at the unchanged main `bEnd`.
This lets the audition continue after takeover. Production JSON strategy jobs
omit that extra PCM and the experimental prelude preparation. Internal auditions
can freeze their previously preferred single method with
`--audition-single-method bass|filter|yield|vocal`. That override requires an
audition output directory and is never accepted as a public job field.

## Checks

```sh
python3 -m unittest tests.test_plan_gateway tests.test_jetson_plan tests.test_metric_gateway tests.test_metric_mix tests.test_execution_strategy
```

The tests cover Origin, size and queue boundaries, forged source identities,
out-of-range cues, expired engine versions, profile-only evidence, private paths,
temporary PCM cleanup and unchanged successful JSON. Fixture PCM is not listening
evidence. Real deployment acceptance must exercise the fixed Jetson CLI and phone
playback with verified current tracks.

A GET for a queued/running record no longer owned by the current process returns a failed state; POST can safely resubmit it after a restart. Profile/manifest revisions invalidate old ready records, even when the master and report stay unchanged.
