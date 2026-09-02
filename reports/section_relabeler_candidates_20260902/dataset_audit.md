# Section relabel dataset audit

Dataset SHA-256: `ef5d2db8e7857b4c9138b9ab932bfd2f0faf33e6b2df5e9f633999ba8ddd68e9`

## Usable evidence

- All data: 65 development songs + 8 historical test songs.
- Intentionally excluded: 28 structurally chaotic development songs.
- Trainable development evidence: 437 segments from 36 independent songs.
- SongFormer baseline: 364/437 correct (83.30%).

## Labels

| Label | Segments | Independent songs | Median duration | P10–P90 duration |
|---|---:|---:|---:|---:|
| intro | 38 | 34 | 14.3s | 7.9–22.2s |
| verse | 166 | 36 | 17.5s | 13.6–26.3s |
| chorus | 124 | 35 | 17.6s | 13.7–21.0s |
| bridge | 9 | 6 | 19.1s | 16.2–25.1s |
| instrumental | 15 | 8 | 19.4s | 15.5–23.2s |
| outro | 32 | 25 | 17.0s | 13.0–20.4s |
| silence | 24 | 24 | 2.3s | 1.4–4.8s |
| pre-chorus | 29 | 11 | 17.0s | 14.9–20.0s |

## Feature coverage

| Source | Dimensions | Development coverage |
|---|---:|---:|
| songformer_local | 52 | 100.00% |
| whole_song_structure | 24 | 100.00% |
| encoder_projection | 1024 | 100.00% |
| mixed_audio_dsp | 312 | 100.00% |
| demucs_stems | 208 | 100.00% |

## Main cautions

- bridge only appears in 6 independent development tracks
- instrumental only appears in 8 independent development tracks
- Segments in one song are correlated; model selection and evaluation must group by track_id.
- The current eight-song test split is historically exposed; final selection needs a new untouched blind test set.

The JSON companion contains complete source→human confusion, style breakdown, position/confidence error rates, transitions, and compact whole-song sequences.
