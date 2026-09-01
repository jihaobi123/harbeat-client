# Jetson EDMFormer Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add EDMFormer as a Jetson Shadow label model that reuses the installed MuQ and MusicFM assets, keeps SongFormer boundaries authoritative, and publishes complete EDM function probabilities for human review.

**Architecture:** Run EDMFormer in a separate dependency overlay and work directory, sequentially loading MuQ, MusicFM, and EDMFormer so it does not compete with SongFormer for GPU memory. Preserve EDMFormer's own boundaries as comparison evidence, but aggregate label probabilities inside existing SongFormer-to-Bar section blocks. Store results in a distinct `harbeat.edm_structure_analysis@0.1.0` sidecar.

**Tech Stack:** Python 3.10, Jetson NVIDIA PyTorch 2.4 CUDA, EDM-98/EDMFormer, MuQ, MusicFM, Pydantic v2, JSON Schema, FastAPI, React/Vitest, pytest, systemd.

---

## Fixed deployment decisions

- Reuse `/opt/harbeat/models/MuQ-large-msd-iter` and the verified MusicFM checkpoint already installed for SongFormer.
- Never run the upstream `install_inference_deps.sh` on the production Python environment because it performs unconstrained dependency installation.
- Install EDM-98 source with `--no-deps` into an isolated overlay and verify exact source and checkpoint hashes.
- EDMFormer has `deployment_status="shadow"`; Planner, RK3588, and automatic mix decisions do not consume it.
- Register EDMFormer with `harbeat.model_manifest@1.1.0` from the Stage 5 plan so `shadow` is a valid registry state; do not modify the existing V1 manifest contract.
- `canonical_boundary_source` remains `songformer_bar_snap_v1`.
- Preserve all six raw probabilities: `intro`, `buildup`, `drop`, `breakdown`, `outro`, and `silence`.
- Do not deploy `ExpandedStructureHead` until a trained and reviewed checkpoint exists. Reserve its input/output contract now.

## File map

- Create `schemas/music_analysis/edm_structure_analysis_v0_1.schema.json`: Shadow output contract.
- Create `app/modules/edm_structure/schemas.py`: strict runtime models and disabled fusion state.
- Create `app/modules/edm_structure/store.py`: atomic shared sidecar storage.
- Create `app/modules/edm_structure/alignment.py`: aggregate EDMFormer probabilities inside SongFormer Bar blocks.
- Create `app/modules/edm_structure/runner.py`: isolated EDMFormer command runner.
- Create `experiments/run_edmformer_isolated.py`: low-memory sequential inference adapter.
- Create `scripts/generate_edm_structure_analysis.py`: canary and Pilot CLI.
- Create `deploy/edmformer/*`: pinned installer, wrapper, verification, systemd configuration.
- Modify `app/shared/config.py`: disabled-by-default EDMFormer settings.
- Modify `app/modules/bar_annotations/router.py` and `web/src/pages/AnnotationWorkbench.tsx`: read-only candidate display.

### Task 1: Define the EDM structure sidecar and future fusion interface

**Files:**
- Create: `schemas/music_analysis/edm_structure_analysis_v0_1.schema.json`
- Create: `app/modules/edm_structure/schemas.py`
- Test: `app/tests/test_edm_structure_schema.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_ready_segment_keeps_all_six_probabilities():
    segment = EdmSegmentCandidate.model_validate(candidate_payload())
    assert set(segment.edmformer_label_probabilities) == {
        "intro", "buildup", "drop", "breakdown", "outro", "silence"
    }


def test_expanded_head_is_explicitly_not_installed():
    state = ExpandedStructureHeadState()
    assert state.enabled is False
    assert state.model_status == "not_installed"
    assert state.input_contract_version == "expanded_structure_input_v1"
```

- [ ] **Step 2: Run and verify failure**

Run: `python3 -m pytest -q app/tests/test_edm_structure_schema.py`

Expected: FAIL because the EDM structure module does not exist.

- [ ] **Step 3: Implement strict contracts**

Require:

```python
class ExpandedStructureHeadState(BaseModel):
    enabled: Literal[False] = False
    model_status: Literal["not_installed"] = "not_installed"
    model_version: Literal[None] = None
    input_contract_version: Literal["expanded_structure_input_v1"] = "expanded_structure_input_v1"
    output_contract_version: Literal["expanded_structure_output_v1"] = "expanded_structure_output_v1"


class EdmSegmentCandidate(BaseModel):
    canonical_section_id: str
    start_bar_index: int
    end_bar_index: int
    start_sec: float
    end_sec: float
    canonical_boundary_source: Literal["songformer_bar_snap_v1"]
    edmformer_label_candidate: EdmLabel
    edmformer_label_probabilities: dict[EdmLabel, float]
    edmformer_boundary_candidates: list[float]
    validation_status: Literal["unreviewed", "reviewed", "rejected"]
```

The document must include audio, SongFormer, MuQ, MusicFM, and EDMFormer hashes plus aggregation version.

- [ ] **Step 4: Run validation and commit**

Run: `python3 -m pytest -q app/tests/test_edm_structure_schema.py && python3 -m jsonschema -i app/tests/fixtures/edm-structure-ready.json schemas/music_analysis/edm_structure_analysis_v0_1.schema.json`

Expected: PASS.

```bash
git add schemas/music_analysis/edm_structure_analysis_v0_1.schema.json app/modules/edm_structure/schemas.py app/tests/test_edm_structure_schema.py app/tests/fixtures/edm-structure-ready.json
git commit -m "feat(structure): define EDMFormer shadow sidecar"
```

### Task 2: Add atomic storage and SongFormer block alignment

**Files:**
- Create: `app/modules/edm_structure/store.py`
- Create: `app/modules/edm_structure/alignment.py`
- Test: `app/tests/test_edm_structure_store.py`
- Test: `app/tests/test_edm_structure_alignment.py`

- [ ] **Step 1: Write failing tests**

```python
def test_alignment_uses_songformer_blocks_without_replacing_boundaries():
    result = align_edm_probabilities(frame_scores(), songformer_blocks())
    assert [(x.start_bar_index, x.end_bar_index) for x in result] == [(0, 4), (4, 12)]
    assert all(x.canonical_boundary_source == "songformer_bar_snap_v1" for x in result)


def test_short_high_probability_frame_is_overlap_weighted():
    segment = align_edm_probabilities(one_short_drop_frame(), one_eight_bar_block())[0]
    assert segment.edmformer_label_candidate != "drop"
```

- [ ] **Step 2: Implement atomic storage**

Use a separate root such as `/data/harbeat/edm-structure-analysis`. Apply the same safe track ID, temporary file, `fsync`, and `os.replace` rules as the SongFormer sidecar store.

- [ ] **Step 3: Implement duration-weighted alignment**

Intersect each EDMFormer frame/window with canonical SongFormer Bar blocks, calculate overlap-weighted mean for each of the six labels, normalize finite probabilities, retain maximum and mean evidence, and keep EDMFormer boundaries only in `edmformer_boundary_candidates`.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_edm_structure_store.py app/tests/test_edm_structure_alignment.py`

Expected: PASS.

```bash
git add app/modules/edm_structure/store.py app/modules/edm_structure/alignment.py app/tests/test_edm_structure_store.py app/tests/test_edm_structure_alignment.py
git commit -m "feat(structure): align EDMFormer labels to SongFormer blocks"
```

### Task 3: Adapt EDM-98 inference to the existing Jetson runtime

**Files:**
- Create: `experiments/run_edmformer_isolated.py`
- Create: `app/modules/edm_structure/runner.py`
- Test: `tests/test_edmformer_runtime.py`
- Test: `app/tests/test_edm_structure_runner.py`

- [ ] **Step 1: Write failing runtime tests**

```python
def test_runtime_fingerprint_contains_every_model_hash():
    fp = build_runtime_fingerprint(runtime_paths())
    assert set(fp["checkpoint_sha256"]) == {"edmformer", "muq", "musicfm", "musicfm_stats"}


def test_failed_edmformer_never_changes_songformer_sidecar(tmp_path):
    before = sha256_file(tmp_path / "songformer-sections" / "t1.json")
    fake_runner(exit_code=1).run(track_id="t1", audio_path="song.wav")
    assert sha256_file(tmp_path / "songformer-sections" / "t1.json") == before
```

- [ ] **Step 2: Implement low-memory inference**

Accept explicit paths for EDMFormer source, config, checkpoint, MuQ root, MusicFM source, MusicFM checkpoint, output directory, and audio. Load and unload embedding models sequentially, cache embeddings under a content-addressed namespace, then run the EDMFormer head. Emit frame/time label probabilities, EDMFormer boundaries, runtime fingerprint, elapsed time, and peak CUDA memory.

The production command must include `--device cuda --precision float16 --low-memory`; it must not start Gradio or hold models resident after a job.

- [ ] **Step 3: Implement the validated command runner**

Use `shlex.split` only for administrator-owned configuration, replace explicit `{audio}` and `{output_dir}` tokens, invoke with `shell=False`, serialize jobs with a lock, and reject a manifest whose resolved audio path or fingerprint does not match the request.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q tests/test_edmformer_runtime.py app/tests/test_edm_structure_runner.py`

Expected: PASS.

```bash
git add experiments/run_edmformer_isolated.py app/modules/edm_structure/runner.py tests/test_edmformer_runtime.py app/tests/test_edm_structure_runner.py
git commit -m "feat(structure): run EDMFormer in Jetson low-memory mode"
```

### Task 4: Generate Pilot sidecars and expose read-only candidates

**Files:**
- Create: `scripts/generate_edm_structure_analysis.py`
- Modify: `app/shared/config.py`
- Modify: `app/modules/bar_annotations/router.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/types/annotation.ts`
- Modify: `web/src/pages/AnnotationWorkbench.tsx`
- Test: `app/tests/test_generate_edm_structure_analysis.py`
- Test: `app/tests/test_bar_annotation_router.py`
- Test: `web/src/pages/AnnotationWorkbench.test.tsx`

- [ ] **Step 1: Add disabled settings**

```python
edmformer_enabled: bool = False
edm_structure_dir: str = "./data/edm-structure-analysis"
edmformer_work_dir: str = "./data/edmformer-cache"
edmformer_command: str = ""
edmformer_timeout_sec: int = 1800
```

- [ ] **Step 2: Implement generation**

Load the validated SongFormer sidecar and canonical timeline first. If either is unavailable, store a failed EDM sidecar with an explicit error and do not invent boundaries. Support `--track-id`, `--all`, `--overwrite`, `--report`, and `--fail-on-failed`.

- [ ] **Step 3: Add authenticated read-only retrieval**

Add `GET /api/v1/bar-annotations/{dataset_version}/{track_id}/edm-structure-candidates`. The endpoint must not write or increment a user's annotation revision.

- [ ] **Step 4: Display six probabilities**

In the current section block panel, show the highest EDM candidate plus all six probabilities, `Shadow 候选`, the model's own boundary comparison, and `ExpandedStructureHead 未安装`. Do not replace the SongFormer block selector.

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_generate_edm_structure_analysis.py app/tests/test_bar_annotation_router.py && npm --prefix web test -- AnnotationWorkbench.test.tsx`

Expected: PASS.

```bash
git add scripts/generate_edm_structure_analysis.py app/shared/config.py app/modules/bar_annotations/router.py web/src/api/client.ts web/src/types/annotation.ts web/src/pages/AnnotationWorkbench.tsx app/tests/test_generate_edm_structure_analysis.py app/tests/test_bar_annotation_router.py web/src/pages/AnnotationWorkbench.test.tsx
git commit -m "feat(web): expose EDMFormer shadow candidates"
```

### Task 5: Add a pinned Jetson installer that reuses existing assets

**Files:**
- Create: `deploy/edmformer/edmformer-python`
- Create: `deploy/edmformer/install-jetson.sh`
- Create: `deploy/edmformer/verify-runtime.sh`
- Create: `deploy/edmformer/harbeat-edmformer.conf.example`
- Create: `deploy/edmformer/README.md`
- Test: `app/tests/test_edmformer_deploy_contract.py`

- [ ] **Step 1: Write failing deployment tests**

```python
def test_installer_reuses_songformer_assets_and_preserves_torch():
    script = INSTALLER.read_text()
    assert "/opt/harbeat/models/MuQ-large-msd-iter" in script
    assert "/opt/harbeat/models/SongFormer/src/SongFormer/ckpts/MusicFM" in script
    assert "--no-deps" in script
    assert "install_inference_deps.sh" not in script


def test_service_keeps_edmformer_shadow():
    config = SERVICE_CONFIG.read_text()
    assert "EDMFORMER_DEPLOYMENT_STATUS=shadow" in config
    assert "EXPANDED_STRUCTURE_HEAD_ENABLED=false" in config
```

- [ ] **Step 2: Implement pinned installation**

Download a pinned EDM-98 source archive into `/opt/harbeat/models/EDM-98`, verify the revision marker, and install it with `--no-deps` into `/opt/harbeat/runtime/edmformer-packages`. Install only missing pure-Python dependencies into that overlay. Do not reinstall torch, torchvision, MuQ, or MusicFM.

Place the EDMFormer checkpoint under `/opt/harbeat/models/EDM-98/data/checkpoints/model.pt`, record its SHA-256, and refuse activation when it is absent or an LFS pointer instead of binary content.

- [ ] **Step 3: Verify compatibility and memory**

Run a ten-second fixture and one complete Pilot song. Verify the six probabilities are finite and normalized, the CUDA device is Jetson Orin, the installed torch remains NVIDIA's build, existing SongFormer verification still passes, peak memory is recorded, and disk free space remains above 8 GB.

- [ ] **Step 4: Run contract tests and commit**

Run: `python3 -m pytest -q app/tests/test_edmformer_deploy_contract.py && bash -n deploy/edmformer/*.sh`

Expected: PASS.

```bash
git add deploy/edmformer app/tests/test_edmformer_deploy_contract.py
git commit -m "ops(structure): add Jetson EDMFormer shadow runtime"
```

### Task 6: Canary, Pilot backfill, production Shadow activation, and rollback record

**Files:**
- Create: `outputs/edmformer-shadow-deployment.json`

- [ ] **Step 1: Capture pre-deployment evidence**

Record current service drop-ins, SongFormer sidecar count and recursive digest, human annotation recursive digest, model disk usage, free disk, and API health.

- [ ] **Step 2: Run two canaries**

Use one short and one long EDM track. Compare EDMFormer boundaries against SongFormer but do not publish a boundary replacement. Reject activation if the process OOMs, produces missing probabilities, or changes existing SongFormer or human sidecars.

- [ ] **Step 3: Backfill the 10-track Pilot sequentially**

Use concurrency `1`, `--low-memory`, and cached embeddings. Record per-stage duration, cache hit, peak memory, segment count, top label distribution, and failures.

- [ ] **Step 4: Activate the read-only Shadow endpoint**

Install the versioned release, validate merged systemd settings, restart the API, and verify public routes. Authenticate to `/annotate`, confirm the SongFormer section remains selected while the six EDM probabilities appear, and confirm no annotation revision is created by viewing candidates.

- [ ] **Step 5: Record results and rollback**

Create `outputs/edmformer-shadow-deployment.json` with all source/checkpoint hashes, reused asset hashes, ten-track results, timing, memory, disk, pre/post data hashes, health status, and rollback steps. Rollback removes only the EDMFormer service drop-in and restores the preceding release; it does not delete model caches or sidecars.

```bash
git add outputs/edmformer-shadow-deployment.json
git commit -m "docs(ops): record EDMFormer shadow deployment"
```

## Acceptance gate

- All six EDM probabilities are preserved for every published segment.
- SongFormer Bar-aligned blocks remain the canonical boundaries.
- EDMFormer's boundary candidates are visible only as comparison evidence.
- Existing SongFormer checkpoint/runtime verification still passes.
- Existing SongFormer and human annotation recursive digests are unchanged.
- Planner and RK3588 do not consume EDMFormer Shadow output.
- ExpandedStructureHead is explicitly disabled with stable interface versions.
- The Pilot report includes false-drop, instrumental-drop, buildup, and breakdown review queues.
