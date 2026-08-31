# SongFormer Label Contract Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve SongFormer's boundary quality and full label evidence while separating model label candidates from HarBeat's mix-oriented roles, keeping existing API consumers compatible.

**Architecture:** Add one pure section-contract module at the library boundary and one pure runtime-support module beside the isolated SongFormer runner. The runner emits raw eight-class evidence and a reproducible model/cache fingerprint; the library module canonicalizes that evidence into the public segment contract. The canonical bar grid is generated only from beat/downbeat timing and never from a semantic section label.

**Tech Stack:** Python 3, NumPy, PyTorch, SQLAlchemy JSON, Pydantic, pytest

---

## Task 1: Define the canonical section label contract

**Files:**

- Create: `app/modules/library/section_contract.py`
- Create: `tests/test_section_label_contract.py`

- [ ] **Step 1: Write failing contract tests**

Cover these public behaviors:

```python
def test_songformer_inst_is_preserved_and_canonicalized():
    segment = enrich_section_segment(
        {
            "start": 16.0,
            "end": 32.0,
            "label": "inst",
            "label_probabilities": {"intro": 0.05, "inst": 0.85, "outro": 0.10},
        },
        source="songformer",
    )
    assert segment["songformer_label"] == "inst"
    assert segment["structure_label_candidate"] == "instrumental"
    assert segment["structure_label_probabilities"]["instrumental"] == 0.85
    assert segment["mix_roles"] == ["instrumental_focus"]
    assert segment["label"] == "instrumental"


def test_pre_chorus_exposes_transition_and_buildup_candidates():
    segment = enrich_section_segment(
        {"start": 32.0, "end": 40.0, "label": "pre-chorus"},
        source="songformer",
    )
    assert segment["structure_label_candidate"] == "pre-chorus"
    assert segment["mix_roles"] == ["transition", "buildup"]
    assert segment["mix_role_scores"] == {"transition": 1.0, "buildup": 0.7}


def test_fallback_contract_marks_missing_evidence():
    segment = enrich_section_segment(
        {"start": 0.0, "end": 8.0, "label": "intro"},
        source="all_in_one",
    )
    assert segment["structure_label_probabilities"] == {}
    assert segment["structure_label_confidence"] is None
    assert segment["structure_label_margin"] is None
    assert segment["label_evidence_status"] == "missing"
```

- [ ] **Step 2: Run the new test and confirm RED**

Run:

```bash
python3 -m pytest tests/test_section_label_contract.py -q
```

Expected: import failure because `section_contract.py` does not exist.

- [ ] **Step 3: Implement the pure contract module**

The module must expose:

```python
LABEL_CONTRACT_VERSION = "songformer_label_contract_v2"


def canonical_structure_label(raw_label: object) -> str:
    normalized = str(raw_label or "unknown").strip().lower()
    return {"inst": "instrumental"}.get(normalized, normalized)


def enrich_section_segment(item: Mapping[str, object], *, source: str) -> dict[str, object]:
    # Preserve the raw SongFormer label, canonicalize public structure labels,
    # normalize the probability distribution, calculate top-1 confidence and
    # top-1/top-2 margin, and derive deterministic mix-role candidates.
    raw_label = str(item.get("label") or "unknown").strip().lower()
    result = dict(item)
    result["structure_label_candidate"] = canonical_structure_label(raw_label)
    return result
```

Rules are fixed by the approved design:

- `inst` becomes public `instrumental`, while raw `songformer_label` remains `inst`.
- `pre-chorus` stays a structure label and produces `transition` and `buildup` mix-role candidates.
- Other SongFormer labels retain their normalized names and get no invented mix role.
- The legacy `label` field aliases `structure_label_candidate`.
- Empty evidence is represented by `{}`, `None`, `None`, and `label_evidence_status="missing"`.
- Malformed/non-finite/negative probabilities are ignored; valid entries are renormalized.

- [ ] **Step 4: Run the contract test and confirm GREEN**

Run:

```bash
python3 -m pytest tests/test_section_label_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/library/section_contract.py tests/test_section_label_contract.py
git commit -m "feat(analysis): define section label contract"
```

## Task 2: Preserve SongFormer probability evidence and fingerprint runtime inputs

**Files:**

- Create: `experiments/songformer_runtime_support.py`
- Modify: `experiments/run_songformer_isolated.py`
- Create: `tests/test_songformer_runtime_support.py`

- [ ] **Step 1: Write failing runtime-support tests**

Tests must verify:

1. Softmax evidence is aggregated inside each final post-processed segment.
2. Output contains all eight allowed label names in deterministic order.
3. The returned top confidence and margin match the aggregate distribution.
4. Cache namespace changes when runner version, contract version, checkpoint hash, source revision, dataset ID, sample rate, layer, precision, or frame rate changes.
5. File hashing is reused only when resolved path, file size, and nanosecond mtime match.

Representative test:

```python
def test_aggregate_segment_label_evidence_keeps_all_allowed_classes():
    logits = np.array([[4.0, 1.0, 0.0], [3.0, 2.0, 0.0], [0.0, 4.0, 1.0]])
    evidence = aggregate_segment_label_evidence(
        logits,
        segments=[{"start": 0.0, "end": 2.0, "label": "intro"}],
        frame_rate=1.0,
        allowed_label_ids=[0, 1, 2],
        id_to_label={0: "intro", 1: "verse", 2: "chorus"},
    )
    assert list(evidence[0]["label_probabilities"]) == ["intro", "verse", "chorus"]
    assert sum(evidence[0]["label_probabilities"].values()) == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
python3 -m pytest tests/test_songformer_runtime_support.py -q
```

Expected: import failure because the support module does not exist.

- [ ] **Step 3: Implement runtime support without importing SongFormer**

Add pure helpers for:

- stable NumPy softmax and time-to-frame clipping;
- per-segment mean probability aggregation over the final rule-postprocessed boundaries;
- SHA-256 checkpoint hashing with a JSON path/size/mtime manifest;
- SongFormer source revision discovery;
- deterministic fingerprint object and namespace digest.

The fingerprint must contain:

```python
{
    "runner_version": "songformer_isolated_v2",
    "label_contract_version": "songformer_label_contract_v2",
    "songformer_source_revision": source_revision,
    "songformer_checkpoint_sha256": songformer_checkpoint_sha256,
    "musicfm_checkpoint_sha256": musicfm_checkpoint_sha256,
    "musicfm_stats_sha256": musicfm_stats_sha256,
    "muq_model_sha256": muq_model_sha256,
    "dataset_id": "harmonixset",
    "sample_rate": 24000,
    "encoder_layer": 10,
    "precision": "float32",
    "frame_rate": 8.333,
}
```

- [ ] **Step 4: Integrate support into the isolated runner**

After official SongFormer post-processing determines final boundaries, attach evidence to every final segment:

```python
segments = attach_segment_label_evidence(
    segments,
    function_logits=function_logits,
    frame_rate=FRAME_RATE,
    allowed_label_ids=allowed_label_ids,
    id_to_label=ID_TO_LABEL,
)
```

Store encoder tensors below a namespace-specific directory and key completed jobs by both audio fingerprint and namespace. Extend the runner manifest with the full fingerprint, namespace, and contract version. Missing optional checkpoint paths must have explicit stable values such as `"not_applicable"`; they must never silently reuse a different namespace.

- [ ] **Step 5: Run runtime tests and syntax check**

Run:

```bash
python3 -m pytest tests/test_songformer_runtime_support.py -q
python3 -m py_compile experiments/songformer_runtime_support.py experiments/run_songformer_isolated.py
```

Expected: all tests pass and compilation succeeds.

- [ ] **Step 6: Commit**

```bash
git add experiments/songformer_runtime_support.py experiments/run_songformer_isolated.py tests/test_songformer_runtime_support.py
git commit -m "feat(songformer): preserve label evidence and fingerprint cache"
```

## Task 3: Propagate the contract through analysis, persistence, and API schemas

**Files:**

- Modify: `app/modules/library/analysis.py`
- Modify: `app/modules/library/background_tasks.py`
- Modify: `app/modules/library/schemas.py`
- Modify: `tests/test_songformer_sections_integration.py`
- Modify: `tests/test_all_in_one_sections.py`
- Modify: `app/tests/test_extended_analysis.py`
- Create or modify: `tests/test_library_background_section_contract.py`

- [ ] **Step 1: Add failing integration assertions**

Verify SongFormer output retains:

```python
assert segment["boundary_source"] == "songformer"
assert segment["songformer_label"] == "inst"
assert segment["structure_label_candidate"] == "instrumental"
assert len(segment["structure_label_probabilities"]) == 8
assert segment["label"] == "instrumental"
assert result["section_analysis"]["authoritative_boundary_model"] == "songformer"
assert result["section_analysis"]["structure_label_source"] == "songformer_candidate"
assert result["section_analysis"]["label_contract_version"] == "songformer_label_contract_v2"
```

Verify the background task reconstructs `cue_points` without dropping the candidate, evidence, roles, confidence, or margin. Verify Pydantic accepts and serializes those optional fields while still accepting old cue objects.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
python3 -m pytest \
  tests/test_songformer_sections_integration.py \
  tests/test_all_in_one_sections.py \
  tests/test_library_background_section_contract.py \
  app/tests/test_extended_analysis.py -q
```

Expected: new contract assertions fail.

- [ ] **Step 3: Enrich segments exactly once at the analysis boundary**

Update `_normalize_functional_segments` to call `enrich_section_segment`. Do not recalculate probabilities downstream. Update cue and phrase-map conversion functions to retain every contract field. Bump:

```python
CORE_ANALYSIS_VERSION = "songformer_label_contract_v2"
```

Add these `section_analysis` fields:

```python
{
    "authoritative_boundary_model": "songformer",
    "structure_label_source": "songformer_candidate",
    "label_contract_version": LABEL_CONTRACT_VERSION,
    "intro_end_candidate": intro_end_candidate,
    "semantic_intro_applied_to_bar_grid": False,
    "runtime_fingerprint": songformer_manifest.get("runtime_fingerprint"),
    "cache_namespace": songformer_manifest.get("cache_namespace"),
}
```

Fallback segments use the same shape with empty evidence and source-specific metadata.

- [ ] **Step 4: Extend persistence and API schemas compatibly**

Add optional fields to `LibraryCuePoint`; keep all existing required fields and names unchanged. When rebuilding cue points in `background_tasks.py`, copy the complete contract rather than manually selecting only the legacy keys.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/library/analysis.py app/modules/library/background_tasks.py app/modules/library/schemas.py tests app/tests/test_extended_analysis.py
git commit -m "feat(analysis): expose SongFormer candidate labels and mix roles"
```

## Task 4: Decouple the canonical bar grid from semantic Intro labels

**Files:**

- Modify: `app/modules/library/analysis.py`
- Modify: `app/tests/test_extended_analysis.py`
- Modify: `tests/test_songformer_sections_integration.py`

- [ ] **Step 1: Write a failing regression test**

Use raw downbeats beginning at zero and an Intro candidate ending later:

```python
def test_intro_candidate_does_not_remove_base_downbeats():
    result = build_canonical_bar_grid(
        raw_downbeats=[0.0, 2.0, 4.0, 6.0, 8.0],
        beat_times=[0.0, 0.5, 1.0, 1.5, 2.0],
        beats_per_bar=4,
    )
    assert result[0] == 0.0
```

The integration result must expose the semantic `intro_end_candidate` separately while keeping the first valid timing downbeat.

- [ ] **Step 2: Run the regression and confirm RED**

Run:

```bash
python3 -m pytest app/tests/test_extended_analysis.py tests/test_songformer_sections_integration.py -q
```

Expected: the current intro-aware grid trims early downbeats.

- [ ] **Step 3: Replace intro-dependent grid construction**

Refactor `_start_bar_grid_after_intro` into `_build_canonical_bar_grid`. The new function may repair or synthesize a regular grid from raw downbeats and beats, but it must not accept or inspect functional segments. `_functional_intro_end` remains available only to report `intro_end_candidate`.

- [ ] **Step 4: Run tests and confirm GREEN**

Run the Step 2 command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/library/analysis.py app/tests/test_extended_analysis.py tests/test_songformer_sections_integration.py
git commit -m "fix(analysis): keep intro semantics out of the bar grid"
```

## Task 5: Teach downstream mix consumers to use the new layers

**Files:**

- Modify: `app/modules/dj_set/section_energy.py`
- Modify: `app/modules/dj_control/spotify_mix/section_features.py`
- Modify or create: `tests/test_section_energy.py`
- Modify or create: `tests/test_section_features.py`

- [ ] **Step 1: Add failing downstream tests**

Verify:

- `instrumental` and legacy `inst` produce the same instrumental density behavior.
- `pre-chorus` plus `mix_roles=["transition", "buildup"]` is treated as a transition/build candidate.
- consumers prefer `mix_roles` for mix decisions and use `structure_label_candidate` for semantic decisions;
- old objects containing only `label` remain valid.

- [ ] **Step 2: Run downstream tests and confirm RED**

Run:

```bash
python3 -m pytest tests/test_section_energy.py tests/test_section_features.py -q
```

If a named file does not yet exist, create the focused test file at that path before running.

- [ ] **Step 3: Implement layered consumption**

Use this lookup order:

```python
structure_label = section.get("structure_label_candidate") or section.get("label") or "unknown"
mix_roles = section.get("mix_roles") or []
```

Do not convert `pre-chorus` directly to `drop` or `breakdown`. Keep `inst` as a compatibility alias only.

- [ ] **Step 4: Run downstream tests and confirm GREEN**

Run the Step 2 command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/dj_set/section_energy.py app/modules/dj_control/spotify_mix/section_features.py tests
git commit -m "feat(mix): consume section candidates and mix roles"
```

## Task 6: Full regression, contract documentation, review, and delivery

**Files:**

- Modify: `docs/superpowers/specs/2026-08-31-songformer-label-contract-design.md` only if implementation details differ without changing approved behavior
- Modify relevant existing developer/API documentation discovered by `rg "phrase_map|section_analysis|cue_points" docs`

- [ ] **Step 1: Run all focused analysis tests**

```bash
python3 -m pytest \
  tests/test_section_label_contract.py \
  tests/test_songformer_runtime_support.py \
  tests/test_songformer_sections_integration.py \
  tests/test_all_in_one_sections.py \
  app/tests/test_extended_analysis.py -q
```

Expected: all pass.

- [ ] **Step 2: Run the repository test suite**

```bash
python3 -m pytest -q
```

Expected: all runnable tests pass; environment-only skips are reported explicitly.

- [ ] **Step 3: Perform an isolated-runner smoke check**

If local SongFormer and checkpoints are present, run one short fixture and inspect the JSON for eight probabilities, candidate fields, full base downbeats, and fingerprints. If assets are absent, run import/compile tests and record the missing asset as an environment limitation rather than fabricating output.

- [ ] **Step 4: Review the complete diff**

```bash
git diff 15c3c20...HEAD --check
git diff 15c3c20...HEAD --stat
```

Use the required code-review workflow. Fix all Critical and Important findings, rerun affected tests, and request a re-review when fixes are material.

- [ ] **Step 5: Finalize documentation and commit remaining changes**

```bash
git add docs app experiments tests
git commit -m "docs(analysis): document SongFormer label evidence contract"
```

Skip this commit if there are no remaining changes.

- [ ] **Step 6: Push the implementation branch**

```bash
git push -u origin codex/songformer-label-contract-v1
```

Report the remote branch, final commit SHA, test results, any environment-only skipped checks, and the exact contract consumers should adopt.
