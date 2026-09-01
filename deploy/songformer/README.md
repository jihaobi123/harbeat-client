# Jetson SongFormer runtime

This deployment is limited to the shared annotation Pilot. It installs the official SongFormer source and checkpoints, an isolated Python dependency overlay, and the MuQ model used by the validated HarBeat runner. It does not install or enable the residual section-label classifier.

## Install

Run from a versioned HarBeat release on Jetson:

```bash
sudo mkdir -p /opt/harbeat/models /opt/harbeat/runtime
sudo chown -R mark:mark /opt/harbeat/models /opt/harbeat/runtime
deploy/songformer/install-jetson.sh \
  /opt/harbeat/models \
  /opt/harbeat/runtime \
  /opt/harbeat/current/venv/bin/python
```

The installer pins SongFormer to `139b2aa3b14bd1c6d961d0994e9fc975f1ef7fd5`, verifies the upstream checkpoint MD5 manifest, and refuses to overwrite a dirty source tree.

## Configure

Copy `harbeat-songformer.conf.example` to the service override directory, then validate with `systemd-analyze verify` before restarting. Keep `SECTION_RELABELER_ENABLED=false` until a separately validated residual JSON model exists.

## Verify

```bash
deploy/songformer/verify-runtime.sh \
  /opt/harbeat/models/SongFormer \
  /opt/harbeat/models/MuQ-MuLan-large \
  /opt/harbeat/runtime/songformer-python
```

Run two explicit Pilot IDs before the full backfill. The backfill writes only to `SONGFORMER_SECTION_DIR`; `/data/harbeat/bar-annotations` remains protected.

## Rollback

Restore the preceding versioned application release and remove or rename only `/etc/systemd/system/harbeat-api.service.d/songformer.conf`. Do not delete model caches or either persistent annotation directory during rollback.

