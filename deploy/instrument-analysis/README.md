# Jetson instrument-analysis Shadow runtime

This runtime installs pinned ADTOF-PyTorch and PANNs sources without replacing
the NVIDIA Jetson CUDA PyTorch build. It runs only as an offline analysis
worker. Results are unreviewed model candidates and are stored outside the
per-user annotation directory.

## Install

Run from a versioned HarBeat release after confirming that the root filesystem
has at least 8 GiB free:

```bash
deploy/instrument-analysis/install-jetson.sh \
  /opt/harbeat/models \
  /opt/harbeat/runtime \
  /opt/harbeat/current/venv/bin/python
```

The installer pins both Git revisions, verifies the bundled ADTOF checkpoint,
verifies the official Zenodo PANNs MD5 and a committed SHA-256, and installs
only three additional packages into an isolated overlay with `--no-deps`.

## Verify and configure

```bash
deploy/instrument-analysis/verify-runtime.sh \
  /opt/harbeat/models \
  /opt/harbeat/runtime/instrument-analysis-python \
  /opt/harbeat/current
```

Replace `__HARBEAT_RELEASE__` in the example service drop-in, validate the
merged service configuration, and run two explicit Pilot canaries before the
full ten-track backfill. Keep concurrency at one.

## Data safety and rollback

The worker writes shared candidates only to
`/data/harbeat/instrument-analysis`. It never writes to
`/data/harbeat/bar-annotations`. Rollback restores the preceding versioned
application release and removes only the instrument-analysis service drop-in;
model caches and both annotation directories remain intact.
