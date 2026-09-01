# Jetson Stage 5 Instrument and Drum Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a reproducible Jetson Shadow pipeline that converts existing Demucs stems into five-class drum events and broad instrument candidates, aligns every result to the canonical Bar timeline, and exposes reviewable candidates without changing `BarFeature v1` or existing human annotations.

**Architecture:** Reuse the current Demucs stems and canonical timeline. Run ADTOF-PyTorch and PANNs in an isolated dependency overlay that imports the Jetson NVIDIA CUDA PyTorch without allowing pip to replace it. Persist shared model candidates in `harbeat.instrument_analysis@0.1.0` sidecars; each user's corrections remain in the existing per-user annotation store.

**Tech Stack:** Python 3.10, NVIDIA Jetson PyTorch 2.4 CUDA, Pydantic v2, JSON Schema 2020-12, ADTOF-PyTorch, PANNs, FastAPI, React/Vitest, pytest, systemd.

---

## Fixed deployment decisions

- Run on the Jetson analysis worker only; never run these models during playback.
- First deployed candidate set is ADTOF-PyTorch plus PANNs. Essentia MTG remains research-only because its published models are CC BY-NC-SA unless a proprietary license is obtained.
- ADTOF receives the existing Demucs `drums` stem. Missing stems produce `unavailable`, never `absent`.
- PANNs receives the full song in overlapping windows and is only a candidate generator. It cannot overwrite human labels or existing stem-presence candidates.
- Do not change `schemas/music_analysis/bar_feature_v1.schema.json`.
- Do not install Separate-and-Detect in this release. Its upstream environment pins x86/CUDA 11.6-era binaries and conflicts with the Jetson CUDA PyTorch ABI.
- Keep both models in Shadow status until the golden-set A/B report and license review pass.

## File map

- Create `schemas/music_analysis/instrument_analysis_v0_1.schema.json`: experimental sidecar contract.
- Create `schemas/music_analysis/model_manifest_v1_1.schema.json`: backward-compatible registry contract adding `research` and `shadow` without changing V1.
- Create `config/instrument-taxonomy-v0.1.0.json`: frozen 14-class and five-drum taxonomy.
- Create `app/modules/instrument_analysis/schemas.py`: strict runtime models matching the JSON Schema.
- Create `app/modules/instrument_analysis/store.py`: atomic shared candidate sidecar store.
- Create `app/modules/instrument_analysis/alignment.py`: map events and window probabilities to Bars and Beats.
- Create `app/modules/instrument_analysis/runner.py`: isolated command runner and manifest validation.
- Create `app/modules/instrument_analysis/service.py`: build and retrieve model candidates without writing user revisions.
- Create `scripts/generate_instrument_analysis.py`: one-track and Pilot backfill CLI.
- Create `deploy/instrument-analysis/*`: pinned Jetson installer, wrapper, verification, and service configuration.
- Modify `app/shared/config.py`: add disabled-by-default runtime paths and switches.
- Modify `app/modules/bar_annotations/router.py`: add authenticated read-only candidate endpoint.
- Modify `web/src/pages/AnnotationWorkbench.tsx`: show drum events and broad instrument candidates for the selected Bar range.

### Task 1: Freeze the taxonomy and sidecar contract

**Files:**
- Create: `config/instrument-taxonomy-v0.1.0.json`
- Create: `schemas/music_analysis/instrument_analysis_v0_1.schema.json`
- Create: `schemas/music_analysis/model_manifest_v1_1.schema.json`
- Create: `app/modules/instrument_analysis/schemas.py`
- Test: `app/tests/test_instrument_analysis_schema.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_ready_sidecar_requires_bar_results_and_provenance():
    payload = ready_payload()
    payload["bars"] = []
    with pytest.raises(ValidationError):
        InstrumentAnalysisDocument.model_validate(payload)


def test_classifier_status_is_shadow_only():
    payload = ready_payload()
    payload["models"]["panns"]["deployment_status"] = "production"
    with pytest.raises(ValidationError):
        InstrumentAnalysisDocument.model_validate(payload)


def test_model_manifest_v1_1_adds_shadow_without_mutating_v1():
    v1 = load_schema("schemas/music_analysis/model_manifest_v1.schema.json")
    v1_1 = load_schema("schemas/music_analysis/model_manifest_v1_1.schema.json")
    assert "shadow" not in v1["properties"]["status"]["enum"]
    assert "shadow" in v1_1["properties"]["status"]["enum"]
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_schema.py`

Expected: FAIL because `app.modules.instrument_analysis.schemas` does not exist.

- [ ] **Step 3: Add the frozen taxonomy**

```json
{
  "schema_name": "harbeat.instrument_taxonomy",
  "schema_version": "0.1.0",
  "instrument_classes": [
    "drums", "percussion", "bass", "acoustic_guitar", "electric_guitar",
    "piano", "electric_piano", "synthesizer", "strings", "brass",
    "woodwind", "organ", "sampler_fx", "voice"
  ],
  "drum_classes": ["kick", "snare", "hihat", "tom", "cymbal"]
}
```

- [ ] **Step 4: Implement strict Pydantic and JSON Schema contracts**

Define `Availability`, `ValidationStatus`, `ModelEvidence`, `DrumEvent`, `DrumSummary`, `InstrumentProbability`, `InstrumentBarAnalysis`, and `InstrumentAnalysisDocument`. Require monotonically increasing Bars, event times within track duration, `deployment_status="shadow"`, SHA-256 checkpoint hashes, `timeline_fingerprint`, and explicit model errors.

The root model must use:

```python
class InstrumentAnalysisDocument(BaseModel):
    schema_name: Literal["harbeat.instrument_analysis"] = "harbeat.instrument_analysis"
    schema_version: Literal["0.1.0"] = "0.1.0"
    track_id: str = Field(pattern=ID_PATTERN)
    status: Literal["ready", "partial", "failed"]
    timeline_fingerprint: str = Field(min_length=64, max_length=64)
    taxonomy_version: Literal["instrument_taxonomy@0.1.0"]
    models: dict[Literal["adtof", "panns"], ModelEvidence]
    bars: list[InstrumentBarAnalysis]
    warnings: list[str] = Field(default_factory=list)
```

Copy the existing model manifest contract into `model_manifest_v1_1.schema.json`, change only `schema_version` to `1.1.0`, and extend `status` to `research`, `shadow`, `candidate`, `staging`, `production`, `retired`, and `rejected`. Keep `model_manifest_v1.schema.json` byte-for-byte unchanged.

- [ ] **Step 5: Validate both implementations**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_schema.py && python3 -m jsonschema -i app/tests/fixtures/instrument-analysis-ready.json schemas/music_analysis/instrument_analysis_v0_1.schema.json`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/instrument-taxonomy-v0.1.0.json schemas/music_analysis/instrument_analysis_v0_1.schema.json schemas/music_analysis/model_manifest_v1_1.schema.json app/modules/instrument_analysis/schemas.py app/tests/test_instrument_analysis_schema.py app/tests/fixtures/instrument-analysis-ready.json
git commit -m "feat(analysis): define instrument analysis sidecar"
```

### Task 2: Add an atomic shared candidate store

**Files:**
- Create: `app/modules/instrument_analysis/store.py`
- Test: `app/tests/test_instrument_analysis_store.py`

- [ ] **Step 1: Write failing path-safety and atomicity tests**

```python
def test_store_rejects_unsafe_track_id(tmp_path):
    with pytest.raises(InstrumentAnalysisInvalid):
        InstrumentAnalysisStore(tmp_path).load("../../etc/passwd")


def test_store_round_trip_does_not_touch_human_annotation_root(tmp_path):
    human = tmp_path / "bar-annotations"
    human.mkdir()
    before = directory_hash(human)
    store = InstrumentAnalysisStore(tmp_path / "instrument-analysis")
    store.save(ready_document())
    assert store.load("track_001") == ready_document()
    assert directory_hash(human) == before
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_store.py`

Expected: FAIL because the store is missing.

- [ ] **Step 3: Implement the store**

Use the same safety pattern as `SongFormerSectionStore`: validate `track_id` with `^[A-Za-z0-9][A-Za-z0-9._:-]*$`, write a temporary file in the destination directory, flush and `fsync`, then publish with `os.replace`. Store only `<track_id>.json` inside the configured candidate directory.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_store.py`

Expected: PASS.

```bash
git add app/modules/instrument_analysis/store.py app/tests/test_instrument_analysis_store.py
git commit -m "feat(analysis): persist shared instrument candidates"
```

### Task 3: Align drum events and model windows to the canonical timeline

**Files:**
- Create: `app/modules/instrument_analysis/alignment.py`
- Test: `app/tests/test_instrument_analysis_alignment.py`

- [ ] **Step 1: Write failing boundary tests**

```python
def test_event_keeps_absolute_time_and_fractional_beat_position():
    event = align_drum_event(raw_event(1.75, "snare"), timeline_4_4())
    assert event.bar_index == 0
    assert event.beat_index_in_bar == 1
    assert event.beat_position == pytest.approx(2.5)
    assert event.time_sec == 1.75


def test_window_aggregation_keeps_mean_max_and_coverage():
    result = aggregate_probability_windows(
        windows=[window(0.0, 2.0, 0.2), window(2.0, 4.0, 0.8)],
        bar=bar(1.0, 3.0),
    )
    assert result.mean_probability == pytest.approx(0.5)
    assert result.max_probability == pytest.approx(0.8)
    assert result.active_coverage == pytest.approx(0.5)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_alignment.py`

Expected: FAIL because the alignment module is missing.

- [ ] **Step 3: Implement overlap-weighted aggregation**

Use `build_canonical_timeline(song)` as the only Bar source. Preserve original event seconds, map to the containing Bar, choose the nearest Beat for `beat_index_in_bar`, and calculate fractional beat position from adjacent Beat times. Aggregate classifier windows by overlap duration rather than center frame.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_alignment.py`

Expected: PASS.

```bash
git add app/modules/instrument_analysis/alignment.py app/tests/test_instrument_analysis_alignment.py
git commit -m "feat(analysis): align drum and instrument evidence to bars"
```

### Task 4: Add isolated ADTOF and PANNs runners

**Files:**
- Create: `app/modules/instrument_analysis/runner.py`
- Create: `experiments/run_instrument_analysis_isolated.py`
- Test: `app/tests/test_instrument_analysis_runner.py`
- Test: `tests/test_instrument_analysis_runtime.py`

- [ ] **Step 1: Write failing runner-contract tests**

```python
def test_runner_requires_drums_stem_for_adtof(tmp_path):
    result = fake_runner().run(track_id="t1", audio_path=tmp_path / "song.wav", stems={})
    assert result.models["adtof"].availability == "unavailable"
    assert "DRUMS_STEM_MISSING" in result.warnings


def test_runner_rejects_manifest_for_another_audio(tmp_path):
    write_runtime_manifest(tmp_path, audio_path="/other/song.wav")
    with pytest.raises(InstrumentRuntimeError):
        runner(tmp_path)._read_result(Path("/music/song.wav"))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_runner.py tests/test_instrument_analysis_runtime.py`

Expected: FAIL because the runner is missing.

- [ ] **Step 3: Implement the isolated process**

The CLI must accept:

```text
--audio PATH
--drums-stem PATH
--output-dir PATH
--adtof-weights PATH
--panns-weights PATH
--device cuda
--precision float16
```

Load models sequentially: ADTOF, publish raw five-class events to an in-memory result, release it with `del model; torch.cuda.empty_cache()`, then load PANNs and run overlapping 10-second windows with 5-second hop. Save one manifest containing audio fingerprint, checkpoint hashes, runtime fingerprint, raw events, raw window scores, elapsed seconds, peak allocated CUDA bytes, and errors per model.

Run subprocesses with an argument list, `shell=False`, a filesystem lock, bounded timeout, and a dedicated work directory. A model failure must produce `partial` output without erasing results from the other model.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_runner.py tests/test_instrument_analysis_runtime.py`

Expected: PASS.

```bash
git add app/modules/instrument_analysis/runner.py experiments/run_instrument_analysis_isolated.py app/tests/test_instrument_analysis_runner.py tests/test_instrument_analysis_runtime.py
git commit -m "feat(analysis): run ADTOF and PANNs in isolation"
```

### Task 5: Build sidecars and a Pilot backfill command

**Files:**
- Create: `app/modules/instrument_analysis/service.py`
- Create: `scripts/generate_instrument_analysis.py`
- Modify: `app/shared/config.py`
- Test: `app/tests/test_generate_instrument_analysis.py`
- Test: `app/tests/test_settings.py`

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_backfill_skips_matching_cache_without_overwrite(tmp_path):
    first = run_pilot(tmp_path, overwrite=False)
    second = run_pilot(tmp_path, overwrite=False)
    assert first["generated"] == 1
    assert second["cached"] == 1
    assert fake_runtime.calls == 1


def test_output_never_uses_bar_annotation_directory(settings):
    assert Path(settings.instrument_analysis_dir).resolve() != Path(settings.bar_annotation_dir).resolve()
```

- [ ] **Step 2: Add disabled-by-default settings**

```python
instrument_analysis_enabled: bool = False
instrument_analysis_dir: str = "./data/instrument-analysis"
instrument_analysis_work_dir: str = "./data/instrument-analysis-cache"
instrument_analysis_command: str = ""
instrument_analysis_timeout_sec: int = 1800
```

- [ ] **Step 3: Implement one-track and Pilot generation**

Require the current Pilot manifest, resolve the existing song and stems from the database, build the canonical timeline, call the runner, aggregate evidence, validate the document, and atomically save it. Support `--track-id` repeated, `--all`, `--overwrite`, `--report`, and `--fail-on-partial`.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_generate_instrument_analysis.py app/tests/test_settings.py`

Expected: PASS.

```bash
git add app/modules/instrument_analysis/service.py scripts/generate_instrument_analysis.py app/shared/config.py app/tests/test_generate_instrument_analysis.py app/tests/test_settings.py
git commit -m "feat(analysis): generate instrument Pilot sidecars"
```

### Task 6: Expose read-only candidates in the annotation site

**Files:**
- Modify: `app/modules/bar_annotations/router.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/types/annotation.ts`
- Modify: `web/src/pages/AnnotationWorkbench.tsx`
- Test: `app/tests/test_bar_annotation_router.py`
- Test: `web/src/pages/AnnotationWorkbench.test.tsx`

- [ ] **Step 1: Write failing API and UI tests**

```python
def test_instrument_candidates_require_auth_and_do_not_create_revision(client, authenticated_headers):
    response = client.get("/api/v1/bar-annotations/ds/t1/instrument-candidates", headers=authenticated_headers)
    assert response.status_code == 200
    assert response.json()["schema_name"] == "harbeat.instrument_analysis"
    assert annotation_file_count() == 0
```

```tsx
it('shows drum events and model candidates as unreviewed evidence', async () => {
  render(<AnnotationWorkbench onDirtyChange={() => undefined} />)
  expect(await screen.findByText('五类鼓事件')).toBeInTheDocument()
  expect(screen.getByText('模型候选，不是人工真值')).toBeInTheDocument()
})
```

- [ ] **Step 2: Implement a read-only endpoint**

Return `404` for a track outside the Pilot, `204` when no sidecar exists, and a validated sidecar for authenticated users. Do not place model candidates inside the save request and do not increment an annotation revision.

- [ ] **Step 3: Add the Bar-range candidate panel**

For the current selected Bars show five drum counts, clickable event timestamps, the 14 mapped candidate classes, confidence, and warnings. The UI label must say `模型候选，不是人工真值`. Reuse the existing audio player to seek to event time; do not add another audio element.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest -q app/tests/test_bar_annotation_router.py && npm --prefix web test -- AnnotationWorkbench.test.tsx`

Expected: PASS.

```bash
git add app/modules/bar_annotations/router.py web/src/api/client.ts web/src/types/annotation.ts web/src/pages/AnnotationWorkbench.tsx app/tests/test_bar_annotation_router.py web/src/pages/AnnotationWorkbench.test.tsx
git commit -m "feat(web): review instrument and drum candidates"
```

### Task 7: Build the Jetson installer without replacing CUDA PyTorch

**Files:**
- Create: `deploy/instrument-analysis/instrument-analysis-python`
- Create: `deploy/instrument-analysis/install-jetson.sh`
- Create: `deploy/instrument-analysis/verify-runtime.sh`
- Create: `deploy/instrument-analysis/harbeat-instrument-analysis.conf.example`
- Create: `deploy/instrument-analysis/README.md`
- Test: `app/tests/test_instrument_analysis_deploy_contract.py`

- [ ] **Step 1: Write failing deployment-contract tests**

```python
def test_installer_never_resolves_or_replaces_torch():
    script = INSTALLER.read_text()
    assert "--no-deps" in script
    assert "pip install torch" not in script
    assert "torch==" not in script


def test_service_defaults_to_shadow_and_separate_directories():
    config = SERVICE_CONFIG.read_text()
    assert "INSTRUMENT_ANALYSIS_ENABLED=true" in config
    assert "INSTRUMENT_ANALYSIS_DEPLOYMENT_STATUS=shadow" in config
    assert "/data/harbeat/instrument-analysis" in config
```

- [ ] **Step 2: Implement pinned installation**

Install sources into `/opt/harbeat/models/instrument-analysis-src` with revision marker files. Install only pure-Python dependencies into `/opt/harbeat/runtime/instrument-analysis-packages` using `--no-deps`, reuse `/opt/harbeat/current/venv/bin/python`, and prepend the overlay in the wrapper. Download weights into:

```text
/opt/harbeat/models/ADTOF-pytorch/adtof_model.pth
/opt/harbeat/models/PANNs/Cnn14_DecisionLevelMax_mAP=0.385.pth
```

Verify every file against a committed SHA-256 allowlist before activation. The installer must refuse a source directory with no matching revision marker and refuse `/`, `$HOME`, or an empty target.

- [ ] **Step 3: Add runtime verification**

Run CUDA imports, validate the NVIDIA torch build string, load each checkpoint one at a time, transcribe a committed ten-second fixture, and assert the five ADTOF classes and 527 PANNs outputs are finite. Print JSON with CUDA version, device, package versions, checkpoint hashes, runtime seconds, and peak allocated memory.

- [ ] **Step 4: Run contract tests and commit**

Run: `python3 -m pytest -q app/tests/test_instrument_analysis_deploy_contract.py && bash -n deploy/instrument-analysis/*.sh`

Expected: PASS.

```bash
git add deploy/instrument-analysis app/tests/test_instrument_analysis_deploy_contract.py
git commit -m "ops(analysis): add Jetson instrument runtime"
```

### Task 8: Stage, backfill two tracks, then enable the 10-track Pilot

**Files:**
- Modify: `outputs/instrument-analysis-deployment.json`

- [ ] **Step 1: Preserve baseline evidence**

Record recursive SHA-256 digests for `/data/harbeat/bar-annotations`, sidecar counts, current service drop-ins, `df -h /`, and `systemctl status harbeat-api`. Require at least 8 GB free before installation and leave the existing SongFormer runtime untouched.

- [ ] **Step 2: Install and verify the runtime**

Run the versioned release installer and `verify-runtime.sh`. Expected: CUDA available, both checkpoints valid, no generic PyTorch wheel installed, and the existing SongFormer verification still passes.

- [ ] **Step 3: Run two canaries**

Generate GIVEAHOOP and one long track. Reject activation if a stem is shorter than the timeline, event times are outside duration, peak memory causes OOM, or either sidecar fails JSON Schema validation.

- [ ] **Step 4: Backfill the Pilot sequentially**

Run one worker with concurrency `1`. Expected: ten sidecars, per-model timing and memory in the report, model status `shadow`, and zero changes under `/data/harbeat/bar-annotations`.

- [ ] **Step 5: Enable the read-only endpoint and UI**

Install the versioned release, validate merged systemd configuration, restart the API, and verify `/`, `/login`, `/register`, `/annotate`, and `/health` all return `200`. Load an authenticated workspace and confirm candidates appear without creating a revision.

- [ ] **Step 6: Record rollback and commit**

Write `outputs/instrument-analysis-deployment.json` with release, model revisions and hashes, runtime fingerprint, track counts, timing, peak memory, pre/post human annotation hash, public health results, and the exact rollback drop-in backup.

```bash
git add outputs/instrument-analysis-deployment.json
git commit -m "docs(ops): record instrument analysis deployment"
```

## Acceptance gate

- Five ADTOF classes are present with original seconds and fractional Beat positions.
- PANNs probabilities are stored as unreviewed candidates and never overwrite explicit stem evidence.
- Ten Pilot tracks complete without OOM, and each per-model failure degrades to `partial` or `unavailable`.
- Existing SongFormer inference still passes after installation.
- `/data/harbeat/bar-annotations` recursive digest is unchanged.
- Planner and RK3588 do not consume these Shadow results.
- The deployment record identifies all model and preprocessing hashes.
