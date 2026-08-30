# HarBeat 音乐分析共同开发合同 V1

- 版本：1.0.0
- 状态：V1 技术默认值已定稿，待团队签署生效
- 生效日期：2026-08-30
- 适用范围：数据标注、训练、离线分析、模型推理、数据库、API、Planner 和 RK 接入

机器校验文件：

- [`BarFeature` JSON Schema](../contracts/schemas/analysis/bar_feature_v1.schema.json)
- [`TrackAnalysis` JSON Schema](../contracts/schemas/analysis/track_analysis_v1.schema.json)
- [Feature Registry Entry JSON Schema](../contracts/schemas/analysis/feature_registry_entry_v1.schema.json)
- [Annotation Record JSON Schema](../contracts/schemas/analysis/annotation_record_v1.schema.json)
- [Dataset Track JSON Schema](../contracts/schemas/analysis/dataset_track_v1.schema.json)
- [Analysis Job JSON Schema](../contracts/schemas/analysis/analysis_job_v1.schema.json)
- [MERT Cache Manifest JSON Schema](../contracts/schemas/analysis/mert_cache_manifest_v1.schema.json)
- [Model Manifest JSON Schema](../contracts/schemas/analysis/model_manifest_v1.schema.json)
- [历史 69 项迁移 Registry](../contracts/registries/analysis_features_v1.jsonl)

## 1. 文档效力

这份文件是共同开发合同，不是字段示例。两名成员和 GPT 都按本文开发；代码、Notebook、数据库字段或聊天记录与本文冲突时，以本文和对应 JSON Schema 为准。

本文中的用词有固定含义：

- “必须”表示不满足就不能合并或交付；
- “应”表示默认做法，偏离时要写 Decision Record；
- “可以”表示兼容选择，不要求所有实现都采用。

本合同冻结 V1 的技术语义。历史 69 项已经无损迁入 Registry，但其中未验证项的正反例、详细语义和模型上线门槛仍需要 Pilot 数据与制作人签字，详见第 19 节。

## 2. 已冻结的总原则

| 项目 | V1 决定 |
|---|---|
| 绝对时间基准 | 解码后规范音频的起点，单位为秒 |
| 区间语义 | `[start, end)`，包含开始，不包含结束 |
| 索引 | Beat、Bar、数组位置统一从 0 开始 |
| Planner 主输入 | `TrackAnalysis`，其中 `bars` 是 `BarFeature[]` |
| 分析方式 | 离线；RK 只读取版本化结果 |
| 主数据格式 | UTF-8 JSON；训练清单与标注使用 JSONL |
| 字段命名 | `snake_case`，不允许同义字段并存 |
| 空值 | `null` 表示没有值，`0` 只表示真实零 |
| 数值 | JSON number；禁止 `NaN`、`Infinity` 和字符串数值 |
| 版本 | Schema 使用 SemVer；分析结果不可被静默覆盖 |
| 失败 | 明确输出缺失原因、错误码和 `needs_review`，不伪造结果 |
| 来源追踪 | 每个可消费特征都要引用一条 provenance 记录 |

## 3. 基础类型和序列化

### 3.1 通用类型

| 类型 | JSON 类型 | 规则 | 示例 |
|---|---|---|---|
| `Id` | string | 1–128 字符；只用字母、数字、`.`、`_`、`:`、`-` | `an_01J8K4` |
| `Timestamp` | string | ISO 8601 UTC，必须带 `Z` | `2026-08-30T08:15:30Z` |
| `Seconds` | number | `>= 0`，内部使用 float64 | `12.483921` |
| `Probability` | number | 闭区间 `[0, 1]` | `0.82` |
| `NormalizedScore` | number | 闭区间 `[0, 1]`，定义必须登记 | `0.64` |
| `Sha256` | string | 64 位小写十六进制 | `a3f1...` |
| `Version` | string | SemVer `major.minor.patch` | `1.0.0` |
| `JsonPath` | string | 相对 `BarFeature` 根节点的点路径 | `elements.vocal.activity` |

持久化时最多保留 6 位小数；模型内部可以使用更高精度。比较时间使用 1 毫秒容差，不能直接比较浮点数是否完全相等。

### 3.2 ID

- `track_id` 标识项目中的一首逻辑歌曲，重新分析时不变；
- `analysis_id` 标识一次不可变分析结果，每次重分析生成新值；
- `job_id` 标识一次任务执行；重试沿用原 `job_id` 并增加 `attempt`；
- `model_id` 标识模型和权重组合，不能只写模型类别；
- `dataset_version` 标识一个不可变数据集快照；
- `provenance_ref` 指向当前 `TrackAnalysis.provenance` 中的键。

数据库可以继续使用现有字符串 `track_id`，不强制迁移成 UUID。新 ID 应使用 UUIDv7、ULID 或项目统一的可排序 ID；同一类 ID 不能混用多种生成方式。

### 3.3 时间和音乐索引

- `start_sec`、`end_sec` 都相对规范音频起点；
- `bar_index`、`beat_start_index` 从 0 开始；
- `start_bar_index` 包含该 Bar，`end_bar_index` 不包含该 Bar；
- `beat_times_sec` 必须严格递增；
- 相邻 Bar 应满足 `abs(current.end_sec - next.start_sec) <= 0.001`；
- 非量化边界保存真实秒数，同时把 `needs_review` 设为 `true`；
- 4/4 中“8 拍”是 8 个 Beat，也就是 2 个 Bar；产品文字若指 8 个 Bar，必须写“8 小节”。

### 3.4 缺失、未知和真实零

每个特征都使用统一包装结构：

```json
{
  "value": 0.82,
  "availability": "available",
  "confidence": 0.76,
  "provenance_ref": "prov_vocal_head_1",
  "validation_status": "provisional"
}
```

规则如下：

| 情况 | `value` | `availability` | 说明 |
|---|---|---|---|
| 正常输出 | 实际值 | `available` | 必须有 `provenance_ref` |
| 本次未请求 | `null` | `not_computed` | 不能填默认零 |
| 依赖缺失 | `null` | `unavailable` | 在 `missing_fields` 记录路径 |
| 质量门控失败 | `null` | `invalid` | 在 `warnings` 记录原因 |
| 已运行但类别无法判断 | `unknown` | `available` | 仅适用于包含 `unknown` 的枚举 |
| 真实没有活动 | `0` 或 `absent` | `available` | 这是有效结果 |

`confidence` 表示该值在当前样本上的可信程度，不等于分类概率。没有经过校准的实现必须填 `null`，不能把 Softmax 最大值直接叫作 confidence。

### 3.5 验证状态

```text
unvalidated  尚未在目标域验证
provisional  已完成初步验证，只允许灰度或辅助展示
validated    已达到 Feature Registry 中的生产门槛
rejected     已确认不可用，Planner 不得读取
```

## 4. 音频输入和预处理

### 4.1 规范音频

分析流水线先生成一份逻辑上的规范 PCM：

| 项目 | V1 固定值 |
|---|---|
| 采样率 | 44,100 Hz |
| 声道 | 2 声道，顺序为 Left、Right |
| 样本类型 | float32，范围 `[-1, 1]` |
| 时间起点 | 解码后第一个有效样本 |
| 响度处理 | 测量前不做响度归一化 |
| 截断 | 不自动裁掉前后静音 |

原文件字节计算 `audio_sha256`，规范 PCM 计算 `decoded_pcm_sha256`。文件封装不同但解码内容相同的音频，可以通过后者复用分析缓存。

模型适配器可以从规范 PCM 重采样或转单声道，但必须把采样率、声道规则、重采样器和版本写入 provenance 与缓存键。MERT 的输入采样率从 checkpoint 配置读取，不能散落在训练脚本里硬编码。

### 4.2 预处理版本

`preprocessing_version` 每次修改以下任一内容都要升级：

- 解码器或重采样器；
- 声道混合规则；
- 响度、裁剪或归一化；
- MERT 窗口与步长；
- Bar 对齐和池化方式；
- 显式特征频段与标准化。

训练和生产必须引用同一个预处理实现。Notebook 中的私有预处理不能进入正式实验结果。

## 5. Canonical Timeline

`TrackAnalysis.timeline` 是所有任务的唯一时间轴。模型不能各自生成一套 Bar 编号后直接写入结果。

生成顺序固定为：

```text
规范音频
→ Beat
→ Downbeat
→ Meter Segment
→ Bar
→ 特征和标签对齐
```

### 5.1 Timeline 不变量

- Beat、Downbeat 和 Bar 都按时间严格递增；
- 每个 Downbeat 必须对应一个 Beat，容差为 30 毫秒；
- 完整 Bar 的 `beat_count` 等于当前 Meter 的 numerator；
- 曲首或曲尾不足一小节时允许 `is_partial=true`；
- `bar_count` 必须等于 `bars.length`；
- `BarFeature.beat_times_sec.length` 必须等于 `beat_count`；
- Meter 发生变化时必须创建新的 `meter_segment`；
- 持续错拍、半拍或整小节偏移必须触发 `TIMELINE_SUSPECT`。

Timeline 质量不过关时，可以生成 `partial` 分析供人工检查，但 Planner 不得使用依赖 Bar 对齐的危险动作。

## 6. Feature Registry 合同

Feature Registry 是特征数量、定义和上线状态的唯一来源。每一行必须包含以下字段：

机器定义见 [`feature_registry_entry_v1.schema.json`](../contracts/schemas/analysis/feature_registry_entry_v1.schema.json)。Registry 建议使用 JSONL，每行是一条独立记录。

| 字段 | 类型 | 规则 |
|---|---|---|
| `feature_id` | string | 永久 ID，推荐等于输出路径 |
| `definition_version` | SemVer | 定义变化时升级 |
| `display_name_zh` | string | 中文展示名 |
| `json_path` | JsonPath | 在 `BarFeature` 或 `TrackAnalysis` 中的位置 |
| `granularity` | enum | `track`、`section`、`bar`、`beat`、`event` |
| `dtype` | enum | `boolean`、`integer`、`number`、`enum`、`vector`、`segment_list` |
| `unit` | string/null | `second`、`bpm`、`lufs`、`dbfs`、`ratio` 或 `null` |
| `allowed_values_or_range` | JSON | 枚举或数值范围 |
| `semantic_definition` | string | 制作人可以据此判断对错 |
| `source_policy` | array | 允许的规则、显式分析或模型来源 |
| `dependencies` | array | 上游 `feature_id` |
| `missing_policy` | enum | `null`、`unknown`、`block` |
| `consumer` | array | Planner、UI、训练任务等 |
| `validation_metric` | string | 主要评价指标 |
| `production_threshold` | number/string/null | Pilot 后填写 |
| `status` | enum | `planned`、`implemented`、`provisional`、`validated`、`retired` |
| `owner` | string | B1、B2 或 A 审核人 |
| `license` | string/null | 方法、数据或权重许可 |

V1 必须先登记这些输出族：

| 输出路径 | 类型 | 单位/范围 |
|---|---|---|
| `timing.bpm` | number | BPM，`> 0` |
| `timing.meter` | object | numerator/denominator |
| `timing.downbeat_confidence` | probability | `[0,1]` |
| `structure.phrase_start_probability` | probability | `[0,1]` |
| `structure.phrase_end_probability` | probability | `[0,1]` |
| `structure.section_start_probability` | probability | `[0,1]` |
| `structure.section_end_probability` | probability | `[0,1]` |
| `structure.section_label` | enum | V1 粗粒度 Section |
| `elements.{drums,vocal,bass,melody}.state` | enum | 元素状态 |
| `elements.{drums,vocal,bass,melody}.activity` | probability | `[0,1]` |
| `elements.{drums,vocal,bass,melody}.entry_probability` | probability | `[0,1]` |
| `elements.{drums,vocal,bass,melody}.exit_probability` | probability | `[0,1]` |
| `acoustic.energy_normalized` | score | `[0,1]`，只在同一版本内比较 |
| `acoustic.lufs_short_term` | number | LUFS |
| `acoustic.rms_dbfs` | number | dBFS |
| `acoustic.sub_energy_ratio` | ratio | 20–60 Hz |
| `acoustic.bass_energy_ratio` | ratio | 60–250 Hz |
| `acoustic.mid_energy_ratio` | ratio | 250–4,000 Hz |
| `acoustic.high_energy_ratio` | ratio | 4,000 Hz–Nyquist |
| `harmony.local_key` | enum | `C:maj`、`F#:min`、`unknown` 等 |
| `harmony.chroma` | vector | 12 维，C 到 B |
| `rhythm.drum_density` | score | `[0,1]`，定义版本化 |
| `rhythm.groove_strength` | score | `[0,1]`，定义版本化 |

历史 `feature_selection.csv` 已逐行导入
[`analysis_features_v1.jsonl`](../contracts/registries/analysis_features_v1.jsonl)。当前 `0.1.0`
条目只冻结 ID、状态、历史指标、样本量和别名关系；未补齐制作人签字的详细语义、
正反例和边界案例之前，不得把迁移完成宣称为全部特征已可训练或可上线。

## 7. 标签合同

### 7.1 元素状态

元素为 `drums`、`vocal`、`bass`、`melody`。状态使用单选枚举：

| 状态 | 定义 |
|---|---|
| `absent` | 该 Bar 没有可感知且与混音相关的元素活动 |
| `background` | 元素存在，但不是当前听觉焦点 |
| `foreground` | 元素存在，并且是当前主要听觉内容之一 |
| `entering` | 元素在该 Bar 内从无或很弱进入明显活动 |
| `ending` | 元素在该 Bar 内明显结束或衰减到无 |
| `unknown` | 已听取或已推理，但无法可靠归类 |

`activity`、`entry_probability` 和 `exit_probability` 独立保存。模型不需要用一个 state 同时表达所有信息。

### 7.2 V1 Section

```text
intro
main
build
breakdown
outro
unknown
```

详细标签 `verse`、`chorus`、`drop`、`bridge` 等保存在标注扩展中，不进入 V1 `section_label`。等详细标签的一致性和样本量达到门槛后，再升级 Schema。

### 7.3 标注记录

每条标注使用同一外壳：

机器定义见 [`annotation_record_v1.schema.json`](../contracts/schemas/analysis/annotation_record_v1.schema.json)。

```json
{
  "annotation_id": "ann_01J8K4",
  "dataset_version": "bar-understanding-1.0.0",
  "track_id": "track_001",
  "task_id": "elements.vocal.state",
  "start_sec": 21.5,
  "end_sec": 26.5,
  "start_bar_index": 12,
  "end_bar_index": 15,
  "value": "foreground",
  "annotator_id": "producer_01",
  "annotation_status": "adjudicated",
  "annotator_confidence": 0.9,
  "candidate_source": "model:vocal_head_candidate_1",
  "created_at": "2026-08-30T08:15:30Z"
}
```

`annotation_status` 只能是：

```text
candidate
annotated
reviewed
adjudicated
rejected
```

模型候选不能冒充人工真值。训练默认只使用 `reviewed` 和 `adjudicated`；使用弱标签时要单独配置 loss weight，并在实验记录中声明。

### 7.4 Timeline 修订

标注同时保存秒数和 Bar 索引。若 Timeline 变化超过 30 毫秒或 Bar 编号变化，旧标注不能原地改写；必须生成新 Dataset Version，并记录重对齐脚本和人工抽检结果。

## 8. `BarFeature` 合同

正式定义位于 [`bar_feature_v1.schema.json`](../contracts/schemas/analysis/bar_feature_v1.schema.json)。Payload 固定使用：

```json
{
  "schema_name": "harbeat.bar_feature",
  "schema_version": "1.0.0"
}
```

### 8.1 必填分组

```text
timing
structure
elements
acoustic
harmony
rhythm
quality
```

分组本身始终存在。尚未计算的内部字段使用第 3.4 节的 `null + not_computed`，不能删除整个分组，也不能传未经登记的私有字段。

### 8.2 Bar 级质量

`quality` 必须包含：

- `timeline_confidence`；
- `overall_confidence`；
- `validation_status`；
- `needs_review`；
- `ood_probability`；
- `missing_fields`；
- `warnings`。

`overall_confidence` 不能用所有 confidence 的简单平均。V1 在没有校准方法前填 `null`，由 Planner 根据具体字段和质量门控决定是否可用。

### 8.3 Legacy 窗口聚合门槛

把现有 `energy_curve` 或 `stem_activity_windows` 聚合到 Bar 时，窗口并集必须覆盖
该 Bar 时长的至少 95%。低于 95% 使用 `null + invalid` 并写入
`*_PARTIAL_COVERAGE`；无任何窗口使用 `null + not_computed`。窗口的 `start/end`
非法或值超出 `[0,1]` 时必须写 `*_INVALID_WINDOW`，禁止截断成 0 或 1。

重叠窗口先在重叠时段取均值，再按时间加权，不能重复计算重叠时长。该聚合结果引用
`source_type=derived` 的独立 provenance。连续 activity 不能由 Adapter 用临时阈值改写为
`absent/background/foreground`；元素 state 在对应标签或规则通过评审前保持
`null + not_computed`。

### 8.4 不进入 V1 的字段

Fine Drum、Rap/Singing/Spoken、Bass Type、详细 Section、Style、Metric Embedding 暂不加入正式 V1 Schema。实验结果放在模型实验产物中；达到 Registry 门槛后通过向后兼容的小版本或 V2 加入。

## 9. `TrackAnalysis` 合同

正式定义位于 [`track_analysis_v1.schema.json`](../contracts/schemas/analysis/track_analysis_v1.schema.json)。一个对象代表一首歌的一次不可变分析结果。

### 9.1 状态

`TrackAnalysis.status` 只能是：

```text
succeeded
partial
```

完全失败的任务不生成伪 `TrackAnalysis`，错误保存在 Analysis Job。部分阶段失败但 Timeline 和 BarFeature 仍可校验时，生成 `partial`，同时列出 `missing_feature_sets`。

### 9.2 版本和修订

- 同一 `track_id` 第一次成功分析为 `revision=1`；
- 重分析生成新的 `analysis_id` 并递增 revision；
- 旧结果保留，不能原地覆盖；
- Planner 必须保存其使用的 `analysis_id`；
- `latest` 只是查询别名，已经生成的 MixPlan 不能跟随 `latest` 漂移。

### 9.3 旧字段兼容

现有 `LibrarySong.bpm`、`beat_points`、`phrase_map` 等字段暂时作为 Legacy Projection 保留。它们由最新批准的 `TrackAnalysis` 生成，不再是新的权威来源。

迁移顺序：

1. 现有分析结果通过 Adapter 生成 `TrackAnalysis 1.0.0`；
2. 新 API 和 Planner 改读 `TrackAnalysis`；
3. 核对固定 Fixture；
4. 最后再决定是否删除旧字段。

## 10. Provenance

每个 `FeatureValue.provenance_ref` 指向 `TrackAnalysis.provenance`。记录至少包含：

```text
source_type
method_id
method_version
model_id
model_sha256
dataset_version
calibration_version
preprocessing_version
config_sha256
code_commit
computed_at
license_id
```

`source_type` 枚举为：

```text
explicit
rule
pretrained_model
trained_head
manual
derived
```

规则输出也必须有版本和配置哈希。`model_id=null` 只表示该方法没有模型权重，不表示可以省略来源。

## 11. Analysis Job 和 Worker

### 11.1 Job 状态

```text
queued
running
succeeded
partial
failed
cancelled
```

允许的转换：

```text
queued → running | cancelled
running → succeeded | partial | failed | cancelled
failed → queued       仅重试时，attempt + 1
```

`succeeded`、`partial` 和 `cancelled` 是终态。需要重新运行终态任务时创建新 `job_id`，不能把终态改回 running。

### 11.2 Stage

Stage 名称固定为：

```text
decode
timeline
stems
explicit
mert
bar_content
structure
persist
```

Stage 状态为 `pending`、`running`、`succeeded`、`skipped` 或 `failed`。V1 最低成功条件是 `decode`、`timeline`、`explicit`、`persist` 成功，并且 TrackAnalysis 通过 Schema 与不变量校验。可选 Stage 失败时返回 `partial`。

### 11.3 Job 字段

机器定义见 [`analysis_job_v1.schema.json`](../contracts/schemas/analysis/analysis_job_v1.schema.json)。

| 字段 | 类型 | 说明 |
|---|---|---|
| `job_id` | Id | 任务 ID |
| `track_id` | Id | 目标歌曲 |
| `status` | enum | 总状态 |
| `requested_feature_sets` | string[] | 本次请求范围 |
| `attempt` | integer | 从 1 开始 |
| `max_attempts` | integer | 默认 3 |
| `progress` | number | `[0,1]`，按 Stage 权重计算 |
| `stages` | object | 每个 Stage 的状态和时间 |
| `analysis_id` | Id/null | 成功或 partial 时填写 |
| `error` | object/null | 失败信息 |
| `created_at` | Timestamp | 创建时间 |
| `started_at` | Timestamp/null | 开始时间 |
| `heartbeat_at` | Timestamp/null | Worker 心跳 |
| `ended_at` | Timestamp/null | 终态时间 |

Worker 每 30 秒更新 heartbeat。运行中 120 秒无 heartbeat 的任务标为失联，由调度器按幂等规则决定重试。

### 11.4 错误码

```text
INPUT_NOT_FOUND
AUDIO_DECODE_FAILED
TIMELINE_FAILED
TIMELINE_SUSPECT
STEM_FAILED
EXPLICIT_FEATURE_FAILED
MERT_FAILED
MODEL_INFERENCE_FAILED
SCHEMA_VALIDATION_FAILED
PERSIST_FAILED
WORKER_LOST
CANCELLED_BY_USER
```

错误对象包含 `code`、`message`、`stage`、`retryable` 和经过脱敏的 `details`。API 不返回堆栈、文件系统绝对路径或凭据。

### 11.5 幂等

同一个 `track_id + audio_sha256 + requested_feature_sets + pipeline_version + Idempotency-Key` 必须返回同一个活动任务。重复请求不能创建并行的 GPU 重任务。

## 12. API 合同

### 12.1 创建任务

```http
POST /api/library/songs/{track_id}/analysis-jobs
Idempotency-Key: <client-generated-id>
```

```json
{
  "requested_feature_sets": [
    "timeline",
    "explicit",
    "stems",
    "mert",
    "bar_content",
    "structure"
  ],
  "target_schema": "harbeat.track_analysis@1.0.0",
  "force": false
}
```

返回 HTTP 202：

```json
{
  "code": 0,
  "message": "accepted",
  "data": {
    "job_id": "job_01J8K4",
    "track_id": "track_001",
    "status": "queued"
  }
}
```

### 12.2 查询任务

```http
GET /api/analysis-jobs/{job_id}
```

返回第 11.3 节定义的完整 Job。轮询频率不得高于每 2 秒一次；后续可以增加事件推送，但不能改变 Job 对象语义。

### 12.3 读取分析

```http
GET /api/library/songs/{track_id}/analyses/{analysis_id}
GET /api/library/songs/{track_id}/analyses/latest
```

成功返回 `APIResponse[TrackAnalysis]`。`latest` 只返回当前批准版本，不返回仍在运行或已 rejected 的分析。

### 12.4 HTTP 状态

| HTTP | 场景 |
|---|---|
| 200 | 查询成功 |
| 202 | 已创建或复用异步任务 |
| 400 | 请求字段或 Schema 不合法 |
| 401/403 | 未登录或无权访问歌曲 |
| 404 | 歌曲、任务或分析不存在 |
| 409 | 版本、幂等键或状态冲突 |
| 422 | 音频或参数可解析，但不满足分析合同 |
| 500 | 未分类服务端错误 |
| 503 | Worker、GPU 或依赖服务不可用 |

现有同步 `/songs/{track_id}/analyze` 标记为 Legacy。新客户端不再调用；过渡期内它只负责创建 Job 并返回 202，不再在请求线程运行整首分析。

## 13. 持久化合同

V1 使用不可变分析记录，推荐逻辑表如下：

### 13.1 `music_analysis_runs`

| 字段 | 类型 | 约束 |
|---|---|---|
| `analysis_id` | string | 主键 |
| `track_id` | string | 索引 |
| `revision` | integer | 与 track 组成唯一键 |
| `schema_name` | string | `harbeat.track_analysis` |
| `schema_version` | string | `1.0.0` |
| `status` | string | `succeeded` 或 `partial` |
| `audio_sha256` | char(64) | 索引 |
| `pipeline_version` | string | 必填 |
| `payload` | JSON/JSONB | 完整 TrackAnalysis |
| `created_at` | UTC timestamp | 必填 |

### 13.2 `music_analysis_bars`

| 字段 | 类型 | 约束 |
|---|---|---|
| `analysis_id` | string | 外键 |
| `bar_index` | integer | 与 analysis 组成主键 |
| `start_sec` | double | 索引 |
| `end_sec` | double | 必须大于 start |
| `payload` | JSON/JSONB | 完整 BarFeature |

如果第一版只保存 TrackAnalysis JSON，也必须保留未来拆分 Bar 表的迁移路径。不能继续为每个新特征无限增加 `LibrarySong` 列。

持久化事务顺序为：写运行记录与 Bars，校验计数和引用，提交事务，再更新 `latest_analysis_id`。任一步失败都不能让 Planner 看见半份结果。

## 14. 缓存合同

### 14.1 分层

```text
decoded_pcm
timeline
stems
explicit_features
mert_hidden_states
task_outputs
track_analysis
```

### 14.2 缓存键

缓存键统一为：

```text
hb:{layer}:v1:{sha256(canonical_json(key_material))}
```

`key_material` 至少包含：

```text
decoded_pcm_sha256
preprocessing_version
component_id
component_version
model_sha256
config_sha256
feature_definition_version
output_schema_version
```

没有模型的层使用 `model_sha256=null`。Canonical JSON 必须按键名字典序、UTF-8、无多余空格序列化。

### 14.3 缓存行为

- 内容对象不可变；升级模型或配置会产生新键；
- `latest` 指针可以失效，内容对象不能被原地覆盖；
- 读取缓存后仍要校验元数据和输出 Schema；
- 缓存命中不能跳过许可证、用户权限和数据删除检查；
- 删除歌曲时按数据策略删除指针，并根据授权范围清理内容对象；
- 失败结果不进入正常缓存，可以短期保存失败退避记录。

## 15. MERT Embedding 合同

V1 默认冻结 MERT，只训练 Layer Mixer、融合层、时序模型和任务头。

### 15.1 切片

| 项目 | V1 固定值 |
|---|---|
| 窗口 | 5.0 秒 |
| 步长 | 2.5 秒 |
| 最后窗口 | 右侧补零，保存 `valid_duration_sec` |
| 随机裁剪 | 禁止用于缓存和生产推理 |
| 时间戳 | 每个窗口保存绝对 `start_sec`、`end_sec` |

Bar 对齐使用真实时间重叠加权，不按数组索引猜测。补零区域必须通过 Mask 排除。

### 15.2 缓存格式

机器定义见 [`mert_cache_manifest_v1.schema.json`](../contracts/schemas/analysis/mert_cache_manifest_v1.schema.json)。

- Tensor 使用 `safetensors`，不使用 pickle；
- 缓存 dtype 为 float16，训练计算转成 float32；
- 保存 `hidden_states`、`window_start_sec`、`valid_duration_sec` 和 `attention_mask`；
- Manifest 记录 `model_id`、权重哈希、输入采样率、层编号、hidden size、窗口、步长和 dtype；
- Layer 顺序必须显式保存，不能假设“数组第 0 项就是 Transformer 第 1 层”；
- 层编号 `0` 只表示输入 Embedding 状态，Transformer 层从 `1` 开始；若 `includes_embedding_state=false`，`selected_layers` 不得包含 `0`；
- `tensor_shape` 固定为 `[window_count, selected_layer_count, frame_count, hidden_size]`；两个时间数组长度必须等于 `window_count`；
- 数据集标准化不写回 MERT 原始缓存，只能在训练 Fold 上拟合并保存到模型产物。

若只缓存选定层，`selected_layers` 必须进入缓存键。更换 Layer Mixer 不需要重跑 MERT，只要原缓存包含所需层。

## 16. Dataset 和 Split 合同

### 16.1 Dataset Track

`metadata.jsonl` 每行至少包含：

机器定义见 [`dataset_track_v1.schema.json`](../contracts/schemas/analysis/dataset_track_v1.schema.json)。

```json
{
  "track_id": "track_001",
  "audio_uri": "dataset://audio/track_001.wav",
  "audio_sha256": "<64 lowercase hex>",
  "duration_sec": 213.4,
  "artist_group_id": "artist_001",
  "leakage_group_id": "work_001",
  "rights": {
    "research": true,
    "training": true,
    "commercial": false,
    "stems_allowed": true,
    "expires_at": null
  },
  "annotation_sets": ["bar_content-1.0.0"],
  "created_at": "2026-08-30T08:15:30Z"
}
```

`audio_uri` 不能包含个人本机绝对路径。凭据不进入 Dataset Manifest。

### 16.2 拆分

PoC 默认按 `leakage_group_id` 做 70% Train、15% Validation、15% Blind Test。比例按歌曲组计算，不按切出的 Bar 数计算。

规则：

- 同一 `leakage_group_id` 只能出现在一个 Split；
- 原版、Remix、Edit、Live 和重制版如果共享大量音乐内容，放入同一 leakage group；
- Style 和 Metric Learning 的 Blind Test 必须 Artist-disjoint；
- 标准化、类别权重、阈值和校准只使用 Train/Validation；
- Blind Test 清单冻结后，日常实验不可查看标签；
- 重新拆分必须升级 `split_version`，旧实验不能改写结果。

片段数量不能替代独立歌曲数。实验报告同时写歌曲数、艺人数、leakage group 数和每类标注时长。

## 17. 训练、评估和校准合同

### 17.1 实验输入

每次训练必须固定：

```text
code_commit
dataset_version
split_version
feature_definition_version
preprocessing_version
mert_model_id_and_sha256
embedding_cache_version
training_config_sha256
random_seed
```

### 17.2 基线顺序

```text
Majority/Rule Baseline
→ Explicit + Linear
→ MERT + Linear Probe
→ MERT + Nonlinear Head
→ MERT + Explicit Fusion
→ TCN/BiGRU
→ 必要时才测试 Transformer 或解冻 Backbone
```

前一个结果没有可靠超过基线时，先检查标签、泄漏、时间对齐和实现，不直接增加模型规模。

### 17.3 评价

| 任务 | 必报指标 |
|---|---|
| 多标签分类 | Macro F1、Micro F1、mAP、每类 Precision/Recall |
| 互斥分类 | Macro F1、Balanced Accuracy、混淆矩阵 |
| 边界检测 | ±1 Downbeat F1、Precision/Recall、偏移分布 |
| 连续回归 | MAE、Spearman、校准或排序一致性 |
| Embedding | Recall@K、成对准确率、制作人偏好 |

必须同时报告按歌曲聚合的指标，不能只把所有 Bar 当成独立样本计算一个总分。

### 17.4 阈值和校准

- 阈值只在 Validation 上选择；
- 多分类优先使用 Temperature Scaling；
- 多标签按任务和类保存阈值，样本不足时不使用复杂校准；
- 回归分数如果供 Planner 排序，要报告排序一致性；
- 校准产物有独立 `calibration_version` 和哈希；
- Blind Test 只在候选模型冻结后运行一次。

## 18. Model Registry 合同

每个可加载模型必须有不可变 Manifest：

机器定义见 [`model_manifest_v1.schema.json`](../contracts/schemas/analysis/model_manifest_v1.schema.json)。

```text
model_id
model_version
task_ids
status
artifact_uri
artifact_sha256
framework_and_version
input_schema
output_schema
backbone_id_and_sha256
dataset_version
split_version
feature_definition_version
preprocessing_version
training_config_sha256
code_commit
metrics
thresholds
calibration_version
license_id
limitations
fallback_model_id
approved_by
approved_at
```

`status` 为：

```text
candidate
staging
production
retired
rejected
```

同一 `model_id@model_version` 不能指向不同权重。只有 `production` 模型能成为 Planner 默认来源；`staging` 只允许灰度和离线对比。

## 19. 仍需人工签字的内容

以下内容不能靠字段设计替代，需要在正式训练前补齐：

| 项目 | 负责人 | 阻塞范围 |
|---|---|---|
| 每个音乐标签的正例、反例和边界案例 | B1 + 制作人 | 对应任务正式标注和训练 |
| Pilot 后的指标数值门槛 | B2 + 制作人 + 项目负责人 | 模型进入 production |
| 历史 69 项的详细音乐语义与正反例签字 | B1 + 制作人；机器迁移已完成 | 未签字项进入正式训练或升级 production |
| MERT、Demucs 和其他模型的商业许可 | 项目负责人 | 商业部署 |
| 数据保存期限和删除 SLA | 项目负责人 | 正式数据收集 |

这些项目未签字不影响 `BarFeature` Adapter、Worker、缓存和 Fixture 开发，但会阻塞对应模型的正式训练或上线。

## 20. 兼容和变更规则

Schema 使用 SemVer：

- Patch：修正文档或校验器 Bug，不改变合法 Payload 集合；
- Minor：新增可选字段或枚举能力，旧 Reader 可以安全忽略；
- Major：删除字段、改类型、改单位、改时间语义或改标签含义。

V1 JSON Schema 使用 `additionalProperties=false`。需要增加字段时先更新 Feature Registry 和 Schema，再改 Producer；不能先偷偷输出字段让 Consumer 猜。

变更顺序：

1. Decision Record；
2. 更新 Schema 和迁移说明；
3. 更新 Producer、Adapter 和 Fixture；
4. 更新 Consumer；
5. 双版本运行和对照；
6. 旧版本退役。

Reader 遇到未知 major 版本必须拒绝并返回 `SCHEMA_VERSION_UNSUPPORTED`，不能尽力猜测。

## 21. 合并前验收

### 21.1 Schema

- 两个 JSON Schema 自身可以解析；
- 固定的有效样本通过校验；
- 缺失必填字段、非法枚举、NaN 替代值和额外字段会失败；
- 所有 `provenance_ref` 在 TrackAnalysis 中存在；
- `analysis_id`、`track_id` 在父子对象中一致。

### 21.2 Timeline 和 Bar

- 10 首 Fixture 的 Beat、Downbeat、Bar 单调且连续；
- Bar 数、Beat 数和 Meter 一致；
- 非 4/4、曲首不完整 Bar、变速和静音开头有测试；
- Timeline 低置信度时 Planner 受到门控。

### 21.3 Job 和缓存

- 重复幂等请求不会启动第二个重任务；
- Worker 失联、超时和重试有测试；
- 模型或预处理版本变化会产生新缓存键；
- 旧分析仍可读取和回滚；
- partial 结果不会被标成 succeeded。

### 21.4 训练和模型

- Split 无歌曲组泄漏；
- 标准化只在 Train 拟合；
- Blind Test 标签不进入日常实验；
- 导出模型可以由生产推理接口加载；
- Model Registry 能追溯到数据、代码、配置和许可证。

## 22. 开发开始时的默认任务

按以下顺序落地合同：

1. A/GPT 根据机器 Schema 生成 Pydantic 类型和校验测试；
2. A/GPT 编写现有分析结果到 `TrackAnalysis 1.0.0` 的 Adapter；
3. B1 建立 V1 Feature Registry 和 Label Guide；
4. B1 与制作人完成 20–30 首 Pilot 标注；
5. B2 固定 MERT 缓存 Manifest，跑 Linear Probe；
6. A/GPT 统一 Analysis Job、Worker、API 和持久化；
7. 双方用 10 首 Fixture 做第一次合同验收。

完成第 1、2 和 7 项后，原先文档里的 JSON 才从“设计方向”变成项目中实际可依赖的接口。

## 23. 签署与生效

团队可以直接采用本文默认值。签署前只需要填写人员、权威位置和第 19 节中的业务决定，不需要重新讨论已经冻结的字段名、数据类型和时间语义。

| 项目 | 填写内容 |
|---|---|
| 项目负责人 |  |
| B1 标签与数据负责人 |  |
| B2 模型与评估负责人 |  |
| 工作流 A 人工审核人 |  |
| 音乐标签批准人 |  |
| 合同版本 | `1.0.0` |
| Schema 目录 | `contracts/schemas/analysis/` |
| 生效代码提交 |  |
| 生效日期 |  |

```text
项目负责人：____________________  日期：____________

B1 负责人：_____________________  日期：____________

B2 负责人：_____________________  日期：____________

工作流 A 人工审核人：___________  日期：____________

音乐制作人：____________________  日期：____________
```
