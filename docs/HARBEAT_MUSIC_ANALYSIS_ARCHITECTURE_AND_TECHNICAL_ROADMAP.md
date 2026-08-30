# HarBeat 音乐分析架构与技术路线图

- 版本：2026-08-30
- 状态：目标架构草案，供产品、音乐制作、算法和后端团队共同评审
- 范围：从输入一首完整歌曲，到输出可供自动混音使用的结构化音乐特征

关联文档：

- [HarBeat 69 项特征实施与训练顺序](./HARBEAT_69_FEATURE_IMPLEMENTATION_ORDER.md)
- [HarBeat 音乐分析共同开发合同 V1](./HARBEAT_MUSIC_ANALYSIS_DEVELOPMENT_CONTRACT_V1.md)

## 1. 文档目的

HarBeat 的分析目标是建立一张可供混音引擎读取的音乐地图，整曲风格标签只是其中一项。系统需要知道每一拍和每个小节发生了什么、音乐在什么位置换乐句和段落、哪些元素正在进入或退出，以及两个片段是否适合衔接。

目标输出包括：

- 全曲级信息：BPM、调性、风格概率、响度和全曲向量；
- 段落级信息：Intro、Verse、Chorus、Drop、Break、Outro 等结构；
- 小节级信息：人声、鼓、贝斯、旋律、律动、能量、和声和边界状态；
- 事件级信息：Beat、Downbeat、鼓击、贝斯音符和进入/退出事件；
- 帧级信息：响度、频段能量、Chroma、人声活动和 MERT 隐状态；
- 混音级信息：安全进入点、退出点、冲突风险和转场候选。

## 2. 当前实现与目标实现

现有 HarBeat 已经具备一套规则和 MIR/DSP 音频分析链，包括 BPM、Beat、Downbeat、调性、能量、LUFS、规则版 Phrase、规则版 Groove、Demucs 四轨分离、Stem 活跃窗口和基础转场建议。现有代码可为第一版自动混音提供输入，但高层语义仍以规则和代理指标为主。

目标架构会保留这些可测量能力，再加入预训练音乐表示和监督学习模型。

| 模块 | 当前状态 | 目标状态 |
|---|---|---|
| BPM、Beat、Downbeat、Bar | 已有规则/模型链，仍需目标曲库校准 | 建立统一时间轴，增加质量门控和人工复核闭环 |
| Demucs 四轨分离 | 已接入后台分析 | 保留，增加 Stem 质量、残留和伪影检查 |
| 响度、能量、频谱 | 已实现 | 统一为 Frame/Bar 级显式特征 |
| Phrase、Section | 已有规则版 | 以 MERT、显式特征和 TCN/BiGRU 训练结构模型 |
| Groove、Mood、Danceability | 主要是规则和代理指标 | Groove 改为目标域监督学习；Mood 和 Danceability 独立验证 |
| 风格识别 | 当前生产代码仍是规则、元数据和 Spotify 融合；实验报告已验证 Embedding 路线更好 | 使用预训练 Embedding 和多标签分类头；规则只负责解释和约束 |
| 人声、贝斯高层语义 | 尚未形成可靠训练模型 | 使用 Vocal/Bass 专用任务头 |
| 相似度 | 尚未形成正式能力 | 分别训练 Style、Groove、Timbre、Melody Embedding |

因此，本文中的 MERT、多任务头和 Metric Learning 属于目标架构，不代表当前代码已经完成这些模型。

## 3. 架构原则

### 3.1 能直接测量的内容不交给语义模型猜

BPM、拍点、响度、峰值、频段能量、音符起止和 Chroma 有明确的信号定义，应由专业模型或 DSP 直接计算。MERT 可以辅助质量判断，但不应取代精确测量。

### 3.2 难以手写规则的语义交给监督学习

Rap、Singing、808、Groove、Phrase、Section、Style 和 Production 语义依赖复杂的声音组合。它们由预训练音乐表示和目标域标签学习，不再依赖大量人工阈值。

### 3.3 所有结果必须落到统一时间轴

模型输出不能停留在一个整曲标签或高维向量。每项结果必须能映射到 Frame、Beat、Bar、Phrase、Section 或 Song，并保存开始、结束、置信度和来源。

### 3.4 共享重计算，分开任务判断

MERT 对一首歌只运行一次。不同任务共享它产生的时间序列 Embedding，再使用各自的小型适配层和输出头。不同任务可以共享表示，但不强迫使用相同时间范围或相同损失函数。

### 3.5 离线分析与现场执行分离

Jetson 或分析 Worker 负责 MERT、Demucs 和结构模型等重任务。RK3588 只接收版本化分析结果和混音计划，负责缓存、实时播放、DSP 和安全降级，不在现场重新运行重分析。

## 4. 系统边界

```text
授权音源
   │
   ▼
Jetson / Analysis Worker
   ├─ 基础 MIR/DSP
   ├─ Demucs 与 Stem 分析
   ├─ MERT Embedding
   ├─ 多任务语义模型
   └─ TrackAnalysis / BarFeature
           │
           ▼
Planner / Transition Scorer
   ├─ 候选歌曲排序
   ├─ 进入点与退出点选择
   └─ MixPlan
           │
           ▼
RK3588
   ├─ 素材下载与校验
   ├─ 双 Deck 播放
   ├─ EQ、Stem Curve、FX
   └─ 现场安全降级
           │
           ▼
音响与执行状态回传
```

职责边界：

| 组件 | 负责 | 不负责 |
|---|---|---|
| App | 展示结构、选择任务、提交意图、显示执行状态 | 不分析音频，不重新选择转场点 |
| Jetson/API | 保存权威分析、生成候选和计划、调度重任务 | 不承担毫秒级音频执行 |
| Analysis Worker | Demucs、MERT、MIR/DSP 和任务模型推理 | 不直接控制声卡 |
| PostgreSQL/对象存储 | 保存版本化分析和音频资产 | 不负责实时状态 |
| RK3588 | 缓存、播放、DSP、物理控制和实际执行状态 | 不重新训练或重分析歌曲 |

## 5. 端到端分析数据流

```text
Original Mix
   │
   ├───────────────┐
   ▼               ▼
统一时间轴         Demucs 四轨
Beat/Downbeat      vocals/drums/bass/other
Bar/Tempo          │
   │               ├─ Drum Events / Grid
   │               ├─ Bass Notes / Grid
   │               ├─ Vocal Activity / F0
   │               └─ Melody / Harmony 辅助
   │
   ├───────────────┐
   ▼               ▼
显式 MIR/DSP       MERT Shared Representation
响度/频谱/调性      Frame Embedding Sequence
   │               │
   └───────┬───────┘
           ▼
多尺度对齐与特征融合
Frame → Beat → Bar → Phrase → Section → Song
           │
           ├─ 片段内容多任务网络
           ├─ 结构多任务网络
           └─ 风格与相似度网络
           │
           ▼
BarFeature[] + Sections[] + Events[]
           │
           ▼
Transition Candidate → MixPlan → RK 执行
```

## 6. 统一时间层级

系统以秒为绝对时间基准，以 Beat 和 Bar 为音乐结构基准。

| 层级 | 典型分辨率 | 主要内容 | 主要消费者 |
|---|---:|---|---|
| Frame | 模型原始帧率或 50–100 ms 聚合 | MERT 隐状态、响度、Chroma、人声活动、频段能量 | 上层聚合和事件检测 |
| Beat | 每拍 | Beat、Downbeat、鼓击、Bass Note、节拍相位 | 节拍对齐、量化和转场执行 |
| Bar | 每小节 | 元素状态、能量、局部调性、Groove、边界概率 | 分析主工作层、Planner |
| Phrase | 通常为多个小节，不固定长度 | 乐句边界、进入/结束和内部位置 | 转场点选择 |
| Section | 完整功能段落 | Intro、Verse、Chorus、Drop、Break、Outro | 曲目结构和混音角色 |
| Song | 全曲 | 全局 BPM、Key、Style、LUFS、全曲向量 | 搜索、推荐和候选过滤 |

“8 拍”不能作为唯一固定结构。4/4 音乐中 8 拍等于 2 小节，但制作语境里也可能有人把“8 拍”口语化地指成 8 小节。底层保存 Beat 和 Bar，产品层按需要生成 8 拍、4 小节、8 小节或 16 小节视图。

## 7. 分析模块

### 7.1 Canonical Timeline

职责：

- 计算全局 BPM、候选 BPM 和置信度；
- 生成 Beat、Downbeat、Meter 和 Bar；
- 计算局部 Tempo 和 Tempo Stability；
- 将所有模型的原始时间坐标转换成绝对秒；
- 标记需要人工复核的拍点和小节错位。

这一层是全系统的硬依赖。时间轴错误会同时污染鼓点网格、Phrase、Section、Entry/Ending 和最终转场点。

### 7.2 Stem Separation

默认使用 Demucs `htdemucs` 输出：

- vocals；
- drums；
- bass；
- other。

每次分轨必须保存模型版本、输入文件哈希、采样率、Stem 完整度和重建质量代理值。Stem 不完整时保留 Original Mix，并让下游模型进入降级模式。

### 7.3 显式 MIR/DSP

#### 节奏与事件

- Beat、Downbeat、Meter、Bar；
- Kick、Snare、Clap、Closed Hat、Open Hat、Cymbal、Tom、Percussion；
- 16 分音符 Drum Grid；
- Drum Density、Transient Density。

#### 贝斯

- Note Onset、Offset、Pitch、Bend、Confidence；
- Bass Activity、Sub Energy、Attack、Decay/Release Proxy；
- Pitch Movement、Note Density、Bass Grid。

#### 人声

- Vocal Activity、Density；
- F0、F0 Coverage、Pitch Range、Pitch Sustain；
- Onset Density、Melodic Contour。

#### 和声

- Global Key、Mode、Camelot、Confidence；
- Chroma/HPCP；
- Bar-level Chroma；
- Local Key 和 Chord 只作为候选，经过商业混音目标域验证后才能升级。

#### 声学和混音

- Integrated LUFS、Short-term Loudness、True Peak、Dynamic Range；
- Sub、Bass、LowMid、Mid、HighMid、High Energy；
- Spectral Centroid、Spectral Flux、Transient Density。

### 7.4 MERT Shared Representation

MERT 是预训练音乐编码模型。它读取完整 Mix，输出随时间变化的高维隐状态。MERT 是模型，Embedding 是模型产生的数字表示。

第一阶段使用冻结的 MERT：

```text
Original Mix
   ↓
Frozen MERT
   ↓
多层 Hidden States
   ↓
Learnable Layer Mixer
   ↓
Frame / Beat / Bar / Section Embedding
```

实现注意事项：

- 完整 Mix 是默认输入，Vocal/Bass 任务可以进行 Full Mix 与 Stem A/B 实验；
- 使用约 5 秒窗口和重叠步长时，需要明确中心裁剪或加权拼接规则；
- 所有窗口保存绝对时间戳，禁止按数组索引猜时间；
- MERT-v1-95M 有 12 个 Transformer 层；若包含输入 Embedding 状态，程序可能返回 13 组隐状态；
- Bar Mean Pooling 适合一般语义，Groove 不应只依赖均值，需要保留 Drum/Bass Grid 或局部 Token 序列。

### 7.5 多尺度特征融合

不同任务需要不同上下文：

```text
Frame/Beat：鼓击、音符、人声活动
1–4 Bars：人声、贝斯、律动、旋律状态
8–32 Bars：Phrase、Section、Ending、Style Change
30 秒或全曲：Global Style、Production、全曲相似度
```

统一融合表示可以写成：

```text
Bar Representation
= MERT Bar Embedding
+ Drum/Bass Grid Encoder
+ Vocal/Bass/Melody Explicit Features
+ Harmony/Acoustic Features
+ Quality Mask
```

缺失 Stem 或低置信特征必须通过 Mask 明确告诉模型，不能用零值假装真实测量结果。

## 8. 三组多任务网络

### 8.1 网络 A：片段内容理解

目标：回答当前一拍或小节里有什么。

共享输入：MERT Bar Embedding、人声/贝斯显式特征、Drum/Bass Grid、能量、频谱和 Chroma。

推荐结构：

```text
Numeric Features → MLP ───────┐
Drum/Bass Grid → 1D CNN ──────┼→ Fusion Encoder
MERT Bar Embedding ────────────┘
                                  ├─ Vocal Adapter → 多标签头
                                  ├─ Bass Adapter → 多标签头
                                  ├─ Groove Adapter → 分类/回归头
                                  └─ Melody Adapter → 状态/回归头
```

主要输出：

- Vocal：Absent、Background、Foreground、Entering、Ending、Rap、Singing、Spoken、Chop；
- Bass：Absent、Present、Entering、Ending、808、Synth、Electric、Other；
- Groove：类型、强度、Swing、Syncopation、Kick/Bass 关系；
- Melody：Activity、Density、Foreground、Entering、Ending。

### 8.2 网络 B：结构理解

目标：根据前后小节识别边界、段落和元素变化。

第一版使用 TCN；BiGRU 作为对照；数据量和长距离重复任务成熟后再评估小型 Transformer Encoder。

```text
连续 8–32 个 Bar Representation
              ↓
        Shared TCN/BiGRU
       ├─ Phrase Boundary Head
       ├─ Section Boundary Head
       ├─ Section Label Head
       ├─ Vocal/Melody Ending Head
       └─ Style/Energy Change Head
```

结构标签需要增加持续时间和转移约束，防止模型在相邻小节间频繁闪烁。可先使用概率平滑、最短段落长度和边界合并，后续再评估 CRF、HMM 或半马尔可夫解码。

### 8.3 网络 C：风格与相似度

目标：回答片段是什么风格、整体制作特征是什么、与其他片段在哪个维度相似。

```text
8–16 Bars / Section / 30 秒 MERT Sequence
                       ↓
                 Attention Pooling
                       ↓
              Shared Long-context Encoder
       ├─ 21 类 Style Sigmoid Head
       ├─ Style Stability Regression Head
       ├─ Style Metric Head
       ├─ Groove Metric Head
       ├─ Timbre Metric Head
       └─ Melody Metric Head
```

分类头与相似度头解决不同问题：分类头输出已定义标签的概率；Metric Head 输出 128 或 256 维归一化向量，用距离表示相似性。Style、Groove、Timbre 和 Melody 使用独立投影头，不能用一个距离代表所有相似关系。

## 9. 输出头和训练目标

| 任务 | 输出层 | 常用损失 | 示例 |
|---|---|---|---|
| 互斥分类 | Softmax | Cross Entropy | Section Label |
| 多标签分类 | Sigmoid | Binary Cross Entropy/Focal Loss | Style、Rap/Singing、Bass Type |
| 连续回归 | 线性层或 Sigmoid | Huber/MSE/排序损失 | Groove Strength、Activity |
| 边界检测 | Sigmoid | 加权 BCE/Focal Loss | Phrase/Section Boundary |
| 相似度 | L2 归一化向量 | Contrastive/Triplet/InfoNCE | Groove/Timbre Similarity |

总损失是各任务损失的加权和：

```text
L_total = Σ λ_task × mask_task × L_task
```

`mask_task` 用于处理共享曲库中部分歌曲只标了某些任务的情况。任务权重不能长期固定拍脑袋设置，应根据标签规模、梯度冲突和验证集表现调整。

## 10. BarFeature 数据合同

`BarFeature` 是分析层和 Planner 之间的主合同。本文早期版本中的 JSON 只是架构示意，不能直接用于实现；字段类型和校验规则已经移到《HarBeat 音乐分析共同开发合同 V1》。

正式 Payload 使用：

```json
{
  "schema_name": "harbeat.bar_feature",
  "schema_version": "1.0.0"
}
```

V1 必填分组是 `timing`、`structure`、`elements`、`acoustic`、`harmony`、`rhythm` 和 `quality`。每个特征都保存 availability、confidence、provenance 和 validation status。缺失、未计算和真实零的处理以 [`BarFeature` JSON Schema](../contracts/schemas/analysis/bar_feature_v1.schema.json) 为准。

## 11. 数据与标注体系

### 11.1 先标混音需要的结果

音乐制作人优先标注：

- Beat/Downbeat 修正；
- Phrase 和 Section 边界；
- Section 标签；
- 每小节 Vocal、Drum、Bass、Melody 状态；
- 元素进入和结束；
- 适合进入、退出和禁止混入的位置。

标注工具应先自动生成候选，制作人主要负责拖动边界、批量标记范围和修改标签。不要让制作人逐小节从零填写。

### 11.2 标注层级

Section 建议保存两级标签：

- 粗粒度：Intro、Main、Build、Breakdown、Outro、Unknown；
- 细粒度：Verse、Pre-Chorus、Chorus、Post-Chorus、Drop、Break、Bridge、Solo、Instrumental。

第一版模型先学习边界和粗粒度标签，细粒度标签在一致性足够后启用。

### 11.3 数据拆分

- 同一首歌的片段只能出现在一个数据集合；
- Remix、Radio Edit、Live 和原版尽量放在同一组；
- 风格、音色任务采用 Artist-disjoint 测试；
- 报告独立歌曲数和艺人数，不能只报告片段数；
- 保留一个从未参与阈值、模型和超参数选择的盲测集。

### 11.4 下游输入防泄漏

Style Head 使用 Vocal、Bass、Groove 等上游结果时，训练阶段必须使用上游模型的折外预测概率，不能使用人工真值替代运行时预测。Section 扩展模型同样遵守这一规则。最终评估必须从原始音频完整跑到输出。

## 12. 训练策略

### 12.1 每个任务保留四组基线

```text
1. Explicit Features + 线性模型
2. MERT Embedding + Logistic Regression/Linear Probe
3. MERT Embedding + 非线性任务头
4. MERT + Explicit Features + Fusion Head
```

这四组实验分别回答：显式特征是否足够、MERT是否有用、复杂任务头是否有用、融合是否真的提高效果。

### 12.2 第一阶段冻结 MERT

第一轮只训练：

- Layer Mixer；
- Projection；
- 显式特征归一化层；
- Fusion Encoder；
- TCN/适配层；
- 各任务输出头。

只有当数据规模、标签质量和消融实验都支持时，才评估部分解冻或 LoRA。

### 12.3 校准和未知类别

模型上线前需要：

- 每类阈值校准；
- Reliability Diagram、ECE 和 Brier Score；
- Unknown/OOD 测试集；
- 最大概率、熵、Embedding 距离和标签冲突联合判断；
- 低置信结果降级为 `unknown` 或 `needs_review`。

OOD 规则本身也必须用已知未知样本验证，不能把熵高直接等同于未知风格。

## 13. 验证与上线门槛

| 层级 | 主要指标 | 业务检查 |
|---|---|---|
| Beat/Downbeat | Beat/Downbeat F-measure、持续错拍率 | 是否存在整首错一拍或半拍 |
| Drum/Bass/Vocal 事件 | Precision、Recall、F1、时间偏差 | 是否会误导混音动作 |
| 每小节状态 | Macro/Micro F1、持续稳定性 | 是否出现相邻小节频繁闪烁 |
| Phrase/Section 边界 | ±1 Downbeat Boundary F1 | 制作人能否直接使用边界 |
| Section 标签 | Macro F1、每类召回 | Drop、Break、Outro 是否可靠 |
| 回归分数 | MAE、相关性、排序一致性 | 制作人是否同意高低关系 |
| Style | Macro F1、Top-k、Calibration | 混合风格和未知风格是否诚实 |
| Metric Embedding | Recall@K、成对准确率、制作人偏好 | 检索出来的片段是否真的相似 |
| 全链路 | 盲测、端到端失败率 | 是否减少人工找点时间和冲突 |

任何新特征必须经过目标域数据、Explicit/MERT/Fusion 对照、校准和盲测，才能从候选状态升级为正式能力。

## 14. 推理和部署

### 14.1 离线流水线

```text
导入音频
→ 创建 analysis_job
→ 统一解码与重采样
→ Beat/Downbeat/Bar
→ Demucs
→ 显式 MIR/DSP
→ MERT Embedding 缓存
→ 多任务模型
→ 时间平滑和约束解码
→ BarFeature/TrackAnalysis 持久化
→ Planner 生成候选和计划
```

### 14.2 缓存原则

- 音频文件哈希相同且预处理版本相同，允许复用 MERT Embedding；
- 模型头升级时不需要重复运行 Demucs 和 MERT；
- MERT、显式特征和任务输出分层缓存；
- 缓存键必须包含模型、采样率、窗口、归一化和特征 Schema 版本。

### 14.3 版本和回滚

每次分析保存：

- `analysis_version`；
- `schema_version`；
- `feature_definition_version`；
- `preprocessing_version`；
- 各模型名称、权重哈希和许可证；
- 训练数据版本；
- 校准版本；
- 推理参数和阈值版本。

旧分析结果不能被新模型静默覆盖。重新分析应生成新版本，Planner 明确选择使用哪个版本。

## 15. 技术路线图

### Phase 0：定义和标注试运行

- 冻结 Beat、Bar、Phrase、Section 和元素状态定义；
- 用 20–30 首代表性歌曲双人标注；
- 统计边界和标签一致性；
- 建立 Feature Registry 和 BarFeature Schema。

验收：制作人和算法人员对标签定义达成一致，常见分歧有处理规则。

### Phase 1：统一时间轴和现有特征收口

- 收口 Beat、Downbeat、Meter、Bar、Key、LUFS、能量和 Stem；
- 把当前规则输出迁移到统一时间轴；
- 增加来源、置信度、版本和缺失值语义。

验收：选定目标曲库中不再出现未被发现的整曲 Bar 偏移。

### Phase 2：MERT 基础设施

- 固定音频预处理；
- 缓存多层隐状态；
- 实现 Layer Mixer、时间拼接和 Bar Pooling；
- 验证 Embedding 与 Beat/Bar 对齐。

验收：同一音频重复推理结果一致，窗口边界没有明显跳变。

### Phase 3：Bar Understanding V1

- 标注 150–300 首目标歌曲；
- 训练 Vocal/Drum/Bass/Melody 状态和 Entry/Ending；
- 训练 Phrase/Section Boundary 和粗粒度 Section；
- 对比 MLP、TCN 和现有规则基线。

验收：制作人可以直接使用模型输出的每小节内容和结构地图。

### Phase 4：精细语义

- Fine Drum Events；
- Rap/Singing/Spoken/Chop；
- 808/Synth/Electric Bass；
- Melody Ending 和 Local Harmony；
- Groove 分类和连续分数。

验收：每个任务分别通过盲测，不依靠下游产品规则掩盖错误。

### Phase 5：Expanded Structure

- 使用上游折外预测重新训练结构模型；
- 增加详细 Section、Vocal/Melody Ending、Style Change；
- 加入持续时间和合法转移约束。

验收：详细结构标签稳定，边界误差满足混音容忍度。

### Phase 6：Style 与相似度

- 先保留 Discogs-EffNet + Logistic Regression 作为基线；
- 训练 21 类 MERT 多标签 Style Head；
- 训练 Local/Global Style 和 Style Stability；
- 训练 Style、Groove、Timbre、Melody Metric Heads。

验收：Artist-disjoint 盲测通过，相似度结果通过制作人成对试听。

### Phase 7：Planner 闭环

- 用 BarFeature 生成 TransitionCandidate；
- 比较 Tempo、Beat、Phrase、Harmony、Vocal、Bass、Energy 和 Spectral 安全性；
- Planner、App、RK 使用同一 `transition_id` 和时间点；
- 保存实际执行结果和人工反馈。

验收：计划评分、App 展示和 RK 执行使用同一候选，不在现场重新选点。

## 16. 风险和处理原则

### 标签不一致

先修定义和标注工具，不用更复杂模型掩盖问题。边界和粗粒度标签稳定后再扩展细粒度标签。

### 目标域偏差

公开数据只能用于预训练和基线。最终门槛由 HarBeat 真实曲库、舞种和混音场景决定。

### 多任务负迁移

共享模型可能让一个任务拖累另一个任务。每个任务保留独立验证，必要时加入任务适配层、调整损失权重或拆分网络。

### 训练与运行不一致

下游模型必须使用折外上游预测训练；预处理、采样率、窗口和标准化全部版本化。

### 商业授权

MERT-v1-95M 当前公开权重的许可包含非商业限制。Beat This、ADTOF、Demucs、Basic Pitch 和其他模型也需要逐项记录代码、权重、数据和依赖许可证。研究验证通过不等于可以直接进入商业产品。

### 计算成本

MERT 和 Demucs 离线运行并分层缓存。任务头保持轻量，模型升级优先复用已有 Stem、显式特征和 Embedding。

## 17. 架构决策摘要

1. 保留已经可靠的 MIR/DSP，不用 MERT 重新猜测精确测量值。
2. MERT 作为共享音乐表示，一首歌只提取一次 Embedding。
3. 片段内容、结构、风格与相似度采用不同时间尺度和任务头。
4. 第一版先训练 Bar Understanding，而不是优先训练完整 21 类风格。
5. Phrase 和 Section 先做边界与粗标签，再做细标签。
6. `BarFeature[]` 是分析层到 Planner 的主合同。
7. Jetson 负责离线重分析，RK 负责现场实时执行。
8. 任何新特征都必须经过目标域标注、对照实验、校准和盲测。
9. 69 项特征不要求全部上线，但每一项必须有明确处置结果。

## 18. 术语表

| 术语 | 含义 |
|---|---|
| MERT | 预训练音乐编码模型，负责把音频转换为高维时间序列表示 |
| Embedding | 模型输出的数字向量，可供分类、回归和相似度模型读取 |
| Backbone | 多个任务共享的特征提取主干，这里主要指 MERT |
| Task Head | 接在共享表示后面、负责回答具体问题的小型模型 |
| MLP | 处理固定长度数值向量的多层神经网络 |
| CNN | 用滑动窗口识别局部模式的卷积网络 |
| TCN | 通过扩张卷积理解较长时间序列的网络 |
| BiGRU | 同时从前后两个方向读取序列的循环网络 |
| Transformer Encoder | 使用自注意力比较序列中各位置关系的编码模型 |
| Attention Pooling | 学习不同时间位置权重，再汇总为固定长度向量 |
| Multi-label | 一个片段可以同时拥有多个标签，例如 House 和 Disco |
| Metric Learning | 训练向量空间，使相似片段靠近、不同片段远离 |
| OOD | 不属于已知训练分布的输入或类别 |
| BarFeature | HarBeat 按小节保存的统一音乐分析记录 |
