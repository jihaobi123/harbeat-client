# Public Annotation Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/annotate` beside the existing HarBeat site so any registered user can label the same 10 Pilot songs while keeping revisions and files isolated per annotator.

**Architecture:** Port the remote `bar-understanding-v1` workbench into a new `app.modules.bar_annotations` namespace so it can coexist with the existing Presence module. A manifest allowlists the shared songs, authenticated read-only media endpoints expose only those songs, and the store keys every file by dataset, user and track. The React app selects the old site or the annotation portal from `window.location.pathname`.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, atomic JSON files with FileLock, React 18, Zustand, TypeScript, Vitest, Pytest, Nginx, systemd.

---

### Task 1: Import the Bar Understanding domain under a non-conflicting namespace

**Files:**
- Create: `app/modules/bar_annotations/__init__.py`
- Create: `app/modules/bar_annotations/candidates.py`
- Create: `app/modules/bar_annotations/public_datasets.py`
- Create: `app/modules/bar_annotations/schemas.py`
- Create: `app/modules/library/bar_feature_adapter.py`
- Create: `app/modules/library/feature_review_artifacts.py`
- Test: `app/tests/test_bar_annotation_candidates.py`
- Test: `app/tests/test_bar_annotation_public_datasets.py`

- [ ] **Step 1: Port the remote tests first and point imports at `app.modules.bar_annotations`**

Copy the assertions from `origin/codex/bar-understanding-v1:app/tests/test_annotation_candidates.py` and `test_annotation_public_datasets.py`. Change only the namespace:

```python
from app.modules.bar_annotations.candidates import build_candidate_bars
from app.modules.bar_annotations.public_datasets import normalize_section_label
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```bash
pytest -q app/tests/test_bar_annotation_candidates.py app/tests/test_bar_annotation_public_datasets.py
```

Expected: collection fails because `app.modules.bar_annotations` does not exist.

- [ ] **Step 3: Port the frozen domain files**

Port these exact remote sources from `origin/codex/bar-understanding-v1`:

```text
app/modules/annotations/candidates.py       -> app/modules/bar_annotations/candidates.py
app/modules/annotations/public_datasets.py  -> app/modules/bar_annotations/public_datasets.py
app/modules/annotations/schemas.py          -> app/modules/bar_annotations/schemas.py
app/modules/library/bar_feature_adapter.py  -> app/modules/library/bar_feature_adapter.py
app/modules/library/feature_review_artifacts.py -> app/modules/library/feature_review_artifacts.py
```

Replace imports beginning with `app.modules.annotations` by `app.modules.bar_annotations`. Keep label mappings and candidate behavior byte-for-byte otherwise.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the Task 1 pytest command. Expected: all imported candidate and public-dataset tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/bar_annotations app/modules/library/bar_feature_adapter.py app/modules/library/feature_review_artifacts.py app/tests/test_bar_annotation_candidates.py app/tests/test_bar_annotation_public_datasets.py
git commit -m "feat: import bar annotation domain"
```

### Task 2: Add the Pilot manifest and per-user atomic store

**Files:**
- Create: `config/public-annotation-pilot.json`
- Create: `app/modules/bar_annotations/pilot.py`
- Create: `app/modules/bar_annotations/store.py`
- Modify: `app/modules/bar_annotations/schemas.py`
- Modify: `app/shared/config.py`
- Test: `app/tests/test_bar_annotation_store.py`
- Test: `app/tests/test_bar_annotation_pilot.py`

- [ ] **Step 1: Write failing tests for the allowlist and storage path**

Use two user IDs on the same track and assert separate revisions:

```python
store.save(dataset, user_id=11, track_id=track, expected_revision=0,
           timeline_fingerprint="timeline", annotations=[])
store.save(dataset, user_id=12, track_id=track, expected_revision=0,
           timeline_fingerprint="timeline", annotations=[])
assert store.load(dataset, 11, track).revision == 1
assert store.load(dataset, 12, track).revision == 1
assert store.path_for(dataset, 11, track) != store.path_for(dataset, 12, track)
```

Test that `PilotManifest.require_track("private-id")` raises `PilotTrackNotFound` without disclosing database state.

- [ ] **Step 2: Run the tests and verify RED**

```bash
pytest -q app/tests/test_bar_annotation_store.py app/tests/test_bar_annotation_pilot.py
```

Expected: failures for missing `PilotManifest` and the missing `user_id` store dimension.

- [ ] **Step 3: Add the production manifest**

Write `config/public-annotation-pilot.json` with dataset version `bar-understanding-1.0.0` and the 10 IDs from `outputs/presence-pilot-selection.json`:

```json
{
  "dataset_version": "bar-understanding-1.0.0",
  "track_ids": [
    "mt2_bb6003cafad04057a25d8fbc9ac23ebf",
    "mt2_36e912c52484487e8d48453d3078bd27",
    "mt2_aa21861414a54fdaad9576be8a66dd8e",
    "mt2_500a92d8e4c1425f84762fbcaa7e9519",
    "mt2_4a56419a0d3e450a87b4cc03aec14231",
    "mt2_0d88ee2084da4ae1aa254e3ecb42ae37",
    "mt2_74669fa3abbf4346b887c7e8250e400d",
    "mt2_b71b445d21ab431a88b89a7a38fccb65",
    "mt2_2736e29e7d3646c3a059fd72b0d906dc",
    "mt2_718c7b675b8e45eea64ed1dd3a43b2fa"
  ]
}
```

- [ ] **Step 4: Implement strict manifest parsing and per-user paths**

`PilotManifest` validates safe IDs, rejects duplicate tracks and preserves manifest order. The store path is:

```python
return self.root / dataset / "users" / str(user_id) / f"{track}.json"
```

Add `annotator_id: str` to `StoredAnnotationSet`; write it from the authenticated user and validate it when loading.

Add settings with deployment-safe defaults:

```python
bar_annotation_dir: str = "./data/bar-annotations"
bar_annotation_pilot_manifest: str = "./config/public-annotation-pilot.json"
```

- [ ] **Step 5: Run the tests and verify GREEN**

Run the Task 2 pytest command. Expected: all store and manifest tests pass, including traversal, conflict and atomic-write cases.

- [ ] **Step 6: Commit**

```bash
git add config/public-annotation-pilot.json app/modules/bar_annotations app/shared/config.py app/tests/test_bar_annotation_store.py app/tests/test_bar_annotation_pilot.py
git commit -m "feat: isolate public annotations by user"
```

### Task 3: Build authenticated shared workspace and read-only media APIs

**Files:**
- Create: `app/modules/bar_annotations/service.py`
- Create: `app/modules/bar_annotations/router.py`
- Modify: `app/modules/router.py`
- Test: `app/tests/test_bar_annotation_service.py`
- Test: `app/tests/test_bar_annotation_router.py`

- [ ] **Step 1: Write failing service tests for independent workspaces**

Create one fake song and two stores scoped by user. Save different `structure.section_label` values and assert:

```python
alice = build_annotation_workspace(song, dataset, store, user_id=11)
bob = build_annotation_workspace(song, dataset, store, user_id=12)
assert alice.annotations != bob.annotations
assert alice.revision == 1
assert bob.revision == 1
```

Assert the server replaces every submitted `annotator_id` with `user:11`.

- [ ] **Step 2: Write failing router tests for shared access and private-song denial**

Override authentication, database and manifest dependencies. Verify:

```python
assert client.get("/tracks/pilot-1/workspace").status_code == 200
assert client.get("/tracks/private-1/workspace").status_code == 404
assert client.get("/tracks/private-1/audio?token=test").status_code == 404
assert client.get("/tracks/pilot-1/stems/not-a-stem?token=test").status_code == 404
```

- [ ] **Step 3: Run the new tests and verify RED**

```bash
pytest -q app/tests/test_bar_annotation_service.py app/tests/test_bar_annotation_router.py
```

Expected: missing service and router failures.

- [ ] **Step 4: Port and adapt the remote service**

Port `origin/codex/bar-understanding-v1:app/modules/annotations/service.py`, change imports to `bar_annotations`, and thread `user_id` through every store load/save:

```python
stored = store.load(dataset_version, user_id, str(song.id))
store.save(dataset_version, user_id, str(song.id), request.revision,
           timeline_fingerprint(timeline), normalized,
           annotator_id=f"user:{user_id}")
```

- [ ] **Step 5: Implement the API namespace**

Register the router under `/api/bar-annotations`. The catalog query loads the manifest IDs in order and returns only title, artist, duration and Stem availability. Workspace routes require `get_current_user`. Media routes accept the JWT query token used by `<audio>`, decode it, then check the Pilot manifest before opening a file.

Use `FileResponse` with a safe fixed Stem set:

```python
STEM_NAMES = {"vocals", "drums", "bass", "other"}
if stem_name not in STEM_NAMES:
    raise HTTPException(status_code=404, detail="media not found")
```

Return the same 404 for a missing song, a non-Pilot song or an unreadable media path.

- [ ] **Step 6: Run service, router and existing Presence tests**

```bash
pytest -q app/tests/test_bar_annotation_service.py app/tests/test_bar_annotation_router.py app/tests/test_annotation_api.py app/tests/test_presence_e2e.py
```

Expected: all pass; Presence remains under `/api/annotations` and Bar Understanding under `/api/bar-annotations`.

- [ ] **Step 7: Commit**

```bash
git add app/modules/bar_annotations app/modules/router.py app/tests/test_bar_annotation_service.py app/tests/test_bar_annotation_router.py
git commit -m "feat: expose shared pilot annotation api"
```

### Task 4: Add `/annotate` without replacing the old site

**Files:**
- Create: `web/src/types/annotation.ts`
- Create: `web/src/annotation/state.ts`
- Create: `web/src/annotation/state.test.ts`
- Create: `web/src/pages/AnnotationWorkbench.tsx`
- Create: `web/src/pages/AnnotationPortal.tsx`
- Create: `web/src/App.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/client.test.ts`
- Modify: `web/src/components/Sidebar.tsx`
- Modify: `web/src/pages/MainLayout.tsx`

- [ ] **Step 1: Port the remote editor-state test and verify RED**

Copy `origin/codex/bar-understanding-v1:web/src/annotation/state.test.ts` and change no behavior. Run:

```bash
cd web && npm test -- src/annotation/state.test.ts
```

Expected: module-not-found failure for `state.ts`.

- [ ] **Step 2: Port the remote editor types and state implementation**

Port the remote `web/src/types/annotation.ts` and `web/src/annotation/state.ts` unchanged. Run the state test and expect PASS.

- [ ] **Step 3: Write failing path and API tests**

Test that `/` renders the old `MainLayout`, `/annotate` renders `AnnotationPortal`, and the client calls the new namespace:

```ts
expect(fetch).toHaveBeenCalledWith(
  expect.stringContaining('/api/bar-annotations/pilot/tracks'),
  expect.anything(),
)
```

Expected: tests fail because the route and client functions do not exist.

- [ ] **Step 4: Port the workbench and replace private-library dependencies**

Port `origin/codex/bar-understanding-v1:web/src/pages/AnnotationWorkbench.tsx`. Replace `useMusicStore().songs` with `api.getPilotAnnotationTracks()`, use `/api/bar-annotations` workspace methods, and point audio/Stem URLs at the new read-only endpoints.

Create `AnnotationPortal` as a focused shell with a link back to `/`, username/logout controls, and the workbench. Do not mount upload, playlist or private-library controls in this shell.

- [ ] **Step 5: Select the entry from the browser path**

Keep the existing authentication gate and choose the post-login page:

```tsx
const annotationRoute = window.location.pathname === '/annotate'
if (!user) return <LoginPage />
return annotationRoute ? <AnnotationPortal /> : <MainLayout />
```

Add a Sidebar item that navigates with `window.location.assign('/annotate')`. The old views and `<AudioPlayer />` remain unchanged.

- [ ] **Step 6: Run frontend tests and build**

```bash
cd web && npm test && npm run build
```

Expected: all tests pass and Vite produces `web/dist` without TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add web/src
git commit -m "feat: add public annotation portal"
```

### Task 5: Export all annotators without modifying live data

**Files:**
- Create: `scripts/export_bar_annotation_pilot.py`
- Create: `app/tests/test_bar_annotation_export.py`

- [ ] **Step 1: Write a failing two-user export test**

Create two valid saved files for one track and assert the JSONL contains both identities while the report counts one track and two annotators:

```python
assert {row["annotator_id"] for row in rows} == {"user:11", "user:12"}
assert report["annotators_total"] == 2
assert report["tracks_total"] == 1
```

Add one malformed JSON file and assert it appears in `parse_errors` but not in JSONL.

- [ ] **Step 2: Run the export test and verify RED**

```bash
pytest -q app/tests/test_bar_annotation_export.py
```

Expected: import failure for `scripts.export_bar_annotation_pilot`.

- [ ] **Step 3: Implement deterministic export**

Walk `<root>/<dataset>/users/*/*.json` in sorted order, validate every file as `StoredAnnotationSet`, flatten its annotations, and write JSONL plus a report containing:

```python
{
    "dataset_version": dataset,
    "annotators_total": len(annotators),
    "tracks_total": len(tracks),
    "records_exported": len(records),
    "completion_by_annotator": completion,
    "annotators_by_track": annotators_by_track,
    "parse_errors": parse_errors,
}
```

- [ ] **Step 4: Run the export test and verify GREEN**

Run the Task 5 pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/export_bar_annotation_pilot.py app/tests/test_bar_annotation_export.py
git commit -m "feat: export multi-annotator pilot data"
```

### Task 6: Run full regression and produce a release bundle

**Files:**
- Modify if needed: only files already listed above

- [ ] **Step 1: Run backend regression**

```bash
pytest -q app/tests
```

Expected: all tests pass with no collection errors.

- [ ] **Step 2: Run frontend regression and production build**

```bash
cd web && npm test && npm run build
```

Expected: all Vitest tests pass and `web/dist/index.html` exists.

- [ ] **Step 3: Validate configuration and manifests**

```bash
python -m json.tool config/public-annotation-pilot.json >/dev/null
python -m json.tool outputs/presence-pilot-selection.json >/dev/null
git diff --check HEAD~5..HEAD
```

Expected: exit code 0 for every command.

- [ ] **Step 4: Commit any test-only correction**

If regression required a correction, add only the named files and commit it with `fix: stabilize public annotation portal`. If no correction was needed, do not create an empty commit.

### Task 7: Deploy to Jetson with staging, browser verification and rollback

**Files:**
- Production code release: `/opt/harbeat/releases/public-annotation-<commit>`
- Persistent labels: `/data/harbeat/bar-annotations`
- Persistent manifest: release `config/public-annotation-pilot.json`
- systemd drop-in: `/etc/systemd/system/harbeat-api.service.d/public-annotation.conf`
- Nginx configuration: existing HarBeat site block

- [ ] **Step 1: Build a merge release from the current production baseline**

Copy the active production release without `.env`, overlay the reviewed repository files, copy the production `.env`, install only missing Python packages into a release-local `vendor` directory, and set:

```text
BAR_ANNOTATION_DIR=/data/harbeat/bar-annotations
BAR_ANNOTATION_PILOT_MANIFEST=/opt/harbeat/releases/public-annotation-<commit>/config/public-annotation-pilot.json
```

- [ ] **Step 2: Start staging on an isolated port**

Start Uvicorn against the new release on `127.0.0.1:18000`. Verify `/health`, the old root, registration, the Pilot catalog and one workspace before touching production.

- [ ] **Step 3: Add Nginx routing and rate limits**

Keep `/` unchanged. Ensure `/annotate` falls back to `index.html`; proxy `/api/` as before. Apply a conservative burst limit to `/api/auth/register` and `/api/auth/login` while leaving audio streaming outside that rate-limited location.

- [ ] **Step 4: Switch the production service**

Point the service drop-in at the new release, run `systemctl daemon-reload`, restart `harbeat-api`, and verify the effective working directory. Do not delete the previous release or annotation data.

- [ ] **Step 5: Run a two-user production acceptance test**

Create two uniquely named temporary accounts, verify both see the same 10 tracks, save different labels on one song, reload, and confirm each user sees only their own revision. Verify `/`, `/health`, one existing private API and one Presence API still return their expected statuses.

- [ ] **Step 6: Verify persistence after restart**

Restart `harbeat-api`, sign in again with both temporary accounts, and confirm both revisions remain. Archive the two exact annotation files outside the active dataset and deactivate the exact temporary account IDs; do not touch Pilot user data.

- [ ] **Step 7: Record the live release and rollback command**

Record the release path, commit, test totals and public URLs in `outputs/public-annotation-deployment.json`. Rollback consists of restoring the previous systemd WorkingDirectory and Nginx file, then reloading both services; the persistent annotation directory remains untouched.
