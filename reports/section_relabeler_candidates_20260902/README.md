# Frozen section relabeler candidates — 2026-09-02

This directory is a frozen development snapshot. No production winner has
been selected; compare all candidates on a new untouched song set.

Dataset: 437 trainable segments from 36 independent development songs. The 28
tracks marked `structure_too_chaotic` were excluded. SongFormer baseline is
83.30% segment accuracy.

| Candidate | Safe grouped-CV accuracy | Macro-F1 | Fixed | Harmed | Net-gain range across 10 group splits |
|---|---:|---:|---:|---:|---:|
| c01 SongFormer local | 83.30% | 78.45% | 0 | 0 | 0–0 |
| c02 whole-song structure | 83.30% | 78.45% | 0 | 0 | 0–0 |
| c03 encoder projection | 85.58% | 80.80% | 10 | 0 | 7–11 |
| c04 mixed audio | 85.81% | 80.99% | 11 | 0 | 10–12 |
| c05 Demucs stems | 85.81% | 80.99% | 11 | 0 | 10–12 |
| c06 mixed audio + stems | 85.81% | 80.99% | 11 | 0 | 8–11 |

“Safe” means that the residual gate only applies changes at the frozen
high-precision threshold. A candidate returning the baseline is not a failed
file: it means its grouped development evidence did not justify overrides at
the required safety level.

Post-freeze smoke evaluation on the eight historically exposed `test` songs
gave 59.29% for SongFormer, 60.18% for c03 and 61.06% for c04; c03 harmed two
and c04 harmed three originally correct segments. This is a distribution-shift warning,
not a model-selection result. Those songs are not an untouched blind set and
their style metadata is only `input`.

- `manifest.json`: immutable model index and hashes.
- `models/`: exact feature contracts and fitted parameters.
- `reports/`: hyperparameter trials, grouped OOF metrics, stability runs and
  changed segments.
- `dataset_audit.json`: complete data evidence audit.
- `dataset_audit.md`: short human-readable audit.

See `docs/section_relabeler_candidate_library.md` for architecture, limitations
and the blind-test command.
