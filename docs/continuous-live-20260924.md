# Continuous HarBeat player — implementation checkpoint

The independent continuous player lets a listener keep the current song playing while selecting another, prepare that selection in the background, and request a gradual transition from the actual current position. It retains `planVocalOverlap`, the full overlap gain ramps and source-dependent dynamic EQ from the accepted experiment. Pause, seek, volume, cancel-before-lock and optional automatic continuation are included.

The collection contains every indexed song: KPOP 84, EDM 8, reference library 65. Full source time totals 34,648.822 seconds. The user's collection and style labels control browsing; they are not passed as unverified local-style evidence. Seventeen optional genre analyses failed. Their model style is represented by a unique unknown value internally so unrelated unknown songs do not gain a same-style bonus. Their valid original audio and vocal evidence remain eligible for preparation.

## Data and playback

`library.json` is the small UI index; each selected song loads its own `details/<id>.json` (gzip preferred). Every indexed ID remains visible, with explicit play/mix readiness and reasons. Unknown metadata is permitted only for unavailable entries. Browser analysis metadata is bounded to the current/pending/selected songs plus a small LRU.

Native full-song audio consists of the existing-style prefix up to 150 seconds followed by contiguous 30-second FLAC chunks. `audioSegments` uses exact source-sample bounds. The transport schedules chunks on one audio clock and retains only current/next source references. A missed preparation deadline visibly suspends the clock; explicit user pause/stop prevents stale requests resuming playback. Audio pool limit remains 192 MiB.

Compatible entry-window assets retain the accepted FFmpeg atempo recipe and original gradual overlap duration. Rendering groups independent outputs from one input in batches; equal BPM recipes are deduplicated while variants stay keyed by source-song ID. A regression compares actual decoded samples with the accepted recipe at three rates. Immutable NAS files are SHA-bound and registered with the existing read-only media endpoint; audio is not copied to the small server system disk.

A next selection made before a scheduled transition locks cancels that pending transition. A selection made during a committed transition is queued and prepared against the new current song after takeover. Automatic continuation retries temporary cue misses as source time advances, tries compatible alternatives near the tail, and recovers when restrictive filters expand. It keeps playing the current song if no acceptable transition exists.

## Validation and release state

At this checkpoint, 252 web tests and 15 Python corpus tests pass. Ten optional web corpus tests are skipped because their specific fixtures were not supplied. The accepted V3.1 reference fixtures were supplied and pass. TypeScript, continuous, vocal-overlap and V3.1 builds pass. Independent review and a 157-row browser inventory check are complete. Existing 26-song media fixtures validate the new player controls and a real overlap handoff locally. The final browser regression also checks selecting a third song during a committed mix and preparing it again after takeover, plus preservation of the old feedback key. Fresh public-media reads sometimes exceeded the short legacy fixture; the final queue check paused during preload and resumed for the actual audio-clock handoff. Full new-corpus/browser release checks remain.

The source inventory and a read-only 96-clip benchmark are saved under the task output directory. Benchmark time was 5.102 seconds across four workers, excluding actual NAS output and registry cost. This is an estimate for planning the full batch, not completion evidence.

Automatic approval rejected uploading the preparer into the new private NAS directory because source-code transfer and remote writing were not explicit in the authorization it evaluated. The user has been asked to approve uploading this preparation program, processing all 157 tracks, and publishing the separate continuous page. Until that answer arrives, the new media generation and publication remain pending. Existing public pages and music have not been replaced.

Build: `npm run build:continuous` from `web/`. Copy its HTML as `index.html` into the separate release folder, include the existing `v3-clock.js`, generated index as `library.json` plus gzip, lazy details, and evidence. Intended new route: `/analysis-lab-static/continuous-live-20260924/`. Do not publish a benchmark's partial index as the complete library.
