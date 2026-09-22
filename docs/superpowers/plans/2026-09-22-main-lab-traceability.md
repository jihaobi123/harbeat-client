# Main analysis platform mixing traceability plan

User explicitly requests that the existing /analysis-lab show both mixed material provenance and execution process. This completes the previously approved visual-analysis/debugging design; execute inline with writing-plans and test-driven-development.

- [x] Tests first: report association requires exact report ID plus master identity or explicit same-audio/different-version indication; matching titles never bind. Event rows pair by request and plan, missing observations remain unknown. Persisted sessions retain request failures and source identities.
- [x] Add shared browser IndexedDB session storage with serialized writes, explicit save failures, import/export. Save current V3 session automatically; no anonymous server write permission changes. Label same-browser scope and no recovery of previous unexported sessions.
- [x] Add main-platform sidebar mixing debugging entry independent of current selected song; material cards, local energy/style graphs/section/window tables and original-report/source links. Load the deployed versioned catalog, show six-song coverage honestly.
- [x] Embed existing realtime mixer only when requested (avoid starting duplicate players), show saved/imported per-request process, A/B source references, candidate explanations, and planned/audio-thread time comparison. Keep V3 audio implementation unchanged.
- [x] Add report-specific mixing evidence tab, deep links to exact report versions, same-audio version mismatch notice. No title-based evidence reuse.
- [x] Run focused realtime/analysis tests and both builds. Back up deployed main index; add hashed assets without removing other demos; update realtime build for session persistence. Verify HTTP deployment and browser if available. Commit/push same feature branch.

Validation: 69 analysis/realtime tests passed; one environment-dependent real-catalog test skipped. Both production builds passed. Interactive browser automation blocked, so no claim of click/playback acceptance. Deployment adds static assets and atomically replaces entry files; original data and demos retained. Public resource verification is recorded separately.
