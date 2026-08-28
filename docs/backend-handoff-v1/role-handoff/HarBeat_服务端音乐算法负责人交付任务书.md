# HarBeat 服务端音乐算法负责人交付任务书

版本：`v1.0-draft`
合同版本：`music-analysis-v1`
基线日期：2026-08-28
收件人：Jetson 服务端音乐分析算法负责人

状态说明：本文是目标交付任务书，不代表当前代码已经满足合同。当前现状、P0 冲突和实际开工顺序以 `docs/team-development-v1/role-handoff/HarBeat_服务端音乐算法负责人开工与协作说明.md` 为准。

## 1. 你需要交付的最终结果

你负责把现有音乐分析代码整理为后端 Worker 可以稳定调用、版本化验证和部署的算法产物。你的交付不是 FastAPI 路由，也不是直接更新业务数据库，而是：

- 独立 adapter/CLI 或 Python service function；
- 明确的输入合同；
- Core、Stem、Feature、Style 和媒体派生产物；
- 每种 JSON 产物的 JSON Schema；
- 每个文件产物的格式、大小、sha256 和质量信息；
- 模型、阈值、验证版本、适用范围和不可声称内容；
- 成功、降级、不可用和非法输出 fixtures；
- CPU/GPU/RAM/磁盘/耗时报告；
- 可重复部署的模型 manifest 与回归测试。

后端负责 AnalysisRun/Worker/数据库/重试；你负责算法真实产出和质量语义。双方通过 `music-analysis-v1` 合同协作。

## 2. 架构边界

```text
FastAPI/后端
  → PostgreSQL 创建 AnalysisRun/Stage
  → Redis 投递 stage_run_id
  → 独立 Worker 领取 lease
  → Worker adapter 调用你的算法
  → 你的算法写 stage 专用临时目录并输出 JSON
  → Worker 验证 Schema/文件/hash
  → Worker 原子登记 analysis_artifact/media_asset
```

你的算法不得：

- 直接写 users、tracks、user_library_items、devices 等业务表；
- 依赖 FastAPI request/session/global app；
- 自己把任务状态写成 completed；
- 把本地绝对路径作为对外字段；
- 在未知时返回 0 假装结果；
- 把 provisional/candidate_only 自动升级为 validated；
- 在 stdout 混入无法解析的日志和 JSON；
- 默认无限下载模型或依赖不受控网络。

## 3. 当前算法代码位置

主要位于：

| 路径 | 内容 |
|---|---|
| `app/modules/library/background_tasks.py` | 当前 Core→Stem→Feature→Style 流程 |
| `app/modules/library/analysis.py` 及分析子模块 | BPM、Beat、Downbeat、Key、Cue、Energy 等 Core |
| `app/modules/library/stem_analysis.py` 及相关文件 | Demucs Stem、Stem 质量、鼓/Bass/Feature |
| `app/modules/library/high_frequency_style_classifier.py` | 高频风格分析 v4；当前 confirmed 发布仍受验证阻塞 |
| `app/modules/library/feature_registry.py` | 特征 validation status、semantic level、fail-closed |
| `app/tests/` | 算法、模型验证、Feature、Style、Transition 回归测试 |
| `tests/` | BPM/downbeat/stem automix 基线 |
| `scripts/` | 数据集验证、评估、回填和实验脚本 |
| `reports/` | 模型/风格/Downbeat 等验证报告 |

当前工作分支包含正在更新的 tempo、beat、bass、drum、feature/style validation 和 schema 工作。正式接入前必须形成明确 commit/release/model-set，不能让后端依赖“工作目录当前状态”。

## 4. 目标分析阶段

| 阶段 | stage_key | 输入 | 输出 | 产品硬依赖 |
|---|---|---|---|---|
| Core | `core` | 标准音频 | BPM、Beat、Downbeat、Key、Cue、Energy、Transition | 必需；失败 Run failed |
| Stem | `stem_separation` | 标准音频 | vocals/drums/bass/other + 质量 | RK Stem 模式必需；可形成 partial |
| Feature | `feature_analysis` | Core + Stems | 鼓、Bass、节奏、和声、production、pre-style evidence | 风格输入；失败可 partial |
| Style | `style_analysis` | Core + Feature | 21 类风格候选/置信/复核 | 非现场硬依赖；失败可 partial |
| Media | `media_derivatives` | 音频/分析 | preview、waveform、必要 runtime metadata/render | Preview/Manifest 需要 |

依赖：

```text
core ───────────────┬→ media_derivatives
                    └→ stem_separation → feature_analysis → style_analysis
```

## 5. 标准输入合同

Worker 调用每个 stage 时提供：

```json
{
  "contract_version": "music-analysis-v1",
  "analysis_run_id": "018f0000-0000-7000-8000-000000000001",
  "track_id": "018f0000-0000-7000-8000-000000000002",
  "stage_key": "core",
  "input_asset": {
    "asset_id": "018f0000-0000-7000-8000-000000000003",
    "storage_key": "tracks/018f.../original/source.flac",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "size_bytes": 23456789,
    "content_type": "audio/flac",
    "container": "flac",
    "codec": "flac",
    "duration_ms": 243120,
    "sample_rate_hz": 44100,
    "channels": 2
  },
  "execution": {
    "pipeline_version": "<git-sha+model-set>",
    "requested_device": "auto",
    "max_analysis_duration_seconds": 420,
    "deadline_at": "2026-08-28T11:00:00Z",
    "seed": 0
  },
  "upstream_artifacts": []
}
```

规则：

- `storage_key` 由受信任 Worker storage adapter 解析；不接受用户任意绝对路径。
- 算法开始前由 Worker验证输入 sha256；输出回显 input_sha256。
- Core 当前最大分析时长 420 秒，但必须报告真实 duration 和 analyzed duration。
- 输入先经过 ffprobe/等价探测；损坏、无音轨、加密、超限在算法前失败。
- 模型/命令/GPU/阈值来自 Worker 配置，不来自 App 请求。
- 可选外部 metadata 独立超时，失败不能拖垮 Core。

## 6. 所有 JSON 产物公共外壳

```json
{
  "schema_name": "core_music_analysis",
  "schema_version": "1.0.0",
  "contract_version": "music-analysis-v1",
  "analysis_run_id": "<uuid>",
  "track_id": "<uuid>",
  "stage_key": "core",
  "pipeline_version": "<git-sha+model-set>",
  "input_sha256": "<64-hex>",
  "generated_at": "2026-08-28T10:10:00Z",
  "status": "ready",
  "quality": {
    "overall_confidence": 0.87,
    "validation_status": "validated",
    "calibration_version": "tempo_model_validation_v1",
    "flags": []
  },
  "data": {}
}
```

公共枚举和约束：

- `status`: `ready | degraded | unavailable`
- `validation_status`: `validated | failed_validation | provisional | candidate_only | unavailable | deprecated`
- `semantic_level`: `measurement | derived | semantic`
- score/confidence/reliability 范围 `[0,1]`
- 未知使用 null，不使用 0/空字符串伪装
- 时间点用整数毫秒；曲线必须带时间坐标
- 禁止 NaN/Infinity
- 破坏性字段/单位/语义变化必须升级 schema version

## 7. Core 产物

Schema：`core_music_analysis@1.0.0`

### 必需字段

| 字段 | 类型/单位 | 说明 |
|---|---|---|
| `duration_ms` | int ms | 媒体真实时长 |
| `analyzed_duration_ms` | int ms | 实际分析范围 |
| `tempo.bpm` | number BPM | 最终选择 BPM |
| `tempo.confidence` | 0..1 | 共识置信度 |
| `tempo.stability` | 0..1/null | 速度稳定度 |
| `tempo.needs_review` | boolean | 分歧/低置信 |
| `tempo.selected_engine` | string | 引擎/共识策略 |
| `tempo.engine_results[]` | object[] | 每路 bpm/confidence/error |
| `tempo.curve[]` | at_ms/bpm/confidence | 最多 2000 点 |
| `beat_grid.offset_ms` | int/null | 网格偏移 |
| `beat_grid.interval_ms` | number/null | 间隔 |
| `beat_grid.beats[]` | at_ms/confidence | 有界，超限转资产 |
| `beat_grid.downbeats[]` | at_ms/confidence/bar_index | 低置信允许空 |
| `beat_grid.time_signature` | int/null | 未知 null |
| `beat_grid.needs_review` | boolean | Downbeat/Meter 复核 |
| `key.key` | string/null | 规范调名 |
| `key.camelot` | string/null | Camelot |
| `key.confidence` | 0..1 | 最终置信度 |
| `key.needs_review` | boolean | 引擎冲突 |
| `key.candidates[]` | 有界候选 | 最多 5 |
| `energy.overall` | 0..1 | 全曲能量 |
| `energy.curve[]` | start/end/value | 窗口化能量 |
| `loudness.*` | LUFS/dBFS/null | integrated/true peak |
| `cues[]` | object[] | Cue 候选 |
| `sections[]` | object[] | 段落 |
| `phrases[]` | object[] | 乐句 |
| `transition_windows[]` | object[] | 技术过渡窗 |
| `groove` | object | 技术摘要 |
| `danceability` | score/evidence | 不宣称审美事实 |
| `dj_hot_cues[]` | object[] | 候选 |
| `transition_recommendations[]` | object[] | 建议，不是 RK 指令 |

### 当前旧字段映射

- `bpm`, `bpm_curve`, `tempo_stability` → tempo
- `beat_points`, `beat_confidence/details`, `beat_grid_offset/interval` → beat_grid
- `downbeats`, `time_signature` → downbeat/meter
- `key`, `camelot_key`, `key_confidence`, `key_profile` → key
- `energy`, `energy_curve`, `loudness_profile` → energy/loudness
- `cue_points`, `section_analysis`, `phrase_map` → cues/sections/phrases
- `transition_windows`, `groove`, `dancefloor_profile`, `dj_hot_cues` → 同类目标字段

无法规范化的旧内部字段只能短期保存 raw debug，不能直接变成 App/RK 合同。

## 8. Stem 产物

当前模型路线：Demucs `htdemucs`。

文件必须输出并登记：

- vocals
- drums
- bass
- other

每个文件必须提供：`kind=stem, variant, format, size_bytes, sha256, duration_ms, sample_rate_hz, channels`。

只有四个文件全部完成校验，`has_complete_stems=true`。

JSON：

```json
{
  "has_complete_stems": true,
  "stem_asset_ids": {
    "vocals": "<uuid>",
    "drums": "<uuid>",
    "bass": "<uuid>",
    "other": "<uuid>"
  },
  "quality": {
    "score": 0.83,
    "method": "htdemucs",
    "profile": {},
    "flags": []
  },
  "activity": {},
  "clean_regions": {
    "intro": {"start_ms": 0, "end_ms": 16000, "score": 0.88},
    "outro": {"start_ms": 224000, "end_ms": 243120, "score": 0.81}
  },
  "drum_loop": {"detected": false, "score": 0.21, "regions": []}
}
```

算法不能直接生成 asset UUID 业务真相；可输出逻辑文件清单，由 Worker 登记后回填 asset IDs，或使用双方定稿的 staged result protocol。

## 9. Drum/Bass/Feature 产物

### Drum

目标 Schema：`drum_transcription_consensus_v4`。当前代码已输出 v4，但 `modules/stem-separation/contracts/drum-analysis.schema.json` 仍是 v3；这是 P0 合同冲突，修复前不得冻结 Drum 合同。

需要：source drums stem、events/counts、density、patterns、fills、beat alignment、engine routes、confidence、quality flags。

当前验证边界：

- Kick：validated；
- 合并 high_percussion：validated；
- 独立 snare/hihat/tom/cymbal：当前不能整体声称 validated，保持 provisional/candidate_only；
- 低质量鼓类别不能直接触发不可逆自动控制。

### Bass

当前 `bass_model_validation_v1`：Basic Pitch isolated Bass 的 note F1 约 0.8805，允许对音符测量作当前验证声明；更高层 Bass 语义描述仍为 provisional。

### Pre-style Feature

Schema：`pre_style_evidence_v5`

Feature groups：

- rhythm_grammar
- low_frequency
- percussion_timbre
- vocal_delivery
- harmony
- production

每个 feature 必须包含：

- canonical_name
- availability
- detected
- score/probability/decision_threshold
- confidence/reliability
- quality：measurement_confidence/source_quality/estimator_quality/calibration_status
- quality_flags/evidence_level/analysis_method/sources/time_ranges/evidence
- semantic_level
- measurement_score/technical_reliability
- decision：包含连续型测量使用的 measured
- validation_status
- validation_scope
- calibration_version
- style_required_allowed

顶层状态：`ready | degraded | unavailable`。

当前 `feature_calibration_v1` 尚无完整发布校准，不允许笼统声称所有 pre-style feature 已 validated。必须保留 `feature_registry.py` 的 fail-closed 行为。

## 10. 高频风格产物

Schema：`high_frequency_style_analysis_v4`

稳定 style ID 共 21 个：

`boombap, trap, funk, breakbeat, soul_neo_soul, jazz_hiphop, afro_afrobeats, house, grime_uk_hiphop, rnb, disco, jersey_club, drill, amapiano, moombahton, dancehall, baile_funk, memphis_trap, rage, uk_garage, trap_soul`

输出至少包含：

- status：ready/needs_review
- review_reasons
- primary_style：可为 null
- primary_candidate
- top_styles
- detected_styles/influences/styles/group_scores
- model label/instrument evidence
- external tags
- boundary resolution
- confidence/reliability/decision semantics

规则：

- 边界不清/阈值不足时 `primary_style=null`；
- 保留 primary_candidate 供内部复核；
- needs_review 不得在 App 显示为确定风格；
- 外部 tag 只能作 evidence，不能覆盖音频证据；
- provisional 风格可作为推荐弱特征，但 UI 只能显示“可能/相近”。
- 当前 21 类公开弱标签验证不足，所有 Style 默认只允许 candidate/possible；逐 style 通过平衡 heldout 发布门前，不允许向普通 App 输出 confirmed。

## 11. 当前 Beat/Tempo 验证声明

不得扩大以下当前基线：

| 能力 | 版本/数据 | 当前可声明 |
|---|---|---|
| Tempo 共识 | `tempo_model_validation_v1` / GiantSteps | accuracy1 约 0.8387，accuracy2 1.0；适用域有限 |
| Beat | `beat_model_validation_v1` / Beat This GTZAN heldout | Beat F1 约 0.8855，validated |
| Downbeat | 同上 | 原始输出不能整体 validated；置信门约 0.925 时接受覆盖约 0.7241、接受集 F1 约 0.9018 |
| Meter | 同上 | 接受集 accuracy 约 0.9231；低置信必须 abstain |

模型/阈值变化时必须生成新的 validation/calibration version、数据集说明和回归报告。

## 12. 对 App 和 RK 的投影

### App AnalysisSummary

只允许面向用户的有界摘要：

```json
{
  "status": "completed",
  "quality": "ready",
  "duration_ms": 243120,
  "bpm": 128.02,
  "bpm_confidence": 0.94,
  "key": "F# minor",
  "camelot_key": "11A",
  "energy": 0.76,
  "style_labels": []
}
```

你必须评审：哪些 style 可以 certainty=confirmed，哪些只能 possible；哪些字段低置信时必须 null/隐藏。

### RK Manifest

只下发执行必要信息：

- duration/tempo/key 技术摘要；
- beat/downbeat 网格；
- Cue/Section/Phrase 中运行所需投影；
- transition windows/plans；
- master/stem/render/runtime metadata/pad assets 引用；
- analysis_run_id/schema version/quality flags。

不下发：各引擎调试信息、完整 model evidence、外部 metadata、完整风格计算、NAS 路径。

Beat 点太多导致 Manifest > 2 MiB 时输出独立 runtime metadata 资产，Manifest 引用 asset_id。

## 13. Worker 执行合同

### 进程和 stdout

- 算法运行在 Worker 子进程或受控 Python adapter。
- CLI stdout 只输出一个可解析 JSON result；日志写 stderr/结构化日志。
- 外部命令必须 shell=false，使用 argv；音频位置用明确 `{audio}` placeholder。
- 限制 timeout、stdout 大小、工作目录、环境变量和网络。
- 捕获 SIGTERM，尽可能协作取消；不支持取消的库必须能由父进程终止。

### 临时和最终文件

写入：`staging/{run_id}/{stage}/{attempt_token}/`。

算法完成后由 Worker：

1. 解析 JSON；
2. 校验 Schema/NaN；
3. 探测媒体；
4. 计算 size/sha256；
5. 原子移动到不可变资产路径；
6. 提交数据库。

算法不能原地覆盖已 ready 资产。

### 确定性

相同 `input_sha256 + pipeline_version + contract_version + seed` 应产生语义等价结果。规范 JSON 使用稳定 canonicalization 并计算 payload sha256。

## 14. 错误合同

| 错误码 | 可重试 | 场景 |
|---|---:|---|
| `ANALYSIS_INPUT_MISSING` | 运维修复后 | NAS 输入丢失 |
| `ANALYSIS_INPUT_HASH_MISMATCH` | 否 | 文件损坏/被改写 |
| `ANALYSIS_UNSUPPORTED_MEDIA` | 否 | 格式/音轨不支持 |
| `ANALYSIS_MODEL_UNAVAILABLE` | 是 | 模型没部署 |
| `ANALYSIS_GPU_OOM` | 有限 | GPU 显存不足 |
| `ANALYSIS_STAGE_TIMEOUT` | 有限 | 超过 deadline |
| `ANALYSIS_OUTPUT_INVALID` | 否 | Schema/NaN/字段非法 |
| `ANALYSIS_EXTERNAL_ADAPTER_FAILED` | 依场景/降级 | 可选服务失败 |
| `ANALYSIS_CANCELED` | 否 | 协作取消 |
| `ANALYSIS_INTERNAL_ERROR` | 有限 | 未分类错误 |

完整 traceback 进受控 Worker 日志，API 只返回稳定错误码和安全摘要。

## 15. 资源和性能基线

- Core 当前最大分析范围 420 秒；截断要加 quality flag。
- Demucs Stem timeout 初始 1800 秒。
- Jetson Stem GPU Worker 初始并发 1。
- 外部 drum/bass/style/instrument/chord adapter 每个独立 timeout。
- 临时高 IO 优先使用 Jetson 本地 SSD，再由 Worker 发布 NAS。
- 模型在发布前预部署/预热并校验 hash，生产请求不临时无限下载模型。
- 每阶段记录 p50/p95 耗时、CPU、GPU/显存、RAM、临时磁盘、输出大小。

容量数值经真 Jetson 测试后由你和后端/运维共同定稿。

## 16. 配置项

### Tempo/Beat

- `BPM_ENABLE_BEAT_THIS`
- `BPM_ENABLE_ALL_IN_ONE`
- `BPM_ENABLE_ESSENTIA`
- `BPM_CONSENSUS_TOLERANCE`
- `BPM_BEAT_THIS_MODEL/DEVICE`
- `BPM_ALL_IN_ONE_MODEL/DEVICE`

### Downbeat

- `DOWNBEAT_ENABLE_MADMOM`
- `DOWNBEAT_MATCH_TOLERANCE_MS`
- `DOWNBEAT_AGREEMENT_F1`
- `DOWNBEAT_MADMOM_BEATS_PER_BAR`
- `DOWNBEAT_MAX_INTRO_BARS`
- `DOWNBEAT_PERIOD_TOLERANCE`

### Key

- `KEYFINDER_CLI/TIMEOUT_SECONDS`
- `KEY_MADMOM_COMMAND/TIMEOUT_SECONDS`
- `CHROMA_PATH`

### Feature/Style

- `FEATURE_DRUM_TRANSCRIBER_COMMAND`
- `FEATURE_BASS_TRANSCRIBER_COMMAND`
- `FEATURE_CHORD_TRANSCRIBER_COMMAND`
- `FEATURE_STYLE_TAGGER_COMMAND`
- `FEATURE_INSTRUMENT_TAGGER_COMMAND`
- `FEATURE_MODEL_TIMEOUT_SECONDS`
- `ESSENTIA_DISCOGS_MODEL_PATH/METADATA_PATH`
- `ESSENTIA_STYLE_MAX_DURATION_SECONDS`
- `CLAP_MODEL_PATH`

### Worker

- `ANALYSIS_CONTRACT_VERSION`
- `ANALYSIS_PIPELINE_VERSION`
- 各 stage timeout
- heartbeat/lease/max attempts
- `ANALYSIS_TEMP_DIR`
- worker concurrency
- `ENABLE_STARTUP_ANALYSIS=0`

每个配置必须有类型、默认/生产要求、是否 secret、修改是否需要重跑说明。模型路径不能直接输出给 App/RK。

## 17. 模型 Manifest

每次算法 release 提供：

```json
{
  "model_set_version": "harbeat-analysis-models-2026.08.28",
  "pipeline_version": "<git-sha+model-set>",
  "models": [
    {
      "name": "htdemucs",
      "version": "<version>",
      "sha256": "<64-hex>",
      "license": "<license>",
      "purpose": "stem_separation",
      "validation_version": "<version-or-null>"
    }
  ]
}
```

还需记录 Python/系统依赖、模型来源、GPU/CPU支持、许可证限制、验证域和降级路线。

## 18. Fixtures 和 Schema

每种 artifact 至少提供：

- ready/success；
- degraded；
- unavailable；
- low-confidence/needs_review；
- invalid：缺字段、错误类型、NaN、hash 不符。

建议仓库：

```text
contracts/schemas/analysis/
contracts/fixtures/analysis/
```

Python 后端、算法 adapter 和必要的 Dart/RK runtime 投影对同一 fixtures 做合同测试。

## 19. 你必须和后端定稿的内容

- 每个 stage 的输入、输出和 deadline；
- 哪些 Stage/Asset 是 Run succeeded 必需，哪些可 partial；
- Schema/version 和 artifact type；
- Worker 如何回收 staged result/回填 asset ID；
- 取消信号/子进程退出码；
- error code 的 retryable 语义；
- pipeline/model/calibration version 如何组成幂等键；
- 模型预部署、GPU 并发、临时目录和磁盘水位；
- 新旧 Run 并存和 current_analysis_run 切换/回滚。

## 20. 你必须和前端/产品定稿的内容

- BPM/Key/Style/energy 哪些字段允许展示；
- null、degraded、partial、needs_review 的用户文案；
- possible/confirmed 风格标签条件；
- 低置信 Downbeat 是否只隐藏还是提示；
- 上传分析各阶段的用户名称和进度权重；
- 审核前后算法状态与公开状态必须分开显示；
- 推荐使用 provisional 特征时只能作为弱证据。

## 21. 你必须和 RK 定稿的内容

- RK 执行需要的最小 Beat/Cue/Transition 数据；
- 网格点 inline 上限和独立 runtime metadata 格式；
- master/Stem/Render 格式、采样率、声道、大小；
- low-confidence/needs_review 时 RK 如何禁用强量化；
- Transition plan/render 与 audio-engine 版本兼容；
- capability 不支持 Stem/codec 时的降级/重新生成规则。

## 22. 四方协作统一规范

### 22.1 责任边界

| 负责人 | 负责 | 不负责 |
|---|---|---|
| 后端 | Jetson FastAPI、PostgreSQL、媒体/Manifest、Worker编排、设备云端数据、Gateway | 算法结论、RK现场执行、手机页面 |
| 手机前端 | App 页面、中央客户端、RK连接/状态/控制、用户反馈 | 中央业务真相、算法计算、RK执行事实 |
| 服务端算法 | Jetson 分析 adapter、模型、Schema、质量/验证、Stem/Feature/Style | 用户/设备业务表、手机/RK状态机 |
| RK | edge/sync/audio/input、本地SQLite/缓存、Operation/Event、现场事实 | 中央用户曲库、公共审核、服务端分析 |

### 22.2 合同唯一来源

| 合同 | 主维护 | 必须评审/消费 |
|---|---|---|
| 手机中央 OpenAPI | 后端 | 前端；算法评审分析 DTO |
| 音乐分析 Schema | 算法 | 后端校验；前端/RK评审投影 |
| RK Control/Event/Capability | RK | 后端、前端 |
| Manifest/Asset/Sync | 后端 + RK 共同维护 | 算法、前端 |
| 错误/幂等/离线恢复 | 后端定义公共码；RK定义本地执行码 | 四方互审相关部分 |

任何字段不能只在聊天中修改。统一变更流程：

```text
提出 Issue/ADR
→ 先修改 OpenAPI/JSON Schema/状态表
→ 增加 success/error/compatibility fixture
→ 受影响负责人评审
→ 更新生成客户端和合同测试
→ 再实现代码
→ 发布 release note、升级/回滚说明
```

### 22.3 数据和协议规则

- 新 ID 使用 UUID；重试不更换 operation_id/event_id/sync_job_id。
- 时间使用 RFC 3339 UTC；顺序使用 version/sequence，不靠跨机器时钟排序。
- 未知值使用 null；禁止用 0、空字符串或空数组冒充未知事实。
- 枚举只可兼容新增；删除/改语义必须升级版本。
- 状态转换必须有允许表，终态不回退。
- 写操作有 Idempotency-Key/request hash；消费者必须容忍重复消息。
- 中央业务以 PostgreSQL 为准；算法语义以 versioned artifact 为准；现场事实以 RK 最大 sequence 为准；页面只是投影。
- 日志统一 request_id/correlation_id/analysis_run_id/manifest_id/sync_job_id/operation_id/event_id。
- token、配对码、proof、签名 URL、NAS 路径不进入日志/fixture。

### 22.4 版本和共享 Fixture

- Central API：`/api/v1` + OpenAPI version。
- Analysis：contract/schema/pipeline/model/calibration 分别版本化。
- RK：control/event/capability 版本化并 capability negotiation。
- Manifest/PadPreset：schema version + immutable version/hash。
- 发布提供 git SHA、release ID、数据库/SQLite revision、模型/协议版本。
- 跨端升级至少验证当前版和前一兼容版；不兼容时明确拒绝。
- 共享 Schema/fixture 放在 `contracts/schemas/`、`contracts/fixtures/`。
- 每个合同至少有 success、null/degraded、invalid、unauthorized、conflict、timeout/retry、旧版兼容示例。

### 22.5 联调门槛和共同完成定义

开始联调前必须：Schema/OpenAPI 评审通过、四端解析同一 fixtures、后端 Mock/RK simulator/算法 fixture Worker 可运行、错误/超时/恢复用例明确、build/version 可查询。

跨端功能只有同时具备以下内容才算完成：

- 合同和字段说明；
- 正反 fixtures；
- 实现、权限和幂等；
- 单元/合同/集成测试；
- 日志、指标和可诊断错误；
- 断网/重启/重复包恢复；
- 配置、版本、部署和回滚；
- 受影响负责人评审记录。

## 23. 最终交付清单

- 独立、无 FastAPI 依赖的 stage adapter/CLI；
- `music-analysis-v1` 输入/输出实现；
- Core/Stem/Feature/Style JSON Schema；
- success/degraded/unavailable/invalid fixtures；
- 模型 manifest、hash、许可证和部署脚本；
- 当前验证报告和不可声称清单；
- pipeline/model/calibration 版本规则；
- 单元、schema、回归、benchmark 测试；
- CPU/GPU/RAM/磁盘/p50/p95 报告；
- timeout/cancel/OOM/adapter failure 测试；
- App DTO 和 RK Manifest 投影评审记录；
- 新旧算法版本差异和回滚说明。

## 24. 完成标准

- 后端 Worker 可以只凭标准输入调用算法，不导入 FastAPI app；
- 输出全部通过 JSON Schema，禁止 NaN/Infinity；
- 每个产物可追溯 input hash、pipeline/model/calibration version；
- 四个 Stem 全部验证后才 complete；
- optional adapter 失败可以形成 degraded/partial，不永久 running；
- 低置信 Downbeat 会 abstain/needs_review，不制造确定小节；
- provisional/candidate_only 不会进入普通用户确定标签；
- 同输入/版本/seed 结果语义可重复；
- Worker cancel/timeout/kill 不留下 ready 半成品；
- 模型升级生成新 Run/资产，不覆盖旧版本，可回滚；
- RK Manifest 获得足够执行数据但不包含调试/敏感内容；
- 当前验证指标和适用域有报告，不扩大宣传。

## 25. 仓库内详细合同位置

- `docs/backend-handoff-v1/04_音乐分析输入输出合同.md`
- `docs/backend-handoff-v1/05_分析任务状态机与Worker规范.md`
- `docs/backend-handoff-v1/09_资源Manifest与同步协议.md`
- `docs/backend-handoff-v1/11_配置部署安全与运维手册.md`
- `docs/backend-handoff-v1/12_联调测试与验收用例.md`
