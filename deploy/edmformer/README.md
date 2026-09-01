# EDMFormer Jetson runtime

This installs the pinned EDM-98 source and EDMFormer checkpoint as a Shadow
runtime. It reuses the MuQ and MusicFM assets already installed for SongFormer.
It does not install the future ExpandedStructureHead and it never overwrites
SongFormer boundaries or human annotations.

Run only after the disk audit confirms at least 3 GiB free:

```bash
sudo bash deploy/edmformer/install-jetson.sh \
  /opt/harbeat/models /opt/harbeat/runtime \
  /opt/harbeat/current/venv/bin/python
```

The service command captures the six official EDM labels as per-frame
probabilities, then aggregates them inside the canonical SongFormer Bar blocks.
EDMFormer's own boundaries are retained only as comparison candidates.
