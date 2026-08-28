# HarBeat 服务端音乐算法负责人开工与协作说明

版本：`v1.1-draft`
收件人：Jetson 服务端音乐算法负责人
目标合同：`music-analysis-v1`
协作分支：`integration/harbeat-contract-first-v1`

## 1. 你的任务结果

你负责把当前仓库中的音乐分析能力整理成后端 Worker 可以稳定调用、版本化验证、部署和回滚的算法 release。

最终交付不是 FastAPI 路由，也不是直接更新业务数据库，而是：

- 独立 stage adapter/CLI 或无 FastAPI 依赖的 Python service；
- Core、Stem、Feature、Style 标准输入输出；
- 每种 JSON artifact 的正式 JSON Schema；
- staged 文件清单和媒体质量说明；
- 模型/阈值/校准/适用域/不可声称内容；
- ready/degraded/unavailable/invalid fixtures；
- CPU/GPU/RAM/磁盘/耗时和并发报告；
- 模型 manifest、hash、许可证、部署和回滚说明。

后端负责 Run/Stage/Worker/数据库/重试/资产登记；你负责算法真实产出、算法错误和质量语义。

## 2. 当前代码状态

当前主要实现：

| 路径 | 能力 | 判断 |
|---|---|---|
| `app/modules/library/analysis.py` | BPM/Beat/Downbeat/Meter/Key/Energy/Cue/Phrase/Transition | CURRENT/PARTIAL |
| `app/modules/library/background_tasks.py` | Core→Stem→Feature→Style 串行流程并写库 | 仅流程参考，与目标边界 CONFLICT |
| `app/modules/library/stem_analysis.py` | Stem 质量、鼓/Bass/Feature 编排 | CURRENT/PARTIAL |
| `app/modules/library/drum_analysis.py` | 鼓事件和质量，代码输出 v4 | CURRENT，但 Schema CONFLICT |
| `app/modules/library/high_frequency_feature_analysis.py` | Pre-style v5 聚合 | CURRENT/PARTIAL |
| `app/modules/library/feature_registry.py` | semantic level、validation status、fail-closed 注册 | CURRENT，尚未贯通 Style |
| `app/modules/library/feature_calibration.py` | 版本化校准和 `style_required_allowed` | CURRENT，文件尚未稳定发布 |
| `app/modules/library/high_frequency_style_classifier.py` | 21 类候选/边界/review | CURRENT/VALIDATION_BLOCKED |
| `config/model_validation/` | Tempo/Beat/Key/Drum/Bass 验证声明 | CURRENT，需绑定模型 hash/release |
| `modules/stem-separation/contracts/` | 历史 Drum/Stem/Pre-style Schema | CONFLICT/待迁移 |

当前完整测试结果：`568 passed, 3 skipped`。这证明算法基础较完整，但不代表已经满足 `music-analysis-v1`。

## 3. 当前必须先修复的合同和质量问题

### A-01 Style 未真正 fail-closed

当前 Feature 会产生 `validation_status` 和 `style_required_allowed`，但 Style 分类器的 positive/negative/required_any 主要按 availability、score、reliability 判断，没有阻止 `failed_validation` 或 `style_required_allowed=false` 满足风格硬条件。

必须修改为：

```text
required_any 可满足条件：
validation_status == validated
AND style_required_allowed == true
AND decision 不属于 rejected/unknown
```

provisional 是否可作为弱正负证据必须单独写清，但不得生成 confirmed 的必要条件。

### A-02 Drum Schema 版本漂移

代码 `DRUM_ANALYSIS_VERSION=drum_transcription_consensus_v4`，现有 Schema 仍固定 v3。必须选择 v4 作为新合同或回退代码，禁止继续两者并存。

### A-03 Pre-style v5 枚举漂移

连续型校准可能输出 `decision=measured`，现有 v5 Schema 未包含该枚举。任务书与实际字段还存在 `threshold/decision_threshold`、`flags/quality_flags`、`method/analysis_method` 的命名差异。

必须让“真实算法输出”通过 Schema，不允许测试只检查 Schema 文件里存在某些字段。

### A-04 Core 仍是旧扁平秒单位输出

当前 `analyze_audio_file(path)` 返回 `duration/beat_points/downbeats/cue time` 等旧字段，时间主要是秒；目标合同要求公共 envelope、毫秒、run/track/pipeline/input hash 和明确 analyzed duration。

必须通过 adapter 转换，不要直接破坏所有旧内部调用；旧字段兼容期限和删除版本需记录。

### A-05 Style 不能对外声称 confirmed

当前公开弱标签验证中，21 类第一候选命中约 30%，多标签 micro-F1 约 0.3333；仅 Funk/Disco/House 有小规模弱标签结果。当前所有 Style 默认只能是内部候选/possible，逐 style 的 heldout 验证门未通过前不得向 App 输出 confirmed。

## 4. 你的责任与禁止事项

你负责：算法定义、阈值、模型选择、校准、验证、Schema、fixtures、质量和性能。

你不得：

- 直接读写 users/tracks/devices/user_library_items 等业务表；
- 依赖 FastAPI request/session/global app；
- 自己把 AnalysisRun 或 StageRun 写成 completed；
- 输出 NAS 本地绝对路径作为合同字段；
- 未知时用 0 或空字符串伪装结果；
- 把 candidate/provisional/failed_validation 自动变成 validated；
- 在不升级版本时改变字段类型、单位、阈值语义或模型；
- 运行时无限下载模型或依赖无超时外网；
- 用 10 首内部曲库或弱标签结果宣布 21 类生产验证通过。

## 5. 目标 Stage 和发布门

| Stage | 输入 | 主要输出 | Run 影响 |
|---|---|---|---|
| `core` | 标准音频 | tempo/beat/downbeat/key/energy/cue/phrase/transition | P0 必需；失败 Run failed |
| `stem_separation` | 标准音频 | vocals/drums/bass/other + 文件清单 | RK Stem 能力所需；失败可 partial |
| `feature_analysis` | Core + Stems | Drum/Bass/节奏/和声/production/pre-style | Style 上游；失败可 partial |
| `style_analysis` | Core + Feature | 21 类候选/possible/review | 非现场硬依赖；失败可 partial |

Preview、waveform 和一般媒体转码由后端 Media Worker 主责；需要算法语义的 runtime metadata 由你与 RK 定义，后端负责资产发布和 Manifest 装配。

## 6. 标准 adapter

后端给每个 Stage 的输入至少包含：

```json
{
  "contract_version": "music-analysis-v1",
  "analysis_run_id": "<uuid>",
  "track_id": "<uuid>",
  "stage_key": "core",
  "input_asset": {
    "asset_id": "<uuid>",
    "storage_key": "tracks/.../source.flac",
    "sha256": "<64-hex>",
    "size_bytes": 123,
    "content_type": "audio/flac",
    "duration_ms": 243120,
    "sample_rate_hz": 44100,
    "channels": 2
  },
  "execution": {
    "pipeline_version": "<git-sha+model-set>",
    "requested_device": "auto",
    "max_analysis_duration_seconds": 420,
    "deadline_at": "<RFC3339 UTC>",
    "seed": 0
  },
  "upstream_artifacts": []
}
```

storage key 由受信任 Worker 解析为本地路径。算法不能接受 App 传入的任意路径。

输出公共 envelope 至少包含：

```text
schema_name/schema_version/contract_version
analysis_run_id/track_id/stage_key
pipeline_version/input_sha256/generated_at
status/quality/data/staged_files
```

stdout 只输出一个 JSON result，日志写 stderr；或由稳定 Python interface 返回等价对象。外部命令使用 argv、`shell=false`、timeout 和受控工作目录。

## 7. P0 任务拆解

### ALG-00 冻结算法基线

- 整理当前未提交/未跟踪算法改动；
- 形成 clean commit、release ID 和回归测试结果；
- 记录 Python/系统依赖和模型可用性；
- 区分生产代码、评估脚本、报告和版权数据。

### ALG-01 定稿 Schema 和 fixtures

- Core、Stem、Drum v4、Pre-style v5、Style 正式 Schema；
- 修复 `measured`、`failed_validation` 和字段命名；
- `additionalProperties` 策略、数组上限、单位、null 和 unknown enum；
- ready/degraded/unavailable/invalid/compatibility fixtures；
- 真实输出 Schema 测试。

### ALG-02 实现 stage adapter

- 无 FastAPI/SQLAlchemy 业务依赖；
- 标准 input、staging output 和结构化 error；
- SIGTERM/取消、deadline、timeout、输出大小限制；
- 不覆盖 ready 资产，不生成业务 asset UUID；
- 相同 input hash + pipeline/model/calibration + seed 语义可重复。

### ALG-03 Core 规范化

- 保留多引擎 tempo/beat/downbeat/key 路线；
- 输出真实 `duration_ms` 和 `analyzed_duration_ms`；
- 所有媒体时间转换为整数毫秒；
- 引擎结果有界；曲线/网格超限转独立 artifact；
- 低置信 Downbeat/Meter abstain，不制造确定 bar；
- 截断 420 秒必须有 quality flag。

### ALG-04 Stem 和文件产物

- Demucs htdemucs 四轨；
- 输出逻辑文件清单、variant、format、时长、采样率、声道；
- 四文件全部可探测才 complete；
- 质量指标不能把 reconstruction proxy 宣称为分离纯度；
- GPU OOM、timeout、缺模型、文件缺失有稳定错误。

文件 size/hash 和最终 asset_id 由 Worker复核/登记，算法可提供 staged 预计算但不能替数据库形成业务真相。

### ALG-05 Feature 和 fail-closed

- Feature registry、校准 entry、analysis method 精确匹配；
- measurement/derived/semantic 分层；
- `failed_validation` 必须 decision=rejected 且不能成为 Style required；
- 未登记特征默认 candidate_only；
- 为 Style classifier 增加 validation-aware positive/negative/required 规则和测试。

### ALG-06 Style 发布策略

- 21 个稳定 style ID 和 taxonomy version；
- `primary_style_candidate` 与 `primary_style` 分离；
- 当前产品投影只允许 possible/needs_review；
- 逐类建立 balanced heldout validation、threshold、precision/recall/F1、适用域；
- 只有通过 release gate 的 style 才允许 confirmed；
- 外部标签只作有界弱证据，不能绕过原生验证必要条件。

### ALG-07 模型 Manifest 和验证声明

每个 release 提供：模型名称、版本、文件 hash、来源、许可证、用途、设备支持、验证版本、适用域和降级路线。

验证声明必须绑定模型、后处理、阈值和数据 split，不只按 engine 字符串匹配。Beat/Tempo/Key/Drum/Bass 已有配置需要纳入 release；数据集许可限制必须进入部署审核。

### ALG-08 Jetson 性能验收

在真实 Jetson + NAS 记录每 Stage：p50/p95、CPU、GPU/显存、RAM、临时磁盘、输出大小、冷/热启动、并发和失败恢复。Demucs 初始并发为 1，最终数值以实测定稿。

## 8. App 和 RK 投影协作

对 App：只评审有界 AnalysisSummary。BPM/Key/energy 低置信时允许 null/隐藏；Style 当前只 possible，不把调试 evidence 暴露给普通用户。

对 RK：只输出运行必要的 tempo/beat/downbeat/cue/phrase/transition/runtime metadata 和资源引用；不下发模型调试信息、外部 metadata、NAS 路径或完整风格计算。

若 runtime metadata 超过 Manifest 上限，输出独立、hash 可校验的资产，由后端在 Manifest 中引用。

## 9. 你需要与其他负责人定稿

与后端：stage 输入输出、deadline、partial 门、error/retry、staging 文件回收、版本幂等键、current run 切换/回滚、GPU 并发。

与手机/产品：哪些字段允许展示；null/degraded/partial 文案；possible/confirmed 条件；上传分析进度权重。

与 RK：最小 beat/cue/transition 数据；inline 上限；codec/采样率/声道；低置信时禁用哪些强量化；audio-engine 版本兼容。

## 10. 完成标准

- 后端只凭标准输入可调用所有 Stage；
- 算法不导入 FastAPI 业务上下文、不写业务数据库；
- 真实输出全部通过正式 JSON Schema，无 NaN/Infinity；
- 产物可追溯 input/pipeline/model/calibration version；
- failed/candidate/provisional 不会生成不允许的 confirmed Style；
- timeout/cancel/OOM/模型缺失不会留下 ready 半成品；
- 模型和算法升级创建新 Run/asset，可并存和回滚；
- 模型 manifest、许可证、验证和 Jetson 性能报告完整；
- 后端、手机和 RK 完成各自投影评审。

## 11. 开工回执

请首先回复：你接受的 Core/Stem/Feature/Style 当前基线、需要修改的 Schema 版本、Style fail-closed 修复方案、第一批可交给后端的 fixtures，以及需要后端/RK决定的 runtime metadata 问题。
