# Metric mix cloud implementation plan

> **For agentic workers:** Use executing-plans inline, with requesting-code-review at completion. Follow the user's authorization to implement and deploy without another confirmation.

**Goal:** Publish a mobile-usable, metric-driven mixer with auditable provisional rules and real separated audio.

**Architecture:** Trusted cloud library determines frozen plans; a bounded gateway prepares source-bound clips on Jetson; a mobile WebAudio player stitches cached transition and native song segments on one clock. Existing `/listen/` remains available.

**Tech Stack:** Python/FastAPI, NumPy/SciPy/soundfile/FFmpeg, TypeScript/React/WebAudio, systemd/nginx.

- [x] 1. `metric_mix/policy.py`, `features.py`, `render.py`; tests `tests/test_metric_mix.py`. Start with `assert select({'bassOverlap':None})['recommended']=='original'`, reject non-finite measurements, require combination score margin, test synthetic isolated changes and unchanged native takeover. Run `python3 -m unittest tests.test_metric_mix` red then green.
- [x] 2. `metric_mix/prepare.py`, `gateway.py`; test `tests/test_metric_gateway.py`. Reconstruct trusted plan from ID/window/time, verify report/manifest/source files, enforce bounds and queue, call fixed remote program with JSON stdin, return whitelisted public result and immutable assets. Test client path/parameters ignored, expired/missing jobs and errors sanitized.
- [x] 3. `web/src/metric-mix/{app,transport,plan,types}.tsx/ts`, CSS and new Vite entry. Reuse `TrackLibrary`, `planContinuous`, `AudioCache` and `SegmentScheduler`; no mutation to the pre-existing 14 dirty files. Unit tests cover stale plan rejection, source/context mapping, cancellation and selection mapping; tsc and scoped Vitest.
- [x] 4. Check a real pair via NAS on Jetson, store source fingerprints and all method metrics, inspect sample continuity/peak and compare only-target differences. Build standalone release, browser-test cloud-like route and actual output.
- [x] 5. Review using requesting-code-review; fix blocking findings. Deploy isolated service and static route after local checks. Test nginx config before reload, verify original service still works. Run actual public prepare/play at desktop and a phone viewport; record physical-phone test limitation if no device is available.
- [x] 6. Write `docs/metric-mix-standards-20261020.md`, deployment/evidence JSON, release/rollback instructions. Commit only scoped files, preserve existing dirty hashes and old audition tabs, deliver URL and screenshot.

Acceptance and deployment record: `docs/evidence/metric-mix-cloud-20261020.json`. Physical-phone limitations are recorded in the standards and deployment README.
