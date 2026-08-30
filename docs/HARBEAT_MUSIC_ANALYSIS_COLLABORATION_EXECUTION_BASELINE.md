# HarBeat 音乐分析双人协作执行基线

- 版本：1.3
- 状态：定稿
- 生效日期：2026-08-30
- 适用人员：项目负责人、协作开发同事、音乐制作人、参与评审的算法或后端人员
- 修订说明：新增可直接执行的共同开发合同和机器校验 Schema；两名成员继续以工作流 B 为主

关联文档：

- [HarBeat 音乐分析架构与技术路线图](./HARBEAT_MUSIC_ANALYSIS_ARCHITECTURE_AND_TECHNICAL_ROADMAP.md)
- [HarBeat 69 项特征实施与训练顺序](./HARBEAT_69_FEATURE_IMPLEMENTATION_ORDER.md)
- [HarBeat 音乐分析共同开发合同 V1](./HARBEAT_MUSIC_ANALYSIS_DEVELOPMENT_CONTRACT_V1.md)

## 1. 文档效力

本文是 HarBeat 音乐分析项目的协作基线。两名主要执行人员在同一套范围、数据合同、模型评价方法和交付标准下工作。聊天记录、口头约定和临时实验不能覆盖本文；需要改变基线时，先提交书面决策记录，再修改文档版本。

本文已经固定总体方向：

1. 第一版先完成每小节内容、Phrase 和 Section，不以 21 类风格为第一交付物。
2. 精确测量继续使用 MIR/DSP 和专业模型，高层语义使用预训练 Embedding 与任务模型。
3. MERT 第一阶段冻结，只训练 Layer Mixer、融合层、时序模型和任务头。
4. `BarFeature[]` 是分析层交给 Planner 的主合同。
5. 训练、验证和生产推理必须使用相同的预处理、时间轴和 Schema。
6. Jetson/Analysis Worker 负责重分析，RK3588 负责现场实时执行。
7. 所有新特征经过目标域验证、校准和盲测后才能进入正式混音逻辑。

如果没有新的实验证据或产品需求，上述决定不在日常开发中反复讨论。

## 2. 项目第一阶段的共同目标

第一阶段交付 `Bar Understanding V1`。输入一首歌后，系统输出：

- BPM、Beat、Downbeat、Meter 和 Bar；
- 每个 Bar 的开始、结束和 Beat 位置；
- Vocal、Drum、Bass、Melody 的存在、主要状态、进入和结束；
- Phrase Boundary；
- Section Boundary；
- 粗粒度 Section；
- Energy、LUFS、频段能量、Chroma 和基础 Key；
- 每项结果的来源、置信度、模型版本和验证状态。

第一阶段不把以下项目作为阻塞项：

- 完整 21 类 Style；
- Production/Timbre 语义；
- Rap/Singing/Spoken 的全部细分类；
- 808/Synth/Electric Bass 的全部细分类；
- 完整 Groove taxonomy；
- Style、Groove、Timbre、Melody Metric Embedding；
- MERT 全量微调；
- 实时运行 MERT 或 Demucs。

这些能力按《69 项特征实施与训练顺序》后续推进，不进入 V1 的完成条件。

## 3. 开工前必须冻结的决定

下面的项目如果没有定稿，代码写得越多，返工越大。Kickoff 会议必须逐项确认，并把结论写入项目仓库。本章是会议摘要；字段类型、API、Worker、缓存、数据集和模型注册的正式定义以《HarBeat 音乐分析共同开发合同 V1》及其 JSON Schema 为准。

### 3.1 产品输出和使用场景

必须确认：

| 决定 | 本项目默认结论 | 最终批准人 |
|---|---|---|
| 第一消费者 | 自动混音 Planner，UI 只负责展示和人工修正 | 项目负责人 |
| 主输出粒度 | Bar；Beat 为底层，Phrase/Section 为上层 | 项目负责人 + 制作人 |
| 第一版目标 | 每小节内容、Phrase/Section、Entry/Ending | 项目负责人 |
| 风格优先级 | 保留现有基线，但不阻塞 V1 | 项目负责人 |
| 实时要求 | 离线分析，RK 现场只读取结果 | 项目负责人 + 后端负责人 |
| 失败行为 | 输出 `unknown`、`uncertain` 或 `needs_review`，不伪造确定答案 | 双方共同批准 |

需要补充一份制作人使用说明，明确 Planner 实际读取哪些字段、哪些错误会造成严重混音后果、哪些错误只影响展示。

### 3.2 音乐时间单位

必须书面确定：

- 秒是所有模型之间的绝对时间基准；
- Beat 是最小音乐节拍单位；
- Bar 由 Downbeat 和 Meter 确定；
- 4/4 音乐中 8 拍等于 2 小节；
- 产品中如果出现“8 拍”，必须说明指 8 个 Beat 还是 8 个 Bar；
- Phrase 长度不强制固定为 8 拍或 8 小节；
- Section Boundary 必须落在具体 Downbeat 或标记为非量化边界；
- 时间区间统一采用 `[start_sec, end_sec)`，包含开始、不包含结束；
- 所有时间均相对解码后的音频起点，不使用播放器本地偏移。

这组定义由音乐制作人和工作流 A 人工审核人共同批准。任何时间语义变化都视为 Schema 破坏性变更。

### 3.3 标签体系

必须冻结第一版标签：

#### 元素状态

```text
absent
background
foreground
entering
ending
unknown
```

#### 粗粒度 Section

```text
intro
main
build
breakdown
outro
unknown
```

#### 详细 Section 候选

```text
verse
pre_chorus
chorus
post_chorus
drop
break
bridge
solo
instrumental
```

详细标签可以在标注中保存，但 V1 模型先训练边界和粗粒度标签。每个标签必须有：

- 一句话定义；
- 至少三个正例；
- 至少两个容易混淆的反例；
- 边界如何选择；
- 无法判断时使用哪个标签；
- 多标签是否允许；
- 制作人发生分歧时的仲裁规则。

音乐制作人是音乐标签含义的批准人，算法人员不能根据模型方便程度单方面修改定义。

### 3.4 Feature Registry

历史 `feature_selection.csv` 的 69 项已经无损迁入唯一的
[`analysis_features_v1.jsonl`](../contracts/registries/analysis_features_v1.jsonl)。这表示 ID、状态、指标、样本量和别名关系已经纳管；只有音乐制作人补齐详细语义、正反例和边界案例并签字后，才可以宣称对应条目“全部处理完”。

每一行至少包含：

```text
feature_id
name
definition
time_level
output_type
source
dependencies
status
validation_metric
production_threshold
model_or_method_version
license
consumer
owner
```

Feature Registry 只允许通过代码评审修改。改名称不能更换 `feature_id`，改定义必须提升版本。

### 3.5 `BarFeature v1` 数据合同

正式 Payload 固定使用：

```json
{
  "schema_name": "harbeat.bar_feature",
  "schema_version": "1.0.0"
}
```

完整字段、类型、枚举、空值、来源、兼容和迁移规则已经在共同开发合同与 [`BarFeature` JSON Schema](../contracts/schemas/analysis/bar_feature_v1.schema.json) 中冻结。任何模型和规则都不能直接向 Planner 传递私有字段；它们先转换成通过 Schema 校验的 `BarFeature`。

### 3.6 数据来源、权限和许可

必须确认：

- 哪些歌曲允许用于内部研究；
- 哪些歌曲允许用于模型训练；
- 哪些歌曲允许用于商业模型；
- 是否可以保存和共享 Stem；
- 标注结果的所有权；
- 数据保存位置、访问权限和删除流程；
- 公开数据集与目标曲库的用途边界；
- MERT、Beat This、ADTOF、Demucs、Basic Pitch 等代码和权重的许可。

MERT 公开权重的非商业限制不阻止内部研究 PoC，但会阻止未经授权的商业部署。商业授权问题必须在生产接入前解决，并在模型注册表中记录。

### 3.7 数据集和拆分规则

必须冻结：

- Pilot 数据集：20–30 首，用于标签和工具试运行；
- PoC 数据集：150–300 首，用于 Bar Content 和 Basic Structure；
- 扩展数据集：1000 首以上，用于精细语义、Style 和 OOD；
- Train/Validation/Blind Test 的比例；
- Song-disjoint 规则；
- Artist-disjoint 规则；
- Remix、Edit、Live 与原版的分组规则；
- 标注人员和仲裁比例；
- 数据版本号和文件哈希。

同一首歌切出的片段不得跨越训练集和测试集。片段数量不能代替独立歌曲数和独立艺人数。

### 3.8 模型路线和基线

第一阶段默认采用：

```text
Frozen MERT
+ Explicit MIR/DSP Features
→ Fusion MLP/1D CNN
→ TCN
→ Bar Content Heads + Structure Heads
```

每个任务保留四组对照：

```text
Explicit-only
MERT + Linear Probe
MERT + Nonlinear Head
MERT + Explicit Fusion
```

结构任务再比较 MLP、TCN 和 BiGRU。小型 Transformer 只有在数据和长距离结构任务证明有必要时才进入正式实验。第一阶段不直接解冻 MERT。

### 3.9 评价指标和上线门槛

开工前必须确定每项特征的主要指标、辅助指标和业务门槛。不能等模型训练完成后再选择最有利的指标。

| 任务 | 主要指标 | 业务验收 |
|---|---|---|
| Beat/Downbeat | F-measure、持续错拍率 | 不允许未标记的整曲 Bar 偏移 |
| 每小节元素状态 | Macro/Micro F1 | 制作人能看懂每小节内容，状态不闪烁 |
| Entry/Ending | F1、时间偏差 | 误差不影响实际混入和退出 |
| Phrase/Section Boundary | ±1 Downbeat Boundary F1 | 制作人可以直接使用边界 |
| Section Label | Macro F1、每类召回 | 高频业务标签不能被少数大类掩盖 |
| 连续分数 | MAE、相关性、排序一致性 | 制作人认可高低顺序 |
| Style | Macro F1、Top-k、Calibration | 混合和未知风格有诚实输出 |
| Embedding | Recall@K、成对准确率 | 制作人试听认为相似结果有用 |

具体数值门槛由 Pilot 和现有基线测出后写入 Feature Registry。盲测集在门槛确定后保持封闭。

### 3.10 训练与运行一致性

必须统一：

- 音频解码器；
- 采样率和声道处理；
- 响度预处理；
- MERT 窗口、步长和拼接；
- Beat/Bar 对齐；
- 显式特征标准化；
- 缺失输入 Mask；
- 模型和阈值版本；
- 推理后平滑和结构约束。

Notebook 中验证有效、生产代码中没有实现的逻辑不算完成。

### 3.11 协作工具和权威位置

开工前必须确定：

- Git 仓库和主开发分支；
- 任务看板；
- 数据集存储；
- 模型和 Embedding 存储；
- 实验记录工具；
- 计算资源和 GPU 排期；
- 密钥和凭据管理；
- 备份和恢复方式。

聊天工具只用于通知。决定、数据版本、实验结果和交付状态必须写入各自的权威位置。

## 4. 推荐分工

两个人不按特征编号平分，也不再各占一条 A/B 工作流。现有后端已经覆盖了工作流 A 的大部分基础能力，真正需要持续投入的是标签、数据和模型。

两名成员都以工作流 B 为主。工作流 A 作为 GPT 支持线运行，由一名成员兼任人工审核人。只有 A 阻塞数据生产、训练或上线时，才进入人工主排期。

### 4.1 工作流 A：现有分析链收口与模型接入

GPT 负责主要实现；更熟悉后端、数据结构和部署的成员兼任人工审核人。人工审核不是全职岗位，不单独占用一个长期工作位。

根据 2026-08-30 的代码审计，现状如下：

| 模块 | 当前状态 | 接下来的工作性质 |
|---|---|---|
| 时间轴、BPM、Beat、Downbeat、Meter、基础 Bar/Phrase | 已有可运行实现 | 盘点、校准、统一时间合同，不重写 |
| 能量、响度、Key、Groove、Cue、Transition 等显式分析 | 已覆盖一批基础能力 | 映射到 Feature Registry，补测试和缺失项 |
| Demucs、Stem 活跃度和质量结果 | 已有流水线 | 验证结果、统一失败状态并映射到新合同 |
| 数据库字段、分析 API、Manifest、RK 音频缓存 | 已有生产基础 | 收口字段、版本、降级和端到端测试 |
| `BarFeature v1` | 文档中有设计，代码中尚无统一实现 | 新增 Schema、适配器、存储和校验器 |
| Worker | 有 RQ 代码雏形，现有入口仍混用同步调用、后台任务和线程 | 统一执行入口、依赖、部署和任务状态 |
| 特征与模型缓存 | 已有 RK 音频缓存，缺少版本化 Embedding/显式特征/模型结果缓存 | 新增缓存键、失效和迁移规则 |
| 机器学习生产链 | 现有规则结果已部分接入，新的多任务模型尚未贯通 | 新增推理适配器、版本记录和灰度接入 |

因此，工作流 A 以工程收口为主。除测试证明现有实现不满足要求外，不重写 `analysis.py`、Stem 流水线、现有 API 或 RK 缓存。

GPT 可以执行：

- 代码盘点和差距清单；
- Schema、适配器、Worker、缓存和 API 的实现；
- 数据库迁移草案、测试、部署配置和文档；
- 根据工作流 B 的模型合同编写推理封装。

人工审核人必须完成：

- 审核 Schema、数据库迁移、任务状态和缓存失效规则；
- 复核代码差异和自动化测试；
- 在真实环境运行 Fixture、性能测试和故障恢复测试；
- 批准合并与生产部署。

GPT 不决定音乐语义，不批准数据拆分、指标门槛或正式上线。

主要职责：

- 盘点现有分析输出，并逐项映射到 Feature Registry；
- 把现有时间轴、显式分析、Stem 和数据库字段统一到一个版本化合同；
- 实现 `BarFeature v1` Schema，以及“现有分析结果 → BarFeature”的适配器；
- 补齐每 Bar 聚合、来源、置信度、版本和缺失值语义；
- 将同步调用、后台任务、线程和 RQ 雏形收敛为一条正式 Worker 路径；
- 建立 Embedding、显式特征和模型结果的版本化缓存；
- 封装模型推理接口，让工作流 B 导出的模型可以替换 Mock 输出；
- 完成数据库、API、Manifest、Planner 和 RK 的字段兼容与生产接入；
- 为现有能力和新增连接层补齐端到端回归测试、性能测试和失败降级。

交付物：

- 一份“现有能力—目标 69 项特征—缺口”的对照清单；
- 一条确定的正式分析任务执行路径；
- `BarFeature` Schema、现有结果适配器、序列化和校验器；
- 统一的模型推理接口；
- 分析结果版本、缓存、失效和迁移机制；
- 从歌曲导入、现有分析、模型推理到 Planner 消费的端到端测试。

### 4.2 工作流 B：双人人工主线

两名成员的日常排期都放在工作流 B，但各自负责一条稳定子线，避免同时修改数据和训练代码。

#### 4.2.1 B1：标签与数据

适合由更了解产品目标、制作人需求和特征定义的人负责。

主要职责：

- Feature Registry 和 Label Guide；
- 与音乐制作人确定正例、反例和边界案例；
- 标注工具需求、Pilot 标注和仲裁；
- 数据收集、授权、清洗、去重、拆分和版本；
- 训练样本、弱标签和人工真值的来源记录；
- 固定 Fixture、盲测集和数据质量报告。

#### 4.2.2 B2：模型与评估

适合由更熟悉机器学习、训练工程和实验的人负责。

主要职责：

- MERT Embedding 提取规范和缓存合同；
- Linear Probe、Bar Content 多任务模型和结构模型；
- Fine Drum、Vocal、Bass、Groove、Style 等后续任务；
- 损失函数、阈值、校准和消融实验；
- 每类指标、失败样本和目标域盲测报告；
- Model Card、模型导出和模型注册。

B1 和 B2 共同交付：

- 版本化训练集清单和可复现训练配置；
- 训练脚本、模型权重、配置和哈希；
- 阈值、校准配置和独立验证报告；
- 能由工作流 A 推理接口加载的正式模型。

### 4.3 音乐制作人的职责

音乐制作人不承担代码进度，但拥有音乐语义的最终解释权：

- 批准标签定义；
- 标注和仲裁边界；
- 提供正例、反例和困难样本；
- 盲听模型结果；
- 判断错误是否影响实际混音；
- 批准进入/退出点的业务可用性。

制作人的意见必须落入 Label Guide、标注结果或验收记录，不能只停留在语音和聊天里。

### 4.4 人员安排

B1 和 B2 可以按两个人的技能互换。更熟悉后端的人同时兼任工作流 A 人工审核人，但他的主任务仍在 B1 或 B2。项目负责人继续决定范围、优先级和是否上线。

## 5. 决策权和复核关系

| 事项 | 负责人 | 必须复核 | 最终批准 |
|---|---|---|---|
| V1 范围和优先级 | 项目负责人 | 协作同事、制作人 | 项目负责人 |
| 音乐标签定义 | B1 负责人 | B2 负责人 | 音乐制作人 |
| `BarFeature` Schema | A 人工审核人（GPT 起草） | B1、B2 负责人 | 两名成员共同批准 |
| 数据集拆分 | B1 负责人 | B2 负责人 | 两名成员共同批准 |
| 模型结构和损失 | B2 负责人 | B1 负责人 | B2 负责人 |
| 生产推理接口 | A 人工审核人（GPT 实现） | B2 负责人 | A 人工审核人 |
| 指标和门槛 | B2 负责人 | B1 负责人、制作人 | 项目负责人 |
| 许可证与数据权限 | 项目负责人 | 双方 | 项目负责人 |
| 正式上线 | 项目负责人 | 双方、制作人 | 项目负责人 |

任何人都不能单方面修改 `BarFeature`、数据拆分、标签定义或盲测集。

## 6. 最高效的协作方式

### 6.1 先冻结接口，再并行开发

双方先共同完成四个合同：

1. Feature Registry；
2. Label Guide；
3. `BarFeature v1` Schema；
4. 固定的 10 首歌曲集成 Fixture。

合同冻结后，B1 和 B2 是人工主线，A 为两条主线提供工程支持：

```text
人工主线 B1                              人工主线 B2
标签定义与数据集                         MERT 与模型训练
标注、拆分与 Fixture                      评估、校准与模型注册
             \                          /
               固定 Schema 和数据版本
                          ↑
GPT 支持线 A：现有分析链收口、BarFeature、Worker、缓存、模型接入
                          ↑
                 A 人工审核人批准合并
```

B1 先提供标签合同和 Pilot 数据，B2 用固定 Fixture 和预计算特征启动实验。GPT 同时把现有输出适配成 `BarFeature`，再用 Mock 模型打通新增字段。三条线按固定合同交接，不互相等待完整交付。

### 6.2 每人同时只推进一个主任务

两人团队采用 WIP Limit 1：每人同时只有一个 B1 或 B2 主任务处于进行中。GPT 的 A 类任务单独排队，由 A 人工审核人在固定时间评审，避免临时打断模型和数据工作。发现额外问题时先记录，除非它阻塞当前交付。

任务大小控制在半天到两天。超过两天的任务拆成：

- 可独立验证的输入合同；
- 一个最小实现；
- 单元测试或离线评估；
- 集成和文档。

### 6.3 使用短分支和小评审

分支命名：

```text
codex/analysis-<topic>
codex/model-<topic>
codex/data-<topic>
codex/docs-<topic>
```

协作规则：

- 一个分支只解决一个问题；
- 分支尽量在一到两天内合并；
- 提交前同步主分支，解决冲突后再请求评审；
- 不在同一个分支混合数据、模型、接口和无关重构；
- 大模型权重、音频和大型 Embedding 不进入 Git；
- 每个 PR 应在 30 分钟内可以理解和评审；
- Schema、数据拆分和指标变化必须由另一名成员批准，GPT 不能充当批准人；
- 自动测试和最小 Fixture 通过后才合并。

### 6.4 单一事实来源

| 信息 | 权威位置 | 禁止替代方式 |
|---|---|---|
| 项目范围和架构 | `docs/` 中的版本化文档 | 聊天截图 |
| 特征定义和状态 | Feature Registry | 个人表格副本 |
| 标签定义 | Label Guide | 口头描述 |
| 数据集内容和拆分 | Dataset Manifest | 手工复制的文件夹 |
| 实验结果 | Experiment Registry | 只保存在 Notebook 输出 |
| 模型权重和配置 | Model Registry/对象存储 | 通过聊天发送文件 |
| 代码状态 | Git 分支和 PR | 本地未提交目录 |
| 产品任务 | 统一任务看板 | 两个人各自的待办列表 |
| GPT 任务和验收结果 | 统一任务看板、代码差异和测试记录 | 只保留在对话中 |

#### 6.4.1 GPT 支持线交付规则

每个 GPT 任务只处理一个明确目标。任务卡要写清允许修改的范围、输入合同、验收测试和禁止改动的部分。GPT 交付代码、测试结果、未解决风险和文档更新，A 人工审核人复核运行结果后才能合并。

涉及生产部署、凭据、数据删除、破坏性迁移或合同变更时，GPT 只能准备方案和代码，必须由人执行或明确批准。

### 6.5 实验必须可复现

每次实验记录：

```text
experiment_id
hypothesis
code_commit
dataset_version
split_version
feature_version
preprocessing_version
backbone_name_and_hash
config
random_seed
metrics
calibration
artifact_uri_and_hash
conclusion
next_action
```

同一模型名称不能指向不同权重。所有生产模型必须有 Model Card，写明用途、输入、输出、训练数据、指标、限制、许可证和降级方式。

### 6.6 先跑便宜实验，再跑贵实验

每项任务采用固定顺序：

1. 数据和标签 Sanity Check；
2. 规则或 Majority Baseline；
3. Explicit + 线性模型；
4. MERT + Linear Probe；
5. MERT + 非线性 Head；
6. MERT + Explicit Fusion；
7. 时序模型；
8. 必要时才解冻 Backbone。

前一层不能超过基线时，不启动更昂贵的训练。先找数据、标签、时间对齐或实现问题。

### 6.7 固定集成节奏

推荐节奏：

#### 每日异步更新

每人每天在同一任务看板写五行：

```text
昨天完成：
今天目标：
当前阻塞：
是否改动合同：
需要对方决定：
```

没有阻塞时不召开日会。

#### 每周两次 30 分钟集成会

只处理：

- Fixture 是否仍能端到端运行；
- Schema 是否需要变更；
- 当前模型是否可以接入；
- 下一个可交付增量；
- 阻塞和风险。

会议不逐条汇报已经写在看板上的进度。

#### 每周一次制作人验收

使用固定盲听集：

- 检查 Beat/Bar；
- 检查 Phrase/Section；
- 检查每小节元素；
- 记录最严重的五个错误；
- 选择下一轮标注和修复重点。

制作人反馈以样本 ID、时间范围、期望结果和严重等级记录。

### 6.8 尽早做端到端切片

不要先分别建设几个月再集成。第一个纵向切片应在少量歌曲上完整跑通：

```text
输入歌曲
→ Beat/Bar
→ 显式特征
→ MERT Embedding
→ 一个简单 Bar Head
→ BarFeature JSON
→ 数据库存储
→ Planner 读取
→ UI 或报告展示
```

即使第一版模型很简单，也要先证明数据能完整流动。之后每次只替换其中一个模块。

## 7. 标准工作流程

### 7.1 任务进入开发前

任务必须满足 Definition of Ready：

- 有明确用户或下游消费者；
- 输入和输出已定义；
- 使用的 Feature/Schema 版本明确；
- 有训练或测试数据；
- 有主要指标和验收方式；
- 有任务负责人和复核人；
- 已知依赖和许可证状态；
- 任务足够小，可以在两天左右完成一个可验证增量。

不满足这些条件的任务停留在 `Needs Definition`，不进入开发。

### 7.2 开发和训练

标准步骤：

1. 建任务卡；
2. 写假设和验收标准；
3. 固定输入 Fixture 或 Dataset Version；
4. 开短分支；
5. 先写最小验证或测试；
6. 实现；
7. 运行单元、集成或离线评估；
8. 更新 Registry/Model Card；
9. 请求指定人工审核人评审；A 类任务由 A 人工审核人评审，B 类任务由另一名成员评审；
10. 合并后跑端到端 Fixture；
11. 在看板记录结果和下一步。

### 7.3 完成条件

一个功能达到 Definition of Done，需要同时满足：

- 代码进入主分支；
- 自动测试通过；
- 输入输出符合当前 Schema；
- 目标域验证完成；
- 指标和置信区间已记录；
- 与简单基线完成对照；
- 没有训练/测试泄漏；
- 推理配置和训练配置一致；
- 模型、数据和特征版本可追溯；
- 失败和缺失输入有降级；
- 文档和 Registry 已更新；
- 指定人工审核人完成评审；
- 需要制作人验收的任务已经盲听通过。

训练出一个权重文件不算完成。

## 8. 任务卡模板

```markdown
# [任务名称]

Owner:
Reviewer:
目标交付日期:

## 要解决的问题

## 下游消费者

## 输入

## 输出

## 数据/Fixture 版本

## 主要指标和门槛

## 实施方案

## 风险和降级

## Definition of Done

## 结果
```

## 9. 实验记录模板

```markdown
# Experiment [ID]

## 假设

## 代码与配置

- commit:
- config:
- seed:

## 数据

- dataset_version:
- split_version:
- preprocessing_version:

## 模型

- backbone:
- head:
- loss:
- context_window:

## 结果

- primary_metric:
- secondary_metrics:
- calibration:
- per_class_results:

## 对照实验

## 失败样本

## 结论

## 是否进入下一阶段
```

## 10. 决策记录模板

遇到 Schema、标签、数据拆分或架构分歧时，使用：

```markdown
# Decision [ID]: [标题]

日期:
Owner:
Approvers:

## 当前问题

## 约束

## 方案 A

## 方案 B

## 证据

## 最终决定

## 影响范围

## 回滚条件
```

可逆决策优先用小实验解决，限定一到两天。不可逆或会影响数据合同的决定必须双方批准。

## 11. 代码评审清单

### 通用

- [ ] 只解决一个明确问题；
- [ ] 没有覆盖他人的未提交工作；
- [ ] 输入、输出和错误行为清楚；
- [ ] 单元测试或离线评估存在；
- [ ] 没有把密钥、音频、模型权重提交进 Git；
- [ ] 文档和 Schema 已同步。

### 音频分析

- [ ] 时间单位全部是秒；
- [ ] Beat/Bar 对齐有测试；
- [ ] 采样率和声道处理明确；
- [ ] 缺失、未知和真实零可以区分；
- [ ] 特征保存来源和版本；
- [ ] Fixture 输出没有无意变化。

### 模型训练

- [ ] 数据集和拆分版本固定；
- [ ] 同一首歌没有跨集合；
- [ ] 标准化只在训练 Fold 拟合；
- [ ] 下游任务使用折外上游预测；
- [ ] 随机种子和配置已保存；
- [ ] 有简单基线；
- [ ] 每类指标和失败样本已检查；
- [ ] 导出模型可以由生产推理代码加载。

## 12. 里程碑和联合验收

| Gate | 共同交付物 | 通过条件 | 通过后可开始 |
|---|---|---|---|
| G0 定义冻结 | Feature Registry、Label Guide、BarFeature、Fixture | 双方和制作人完成对应批准 | G1/G2 |
| G1 时间轴 | Beat/Downbeat/Bar、质量门控 | 目标样本无未标记整体错位 | G3 |
| G2 显式特征 | DSP、Key、Stem、Vocal/Bass 基础 | 单项验证和时间对齐通过 | G3 |
| G3 Bar Content | 每小节元素状态 | 盲测和制作人检查通过 | G4 |
| G4 Basic Structure | Phrase/Section Boundary、粗标签 | ±1 Downbeat 边界验收通过 | V1 接入 Planner |
| G5 精细语义 | Fine Drum、Vocal、Bass、Melody、Harmony | 各任务独立盲测通过 | G6 |
| G6 Groove | 节奏语法、Groove Head | 指标和转场排序均改善 | G7 |
| G7 Expanded Structure | 详细 Section、Ending、DJ Boundary | 不牺牲基础边界质量 | V2 |
| G8 Style/Metric | Style、Production、相似度向量 | Artist-disjoint 和制作人试听通过 | V3 |
| G9 Planner 闭环 | TransitionCandidate、MixPlan、RK 执行 | 同一候选贯穿评分、展示和执行 | 正式发布 |

任何 Gate 没通过，后续实验可以探索，但不能把依赖该 Gate 的能力标为正式完成。

## 13. 冲突和阻塞处理

### 13.1 技术分歧

双方先写出：

- 争议点；
- 两个可执行方案；
- 各自的验证成本；
- 需要比较的指标；
- 一到两天内可完成的最小实验。

用实验结果决策。没有证据时选更简单、可回滚、生产成本更低的方案。

### 13.2 标签分歧

制作人仲裁，并把案例补充进 Label Guide。算法人员不能通过修改标签来提高分数。

### 13.3 范围和优先级分歧

项目负责人决定。决定必须说明推迟了什么、增加了什么，以及对当前 Gate 的影响。

### 13.4 阻塞超过一天

任务状态改为 `Blocked`，写明：

```text
阻塞原因
已经尝试
需要谁提供什么
不解决会影响哪个 Gate
可否使用降级方案继续
```

不要在私聊中等待，也不要默默切换到另一个大任务。

## 14. 禁止事项

- 两个人各自维护一份 Feature 表；
- 在聊天中改变标签定义却不更新文档；
- 同时修改同一 Schema 而没有负责人；
- 把 Notebook 当成唯一训练实现；
- 手工复制数据集而不记录 Manifest；
- 同一首歌的片段跨 Train/Test；
- 用人工上游真值训练生产下游模型；
- 只报告最高 Accuracy，不报告每类表现和失败样本；
- 为了字段完整输出伪造的确定值；
- 模型权重没有配置、哈希和数据版本；
- 大型音频、Stem、Embedding 和权重进入 Git；
- 未经双方批准修改盲测集；
- 模型指标未通过就接入会触发危险混音动作的正式逻辑；
- 让 RK 在现场重新分析、重新选点或重新评分。

## 15. Kickoff 会议议程

Kickoff 控制在 90 分钟内，会前双方先阅读三份关联文档。

### 0–15 分钟：确认目标

- V1 是 Bar Understanding；
- V1 的下游是 Planner；
- Style、Metric 和 MERT 微调不阻塞 V1。

### 15–35 分钟：确认音乐定义

- Beat、Bar、8 拍、Phrase、Section；
- 元素状态；
- 粗粒度 Section；
- 制作人仲裁方式。

### 35–55 分钟：确认数据和合同

- Feature Registry；
- `BarFeature v1`；
- Pilot 曲库；
- 数据权限和拆分；
- 10 首固定 Fixture。

### 55–70 分钟：确认分工

- 谁负责 B1 标签与数据；
- 谁负责 B2 模型与评估；
- 谁兼任工作流 A 人工审核人；
- GPT 任务从哪里创建、如何验收；
- 谁维护各 Registry；
- 谁批准 Schema、指标和上线。

### 70–85 分钟：确认工具和节奏

- Git 分支；
- 任务看板；
- 数据、模型和实验存储；
- 每周集成和制作人验收时间。

### 85–90 分钟：创建第一批任务

第一批任务按负责人创建：

| 任务 | 默认执行人 |
|---|---|
| Feature Registry 导入、Label Guide V1 | B1 负责人 |
| Pilot 标注和 10 首 Fixture | B1 负责人，制作人参与 |
| MERT Embedding 提取和 Linear Probe | B2 负责人 |
| 评估基线、指标表和实验记录模板 | B2 负责人 |
| 现有分析能力与 69 项目标特征的差距清单 | GPT，A 人工审核人验收 |
| `BarFeature v1`、现有结果适配器和校验器 | GPT，A 人工审核人验收 |
| 正式 Worker 路径和部署检查表 | GPT，A 人工审核人验收 |

## 16. Kickoff 签署区

以下字段在 Kickoff 结束前填写。填写后，本文从“通用定稿”变成当前团队的执行合同。

| 项目 | 填写内容 |
|---|---|
| 项目负责人 |  |
| B1（标签与数据）负责人 |  |
| B2（模型与评估）负责人 |  |
| 工作流 A 人工审核人 |  |
| GPT 任务入口 |  |
| 音乐标签批准人 |  |
| 主开发分支 |  |
| 任务看板地址 |  |
| Dataset Registry 地址 |  |
| Experiment Registry 地址 |  |
| Model Registry 地址 |  |
| Pilot 数据集版本 |  |
| `BarFeature` Schema 版本 | `harbeat.bar_feature@1.0.0` |
| 共同开发合同版本 | `1.0.0` |
| 每周集成时间 |  |
| 每周制作人验收时间 |  |
| 生效日期 | 2026-08-30 |

签署确认：

```text
项目负责人：____________________  日期：____________

协作开发同事：__________________  日期：____________

音乐制作人：____________________  日期：____________
```

## 17. 执行摘要

开工前必须敲定五类事情：做什么、音乐概念如何定义、数据如何管理、模型如何验收、两个人如何交接。两名成员的主任务都放在工作流 B：一人负责 B1 标签与数据，一人负责 B2 模型与评估。工作流 A 由 GPT 主执行，其中一人兼任人工审核人。

先冻结 `BarFeature`、标签合同和 Fixture。B1、B2 随后并行推进，GPT 同时处理 A 类收口任务。每人一次只做一个人工主任务，每日异步更新，每周两次集成，每周一次制作人盲听。数据、模型和决定都要有版本记录；模型先通过简单基线和目标域盲测，再进入正式混音链。
