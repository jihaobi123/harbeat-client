# Section relabeler v3 feature experiments

Date: 2026-09-02

## Goal

Test whether the existing reviewed development set can produce a materially
more accurate, still-low-risk residual relabeler without changing SongFormer
boundaries or collecting new annotations.

The evaluation unit remains a whole song. Every reported validation split keeps
all segments from a song together.

## Data

- Reviewed, trainable development songs: 36
- Reviewed, trainable development segments: 437
- SongFormer-correct baseline segments: 364
- SongFormer baseline accuracy: 83.30%
- Intentionally excluded structurally ambiguous songs remain excluded.
- The locked test split was not used for these experiments.

## Candidates tested

1. Linear logistic residual classifier with different regularization.
2. PCA plus logistic regression.
3. Linear and RBF SVM.
4. Extra Trees on compact and full encoder features.
5. Frozen encoder class prototypes.
6. Two-stage residual prediction:
   - detector: is the SongFormer label likely wrong?
   - corrector: if wrong, what should replace it?
7. Whole-song transition decoding with learned label transitions.
8. Previous/next segment encoder vectors and directional deltas.
9. Boundary-aligned mixed-audio DSP context:
   - log-mel and MFCC summaries;
   - chroma and spectral contrast;
   - RMS, onset density, bandwidth, rolloff, flatness and ZCR.
10. Boundary-aligned Demucs stem context:
    - vocals, drums, bass and other energy proportions;
    - per-stem onset and spectral summaries;
    - vocal MFCC, log-mel and chroma summaries.
11. Local Whisper transcription after Demucs vocal separation.

## Results

| Candidate | Primary grouped-CV accuracy | Safe fixed errors | Correct labels harmed | Stability decision |
|---|---:|---:|---:|---|
| Existing v2 report | 85.58% | 10 | 0 | retain |
| Two-stage detector/corrector | 85.81% | 11 | 0 | gain too small |
| Neighbor encoder deltas | 86.04% | 12 | 0 | rejected: harms appeared under alternate song splits |
| Mixed-audio DSP | 86.27% | 13 | 0 | experimental: gain did not remain above v2 across repeated splits |
| Mixed audio + Demucs stems | 86.27% | 13 | 0 | no incremental gain over mixed audio |

At the best primary split, mixed-audio evidence changed 14 segments: 13 were
correct fixes, none replaced an originally correct label, and one changed an
already-wrong label to another wrong label. With one fixed conservative gate
across ten alternate song-grouped splits, the number of correct fixes ranged
from 4 to 11 with zero harmed correct labels. That stability range does not
beat the existing v2 report's 7-to-11 range and median net gain of 10.

The local Whisper experiment was rejected before training. On both full mixes
and Demucs vocal stems, the small local model produced punctuation/garbage
instead of usable lyric timestamps. Treating that output as lyric repetition
would add false evidence.

## Interpretation

The remaining errors are mainly functional ambiguities, especially
verse/chorus/pre-chorus distinctions. More classifier complexity does not solve
them. Audio energy, timbre and stem balance provide some real information, but
the gain is sensitive to which songs are held out because only 36 independent
songs are available for training.

Reaching 90% segment accuracy would require at least 30 additional net fixes
over the SongFormer baseline. The current safe model produces about 10. Below
the high-confidence region, correction precision drops sharply, so lowering the
gate would trade accuracy on some mistakes for new mistakes on already-correct
labels.

## Decision

- Keep v2 as the low-risk production/shadow candidate.
- Keep the audio and stem extractors as reproducible experimental inputs.
- Do not activate the 86.27% primary-split model as a replacement.
- The next useful data pass should target clean songs containing repeated
  verse/chorus/pre-chorus structures, rather than adding more structurally
  ambiguous songs or more rare labels indiscriminately.

## Reproducible artifacts

- `scripts/extract_section_audio_context.py`
- `scripts/extract_section_stem_context.py`
- `section_audio_context_v1.npz` (local experiment cache, 1,057 segments)
- `section_stem_context_v1.npz` (local experiment cache, 457 development segments)

The caches are keyed by `(track_id, segment_index)`, which is the same identity
used by the annotation dataset and training collector. This prevents segment
order changes from silently attaching features to the wrong annotation.
