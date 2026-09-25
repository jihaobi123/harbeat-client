# Automatic transition quality and playlist import

User approved the five-part design in the conversation on 2026-09-25. Execute in the existing isolated branch; deploy only after regression and independent review.

## Scope and decisions

- Automatic selection shortlists up to eight tracks by current tempo and curated style. Explicit song selection is a strict constraint. Style preference filters the shortlist before scoring.
- New automatic-only planner compares all feasible A exits and B windows in the final 35% of measured music. If none pass, expand to the final 50%; never automatically discard more than half the measured music. Keep a minimum 12-second preparation lead for cold material, 0.25-second execution lead for already prepared material.
- Reuse existing local beat gate, bound vocal evidence, aligned gain-weighted vocal overlap coefficient (0.3), full overlap gains, and dynamic EQ. Remove waiting-time score only in automatic policy. Rank structural boundaries, acoustic phrase tails, speed deviation, and source-bound RMS/low-band continuity. These are ranking proxies, not subjective quality guarantees.
- Compare metadata first, load only winning plan and one backup. Load backup after the winner; protect both from cache eviction. Fall back on download failure; preserve queued manual choices and cancel stale asynchronous work.
- Manual policy and original experiment remain unchanged.
- Accept the exact NetEase short-link host, resolve bounded platform-only redirects, strip Markdown share-text punctuation, and canonicalize resolved playlist ID. Existing QQ restrictions remain.

## Steps and checks

- [x] Reproduce original short-link rejection and confirm canonical URL returns 17 tracks.
- [x] Add failing short-link and unsafe-redirect tests, implement bounded resolution.
- [x] Run import tests with existing local dependency directory; verify exact public link and upload dedup.
- [x] Add automatic policy tests for multiple windows/tracks, no waiting bias, lead time, retention, local beat validity, vocal binding and unchanged EQ.
- [x] Implement automatic quality planner and bounded shortlist; keep manual planner intact.
- [x] Test transport preparation, fallback, cancellation and preservation of user choice; wire automatic UI selection.
- [x] Audit actual library coverage and representative same/cross-style transitions; replay a complete unattended handoff.
- [x] Run all relevant frontend/backend regressions, build, independent code review; resolve findings.
- [x] Publish atomically using existing cloud release lock and verify public bytes, link parsing, upload and playback. Record evidence and limits.
