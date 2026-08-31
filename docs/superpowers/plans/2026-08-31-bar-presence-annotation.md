# Bar Presence Annotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Jetson/Demucs 分离链路上生成 Bar 级 Vocal、Drums、Bass、Melody 出现区间，并提供可追溯的人工纠错页面和 JSONL 导出。

**Architecture:** 后端新增纯函数式 Bar 时间轴适配器和 Presence 候选器，候选与人工修订由文件型 append-only annotation bundle 保存。FastAPI 负责鉴权、生成、读取、复核和导出；现有 Web 管理端增加单曲审核面板。分离任务成功后自动尝试生成候选，时间轴或 Stem 不合格时记录明确状态，不伪造空标签。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、NumPy、SoundFile、librosa、JSON Schema、React 18、TypeScript、Vite、Vitest、HTML Audio/Canvas

---

## 文件结构

新增文件各自只承担一个职责：

- `app/modules/library/bar_timeline.py`：把 downbeat/beat grid 转成统一 Bar 列表。
- `app/modules/library/presence_analysis.py`：从四轨 Stem 计算逐 Bar 特征、概率和候选区间。
- `app/modules/annotations/schemas.py`：API 和 bundle 的 Pydantic 类型。
- `app/modules/annotations/store.py`：原子读写、乐观锁、追加修订和 JSONL 导出。
- `app/modules/annotations/service.py`：把 LibrarySong、候选器和存储层串起来。
- `app/modules/annotations/router.py`：鉴权后的 HTTP 接口。
- `web/src/lib/presenceEditor.ts`：区间编辑纯函数。
- `web/src/components/PresenceAnnotationPanel.tsx`：审核页面。

现有文件只做接线：

- `app/shared/config.py` 增加 annotation 数据目录。
- `app/modules/router.py` 注册 annotation router。
- `app/worker/jobs.py` 和 `app/modules/library/background_tasks.py` 在 Stem 分离后尝试生成候选。
- `app/modules/library/router.py` 的同步分离路径做同样接线。
- `web/src/types/index.ts`、`web/src/api/client.ts` 增加合同。
- `web/src/components/SongDetail.tsx` 挂载审核面板。
- `web/package.json` 增加 Vitest 命令。

## Task 1: Bar 时间轴适配器

**Files:**
- Create: `app/modules/library/bar_timeline.py`
- Create: `app/tests/test_bar_timeline.py`

- [ ] **Step 1: 写 downbeat 优先路径的失败测试**

```python
from app.modules.library.bar_timeline import TimelineError, build_bar_timeline


def test_builds_half_open_bars_from_downbeats():
    timeline = build_bar_timeline(
        downbeats=[0.0, 2.0, 4.0, 6.0],
        beat_points=[i * 0.5 for i in range(16)],
        duration=7.0,
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.9},
        beat_confidence=0.9,
        beat_needs_review=False,
    )
    assert timeline.source == "downbeats"
    assert [(bar.index, bar.start_sec, bar.end_sec, bar.is_partial) for bar in timeline.bars] == [
        (0, 0.0, 2.0, False),
        (1, 2.0, 4.0, False),
        (2, 4.0, 6.0, False),
        (3, 6.0, 7.0, True),
    ]


def test_rejects_timeline_marked_for_review():
    try:
        build_bar_timeline(
            downbeats=[0.0, 2.0], beat_points=[], duration=4.0,
            time_signature={"numerator": 4}, beat_confidence=0.9,
            beat_needs_review=True,
        )
    except TimelineError as exc:
        assert exc.code == "timeline_needs_review"
    else:
        raise AssertionError("expected TimelineError")
```

- [ ] **Step 2: 运行测试，确认缺少模块而失败**

Run: `python -m pytest app/tests/test_bar_timeline.py -q`

Expected: FAIL，错误包含 `No module named 'app.modules.library.bar_timeline'`。

- [ ] **Step 3: 实现 downbeat 路径、beat-grid fallback 和明确错误码**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BarWindow:
    index: int
    start_sec: float
    end_sec: float
    beat_start_index: int
    beat_count: int
    is_partial: bool


@dataclass(frozen=True)
class BarTimeline:
    source: str
    meter_numerator: int
    confidence: float
    bars: tuple[BarWindow, ...]


class TimelineError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_bar_timeline(*, downbeats, beat_points, duration, time_signature,
                       beat_confidence, beat_needs_review) -> BarTimeline:
    if beat_needs_review:
        raise TimelineError("timeline_needs_review", "beat analysis requires review")
    if duration <= 0:
        raise TimelineError("invalid_duration", "song duration must be positive")
    confidence = float(beat_confidence or 0.0)
    if confidence < 0.5:
        raise TimelineError("low_timeline_confidence", "beat confidence is below 0.5")
    meter = int((time_signature or {}).get("numerator") or 4)
    if meter < 1 or meter > 32:
        raise TimelineError("invalid_meter", "meter numerator is outside 1..32")
    clean_beats = sorted({float(point) for point in beat_points if 0 <= float(point) < duration})
    clean_downbeats = sorted({float(point) for point in downbeats if 0 <= float(point) < duration})
    if len(clean_downbeats) >= 2:
        starts = clean_downbeats
        source = "downbeats"
    else:
        meter_confidence = float((time_signature or {}).get("confidence") or 0.0)
        if meter_confidence < 0.7 or len(clean_beats) < meter + 1:
            raise TimelineError("missing_trusted_bar_grid", "no trusted downbeat or beat-grid fallback")
        starts = clean_beats[::meter]
        source = "beat_grid"
    if starts[0] > 0.05:
        starts.insert(0, 0.0)
    boundaries = starts + ([duration] if starts[-1] < duration else [])
    full_lengths = np.diff(starts)
    typical_length = float(np.median(full_lengths)) if len(full_lengths) else duration
    bars = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        beat_start = bisect_left(clean_beats, start - 1e-6)
        beat_end = bisect_left(clean_beats, end - 1e-6)
        beat_count = max(1, beat_end - beat_start)
        bars.append(BarWindow(
            index=index,
            start_sec=round(start, 3),
            end_sec=round(end, 3),
            beat_start_index=beat_start,
            beat_count=beat_count,
            is_partial=(end - start) < typical_length * 0.75,
        ))
    return BarTimeline(source=source, meter_numerator=meter,
                       confidence=confidence, bars=tuple(bars))
```

文件顶部同时导入 `from bisect import bisect_left` 和 `import numpy as np`。

- [ ] **Step 4: 补 beat-grid fallback 和非法输入测试**

```python
def test_falls_back_to_confident_beat_grid():
    timeline = build_bar_timeline(
        downbeats=[], beat_points=[i * 0.5 for i in range(13)], duration=6.5,
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.95},
        beat_confidence=0.92, beat_needs_review=False,
    )
    assert timeline.source == "beat_grid"
    assert [bar.start_sec for bar in timeline.bars] == [0.0, 2.0, 4.0, 6.0]


def test_rejects_untrusted_beat_grid_fallback():
    try:
        build_bar_timeline(
            downbeats=[], beat_points=[0.0, 0.5, 1.0, 1.5, 2.0], duration=3.0,
            time_signature={"numerator": 4, "confidence": 0.4},
            beat_confidence=0.9, beat_needs_review=False,
        )
    except TimelineError as exc:
        assert exc.code == "missing_trusted_bar_grid"
    else:
        raise AssertionError("expected TimelineError")
```

- [ ] **Step 5: 运行测试并提交**

Run: `python -m pytest app/tests/test_bar_timeline.py -q`

Expected: PASS。

```bash
git add app/modules/library/bar_timeline.py app/tests/test_bar_timeline.py
git commit -m "feat: add canonical bar timeline adapter"
```

## Task 2: Bar Presence 候选器

**Files:**
- Create: `app/modules/library/presence_analysis.py`
- Create: `app/tests/test_presence_analysis.py`

- [ ] **Step 1: 写合成 Stem 的失败测试**

```python
def test_detects_vocal_presence_on_bar_boundaries(tmp_path):
    sr = 1000
    bars = make_bars([0.0, 2.0, 4.0, 6.0, 8.0])
    silence = np.zeros(sr * 8, dtype=np.float32)
    vocals = silence.copy()
    t = np.arange(sr * 4) / sr
    vocals[sr * 2:sr * 6] = 0.4 * np.sin(2 * np.pi * 220 * t)
    paths = write_stems(tmp_path, vocals=vocals, drums=silence, bass=silence, other=silence, sr=sr)

    result = analyze_bar_presence(paths, bars)

    assert result["elements"]["vocal"]["availability"] == "available"
    assert [(r["start_bar_index"], r["end_bar_index"]) for r in result["elements"]["vocal"]["candidate_ranges"]] == [(1, 3)]
    assert result["elements"]["vocal"]["bar_probabilities"][0] < 0.1
    assert result["elements"]["vocal"]["bar_probabilities"][1] > 0.8
```

- [ ] **Step 2: 运行测试，确认候选器不存在**

Run: `python -m pytest app/tests/test_presence_analysis.py -q`

Expected: FAIL，错误包含 `cannot import name 'analyze_bar_presence'`。

- [ ] **Step 3: 实现逐 Bar 特征、归一化和迟滞区间**

```python
ELEMENT_TO_STEM = {
    "vocal": "vocals",
    "drums": "drums",
    "bass": "bass",
    "melody": "other",
}

THRESHOLDS = {
    "vocal": {"enter": 0.24, "exit": 0.14},
    "drums": {"enter": 0.20, "exit": 0.12},
    "bass": {"enter": 0.22, "exit": 0.13},
    "melody": {"enter": 0.38, "exit": 0.24},
}


def _rms_dbfs(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
    return 20.0 * np.log10(max(rms, 1e-8))


def _normalize_activity(db_values: list[float]) -> list[float]:
    peak = float(np.percentile(db_values, 95))
    floor = min(peak - 12.0, float(np.percentile(db_values, 10)) + 3.0)
    if peak < -60.0:
        return [0.0 for _ in db_values]
    width = max(6.0, peak - floor)
    return [float(np.clip((value - floor) / width, 0.0, 1.0)) for value in db_values]


def _ranges_from_probabilities(probabilities, enter, exit):
    ranges = []
    start = None
    for index, probability in enumerate(probabilities):
        if start is None and probability >= enter:
            start = index
        elif start is not None and probability < exit:
            confidence = float(np.mean(probabilities[start:index]))
            ranges.append({"start_bar_index": start, "end_bar_index": index,
                           "confidence": round(confidence, 4)})
            start = None
    if start is not None:
        confidence = float(np.mean(probabilities[start:]))
        ranges.append({"start_bar_index": start, "end_bar_index": len(probabilities),
                       "confidence": round(confidence, 4)})
    return ranges
```

`analyze_bar_presence()` 必须校验采样率、时长和文件存在性。Vocal、Drums 和 Bass 使用分离 Stem 的归一化响度，并分别加入覆盖率、瞬态密度或低频占用作为小权重证据。Melody 先对 `other` 做 HPSS，使用 harmonic RMS 和音高覆盖；最终置信度上限为 `0.65`，并设置 `requires_review = true`。

- [ ] **Step 4: 补缺失 Stem、采样率冲突和单 Bar 事件测试**

```python
def test_marks_missing_stem_unavailable(tmp_path):
    paths = write_only_vocals(tmp_path)
    result = analyze_bar_presence(paths, make_bars([0.0, 2.0]))
    assert result["elements"]["bass"]["availability"] == "unavailable"
    assert result["elements"]["bass"]["candidate_ranges"] == []


def test_preserves_single_bar_drum_event(tmp_path):
    paths, bars = one_bar_drum_fixture(tmp_path)
    result = analyze_bar_presence(paths, bars)
    ranges = result["elements"]["drums"]["candidate_ranges"]
    assert [(r["start_bar_index"], r["end_bar_index"]) for r in ranges] == [(2, 3)]


def test_rejects_mismatched_sample_rates(tmp_path):
    paths, bars = mismatched_rate_fixture(tmp_path)
    with pytest.raises(PresenceAnalysisError, match="sample rate"):
        analyze_bar_presence(paths, bars)
```

- [ ] **Step 5: 运行测试并提交**

Run: `python -m pytest app/tests/test_presence_analysis.py -q`

Expected: PASS。

```bash
git add app/modules/library/presence_analysis.py app/tests/test_presence_analysis.py
git commit -m "feat: generate bar-aligned presence candidates"
```

## Task 3: 追加式 Annotation Bundle 存储

**Files:**
- Create: `app/modules/annotations/__init__.py`
- Create: `app/modules/annotations/schemas.py`
- Create: `app/modules/annotations/store.py`
- Modify: `app/shared/config.py`
- Create: `app/tests/test_annotation_store.py`

- [ ] **Step 1: 写创建、修订冲突和原候选保留测试**

```python
def test_review_appends_revision_without_overwriting_candidates(tmp_path):
    store = AnnotationStore(str(tmp_path))
    created = store.create_candidates(user_id=7, bundle=candidate_bundle())
    reviewed = store.save_review(
        user_id=7,
        track_id="track-1",
        expected_revision=created.revision,
        actor_id="user:7",
        elements={"vocal": reviewed_vocal_ranges()},
    )
    assert reviewed.revision == 2
    assert reviewed.candidates.elements["vocal"].candidate_ranges == created.candidates.elements["vocal"].candidate_ranges
    assert len(reviewed.revisions) == 1
    assert reviewed.revisions[0].elements["vocal"].review_state == "reviewed"


def test_rejects_stale_review_revision(tmp_path):
    store = AnnotationStore(str(tmp_path))
    created = store.create_candidates(user_id=7, bundle=candidate_bundle())
    store.save_review(user_id=7, track_id="track-1", expected_revision=1,
                      actor_id="user:7", elements=review_payload())
    with pytest.raises(RevisionConflict):
        store.save_review(user_id=7, track_id="track-1", expected_revision=1,
                          actor_id="user:7", elements=review_payload())
```

- [ ] **Step 2: 运行测试，确认存储模块不存在**

Run: `python -m pytest app/tests/test_annotation_store.py -q`

Expected: FAIL，错误包含 `No module named 'app.modules.annotations'`。

- [ ] **Step 3: 定义 bundle 合同**

```python
class PresenceRange(BaseModel):
    start_bar_index: int = Field(ge=0)
    end_bar_index: int = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_bar_index <= self.start_bar_index:
            raise ValueError("end_bar_index must be greater than start_bar_index")
        return self


class ElementCandidate(BaseModel):
    availability: Literal["available", "unavailable", "invalid"]
    requires_review: bool
    bar_probabilities: list[float]
    candidate_ranges: list[PresenceRange]
    warnings: list[str] = Field(default_factory=list)


class ElementReview(BaseModel):
    review_state: Literal["reviewed", "unknown", "rejected"]
    ranges: list[PresenceRange]


class PresenceAnnotationBundle(BaseModel):
    schema_name: Literal["harbeat.presence_annotation_bundle"]
    schema_version: Literal["1.0.0"]
    dataset_version: str
    track_id: str
    user_id: int
    timeline: TimelineSnapshot
    candidate_source: str
    revision: int
    candidates: CandidateSnapshot
    revisions: list[ReviewRevision]
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: 实现安全路径、原子写入和 JSONL 导出**

`AnnotationStore` 将文件写到 `<annotation_dir>/<user_id>/<safe_track_id>/bar-presence-1.0.0.json`。`track_id` 只接受 `[A-Za-z0-9._:-]+`；写入使用同目录临时文件、`flush()`、`os.fsync()` 和 `os.replace()`。读取时验证 Pydantic 合同。

导出规则：

```python
def export_reviewed_jsonl(bundle: PresenceAnnotationBundle) -> str:
    # Only latest reviewed revisions are exported.
    # Every range becomes one harbeat.annotation_record record.
    # start_sec/end_sec come from bundle.timeline.bars.
    # annotation_status is reviewed; candidate_source remains method version.
```

每条记录使用 `elements.<element>.presence`，`granularity = "bar"`，`value = true`，Bar 区间保持左闭右开。导出后用 `schemas/music_analysis/annotation_record_v1.schema.json` 校验；测试中使用 `jsonschema.Draft202012Validator`。

- [ ] **Step 5: 增加设置并运行测试**

```python
class Settings(BaseSettings):
    annotation_dir: str = "./data/annotations"
```

Run: `python -m pytest app/tests/test_annotation_store.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/modules/annotations app/shared/config.py app/tests/test_annotation_store.py
git commit -m "feat: persist versioned presence annotations"
```

## Task 4: 生成、读取、复核和导出 API

**Files:**
- Create: `app/modules/annotations/service.py`
- Create: `app/modules/annotations/router.py`
- Modify: `app/modules/router.py`
- Create: `app/tests/test_annotation_api.py`

- [ ] **Step 1: 写服务层的所有权和生成测试**

```python
def test_generate_candidates_uses_owned_song(tmp_path):
    song = make_song(user_id=7, downbeats=[0.0, 2.0, 4.0], stems=stem_paths(tmp_path))
    service = PresenceAnnotationService(AnnotationStore(str(tmp_path / "annotations")))
    bundle = service.generate_for_song(song=song, requesting_user_id=7)
    assert bundle.track_id == song.id
    assert bundle.timeline.source == "downbeats"
    assert bundle.candidate_source == "method:bar_presence_candidate@0.1.0"


def test_generate_candidates_rejects_other_users_song(tmp_path):
    song = make_song(user_id=8, downbeats=[0.0, 2.0], stems=stem_paths(tmp_path))
    service = PresenceAnnotationService(AnnotationStore(str(tmp_path / "annotations")))
    with pytest.raises(AnnotationAccessError):
        service.generate_for_song(song=song, requesting_user_id=7)
```

- [ ] **Step 2: 实现服务层错误映射**

`PresenceAnnotationService.generate_for_song()` 调用 `build_bar_timeline()` 和 `analyze_bar_presence()`。时间轴失败时返回结构化 `AnnotationGenerationError(code, message)`；缺失 Stem 时保留可用元素，四轨全缺失则返回 `stems_unavailable`。再次生成同一版本时，不覆盖已有人工 revisions；候选器版本变化时创建新的 Dataset Version。

- [ ] **Step 3: 写接口函数测试**

```python
def test_review_endpoint_uses_authenticated_user(fake_db, current_user, service):
    payload = PresenceReviewRequest(expected_revision=1, elements=review_elements())
    response = review_presence("track-1", payload, db=fake_db,
                               current_user=current_user, service=service)
    assert response.data.revision == 2
    assert service.last_actor_id == f"user:{current_user.id}"
```

- [ ] **Step 4: 实现五个接口并注册 router**

```text
GET  /api/annotations/songs/{song_id}/presence
POST /api/annotations/songs/{song_id}/presence/generate
PUT  /api/annotations/songs/{song_id}/presence/review
POST /api/annotations/songs/{song_id}/presence/adjudicate
GET  /api/annotations/songs/{song_id}/presence/export
```

所有接口先从数据库读取 `LibrarySong`，再检查 `song.user_id == current_user.id`。导出接口返回 `application/x-ndjson`。修订冲突映射为 HTTP 409，时间轴或 Stem 质量问题映射为 HTTP 422，不存在的 bundle 返回 404。

- [ ] **Step 5: 运行后端测试并提交**

Run: `python -m pytest app/tests/test_bar_timeline.py app/tests/test_presence_analysis.py app/tests/test_annotation_store.py app/tests/test_annotation_api.py -q`

Expected: PASS。

```bash
git add app/modules/annotations app/modules/router.py app/tests/test_annotation_api.py
git commit -m "feat: expose presence annotation api"
```

## Task 5: Stem 分离完成后自动生成候选

**Files:**
- Modify: `app/worker/jobs.py`
- Modify: `app/modules/library/background_tasks.py`
- Modify: `app/modules/library/router.py`
- Create: `app/tests/test_presence_generation_hook.py`

- [ ] **Step 1: 写非致命 hook 测试**

```python
def test_presence_generation_failure_does_not_fail_stem_job(monkeypatch):
    monkeypatch.setattr(jobs, "_run_presence_generation", lambda song: (_ for _ in ()).throw(RuntimeError("bad timeline")))
    result = run_job_with_existing_stems(monkeypatch)
    assert result["ok"] is True
    assert result["presence_candidates"]["status"] == "needs_review"
    assert result["presence_candidates"]["error"] == "bad timeline"
```

- [ ] **Step 2: 实现共用 hook**

```python
def try_generate_presence_candidates(song) -> dict:
    try:
        service = PresenceAnnotationService.from_settings()
        bundle = service.generate_for_song(song=song, requesting_user_id=song.user_id)
        return {"status": "candidate", "revision": bundle.revision}
    except (AnnotationGenerationError, TimelineError, PresenceAnalysisError) as exc:
        logger.warning("[presence] candidate generation needs review for %s: %s", song.id, exc)
        return {"status": "needs_review", "error": str(exc)}
```

该函数放在 `app/modules/annotations/service.py`。三条分离路径只调用它，不复制业务逻辑：

- RQ `job_separate_stems()`；
- 旧的 `run_analysis_and_separation()`；
- `/songs/{song_id}/separate-stems` 同步接口。

- [ ] **Step 3: 运行 hook 测试和已有 Stem 测试**

Run: `python -m pytest app/tests/test_presence_generation_hook.py app/tests/test_stem_analysis.py app/tests/test_analysis_manifest.py -q`

Expected: PASS。候选生成失败不改变 Stem 分离成功状态。

- [ ] **Step 4: 提交**

```bash
git add app/worker/jobs.py app/modules/library/background_tasks.py app/modules/library/router.py app/modules/annotations/service.py app/tests/test_presence_generation_hook.py
git commit -m "feat: generate presence candidates after separation"
```

## Task 6: 前端区间编辑纯函数与测试环境

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Create: `web/src/lib/presenceEditor.ts`
- Create: `web/src/lib/presenceEditor.test.ts`
- Modify: `web/src/types/index.ts`
- Modify: `web/src/api/client.ts`

- [ ] **Step 1: 安装 Vitest 并增加命令**

Run: `cd web && npm install --save-dev vitest@^2.1.9`

`web/package.json` 增加：

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "test": "vitest run"
}
```

- [ ] **Step 2: 写区间编辑失败测试**

```typescript
import { describe, expect, it } from 'vitest'
import { addRange, deleteRange, mergeRanges, resizeRange, splitRange } from './presenceEditor'

describe('presence interval editing', () => {
  it('normalizes overlapping ranges to half-open merged ranges', () => {
    expect(addRange([{ start_bar_index: 1, end_bar_index: 3 }], 2, 5))
      .toEqual([{ start_bar_index: 1, end_bar_index: 5 }])
  })

  it('splits one range at an interior bar', () => {
    expect(splitRange([{ start_bar_index: 1, end_bar_index: 6 }], 0, 4))
      .toEqual([{ start_bar_index: 1, end_bar_index: 4 }, { start_bar_index: 4, end_bar_index: 6 }])
  })

  it('rejects a resize that creates an empty interval', () => {
    expect(() => resizeRange([{ start_bar_index: 2, end_bar_index: 4 }], 0, 4, 4))
      .toThrow('range must contain at least one bar')
  })
})
```

- [ ] **Step 3: 实现无 UI 依赖的区间操作**

```typescript
export interface EditableRange {
  start_bar_index: number
  end_bar_index: number
  confidence?: number | null
}

export function normalizeRanges(ranges: EditableRange[]): EditableRange[] {
  const sorted = ranges.map(stripConfidenceForManualEdit).sort((a, b) => a.start_bar_index - b.start_bar_index)
  return sorted.reduce<EditableRange[]>((acc, range) => {
    if (range.end_bar_index <= range.start_bar_index) throw new Error('range must contain at least one bar')
    const last = acc.at(-1)
    if (last && range.start_bar_index <= last.end_bar_index) {
      last.end_bar_index = Math.max(last.end_bar_index, range.end_bar_index)
    } else {
      acc.push({ ...range })
    }
    return acc
  }, [])
}
```

同文件实现 `addRange`、`deleteRange`、`resizeRange`、`splitRange` 和 `mergeRanges`。所有函数返回新数组，不修改 React state 中的原对象。

- [ ] **Step 4: 增加前端合同和 API 方法**

`web/src/types/index.ts` 增加 `PresenceBar`、`PresenceRange`、`ElementCandidate`、`ElementReview`、`PresenceAnnotationBundle`。`web/src/api/client.ts` 增加：

```typescript
export async function getPresenceAnnotations(songId: string) {
  return request<PresenceAnnotationBundle>(
    `/api/annotations/songs/${encodeURIComponent(songId)}/presence`,
  )
}

export async function generatePresenceAnnotations(songId: string) {
  return request<PresenceAnnotationBundle>(
    `/api/annotations/songs/${encodeURIComponent(songId)}/presence/generate`,
    { method: 'POST' },
  )
}

export async function savePresenceReview(songId: string, payload: PresenceReviewRequest) {
  return request<PresenceAnnotationBundle>(
    `/api/annotations/songs/${encodeURIComponent(songId)}/presence/review`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
}

export function getPresenceExportUrl(songId: string): string {
  const token = getToken()
  return `${BASE}/api/annotations/songs/${encodeURIComponent(songId)}/presence/export?token=${encodeURIComponent(token || '')}`
}
```

- [ ] **Step 5: 运行测试和类型构建并提交**

Run: `cd web && npm test`

Expected: PASS。

Run: `cd web && npm run build`

Expected: TypeScript 和 Vite build 成功。

```bash
git add web/package.json web/package-lock.json web/src/lib web/src/types/index.ts web/src/api/client.ts
git commit -m "feat: add presence annotation client contracts"
```

## Task 7: 单曲 Presence 审核面板

**Files:**
- Create: `web/src/components/PresenceAnnotationPanel.tsx`
- Create: `web/src/components/PresenceTimeline.tsx`
- Modify: `web/src/components/SongDetail.tsx`
- Modify: `web/src/index.css`

- [ ] **Step 1: 创建四轨时间线组件**

`PresenceTimeline` 接收 Bar 列表、四类候选、当前人工区间、播放位置和编辑回调。每个 Bar 的宽度按时长比例计算，点击 Bar 跳转，拖过连续 Bar 调用 `onAddRange(element, start, end)`。每个区间渲染左右 resize handle，双击区间删除，按住 `Shift` 点击内部 Bar 拆分。

点击区间主体后，播放器在该区间的 `start_sec` 与 `end_sec` 之间循环；再次点击停止循环。相邻区间被同时选中时显示“合并”按钮，并调用 `mergeRanges()`。每条元素轨道都有 `reviewed / unknown / rejected` 状态选择；`unknown` 和 `rejected` 不允许保留 reviewed ranges。

核心 props 固定为：

```typescript
interface PresenceTimelineProps {
  bars: PresenceBar[]
  elements: Record<PresenceElement, ElementLaneState>
  currentTime: number
  selectedElement: PresenceElement
  onSeek: (seconds: number) => void
  onAddRange: (element: PresenceElement, startBar: number, endBar: number) => void
  onResizeRange: (element: PresenceElement, index: number, startBar: number, endBar: number) => void
  onDeleteRange: (element: PresenceElement, index: number) => void
  onSplitRange: (element: PresenceElement, index: number, splitBar: number) => void
  onMergeRanges: (element: PresenceElement, indexes: number[]) => void
  onLoopRange: (startBar: number, endBar: number) => void
}
```

- [ ] **Step 2: 实现音频与 Stem 切换**

`PresenceAnnotationPanel` 只创建一个 `<audio>`。切换 `original/vocals/drums/bass/other` 时保存 `currentTime` 和播放状态，替换 URL，`loadedmetadata` 后恢复时间，再决定是否继续播放。这样不会同时播放五个音源，也不会因 Stem 切换丢失审核位置。

- [ ] **Step 3: 实现读取、生成、编辑、撤销和保存**

页面状态：

```typescript
type DraftElements = Record<PresenceElement, ElementReview>

const [bundle, setBundle] = useState<PresenceAnnotationBundle | null>(null)
const [draft, setDraft] = useState<DraftElements | null>(null)
const [undoStack, setUndoStack] = useState<DraftElements[]>([])
const [dirty, setDirty] = useState(false)
```

首次 GET 返回 404 时显示“生成机器候选”。生成后把候选区间复制到 draft；人工编辑移除候选 confidence。保存请求必须带 `expected_revision = bundle.revision`。HTTP 409 时不重试覆盖，提示刷新。

键盘：

- Space：播放/暂停；
- `[` / `]`：上一 Bar / 下一 Bar；
- Delete：删除当前选中区间；
- Cmd/Ctrl+Z：撤销上一次区间编辑；
- Cmd/Ctrl+S：保存 reviewed 修订。

- [ ] **Step 4: 挂载到 SongDetail 并补视觉状态**

只在 `song.stems` 存在时显示完整审核面板；没有 Stems 时显示说明和现有分离按钮。四条轨道使用固定颜色，机器概率用轨道底色深浅表示，人工区间用实线边框。Melody 显示“低置信候选，必须人工确认”。

在 `SongDetail` 的 `WaveformPlayer` 后挂载：

```tsx
<PresenceAnnotationPanel song={song} />
```

- [ ] **Step 5: 运行前端测试和 build**

Run: `cd web && npm test && npm run build`

Expected: Vitest PASS；TypeScript 和 Vite build 成功。

- [ ] **Step 6: 提交**

```bash
git add web/src/components/PresenceAnnotationPanel.tsx web/src/components/PresenceTimeline.tsx web/src/components/SongDetail.tsx web/src/index.css
git commit -m "feat: add bar presence review panel"
```

## Task 8: 全链路验证、Pilot 导出和 Jetson 操作说明

**Files:**
- Create: `scripts/export_presence_pilot.py`
- Create: `app/tests/test_presence_e2e.py`
- Create: `docs/PRESENCE_ANNOTATION_PILOT_RUNBOOK.md`

- [ ] **Step 1: 写 4-Bar 全链路测试**

```python
def test_candidate_review_export_round_trip(tmp_path):
    song = synthetic_four_bar_song(tmp_path)
    service = PresenceAnnotationService(AnnotationStore(str(tmp_path / "annotations")))
    candidate = service.generate_for_song(song=song, requesting_user_id=song.user_id)
    reviewed = service.review(
        song=song,
        requesting_user_id=song.user_id,
        expected_revision=candidate.revision,
        elements=accept_all_candidates(candidate),
    )
    records = [json.loads(line) for line in service.export(song, song.user_id).splitlines()]
    assert reviewed.revision == 2
    assert {record["task_id"] for record in records} >= {
        "elements.vocal.presence", "elements.drums.presence", "elements.bass.presence"
    }
    assert all(record["annotation_status"] == "reviewed" for record in records)
```

- [ ] **Step 2: 实现 Pilot 批量导出与统计脚本**

脚本参数固定为：

```text
python scripts/export_presence_pilot.py \
  --annotation-dir data/annotations \
  --output outputs/presence-pilot-1.0.0.jsonl \
  --report outputs/presence-pilot-1.0.0-report.json
```

报告包含歌曲数、每类 reviewed 区间数、Bar 数、候选接受率、人工新增/删除/边界调整次数、不可用元素数和 `needs_review` 原因。脚本遇到未审核歌曲时列入报告但不导出成真值。

- [ ] **Step 3: 写 Jetson/Pilot 操作说明**

Runbook 写清：

1. 确认 API 能读取四个 Stem；
2. 对单曲运行或重跑候选生成；
3. 在 Web 管理端审核并保存；
4. 下载单曲 JSONL；
5. 汇总 10 首 Pilot；
6. 遇到时间轴 `needs_review` 时先修 downbeat，不手工伪造 Bar；
7. Jetson 离线时已有 Stems 仍可审核，新分离任务等待恢复。

- [ ] **Step 4: 运行完整验证**

Run: `python -m pytest app/tests/test_bar_timeline.py app/tests/test_presence_analysis.py app/tests/test_annotation_store.py app/tests/test_annotation_api.py app/tests/test_presence_generation_hook.py app/tests/test_presence_e2e.py -q`

Expected: PASS。

Run: `cd web && npm test && npm run build`

Expected: PASS。

Run: `git diff --check`

Expected: 无输出。

- [ ] **Step 5: 提交**

```bash
git add scripts/export_presence_pilot.py app/tests/test_presence_e2e.py docs/PRESENCE_ANNOTATION_PILOT_RUNBOOK.md
git commit -m "test: verify presence annotation pilot loop"
```

## Task 9: 10 首 Pilot 运行门槛

**Files:**
- Runtime data: `data/annotations/`
- Runtime output: `outputs/presence-pilot-1.0.0.jsonl`
- Runtime report: `outputs/presence-pilot-1.0.0-report.json`

- [ ] **Step 1: 选择 10 首覆盖曲目**

选择结果必须包含长 Intro、突然 Drop、间歇人声、无主唱器乐、低频密集、鼓组稀疏和明显 Stem 泄漏。每首歌记录 `track_id`、曲目类型和入选原因；不把音频文件提交到 Git。

- [ ] **Step 2: 在 Jetson 完成分离和候选生成**

每首歌确认四轨文件存在、Bar 时间轴没有整曲偏移、候选器版本为 `method:bar_presence_candidate@0.1.0`。时间轴不合格的歌曲进入复核队列，修正后生成新的 Dataset Version。

- [ ] **Step 3: 完成人工审核并导出**

Vocal、Drums、Bass 必须全部达到 `reviewed`。Melody 允许 `unknown`，但不能保持未审核。运行批量导出脚本，确认 JSONL 只含 reviewed/adjudicated 记录。

- [ ] **Step 4: 检查闭环门槛**

报告必须回答：

- 10 首是否都能从机器候选走到 reviewed JSONL；
- 是否存在整曲 Bar 偏移；
- Vocal、Drums、Bass 的主要错误来自时间轴、分离还是阈值；
- Melody 是否被错误地从 `other` 自动当作真值；
- 同版本重复生成是否一致；
- 修订历史是否能追溯到操作者和候选器版本。

代码交付在 Task 8 完成；Task 9 是需要真实 Jetson、真实歌曲和人工听审的验收，不用合成测试替代。
