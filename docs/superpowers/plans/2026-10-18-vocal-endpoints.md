# Vocal Endpoint Implementation Plan

> Execute inline using executing-plans and obtain requesting-code-review independent review.

**Goal:** Use existing open projects to produce auditable vocal endpoint candidates and one controlled vocal-handover comparison.

**Architecture:** Source-bound isolated-vocal contexts → official YAMNet and existingSilero → pYIN/envelope → gap/tail candidate policy → frozen baseline/current cue comparison. Independent durable browser UI.

**Tech Stack:** TensorFlow/Essentia CPU isolated model environment, librosa pYIN, numpy/scipy, ffmpeg, React/Vite/WebAudio.

- [x] Verify official projects/weights and source contexts; record runtime/provenance and model limitations.
- [x] Write failing endpoint policy tests, implement seed/breath/tail/gap logic and deterministic candidate/rejection evidence.
- [x] Run actual models on3outgoing contexts plus incoming control; verify times and input hashes; select only cue-compatible confident-enough audition candidates and report all failures.
- [x] Implement isolated baseline-versus-detected-end player and blind UI. Reuse unchanged clips, bass, EQ, bed curves, cues and native takeover. Add readable reveal evidence and isolated vocal playback.
- [x] Appropriate tests/typecheck/build and independent review; fix important findings.
- [x] Actually play both arms in practice, check render markers, early choice and reload/export; preserve practice history, leave empty formal round, save screenshot/evidence and scoped commit.

## Execution results

- Actual models: official Essentia YAMNet + voice/instrumental head on Jetson TensorFlow/Essentia CPU environment; source-bound pre-existing Silero intervals; librosa pYIN on isolated 16kHz vocal contexts. Weights and receipt retained under NAS experiment models directory.
- Original three outgoing cues rejected; HIPHOP low-activity control retained. Twelve-source proxy shortlist yielded original-policy candidate plans. Doin’ It → Tonight was rejected by the new incoming model check. Doin’ It → Talgo is explicitly a new exploratory pair, with A cue unchanged from the rejected probe.
- Final protected end 262.084s; fade 262.391421–262.591421s; checked context through269.788261s without another detected onset. These are provisional activity endpoints, not certified lyric boundaries.
- New pack has nine shared clips (16,399,550 bytes) plus a source-bound isolated vocal review context. Only outgoing vocal gain changes between arms.
-18Python regression tests;24new TypeScript tests;170TypeScript tests total in relevant experiment suites; TypeScript check and standalone build passed. Independent review found and resolved quiet re-entry, VAD-tail confirmation, incoming tail overlap and stale-dependency issues.
- Actual browser practice completed both19.894739sarms with12on-time render-quantum observations; no console errors/warnings. Early vote, solo vocal playback/stop, export and two reloads verified. Practice excluded from listener preferences; a blank formal round4508a2b7-0871-44fd-80e8-b4861f1d3cbd remains.
- Deliverable: http://127.0.0.1:5194/vocal-endpoints.html ; local Vite session75888. Prior trial servers/pages and listener records preserved.
- Evidence: docs/evidence/vocal-endpoints-20261018.json. Working data, models, archived rejected probe, bound analyses, browser exports and screenshot: /Users/jihaobi/Documents/New project/work/vocal-endpoints-20261018.

## Reproduction

Use scripts/analyze_vocal_endpoints.py prepare/model/pitch with the experiment root. The TensorFlow model runtime is /home/mark/harbeat-analysis-model-venv/bin/python; the pitch runtime is /opt/harbeat/current/venv/bin/python. The runner verifies official weight receipts and input context hashes; reports reject stale model/pitch dependencies.

Run scripts/report_vocal_endpoints.py with PYTHONPATH=. for each source-bound context bundle. scripts/render_vocal_endpoint_probe.py binds the frozen selection against NAS sources and reuses the existing phase-shared nine-asset renderer. scripts/prepare_vocal_endpoint_pack.py builds the final pack only after both source identities, incoming tail guards and outgoing endpoint selection pass. In web/, run the independent Vite configuration vite.vocal-endpoints.config.ts.
