# Similar-pair bass retest implementation plan

> **For agentic workers:** Execute with executing-plans in this session; delegate the independent page implementation and use requesting-code-review for independent review.

**Goal:** Six newly selected neighboring pairs and twelve controlled reference/stem auditions.

**Architecture:** Deterministic metadata neighbor selection on original frozen safe plans; unchanged source renderer and CoveragePlayer; isolated two-arm UI and durable rounds.

**Tech Stack:** TypeScript/Vite/React/Web Audio, Python/ffmpeg, source-bound NAS stems.

- [ ] Create `scripts/prepare_bass_neighbors.ts` and pure `web/src/bass-neighbors/similarity.ts`. RED/GREEN tests cover exact neighbor preference, distant/missing evidence, immutable cue plans and vocal-direction mismatch. Use `planAutomaticQuality`, `bassTiming`, `buildV30Eq`, `rankFrozen` unchanged. Write root work selection and full rejection/ranking audit. Two slots per predeclared reference; use unique new tracks and the explicit style/BPM distance from the approved design. Keep bass audio failures in a work rejection file and exclude only that frozen candidate.
- [ ] Delegate `web/src/bass-neighbors/{rounds.ts,rounds.test.ts,BassNeighborsLab.tsx,main.tsx,style.css}`, `web/bass-neighbors.html`, `web/vite.bass-neighbors.config.ts`. Two arms, three assignments each, early choices and immutable first-choice heard snapshot, all-six reveal gate, practice/history/export. Reuse CoveragePlayer. Parameterize `indexedDBBackend(name=databaseName)` for isolated storage while preserving old default. RED/GREEN round tests, no generated audio committed.
- [ ] Reuse `scripts/render_bass_coverage.py` unchanged on selection; verify sources, hash/rates and RMS. Transfer manifest-referenced assets only and put them under `web/neighbor-audio`, with separate `web/bass-neighbors-data.json`. Keep original six-case pack untouched. Record transform from renderer URLs to isolated URLs, preserve asset hashes. Ignore pack, audio and build output.
- [ ] Run new and relevant regression tests, Python renderer tests, TypeScript and isolated build. Review neighbor selection/player/round safety independently. Actually play all twelve clips in a practice round; export and verify original plan/EQ/rest curves and 72 timely render events. Test early vote, original-choice retention, persistence/reload, history and fresh formal round. Save evidence and screenshot. Commit only scoped changes; no production deployment.
