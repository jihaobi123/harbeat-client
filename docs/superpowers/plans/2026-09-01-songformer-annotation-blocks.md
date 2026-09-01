# SongFormer Annotation Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy SongFormer on Jetson and turn its time boundaries into Bar-aligned, reviewable annotation blocks while keeping the untrained residual relabeler disabled behind a stable interface.

**Architecture:** Reuse the isolated SongFormer runner already validated on `origin/codex/section-relabeler-v1`, but keep annotation-section results in an independent sidecar store so existing `phrase_map`, DJ analysis, and human annotation JSON are not rewritten. The public annotation workspace derives deterministic half-open Bar blocks from SongFormer seconds and the canonical Bar grid; the React workbench selects those blocks by default and preserves smaller manual range overrides. The residual classifier contract is exposed as disabled metadata only.

**Tech Stack:** Python 3.10, FastAPI, Pydantic v2, NumPy, PyTorch CUDA on Jetson Orin, React 18, TypeScript, Vitest, pytest, systemd, NAS-backed JSON/cache storage

---

**Execution mode:** Inline execution in the current task. Do not dispatch subagents. Preserve unrelated dirty worktree files and commit only the paths named by each task.

**Approved design:** `docs/superpowers/specs/2026-09-01-songformer-annotation-blocks-design.md`

## File map

- `experiments/run_songformer_isolated.py`: validated MusicFM + MuQ + SongFormer sequential GPU runner.
- `experiments/songformer_runtime_support.py`: evidence aggregation, fingerprints, and cache namespaces.
- `app/modules/bar_annotations/songformer_sections.py`: runtime client, strict sidecar store, and disabled relabeler contract.
- `app/modules/bar_annotations/section_blocks.py`: pure seconds-to-Bar-block conversion.
- `app/modules/bar_annotations/schemas.py`: API contracts for runtime state and blocks.
- `app/modules/bar_annotations/service.py`: join canonical Bars, user annotations, and shared sidecars.
- `app/modules/bar_annotations/router.py`: inject the shared sidecar store.
- `scripts/generate_songformer_annotation_blocks.py`: safe Pilot backfill.
- `web/src/annotation/sectionBlocks.ts`: pure block navigation helpers.
- `web/src/annotation/playback.ts`: pure transport-mode logic.
- `web/src/pages/AnnotationWorkbench.tsx`: block-first workflow and playback fix.
- `deploy/songformer/`: reproducible Jetson install, verification, and rollback documentation.

### Task 1: Import the validated isolated SongFormer runner

**Files:**
- Create: `experiments/run_songformer_isolated.py`
- Create: `experiments/songformer_runtime_support.py`
- Create: `tests/test_songformer_runtime_support.py`

- [ ] **Step 1: Restore the validated files**

```bash
git restore --source=origin/codex/section-relabeler-v1 -- \
  experiments/run_songformer_isolated.py \
  experiments/songformer_runtime_support.py \
  tests/test_songformer_runtime_support.py
```

Expected: these three paths are added. No classifier training or runtime file is restored.

- [ ] **Step 2: Run pure tests and syntax checks**

```bash
python3 -m pytest tests/test_songformer_runtime_support.py -q
python3 -m py_compile experiments/run_songformer_isolated.py experiments/songformer_runtime_support.py
```

Expected: all tests pass without loading model weights.

- [ ] **Step 3: Commit**

```bash
git add experiments/run_songformer_isolated.py experiments/songformer_runtime_support.py tests/test_songformer_runtime_support.py
git commit -m "feat(songformer): import isolated inference runtime"
```

### Task 2: Define the shared SongFormer sidecar contract

**Files:**
- Create: `app/modules/bar_annotations/songformer_sections.py`
- Create: `app/tests/test_songformer_section_store.py`
- Modify: `app/shared/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing tests**

```python
def test_round_trip_preserves_boundaries_and_disabled_relabeler(tmp_path):
    store = SongFormerSectionStore(tmp_path)
    document = songformer_document(
        track_id="track-1",
        audio_fingerprint="audio-sha",
        runtime_fingerprint={"runner_version": "songformer_isolated_v3"},
        segments=[{
            "start": 0.21,
            "end": 8.12,
            "label": "intro",
            "label_probabilities": {"intro": 0.8, "verse": 0.2},
            "label_confidence": 0.8,
            "label_margin": 0.6,
        }],
    )
    store.save(document)
    loaded = store.load("track-1")
    assert loaded.segments[0].start == 0.21
    assert loaded.relabeler.enabled is False
    assert loaded.relabeler.model_status == "not_installed"


def test_invalid_sidecar_fails_closed(tmp_path):
    (tmp_path / "track-1.json").write_text('{"segments": "bad"}')
    with pytest.raises(SongFormerSectionInvalid):
        SongFormerSectionStore(tmp_path).load("track-1")
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest app/tests/test_songformer_section_store.py -q
```

Expected: import failure for `songformer_sections.py`.

- [ ] **Step 3: Implement strict models**

```python
class RelabelerState(BaseModel):
    enabled: Literal[False] = False
    mode: Literal["disabled"] = "disabled"
    model_status: Literal["not_installed"] = "not_installed"
    model_version: None = None
    input_contract_version: Literal["songformer_section_relabeler_input_v1"] = (
        "songformer_section_relabeler_input_v1"
    )
    output_contract_version: Literal["songformer_section_relabeler_output_v1"] = (
        "songformer_section_relabeler_output_v1"
    )


class SongFormerSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str
    label_probabilities: dict[str, float] = Field(default_factory=dict)
    label_confidence: float | None = Field(default=None, ge=0, le=1)
    label_margin: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_time(self):
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        return self


class SongFormerSectionDocument(BaseModel):
    schema_name: Literal["harbeat.songformer_sections"] = "harbeat.songformer_sections"
    schema_version: Literal["1.0.0"] = "1.0.0"
    track_id: str
    status: Literal["ready", "failed"]
    audio_fingerprint: str
    runtime_fingerprint: dict[str, object]
    cache_namespace: str | None = None
    segments: list[SongFormerSegment]
    relabeler: RelabelerState = Field(default_factory=RelabelerState)
    error: str | None = None
```

`SongFormerSectionStore.save` writes a hidden temporary sibling, flushes and `fsync`s it, then uses `os.replace`. Reject unsafe IDs, overlapping/non-monotonic segments, extra fields, and any sidecar claiming the classifier is enabled.

- [ ] **Step 4: Add settings**

```python
songformer_section_dir: str = "./data/songformer-sections"
songformer_command: str = ""
songformer_work_dir: str = "./data/songformer-cache"
songformer_timeout_sec: int = 1800
songformer_enabled: bool = False
```

Mirror these names in `.env.example` without credentials.

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m pytest app/tests/test_songformer_section_store.py app/tests/test_settings.py -q
git add app/modules/bar_annotations/songformer_sections.py app/tests/test_songformer_section_store.py app/shared/config.py .env.example
git commit -m "feat(annotation): define SongFormer section sidecars"
```

### Task 3: Convert SongFormer seconds into deterministic Bar blocks

**Files:**
- Create: `app/modules/bar_annotations/section_blocks.py`
- Create: `app/tests/test_songformer_section_blocks.py`
- Modify: `app/modules/bar_annotations/schemas.py`

- [ ] **Step 1: Write failing conversion tests**

```python
def test_snaps_boundaries_to_nearest_bar_edges():
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline([0.0, 2.0, 4.0, 6.0, 8.0]),
        document=_document([(0.12, 3.82, "intro"), (3.82, 8.0, "verse")]),
    )
    assert [(b.start_bar_index, b.end_bar_index) for b in blocks] == [(0, 2), (2, 4)]
    assert blocks[0].raw_end_time == 3.82
    assert blocks[0].end_time == 4.0


def test_collapsed_boundaries_never_create_zero_length_blocks():
    blocks = build_section_blocks(
        track_id="track-1",
        timeline=_timeline([0.0, 2.0, 4.0]),
        document=_document([(0.0, 1.1, "intro"), (1.1, 1.2, "verse"), (1.2, 4.0, "chorus")]),
    )
    assert all(item.start_bar_index < item.end_bar_index for item in blocks)
    assert any(item.suppressed_boundary_count > 0 for item in blocks)
```

Also cover song edges, deterministic IDs, review thresholds, and missing segments.

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest app/tests/test_songformer_section_blocks.py -q
```

- [ ] **Step 3: Implement the converter**

```python
SNAP_SOURCE = "songformer_bar_snap_v1"


def build_section_blocks(
    *,
    track_id: str,
    timeline: CanonicalTimeline,
    document: SongFormerSectionDocument,
) -> list[SectionAnnotationBlock]:
    edges = [bar.start_sec for bar in timeline.intervals]
    edges.append(timeline.intervals[-1].end_sec)
    raw_boundaries = [document.segments[0].start]
    raw_boundaries.extend(segment.end for segment in document.segments)
    snapped = [0]
    for boundary in raw_boundaries[1:-1]:
        snapped.append(min(range(len(edges)), key=lambda index: abs(edges[index] - boundary)))
    snapped.append(len(edges) - 1)
    unique_edges = sorted(set(snapped))
    fingerprint = sha256(
        json.dumps(document.runtime_fingerprint, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return [
        _block_from_edges(
            track_id=track_id,
            edge_start=edge_start,
            edge_end=edge_end,
            edges=edges,
            raw_boundaries=raw_boundaries,
            snapped_boundaries=snapped,
            cache_namespace=document.cache_namespace,
            runtime_fingerprint=fingerprint,
        )
        for edge_start, edge_end in zip(unique_edges, unique_edges[1:])
        if edge_end > edge_start
    ]
```

The review threshold is `min(1.5, 0.35 * local_bar_duration)`. The ID is the first 20 SHA-256 hex characters of canonical JSON containing track ID, Bar range, cache namespace, and runtime fingerprint. No human annotation is read or changed.

- [ ] **Step 4: Run and commit**

```bash
python3 -m pytest app/tests/test_songformer_section_blocks.py -q
git add app/modules/bar_annotations/section_blocks.py app/modules/bar_annotations/schemas.py app/tests/test_songformer_section_blocks.py
git commit -m "feat(annotation): snap SongFormer sections to Bars"
```

### Task 4: Expose shared blocks in each user's workspace

**Files:**
- Modify: `app/modules/bar_annotations/schemas.py`
- Modify: `app/modules/bar_annotations/service.py`
- Modify: `app/modules/bar_annotations/router.py`
- Modify: `app/tests/test_bar_annotation_service.py`
- Modify: `app/tests/test_bar_annotation_router.py`

- [ ] **Step 1: Add failing assertions**

```python
assert alice.section_blocks == bob.section_blocks
assert alice.annotations != bob.annotations
assert alice.section_block_status == "ready"
assert alice.section_relabeler.model_status == "not_installed"
assert alice.section_blocks[0].start_bar_index == 0
assert alice.section_blocks[0].end_bar_index == 2
```

Also cover `not_analyzed`, invalid sidecar -> `failed`, and `needs_review`.

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest app/tests/test_bar_annotation_service.py app/tests/test_bar_annotation_router.py -q
```

- [ ] **Step 3: Extend the response compatibly**

```python
section_block_status: Literal["ready", "needs_review", "failed", "not_analyzed"]
section_blocks: list[SectionAnnotationBlock] = Field(default_factory=list)
section_model: Optional[SectionModelState] = None
section_relabeler: RelabelerState = Field(default_factory=RelabelerState)
```

Keep saved annotation records unchanged. Do not include the model sidecar fingerprint in `timeline_fingerprint`; a candidate rerun must not invalidate human labels.

- [ ] **Step 4: Join the shared store**

```python
document = section_store.load(str(song.id))
if document is None:
    status, blocks = "not_analyzed", []
elif document.status == "failed":
    status, blocks = "failed", []
else:
    blocks = build_section_blocks(track_id=str(song.id), timeline=timeline, document=document)
    status = "needs_review" if any(item.needs_review for item in blocks) else "ready"
```

- [ ] **Step 5: Verify and commit**

```bash
python3 -m pytest app/tests/test_bar_annotation_service.py app/tests/test_bar_annotation_router.py app/tests/test_bar_annotation_store.py -q
git add app/modules/bar_annotations/schemas.py app/modules/bar_annotations/service.py app/modules/bar_annotations/router.py app/tests/test_bar_annotation_service.py app/tests/test_bar_annotation_router.py
git commit -m "feat(annotation): expose SongFormer annotation blocks"
```

### Task 5: Add block-first frontend selection

**Files:**
- Create: `web/src/annotation/sectionBlocks.ts`
- Create: `web/src/annotation/sectionBlocks.test.ts`
- Modify: `web/src/types/annotation.ts`
- Modify: `web/src/pages/AnnotationWorkbench.tsx`
- Modify: `web/src/index.css`

- [ ] **Step 1: Write failing helper tests**

```typescript
it('selects the first unfinished block', () => {
  expect(defaultBlockSelection(blocks, annotations)).toEqual({ start: 4, end: 8 })
})

it('moves to the next block and wraps', () => {
  expect(nextBlockIndex(blocks, 1)).toBe(2)
  expect(nextBlockIndex(blocks, 2)).toBe(0)
})
```

- [ ] **Step 2: Confirm RED**

```bash
npm --prefix web test -- --run web/src/annotation/sectionBlocks.test.ts
```

- [ ] **Step 3: Add exact frontend contracts**

```typescript
export interface SectionAnnotationBlock {
  block_id: string
  start_bar_index: number
  end_bar_index: number
  start_time: number
  end_time: number
  raw_start_time: number
  raw_end_time: number
  start_snap_error_sec: number
  end_snap_error_sec: number
  source: 'songformer_bar_snap_v1'
  source_segment_indexes: number[]
  needs_review: boolean
  suppressed_boundary_count: number
  model_runtime_fingerprint: string
}
```

- [ ] **Step 4: Implement block navigation and workbench UI**

On load, select `{start: block.start_bar_index, end: block.end_bar_index}`, translating the half-open end to the current inclusive selection state with `selectionEnd = end - 1`. Add previous/next block buttons, block status, review warning, snap error, and “选中整个段落块”. Applying a smaller range continues through `applyRangeLabel`, which already splits overlapping annotation ranges.

- [ ] **Step 5: Verify and commit**

```bash
npm --prefix web test -- --run
npm --prefix web run build
git add web/src/annotation/sectionBlocks.ts web/src/annotation/sectionBlocks.test.ts web/src/types/annotation.ts web/src/pages/AnnotationWorkbench.tsx web/src/index.css
git commit -m "feat(web): annotate by SongFormer section blocks"
```

### Task 6: Fix full playback versus range preview

**Files:**
- Create: `web/src/annotation/playback.ts`
- Create: `web/src/annotation/playback.test.ts`
- Modify: `web/src/pages/AnnotationWorkbench.tsx`

- [ ] **Step 1: Write failing regression tests**

```typescript
it('does not stop full playback at the range end', () => {
  expect(playbackAction({ mode: 'full', currentTime: 8, rangeStart: 0, rangeEnd: 4 })).toBe('continue')
})

it('stops a range preview at its end', () => {
  expect(playbackAction({ mode: 'range_preview', currentTime: 4, rangeStart: 0, rangeEnd: 4 })).toBe('pause')
})

it('loops only in range-loop mode', () => {
  expect(playbackAction({ mode: 'range_loop', currentTime: 4, rangeStart: 0, rangeEnd: 4 })).toBe('loop')
})
```

- [ ] **Step 2: Confirm RED**

```bash
npm --prefix web test -- --run web/src/annotation/playback.test.ts
```

- [ ] **Step 3: Implement transport modes**

```typescript
export type PlaybackMode = 'full' | 'range_preview' | 'range_loop'

export function playbackAction(input: PlaybackInput): PlaybackAction {
  if (input.mode === 'full' || input.currentTime < input.rangeEnd) return 'continue'
  return input.mode === 'range_loop' ? 'loop' : 'pause'
}
```

Native `onPlay` uses `full`; the preview button sets `range_preview`; explicit loop uses `range_loop`. Changing track, source, or selection resets to `full`.

- [ ] **Step 4: Verify and commit**

```bash
npm --prefix web test -- --run
npm --prefix web run build
git add web/src/annotation/playback.ts web/src/annotation/playback.test.ts web/src/pages/AnnotationWorkbench.tsx
git commit -m "fix(web): keep full annotation playback running"
```

### Task 7: Add safe runtime generation and Pilot backfill

**Files:**
- Modify: `app/modules/bar_annotations/songformer_sections.py`
- Create: `scripts/generate_songformer_annotation_blocks.py`
- Create: `app/tests/test_generate_songformer_annotation_blocks.py`
- Modify: `app/worker/jobs.py`
- Modify: `app/modules/library/background_tasks.py`

- [ ] **Step 1: Write failing runtime tests**

Mock subprocess execution and prove that `shlex.split` is used, `shell=False`, placeholders become separate arguments, timeout/non-zero exits save bounded failed sidecars, validated manifests create ready sidecars, and matching fingerprints skip unless forced.

```python
completed = runner.run(track_id="track-1", audio_path=audio)
mock_run.assert_called_once_with(
    expected_command,
    check=True,
    capture_output=True,
    text=True,
    timeout=1800,
    shell=False,
)
assert completed.status == "ready"
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest app/tests/test_generate_songformer_annotation_blocks.py -q
```

- [ ] **Step 3: Implement runtime client and CLI**

Use an OS file lock in the work directory so only one GPU job runs at once. Validate runner output by resolved audio path and complete audio hash. The CLI supports `--manifest`, repeatable `--track-id`, `--dry-run`, `--force`, and `--stop-on-error`. It processes manifest tracks sequentially and never opens `BAR_ANNOTATION_DIR` for writing.

- [ ] **Step 4: Add non-fatal future-upload hooks**

Call `try_generate_songformer_sections(song)` only after beat/downbeat analysis is persisted and only when `songformer_enabled=true`. A failure is logged but cannot change upload/stem completion.

- [ ] **Step 5: Verify and commit**

```bash
python3 -m pytest app/tests/test_generate_songformer_annotation_blocks.py app/tests/test_presence_generation_hook.py app/tests/test_bar_annotation_service.py -q
git add app/modules/bar_annotations/songformer_sections.py scripts/generate_songformer_annotation_blocks.py app/tests/test_generate_songformer_annotation_blocks.py app/worker/jobs.py app/modules/library/background_tasks.py
git commit -m "feat(songformer): generate shared annotation sections"
```

### Task 8: Add reproducible Jetson deployment assets

**Files:**
- Create: `deploy/songformer/install-jetson.sh`
- Create: `deploy/songformer/harbeat-songformer.conf.example`
- Create: `deploy/songformer/verify-runtime.sh`
- Create: `deploy/songformer/README.md`
- Create: `docs/third-party/SongFormer-MuQ-NOTICE.md`

- [ ] **Step 1: Implement safe setup**

The installer validates explicit target paths, refuses broad targets, clones the official SongFormer repository at a recorded immutable commit, initializes submodules, runs the official checkpoint fetcher, verifies upstream MD5 values, downloads `OpenMuQ/MuQ-MuLan-large`, and builds an isolated dependency overlay that cannot replace the working Jetson CUDA PyTorch wheel. It imports `torch`, `muq`, `safetensors`, `ema_pytorch`, and `transformers` before reporting success.

- [ ] **Step 2: Add the service template**

```ini
[Service]
Environment="SONGFORMER_ENABLED=true"
Environment="SONGFORMER_COMMAND=/opt/harbeat/runtime/songformer-python /opt/harbeat/current/experiments/run_songformer_isolated.py {audio} --out-dir {output_dir} --source-root /opt/harbeat/models/SongFormer --muq-model /opt/harbeat/models/MuQ-MuLan-large --device cuda --precision float32"
Environment="SONGFORMER_SECTION_DIR=/data/harbeat/songformer-sections"
Environment="SONGFORMER_WORK_DIR=/mnt/nas/harbeat/cache/songformer-analysis"
Environment="SONGFORMER_TIMEOUT_SEC=1800"
Environment="SECTION_RELABELER_ENABLED=false"
```

- [ ] **Step 3: Document third-party scope**

Record official upstream URLs, pinned revisions, weight hashes, and attribution. Note that official MuQ weights are CC-BY-NC 4.0 and this deployment is restricted to the research/annotation Pilot, not represented as cleared commercial product inference.

- [ ] **Step 4: Verify and commit**

```bash
bash -n deploy/songformer/install-jetson.sh
bash -n deploy/songformer/verify-runtime.sh
grep -R "SECTION_RELABELER_ENABLED=false" deploy/songformer
git add deploy/songformer docs/third-party/SongFormer-MuQ-NOTICE.md
git commit -m "ops(songformer): add Jetson runtime deployment"
```

### Task 9: Run full local verification

- [ ] **Step 1: Backend suite**

```bash
python3 -m pytest \
  tests/test_songformer_runtime_support.py \
  app/tests/test_songformer_section_store.py \
  app/tests/test_songformer_section_blocks.py \
  app/tests/test_generate_songformer_annotation_blocks.py \
  app/tests/test_bar_annotation_service.py \
  app/tests/test_bar_annotation_router.py \
  app/tests/test_bar_annotation_store.py \
  app/tests/test_bar_annotation_pilot.py \
  app/tests/test_bar_annotation_public_datasets.py -q
```

Expected: all pass.

- [ ] **Step 2: Frontend suite**

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

Expected: tests and production build pass.

- [ ] **Step 3: Diff gates**

```bash
git diff --check
git status --short
```

Verify no `section_relabeler.py`, classifier weight, training script, or unrelated dirty file was committed.

### Task 10: Deploy, smoke-test, and backfill Jetson

**Remote paths:**
- Release: `/opt/harbeat/releases/songformer-blocks-<commit>`
- Models: `/opt/harbeat/models/SongFormer`, `/opt/harbeat/models/MuQ-MuLan-large`
- Cache: `/mnt/nas/harbeat/cache/songformer-analysis`
- Sidecars: `/data/harbeat/songformer-sections`
- Override: `/etc/systemd/system/harbeat-api.service.d/songformer.conf`
- Protected: `/data/harbeat/bar-annotations`

- [ ] **Step 1: Record pre-deploy state**

Capture service status, release, disk/RAM, CUDA PyTorch, Pilot manifest hash, and a hash/listing of the protected annotation directory without printing credentials.

- [ ] **Step 2: Install and verify models**

Run setup as `mark`, using sudo only for deployment-owned paths. Abort if fewer than 8 GiB remain locally. Verify official checkpoints and CUDA imports.

- [ ] **Step 3: Publish a versioned release**

Copy only tracked files from the verified commit, install the frontend build, preserve existing environment and persistent paths, add `songformer.conf` with `SECTION_RELABELER_ENABLED=false`, run import checks, then switch the service.

- [ ] **Step 4: Smoke-test two songs**

Process one short and one full Pilot song. Validate sidecars, monotonic boundaries, complete Bar coverage, model/cache fingerprints, safe GPU memory, cache reuse, and disabled residual state.

- [ ] **Step 5: Live regression**

Verify root site, login, registration, `/annotate`, Pilot API, Range audio, user isolation, save conflicts, full playback past the selected block, and range-preview stop.

- [ ] **Step 6: Protect annotations**

Recompute the protected annotation-directory hash before any human save. Expected: byte-for-byte unchanged.

- [ ] **Step 7: Backfill remaining Pilot tracks**

Run sequentially without `--force`. Report ready, needs-review, and failed counts. Do not fabricate blocks for failures.

- [ ] **Step 8: Record deployment**

Commit a credential-free operations note containing release commit, source/model revisions, hashes, tested tracks, results, and rollback instructions.

## Plan self-review

- Spec coverage: runtime, Bar snapping, block-first workflow, local overrides, playback modes, disabled classifier interface, fail-closed behavior, deployment, rollback, and data preservation all have tasks.
- Placeholder scan: every implementation step names its concrete behavior, command, and expected result.
- Type consistency: backend/frontend use `SectionAnnotationBlock`, half-open Bar ranges, `songformer_bar_snap_v1`, and identical disabled relabeler fields.
- Scope boundary: no residual classifier is deployed and no existing annotation or DJ `phrase_map` is migrated.
