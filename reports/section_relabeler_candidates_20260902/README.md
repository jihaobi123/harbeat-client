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
| c03 encoder projection | 85.35% | 80.72% | 9 | 0 | 4–10 |
| c04 mixed audio | 85.81% | 81.03% | 11 | 0 | 2–12 |
| c05 Demucs stems | 83.30% | 78.45% | 0 | 0 | 0–0 |
| c06 mixed audio + stems | 83.30% | 78.45% | 0 | 0 | 0–0 |

“Safe” means that the residual gate only applies changes at the frozen
high-precision threshold. A candidate returning the baseline is not a failed
file: it means its grouped development evidence did not justify overrides at
the required safety level.

Post-freeze smoke evaluation on the eight historically exposed `test` songs
gave 59.29% for SongFormer, 60.18% for c03 and 61.06% for c04; c03/c04 each
harmed three originally correct segments. This is a distribution-shift warning,
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
