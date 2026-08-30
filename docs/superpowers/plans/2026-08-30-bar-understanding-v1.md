# Bar-level Music Understanding V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 HarBeat 的音乐分析合同、69 项特征资产和现有显式分析结果整理成可测试、可版本化的小节级分析基线，为后续 MERT 与多任务模型训练提供稳定输入输出。

**Architecture:** `contracts/` 是跨后端、算法和客户端的唯一机器合同源；现有 DSP/规则分析继续产生可解释证据，适配层只做无损规范化并显式标注缺失状态。训练路线从数据与合同开始，先建立 69 项注册表和 BarFeature 时间轴，再接入 MERT 缓存与模型训练，避免让模型结构先于标签和评估标准。

**Tech Stack:** Python 3.11+、JSON Schema Draft 2020-12、jsonschema、pytest/unittest、现有 FastAPI/SQLAlchemy 音频分析模块。

---

## Task 1: 冻结分析合同的仓库位置与校验入口

**Files:**
- Create: `app/tests/test_music_analysis_contracts.py`
- Create: `contracts/schemas/analysis/analysis_job_v1.schema.json`
- Create: `contracts/schemas/analysis/annotation_record_v1.schema.json`
- Create: `contracts/schemas/analysis/bar_feature_v1.schema.json`
- Create: `contracts/schemas/analysis/dataset_track_v1.schema.json`
- Create: `contracts/schemas/analysis/feature_registry_entry_v1.schema.json`
- Create: `contracts/schemas/analysis/mert_cache_manifest_v1.schema.json`
- Create: `contracts/schemas/analysis/model_manifest_v1.schema.json`
- Create: `contracts/schemas/analysis/track_analysis_v1.schema.json`
- Modify: `contracts/README.md`
- Modify: `contracts/schemas/analysis/README.md`
- Modify: `requirements.txt`

- [x] 写合同发现测试：必须恰好发现八份 V1 Schema、`$id` 唯一、所有本地 `$ref` 可解析。
- [x] 运行合同测试，确认因 Schema 尚未迁入而失败。
- [x] 迁入八份 Schema，将状态枚举与现有特征注册表的真实状态对齐。
- [x] 增加 `jsonschema==4.26.0`，更新合同目录 owner、reviewer、版本和兼容规则。
- [x] 再运行合同测试，确认通过。

## Task 2: 建立代表性合同 Fixture

**Files:**
- Modify: `app/tests/test_music_analysis_contracts.py`
- Create: `contracts/fixtures/analysis/bar_feature_v1.valid.json`
- Create: `contracts/fixtures/analysis/track_analysis_v1.valid.json`
- Modify: `contracts/fixtures/analysis/README.md`

- [x] 先写有效 Fixture、越界值和非法缺失状态测试。
- [x] 运行测试，确认有效 Fixture 尚不存在而失败。
- [x] 添加最小但完整的 BarFeature 与 TrackAnalysis Fixture。
- [x] 验证有效样本通过、越界概率和非法缺失样本被 Schema 拒绝。

## Task 3: 把历史 69 项清单变成机器可读 Feature Registry

**Files:**
- Create: `app/tests/test_export_feature_registry.py`
- Create: `scripts/export_feature_registry_v1.py`
- Create: `contracts/registries/analysis_features_v1.jsonl`
- Modify: `contracts/README.md`

- [x] 写测试：输入 `feature_selection.csv` 后必须生成 69 个唯一 `feature_id`，并保留验证状态、指标、样本量和别名关系。
- [x] 运行测试，确认导出器不存在而失败。
- [x] 实现确定性导出器，使用 `app/modules/library/feature_registry.py` 补齐语义层级和默认状态。
- [x] 每条记录通过 `feature_registry_entry_v1.schema.json`；不把缺失指标伪造成 0。
- [x] 生成并提交 JSONL，重复运行哈希一致。

## Task 4: 建立小节边界与 BarFeature 适配层

**Files:**
- Create: `app/tests/test_bar_feature_adapter.py`
- Create: `app/modules/library/bar_feature_adapter.py`

- [x] 写测试覆盖：标准 4/4、小节尾部不足、无 downbeat、窗口重叠、真实 0 与 unknown 的区别。
- [x] 运行测试，确认适配器不存在而失败。
- [x] 用 downbeat 优先、beat+拍号降级的方式建立 `[start_sec, end_sec)` 小节区间。
- [x] 从现有 BPM、energy 和 stem activity 证据映射 BarFeature；不可用字段使用带原因的 availability wrapper。
- [x] 用 JSON Schema 校验每个输出小节并运行回归测试。

## Task 5: 生成 TrackAnalysis V1，不覆盖旧版 Planner 适配器

**Files:**
- Create: `app/tests/test_track_analysis_v1_adapter.py`
- Create: `app/modules/library/track_analysis_v1_adapter.py`
- Modify: `app/modules/dj_set/track_analysis_adapter.py`

- [x] 先写测试要求稳定 `analysis_id`、显式版本、零基索引和完整 bars 数组。
- [x] 保留 `build_track_analysis_v2` 兼容入口，新增 V1 合同入口，不用默认数值伪装缺失事实。
- [x] 验证新输出通过 `track_analysis_v1.schema.json`，旧 V2 入口继续可导入。

## Task 6: 文档、质量门与下一阶段训练入口

**Files:**
- Create: `docs/HARBEAT_MUSIC_ANALYSIS_DEVELOPMENT_CONTRACT_V1.md`
- Create: `docs/HARBEAT_MUSIC_ANALYSIS_COLLABORATION_EXECUTION_BASELINE.md`
- Create: `docs/HARBEAT_MUSIC_ANALYSIS_ARCHITECTURE_AND_TECHNICAL_ROADMAP.md`
- Create: `docs/HARBEAT_69_FEATURE_IMPLEMENTATION_ORDER.md`
- Modify: `docs/superpowers/plans/2026-08-30-bar-understanding-v1.md`

- [x] 迁入四份已定稿文档，修正所有 Schema 链接指向 `contracts/schemas/analysis/`。
- [x] 在主合同中明确当前里程碑只冻结数据结构，不宣称模型准确率已经达标。
- [x] 运行合同、注册表、适配器和现有 DJ V2 入口回归；Python 3.9 无法执行依赖 3.10+ 类型语法的旧流水线套件，已记录为环境限制。
- [x] 记录下一阶段入口：30 首小节级金标集、MERT 离线缓存、线性 probe、序列模型与校准。
