# Audible vocal overlap experiment

The user approved changing the vocal score and adding music beyond the accepted twenty tracks. The frozen reference is `audio-v3.1.0` at `2ba6c8f`. This work runs in a separate worktree and listening page.

## Controlled comparison

Run the original V3 planner first. Fix its target track, entry window, asset, rate and overlap duration. Rank the existing eligible A timings for that same material again, replacing only the vocal contribution. Preserve the 18-second deadline, beat checks, waiting penalty, section bonus, gain schedule and dynamic EQ rule. The selected source interval can change the resulting EQ coefficients; this is expected and does not change the EQ algorithm. The experiment does not search alternative entry clips or shorten the overlap.

## Score

Use the same VAD intervals and 300 ms source-time padding as V3. Merge padded intervals, clip to the selected source ranges, and map B to playback time with `(source - window.start) / rate`. Intersect A and B playback intervals. For overlap duration D and progress x=t/D, weight simultaneous activity by `4*x*(1-x)`, the normalized product of the existing linear deck gains. Integrate exactly over interval intersections, then divide by `2*D/3`, the integral of the weight over the full overlap. The result is in [0,1], with continuous activity on both sides equal to one. Replace `-0.3*aVocal*bVocal` with `-0.3*weightedOverlap`.

The weight is an audibility proxy, not calibrated vocal loudness or semantic understanding. Keep padding in source seconds and retain VAD source row references. Invalid or mismatched evidence produces an explicit unavailable result. No new analysis detector or threshold is introduced.

## Data and listening

Keep all original twenty track records, windows and assets. Select twelve additional unique tracks from existing NAS reports by model style, tempo and vocal density before evaluating the new score. Require the existing source-bound preprocessing and dynamic EQ evidence. Generate only missing single-song assets in an isolated directory. Keep exclusions in the audit.

The independent page offers baseline versus overlap-score listening, the same A/B music and request position, clear cue and score evidence, and live triggering through the existing transport. New feedback uses its own storage key; old ratings and sessions remain available. Keep fixed new-track test cases even when no plan exists, and label separately any examples chosen to demonstrate changed cues.

## Validation

Unit tests distinguish staggered from simultaneous voices with identical marginal coverage, weight middle collisions above edge collisions, exercise 0.8 and 1.2 rate mapping, and prevent duplicate interval counting. Planner tests verify fixed material, duration, deadlines, unchanged non-vocal score terms, source binding and unchanged baseline output. Corpus checks retain all original cases and use a fixed position matrix for old/new pairs. Real browser checks cover controlled and live playback, audio-thread events, and feedback persistence. Lower proxy scores are not evidence of preferred sound.
