# Vocal-led instrumental bridge experiment

User authorized an independently judged test implementation on 2026-09-25. Keep the accepted /listen/ production player untouched.

## Design

Create six controlled, real-time Web Audio comparisons from the existing verified library. Both arms use identical source excerpts, cue times and tempo mapping. The reference uses the accepted linear full-overlap gain/dynamic EQ recipe at these fixed cues. The experimental arm separately controls each song's accompaniment and vocals: A accompaniment yields early, A vocal remains at its original level until its detected activity ends, B accompaniment enters early, A vocal tail fades out, and B vocal is fully restored before its first detected entrance. Both arms maintain B's matched tempo through the short preview, avoiding a second simultaneous tempo-restoration experiment. This is a bounded listening experiment, not an upgrade to all 158 songs.

Only use candidate B ranges without detected vocals (with 150 ms entry-end / 300 ms entry-start guard) followed by a detected vocal entrance 0.15–2 seconds later. Require A vocal coverage of at least two seconds and a detected end 0.5–3 seconds before exit. Reuse complete local 65 ms beat alignment and source binding. Compare 2/4/8 measured bars, moderate rates 0.94–1.06 and 5–22 source seconds. Rank with existing gain-weighted vocal overlap and musical metadata; structural labels and VAD remain model estimates.

Reuse NAS master and vocal files bound to each exact analysis report. Prepare only short excerpts, not pre-mixed transitions. Merge stereo master/vocal into one four-channel stream before any tempo processing so all channels share the same timing operation. Deliver master/vocal clips with SHA-256, frame counts and source evidence. Accompaniment in the live player is the residual master minus separated vocal; equal vocal/accompaniment gains reconstruct the master algebraically. Separation bleed/artifacts may remain and must be disclosed.

The page provides same-cue reference/experiment buttons, automatic phase display, pause/resume, stop, progress and local preference capture. Loading or replacing a test cancels stale operations; one clock schedules all sources. Bound audio cache and master output protection. Mobile layout, clear labels, link back to normal listening.

## Implementation and verification

1. Candidate scan and six representative combinations; confirm all twelve existing report-bound stem sources.
2. Failing tests for cue eligibility, automation endpoints, no cut of detected A vocal, B voice restored before onset, and unity reconstruction. Implement shared policy.
3. Renderer: source hash/format checks, synchronized four-channel time stretching, equal frame count, bounded disk use, asset SHA/byte metadata. Test with synthetic signals and run on actual stems on Jetson/NAS.
4. Browser transport/page: same-clock sources, source binding, cancellation on replace/stop, pause/resume, phase display, loudness protection. Unit tests before implementation.
5. Compare reference DSP to current buildV30Eq/scheduleV30Eq; do not change production planner, vocal score or transport.
6. Review independently, build, browser desktop/mobile checks, actual playback in both arms, and verify exact deployed asset bytes. Publish only the new experiment directory; record roll-back removal path and limitations.
