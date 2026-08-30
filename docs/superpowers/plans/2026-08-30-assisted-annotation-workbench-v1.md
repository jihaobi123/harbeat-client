# Assisted Annotation Workbench V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-shaped Pilot loop that turns HarBeat analysis and Raveform labels into editable Bar-level candidates and persists schema-valid annotations.

**Architecture:** A new FastAPI annotations module owns label mapping, candidate generation, atomic file persistence and authenticated endpoints. The React page consumes one workspace payload, applies range edits locally, and saves the full annotation set with optimistic revision checking. Existing Bar timeline code remains the only authority for Bar boundaries.

**Tech Stack:** Python 3, FastAPI, Pydantic, JSON Schema, pytest, React 18, TypeScript, Vitest, Vite, Tailwind CSS

---

## File map

- `contracts/registries/annotation_labels_v1.json`: V1 labels and public-dataset mappings.
- `app/modules/annotations/public_datasets.py`: deterministic Raveform label mapping and record conversion.
- `app/modules/annotations/candidates.py`: candidate Section and element states from current analysis.
- `app/modules/annotations/schemas.py`: workspace and save request models.
- `app/modules/annotations/store.py`: revisioned atomic JSON persistence.
- `app/modules/annotations/service.py`: timeline validation, workspace assembly and save orchestration.
- `app/modules/annotations/router.py`: authenticated GET/PUT routes.
- `web/src/annotation/state.ts`: tested range-edit and serialization logic.
- `web/src/pages/AnnotationWorkbench.tsx`: producer-facing page.
- `web/src/types/annotation.ts`: API types.
- `web/src/api/client.ts`, `web/src/components/Sidebar.tsx`, `web/src/pages/MainLayout.tsx`: navigation and API wiring.

### Task 1: Freeze labels and public-data mapping

**Files:**
- Create: `contracts/registries/annotation_labels_v1.json`
- Create: `app/modules/annotations/__init__.py`
- Create: `app/modules/annotations/public_datasets.py`
- Test: `app/tests/test_annotation_public_datasets.py`

- [ ] **Step 1: Write the failing mapping tests**

```python
from app.modules.annotations.public_datasets import map_raveform_section_label


def test_maps_raveform_edm_functions_to_v1():
    assert map_raveform_section_label("Ambient-Intro") == "intro"
    assert map_raveform_section_label("Build-up") == "build"
    assert map_raveform_section_label("Drop 2") == "main"
    assert map_raveform_section_label("Breakdown") == "breakdown"
    assert map_raveform_section_label("Ambient-Outro") == "outro"


def test_unknown_public_label_fails_closed():
    assert map_raveform_section_label("mystery") == "unknown"
```

- [ ] **Step 2: Run the test and confirm `ModuleNotFoundError`**

Run: `python3 -m pytest app/tests/test_annotation_public_datasets.py -q`

- [ ] **Step 3: Add the registry and minimal mapper**

```python
def map_raveform_section_label(label: str) -> str:
    normalized = "-".join(str(label).strip().lower().replace("_", "-").split())
    normalized = normalized.rstrip("-0123456789 ")
    if normalized in {"intro", "ambient-intro"}:
        return "intro"
    if normalized in {"buildup", "build-up"}:
        return "build"
    if normalized in {"breakdown", "ambient-breakdown"}:
        return "breakdown"
    if normalized in {"outro", "ambient-outro"}:
        return "outro"
    if normalized in {"drop", "cooldown", "bridge", "verse", "chorus", "instrumental"}:
        return "main"
    return "unknown"
```

- [ ] **Step 4: Run the mapping tests**

Run: `python3 -m pytest app/tests/test_annotation_public_datasets.py -q`

- [ ] **Step 5: Commit**

```bash
git add contracts/registries/annotation_labels_v1.json app/modules/annotations app/tests/test_annotation_public_datasets.py
git commit -m "feat: freeze annotation label mappings"
```

### Task 2: Generate safe Bar-level candidates

**Files:**
- Create: `app/modules/annotations/candidates.py`
- Test: `app/tests/test_annotation_candidates.py`

- [ ] **Step 1: Write failing tests for Section and element candidates**

```python
def test_candidates_use_phrase_overlap_and_stem_activity(song):
    workspace = build_candidate_bars(song)
    assert workspace[0]["section"]["value"] == "intro"
    assert workspace[0]["elements"]["drums"]["value"] == "foreground"
    assert workspace[0]["elements"]["vocal"]["value"] == "absent"
    assert workspace[0]["elements"]["melody"]["value"] == "unknown"


def test_candidate_transition_marks_entering(song):
    workspace = build_candidate_bars(song)
    assert workspace[1]["elements"]["vocal"]["value"] == "entering"
```

- [ ] **Step 2: Run and confirm the import failure**

Run: `python3 -m pytest app/tests/test_annotation_candidates.py -q`

- [ ] **Step 3: Implement candidate generation on top of `build_bar_features`**

```python
def activity_state(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.15:
        return "absent"
    if value < 0.65:
        return "background"
    return "foreground"
```

The implementation must preserve source, confidence and original fine label. It must leave melody as `unknown` unless direct melody evidence exists.

- [ ] **Step 4: Run candidate and existing Bar adapter tests**

Run: `python3 -m pytest app/tests/test_annotation_candidates.py app/tests/test_bar_feature_adapter.py -q`

- [ ] **Step 5: Commit**

```bash
git add app/modules/annotations/candidates.py app/tests/test_annotation_candidates.py
git commit -m "feat: derive assisted annotation candidates"
```

### Task 3: Add revisioned annotation persistence

**Files:**
- Create: `app/modules/annotations/schemas.py`
- Create: `app/modules/annotations/store.py`
- Test: `app/tests/test_annotation_store.py`

- [ ] **Step 1: Write failing store tests**

```python
def test_store_round_trip_and_revision(tmp_path):
    store = AnnotationStore(tmp_path)
    saved = store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])
    assert saved.revision == 1
    assert store.load("bar-understanding-1.0.0", "track-1").revision == 1


def test_store_rejects_stale_revision(tmp_path):
    store = AnnotationStore(tmp_path)
    store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])
    with pytest.raises(RevisionConflict):
        store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])


def test_store_rejects_timeline_change_in_same_dataset(tmp_path):
    store = AnnotationStore(tmp_path)
    store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])
    with pytest.raises(TimelineConflict):
        store.save("bar-understanding-1.0.0", "track-1", 1, "timeline-b", [])
```

- [ ] **Step 2: Run and verify failure**

Run: `python3 -m pytest app/tests/test_annotation_store.py -q`

- [ ] **Step 3: Implement atomic write and typed records**

```python
temporary = target.with_suffix(f"{target.suffix}.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temporary, target)
```

The Pydantic record model must enforce the current schema enums, UTC `Z` timestamps, half-open Bar ranges and dataset/track identity.

- [ ] **Step 4: Run store tests**

Run: `python3 -m pytest app/tests/test_annotation_store.py -q`

- [ ] **Step 5: Commit**

```bash
git add app/modules/annotations/schemas.py app/modules/annotations/store.py app/tests/test_annotation_store.py
git commit -m "feat: persist revisioned annotation records"
```

### Task 4: Assemble and save a workspace through FastAPI

**Files:**
- Create: `app/modules/annotations/service.py`
- Create: `app/modules/annotations/router.py`
- Modify: `app/modules/router.py`
- Modify: `app/shared/config.py`
- Test: `app/tests/test_annotation_service.py`
- Test: `app/tests/test_annotation_router.py`

- [ ] **Step 1: Write failing service tests**

```python
def test_workspace_contains_canonical_bars_candidates_and_revision(song, tmp_path):
    workspace = build_workspace(song, "bar-understanding-1.0.0", AnnotationStore(tmp_path))
    assert workspace.track_id == song.id
    assert workspace.revision == 0
    assert workspace.bars[0].start_sec == 0.0
    assert workspace.bars[0].end_sec == 2.0


def test_save_rejects_annotation_outside_current_timeline(song, tmp_path):
    with pytest.raises(AnnotationValidationError):
        save_workspace(song, invalid_request, AnnotationStore(tmp_path))
```

- [ ] **Step 2: Run and verify failure**

Run: `python3 -m pytest app/tests/test_annotation_service.py -q`

- [ ] **Step 3: Implement workspace service and authenticated routes**

```python
@router.get("/tracks/{track_id}/workspace", response_model=APIResponse[AnnotationWorkspace])
def get_workspace(track_id: str, dataset_version: str = DEFAULT_DATASET_VERSION, ...):
    song = get_owned_song(db, track_id, current_user.id)
    return APIResponse(data=build_workspace(song, dataset_version, store_for_settings()))
```

The PUT route maps stale revisions and timeline changes to HTTP 409 and malformed annotations to HTTP 422.

- [ ] **Step 4: Run service, route and contract tests**

Run: `python3 -m pytest app/tests/test_annotation_service.py app/tests/test_annotation_router.py app/tests/test_music_analysis_contracts.py -q`

- [ ] **Step 5: Commit**

```bash
git add app/modules/annotations app/modules/router.py app/shared/config.py app/tests/test_annotation_service.py app/tests/test_annotation_router.py
git commit -m "feat: expose annotation workspace api"
```

### Task 5: Convert Raveform annotations into candidates

**Files:**
- Modify: `app/modules/annotations/public_datasets.py`
- Create: `scripts/import_raveform_annotations.py`
- Create: `contracts/fixtures/analysis/raveform_track.valid.json`
- Modify: `app/tests/test_annotation_public_datasets.py`

- [ ] **Step 1: Add a failing conversion test**

```python
def test_raveform_track_conversion_emits_candidate_records(fixture):
    records = convert_raveform_track(fixture, dataset_version="raveform-import-1.0.0")
    assert records[0]["annotation_status"] == "candidate"
    assert records[0]["task_id"] == "structure.section_label"
    assert records[0]["value"] == "intro"
    assert records[0]["candidate_source"].startswith("dataset:raveform:")
```

- [ ] **Step 2: Run and verify failure**

Run: `python3 -m pytest app/tests/test_annotation_public_datasets.py -q`

- [ ] **Step 3: Implement tolerant source parsing and JSONL export**

The converter accepts `start`, `start_sec` or `time`, derives missing ends from the next section, preserves the original label in provenance and never downloads audio.

- [ ] **Step 4: Run conversion tests and a fixture CLI smoke test**

Run: `python3 -m pytest app/tests/test_annotation_public_datasets.py -q`

Run: `python3 scripts/import_raveform_annotations.py --input contracts/fixtures/analysis/raveform_track.valid.json --output /tmp/harbeat-raveform-test.jsonl --dataset-version raveform-import-1.0.0`

- [ ] **Step 5: Commit**

```bash
git add app/modules/annotations/public_datasets.py scripts/import_raveform_annotations.py contracts/fixtures/analysis/raveform_track.valid.json app/tests/test_annotation_public_datasets.py
git commit -m "feat: import raveform section candidates"
```

### Task 6: Add tested frontend annotation state

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Create: `web/src/types/annotation.ts`
- Create: `web/src/annotation/state.ts`
- Create: `web/src/annotation/state.test.ts`

- [ ] **Step 1: Install Vitest and add the test script**

Run: `npm install --save-dev vitest`

Add: `"test": "vitest run"`.

- [ ] **Step 2: Write failing range-edit tests**

```typescript
it('applies one section label to a half-open bar range', () => {
  const draft = applyRangeLabel(emptyDraft(8), { start: 2, end: 6 }, 'structure.section_label', 'build')
  expect(draft.annotations).toHaveLength(1)
  expect(draft.annotations[0].start_bar_index).toBe(2)
  expect(draft.annotations[0].end_bar_index).toBe(6)
})

it('replaces overlapping annotations for the same task without touching other tasks', () => {
  const updated = applyRangeLabel(existingDraft, { start: 1, end: 3 }, 'elements.vocal.state', 'foreground')
  expect(recordsFor(updated, 'elements.drums.state')).toEqual(existingDrumRecords)
})
```

- [ ] **Step 3: Run and verify failure**

Run: `npm test -- src/annotation/state.test.ts`

- [ ] **Step 4: Implement minimal immutable state helpers**

```typescript
export function normalizeRange(start: number, endInclusive: number, barCount: number): BarRange {
  const first = Math.max(0, Math.min(start, endInclusive))
  const last = Math.min(barCount - 1, Math.max(start, endInclusive))
  return { start: first, end: last + 1 }
}
```

- [ ] **Step 5: Run frontend tests and commit**

Run: `npm test -- src/annotation/state.test.ts`

```bash
git add web/package.json web/package-lock.json web/src/types/annotation.ts web/src/annotation
git commit -m "feat: add annotation editor state"
```

### Task 7: Build the producer-facing page

**Files:**
- Create: `web/src/pages/AnnotationWorkbench.tsx`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/Sidebar.tsx`
- Modify: `web/src/pages/MainLayout.tsx`
- Modify: `web/src/index.css`

- [ ] **Step 1: Add API functions and page shell**

```typescript
export async function getAnnotationWorkspace(trackId: string, datasetVersion: string) {
  return request<AnnotationWorkspace>(`/api/annotations/tracks/${trackId}/workspace?dataset_version=${encodeURIComponent(datasetVersion)}`)
}
```

- [ ] **Step 2: Render song selection, audio playback and Bar grid**

Each Bar column shows its number, time, candidate Section and four element candidate states. The selected range remains visible while audio plays.

- [ ] **Step 3: Add range tools and explicit save**

Section and element controls call the tested state helpers. Save sends the current revision and replaces local state only with the successful server response.

- [ ] **Step 4: Build and test**

Run: `npm test`

Run: `npm run build`

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/AnnotationWorkbench.tsx web/src/api/client.ts web/src/components/Sidebar.tsx web/src/pages/MainLayout.tsx web/src/index.css
git commit -m "feat: add assisted annotation workbench"
```

### Task 8: Verify the end-to-end Pilot slice

**Files:**
- Modify: `docs/HARBEAT_MUSIC_ANALYSIS_DEVELOPMENT_CONTRACT_V1.md`
- Create: `docs/ANNOTATION_WORKBENCH_V1.md`

- [ ] **Step 1: Document startup, data location and label workflow**

Document the GET/PUT endpoints, Revision conflict behavior, Raveform conversion command and the fact that `candidate` records are excluded from supervised truth by default.

- [ ] **Step 2: Run focused backend tests**

Run: `python3 -m pytest app/tests/test_annotation_public_datasets.py app/tests/test_annotation_candidates.py app/tests/test_annotation_store.py app/tests/test_annotation_service.py app/tests/test_annotation_router.py app/tests/test_bar_feature_adapter.py app/tests/test_music_analysis_contracts.py -q`

- [ ] **Step 3: Run frontend verification**

Run: `npm test && npm run build`

- [ ] **Step 4: Inspect the final diff and remove generated artifacts**

Run: `git status --short && git diff --check && git diff --stat`

- [ ] **Step 5: Commit documentation**

```bash
git add docs/HARBEAT_MUSIC_ANALYSIS_DEVELOPMENT_CONTRACT_V1.md docs/ANNOTATION_WORKBENCH_V1.md
git commit -m "docs: publish annotation workbench workflow"
```
