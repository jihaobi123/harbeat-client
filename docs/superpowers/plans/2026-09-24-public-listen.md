# HarBeat Public Listen Implementation Plan

> **For agentic workers:** Execute these deployment tasks inline. UI changes follow the separately presented user flow once approved.

**Goal:** Publish a complete 157-song player at `https://8.136.120.255/listen/`, with cloud-local immutable music assets and the existing accepted transition algorithm.

**Architecture:** Reuse the existing ECS and trusted IP certificate. Export bound analysis from the existing processing host, fetch and verify original audio on ECS, then generate native segments and entry variants on ECS local disk, validate SHA-256 and coverage, then atomically expose a release through Nginx. Existing application and experiment routes remain separate.

**Tech Stack:** Python, FFmpeg, React/Vite, Web Audio, rsync, Nginx.

## 1. Generate the library

- [x] Verify ECS capacity, HTTPS certificate renewal, and direct ECS-to-processing-host SSH access.
- [x] Stage the isolated processor and its dependencies; export bound source jobs from the existing published index and reports, then run `render_continuous_cloud.py --workers 2` on ECS local disk.
- [x] Require 157 playable songs, all 152 source-eligible songs to remain mix-ready, and zero rendering failures before publication. Five genuine beat-grid/tempo conflicts remain explicit; the 23 millisecond-tail cases and one sub-sample stem-tail case are normalized without changing original reports.

## 2. Package and verify immutable cloud assets

Files: `scripts/package_continuous_site.py`, `tests/test_public_continuous.py`.

- [x] Run `python3 -m unittest tests.test_public_continuous -v`; first confirm missing exporter failures.
- [x] Implement `build_bundle(corpus, store, out, source_root, expected=157)` to verify complete rows, registry identity and allowed paths; rewrite only delivery URLs; emit compressed library/details and a private transfer manifest.
- [x] Run the same tests. Check coverage for incomplete libraries, changed sources, escaped paths and checksum disagreement.
- [x] Generate audio on ECS, then validate every cloud file size and SHA-256 before linking into `/srv/harbeat-listen/media/` by content hash. Keep at least 5 GiB free; do not delete unrelated data to make room.

## 3. Publish the release

Files: `deploy/analysis-platform/aliyun-listen.conf` and release directory under `/srv/harbeat-listen/releases/`.

- [x] Build with `npm run build:continuous`; copy `continuous.html` as `index.html` and include `v3-clock.js`, library metadata and evidence.
- [x] Add only `/listen` and `/listen/` locations to the existing HTTPS server. Use immutable caching for media, revalidation for HTML/metadata, a strict missing-file 404, and GET/HEAD-only methods.
- [x] Run `nginx -t` before reload. Record the previous symlink and configuration for rollback.
- [x] Switch `/srv/harbeat-listen/current` to the verified release atomically.

## 4. Acceptance

- [x] HTTPS validates without certificate bypass; index lists exactly 157 songs across KPOP, EDM and 风格参考.
- [x] All media are present on ECS with matching checksums; public URLs contain no localhost, private IP, NAS path or analysis-media API dependency.
- [x] Validate public HTML, JS, clock worklet, compressed metadata, whole FLAC and byte-range responses.
- [x] Browser checks: desktop/mobile layout, search/filter, start, pause/resume, volume, seek across both 30-second and later segment boundaries, real handoff and queued third song. Check visible states, console failures and failed network requests.
- [x] Run the existing web suite and relevant Python tests. Record actual outcomes and any untested phone-specific behavior; do not claim 500 concurrent users from functional tests.
