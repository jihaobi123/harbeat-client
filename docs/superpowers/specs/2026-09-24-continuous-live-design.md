# Continuous playback for the 157-track library

The user approved the current vocal-overlap experiment and asked for continuous playback with controls while music plays. They confirmed all three source collections: KPOP (84), EDM (8), and the style reference library (65). The existing V3.1 and comparison pages remain available.

## Playback

The new page starts a full song, shows its current position, and lets the listener browse or choose the next song without restarting the current deck. Controls include pause/resume, seek, volume, next song, collection/style filters and cancellation of a pending transition. A completed handoff makes B the current song, so another handoff can follow in the same session. Automatic continuation prepares another eligible song near the end; users can disable it. User requests replace preparation that has not started mixing. During a locked mix, the latest request waits under the existing deadline rule.

Keep the accepted `planVocalOverlap` score, full linear deck gains and dynamic EQ rule. Changing a collection filters the next-song list; it does not claim that a model proved the local style. Manual BPM, energy and EQ controls are outside this first implementation.

Whole-song WebAudio buffers exceed the existing memory pool for long songs. Use a verified native prefix of at most 150 seconds, then contiguous 30-second FLAC segments. Their source sample boundaries determine scheduling. Prepare upcoming segments before they are needed, retire old buffers and cancel stale loads after seek/stop. Pause and seek affect the current session explicitly; browsing and next-song selection do not. A missed buffer deadline must produce a visible buffering state rather than an unreported gap. Ordinary B entry windows remain near the beginning, within the native prefix.

## Library

Read the 157 indexed manifests and latest source-matched analysis reports. Process every indexed song, preserving its source collection and manual substyle labels. Model style stays a separate field. Validate master/VAD/report identity and measured timing. Existing optional drum-analysis degradation is not by itself a mixing failure. Songs with insufficient mixing evidence remain listed with an explicit reason and verified playback assets when available.

Generate immutable single-song assets on NAS, using the same FFmpeg atempo recipe as the accepted version. Reuse existing assets and deduplicate equal tempo recipes; measure batch cost before full rendering. Native prefixes and body segments cover the full measured source duration. Register generated media with the existing allowlisted media registry, avoiding copies of the full corpus onto the nearly full Jetson system disk. No original manifest, source music, historical report or previous release is overwritten.

Serve a small index and load detailed analysis only for the current and near-future songs. Full track details contain `audioSegments: [{start, end, asset}]`, where the first segment uses `native`; `duration` is the full track duration. Window variants retain the existing A-track keyed contract. Every final asset contains its actual encoded SHA256, byte count and decoded duration.

## Validation and delivery

Tests cover continuous segment scheduling, source seeks after 150 seconds, pause/resume, cancellation, changed next-song requests during preparation and mixing, memory protection and unchanged legacy behavior. Corpus checks account for all 157 entries and distinguish playable, mix-ready and unavailable states. Browser checks play through a segment boundary and at least three consecutive handoffs, change selection while music plays, adjust volume, pause/resume, seek and verify preserved historical feedback.

Publish to a new independent continuous-player address only after its assets and runtime pass checks. Record exact ready/unavailable counts. The user already authorized publishing this line of work to the existing HarBeat server.
