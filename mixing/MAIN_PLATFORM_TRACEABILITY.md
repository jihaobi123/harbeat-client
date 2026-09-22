# Main-platform mixing traceability — 2026-09-22

Open `/analysis-lab?tab=mix-debug`, or select 混音调试与素材来源 in the sidebar. Per-report 混音素材与来源 links the selected original audio to the mix catalog by master SHA256. Matching names alone never attach evidence. A different analysis revision of the same original audio is explicitly identified.

The material view exposes the original report ID, master/actual playback asset hashes, report-file versions, structure candidates, absolute dBFS curve, section style candidates, entry windows, takeover style and subsequent energy bins. Source links open the original feature report, stem audition and raw report JSON. This precise catalog currently covers six demonstration songs, not the whole NAS library.

The process view embeds the existing V3 player on demand. Session records show each trigger, available/excluded candidates, chosen transition and EQ rationale, source provenance, failures and the full event chain. Planned audio-frame timestamps are converted using the recorded sample rate; observations must match request ID, plan ID and event name. Missing observations remain unknown. Audio-thread observations do not measure speaker or Bluetooth latency.

New V3 sessions automatically persist in same-origin browser IndexedDB. Writes are serialized, with failure status and JSON export/import. Independent live tabs and the platform share the database in the same browser profile. This is not server synchronization. Clearing site storage deletes local history; earlier unexported in-memory sessions cannot be recovered. Historical catalogs without titles display their recorded IDs instead of inventing identity.

## Verification and deployment

- 69 analysis/realtime tests passed, one environment-specific catalog test skipped.
- Added an integration regression using an actual LiveTransport export: importability, material title and frame-to-time conversion.
- Main and realtime TypeScript/production builds passed.
- Public main/live HTML and their JS/CSS match the local build byte-for-byte; all six source report endpoints return 200 and master hashes match the catalog.
- Browser automation blocked; interactive playback acceptance was not completed in this change.
- Deployment only appends hashed static assets and replaces main/live entry files. No backend permission, inference or V3 DSP changes.
- Jetson backup: `/home/mark/harbeat-analysis-platform/deploy-backups/main-mix-trace-20260922-120832`.
- Main assets: `index-DKK6H4yK.js`, `index-Buja7ibm.css`.
- Live assets: `realtime-ZhgpWbC8.js`, `realtime-BmMamJRl.css`.

Rollback: restore the backed-up main and live HTML entry files to their original locations; old hashed assets remain available. Stop any running player before refreshing the release.
