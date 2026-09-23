# Protected realtime mixing

User explicitly approved four hard requirements: protected outgoing phrase/section endings, separate incoming accompaniment from vocals, usable intro/contained windows, and continue source playback when no safe plan exists. Execute inline with TDD; preserve previous releases.

- [x] Add strict planner tests: unreviewed boundaries and entries block; merged equal labels; containment; precise vocal time mapping; no deadline relaxation; unchanged ordinary playback.
- [x] Prepare source-bound catalog: existing complete beat list extends candidate intro bars by phase relative to detected downbeat (not a verified beat detector); merged SongFormer episodes; stems-summed backing entry variants; hashes and candidate status.
- [x] Add isolated planner injection to LiveTransport without changing defaults; guarded UI reviews are user actions after bounded audio previews, tied to catalog and assets. No automated human approvals.
- [x] Add preview/confirmation UI, request/continue behavior, exclusions, plan/actual timing logs, and export. Long VAD spans remain candidates; explicit listened review controls exact cut/takeover, not fake whole-song corrected annotations.
- [x] Validate real catalog plus synthetic accepted/blocked transitions, build/deploy independent page, browser-check blocked requests keep A playing and reviews never auto-populate. Push branch.

Design limit: existing VAD is not phrase transcription. Strict section mode requires human audition of exact exit and incoming excerpt/body before execution. Review can explicitly override detector activity at those exact cues, with that discrepancy logged. No promise of semantic phrase detection or zero Demucs vocal leakage; original and backing previews must be available. No hidden fallback to ordinary planner.
