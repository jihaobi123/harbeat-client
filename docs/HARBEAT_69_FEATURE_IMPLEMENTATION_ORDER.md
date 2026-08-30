# HarBeat 69 项特征实施与训练顺序

- 版本：2026-08-30
- 状态：实施顺序草案
- 适用范围：HarBeat 音乐分析、模型训练、验证和自动混音接入

关联文档：

- [HarBeat 音乐分析架构与技术路线图](./HARBEAT_MUSIC_ANALYSIS_ARCHITECTURE_AND_TECHNICAL_ROADMAP.md)
- [HarBeat 音乐分析共同开发合同 V1](./HARBEAT_MUSIC_ANALYSIS_DEVELOPMENT_CONTRACT_V1.md)

## 1. 先说结论

69 项特征不应同时开工，也不能全部用同一种模型训练。正确顺序是：

```text
先统一定义
→ 再把时间轴切准
→ 完成可以直接测量的特征
→ 判断每个小节有什么
→ 判断乐句和段落在哪里变化
→ 增加人声、贝斯、鼓和旋律的精细语义
→ 学习 Groove
→ 扩展详细段落
→ 最后训练 Style、Production 和相似度
```

第一版产品不需要等待 69 项全部完成。阶段 0–4 完成后，系统已经可以输出音乐制作人需要的每小节内容和段落地图。

## 2. “完成 69 项”的定义

现有文档把约 69 项能力分为：

| 当前状态 | 数量 | 本文中的处理方式 |
|---|---:|---|
| Validated | 10 | 保留历史验证范围，优先接入统一时间轴和 `BarFeature`，保持回归测试 |
| Failed Validation | 11 | 不继续修补旧阈值；按业务价值更换方法或删除 |
| Provisional | 23 | 建立独立目标域验证，合格后升级 |
| Candidate Only | 20 | 只用于实验和软输出，不能驱动危险混音动作 |
| Deprecated | 5 | 从正式输出移除，保留历史记录和替代方案 |

以上数量由 [`analysis_features_v1.jsonl`](../contracts/registries/analysis_features_v1.jsonl)
生成；当前没有单独归为 `Unavailable` 的迁移条目。状态变化必须先更新验证证据，再重新生成 Registry。

“做完”表示每项特征都有一个经过评审的最终处置：

```text
正式上线 / 降级软用 / 重做 / 被替代 / 废弃 / 暂不可用
```

不是要求 69 个字段都输出一个看似精确的数字。

## 3. 69 项原始清单的管理方式

《69 项规则 vs. 机器学习》报告说明，完整逐项清单位于外部 `reports/feature_selection.csv`。该 CSV 没有包含在当前附件中，所以本文按报告和项目主文档中出现的全部特征族安排顺序。项目开始执行时，应建立唯一的 `Feature Registry`，把历史 69 项逐行登记进去。

建议字段：

| 字段 | 说明 |
|---|---|
| `feature_id` | 稳定编号，不随名称修改 |
| `name` | 对外名称 |
| `definition` | 音乐含义和正反例 |
| `time_level` | Frame、Beat、Bar、Phrase、Section 或 Song |
| `output_type` | Event、Single-label、Multi-label、Regression、Embedding |
| `source` | DSP、专业模型、MERT Head、规则或人工 |
| `dependency_ids` | 依赖的上游特征 |
| `status` | Validated、Provisional、Candidate、Failed、Deprecated、Unavailable |
| `metric` | 验证指标和容忍范围 |
| `model_version` | 当前生产模型 |
| `license` | 代码、权重和数据许可 |
| `consumer` | Planner、检索、UI、审计或训练输入 |

Feature Registry 是 69 项数量和状态的权威来源。文档中的自然语言列表只负责解释，不负责计数。

## 4. 排序原则

### 4.1 上游错误会污染下游

Downbeat 错一拍，Bar Grid、Phrase、Section、Entry/Ending 和转场点会一起错。因此时间轴必须先于语义模型。

### 4.2 直接测量先于主观判断

LUFS、频段能量、Bass Note 和 Vocal F0 不需要人工风格标签，可以先完成，也能为后续模型提供输入。

### 4.3 存在状态先于类型判断

先判断 Bass 是否存在、何时进入和结束，再判断是 808 还是 Synth Bass。先判断人声活动，再判断 Rap、Singing 或 Spoken。

### 4.4 边界先于详细段落名称

制作人通常更容易一致地标出“这里换段了”，却可能对“这是 Bridge 还是 Break”意见不同。第一版先训练 Phrase/Section Boundary 和粗粒度 Section。

### 4.5 Style 和相似度依赖前面的内容理解

Style 会使用节奏、贝斯、人声、和声、音色和结构证据。相似度还需要稳定的正负样本定义，所以排在后面。

### 4.6 质量和版本信息从第一天开始

Confidence、Source、Validation Status、Model Version、OOD 和 Missing Inputs 从第一天开始保存，并贯穿所有阶段。

## 5. 总依赖图

```text
特征定义与标注规范
        │
        ▼
Beat / Downbeat / Meter / Bar / Stem
        │
        ├───────────────┐
        ▼               ▼
显式 MIR/DSP         MERT Embedding
        │               │
        └───────┬───────┘
                ▼
        每小节元素状态
        Vocal/Drum/Bass/Melody
                │
                ▼
        基础 Phrase / Section
                │
        ┌───────┴────────┐
        ▼                ▼
精细乐器与声乐语义      Local Harmony
        │                │
        └───────┬────────┘
                ▼
              Groove
                │
                ▼
        Expanded Structure
                │
                ▼
       Style / Production
                │
                ▼
       Metric Embeddings
                │
                ▼
       Transition Features
```

## 6. 阶段 0：定义、Schema 和标注试运行

### 目标

在训练任何模型前，让产品、制作人和算法人员对特征含义达成一致。

### 工作项

- 冻结 Beat、Bar、8 拍、Phrase、Section 的定义；
- 冻结粗粒度和细粒度 Section 标签；
- 定义 Vocal、Drum、Bass、Melody 的状态；
- 定义 Entry、Ending、Foreground、Background；
- 定义每项连续分数的参照物；
- 采用共同开发合同中的 Feature Registry、Annotation 和 `BarFeature` Schema，并补齐标签定义与 Registry 内容；
- 选择 20–30 首覆盖主要目标场景的歌曲进行双人标注。

### 状态标签建议

```text
absent
background
foreground
entering
ending
unknown
```

### 验收条件

- 同一批歌曲由两人标注时，边界和核心元素状态基本一致；
- 所有常见分歧都有书面处理规则；
- “8 拍”与“8 小节”在数据结构中不再混用；
- `unknown` 和 `uncertain` 有明确含义。

## 7. 阶段 1：统一时间轴和 Stem

### 必须先完成的能力

| 特征 | 层级 | 方法 | 是否需要训练 HarBeat 模型 |
|---|---|---|---|
| BPM Global | Song | Beat Tracker + 校准 | 否 |
| BPM Confidence | Song | 多证据质量评分 | 否 |
| BPM Candidates | Song | 倍速/半速候选 | 否 |
| Beat Points | Beat | Beat Tracking | 否 |
| Downbeats | Beat/Bar | Downbeat Tracking | 否 |
| Downbeat Confidence | Bar | 质量评分 | 否 |
| Meter/Time Signature | Song/Section | 专业模型或联合推断 | 否，先用现有能力 |
| Bar Boundaries | Bar | Beat + Downbeat | 否 |
| Local Tempo | Bar/Window | Beat 间隔 | 否 |
| Tempo Stability | Song/Window | 局部 Tempo 统计 | 否 |
| 16th Subdivision | Beat | Beat 内量化 | 否 |
| Demucs 四轨 | Song/Frame | `htdemucs` | 否，使用预训练模型 |
| Stem Completeness | Song | 文件和能量检查 | 否 |
| Stem Reconstruction Proxy | Song | Stem 重建误差 | 否 |

### 为什么排第一

后续所有标签和模型输出都必须对齐到小节。即使 Section 分类正确，只要开始时间错一拍，对混音也不可用。

### 验收条件

- 目标曲库中不再出现未被标记的整曲 Bar 偏移；
- 低置信 Beat/Downbeat 自动进入复核队列；
- 所有 Stem 使用同一时间原点、采样率和时长；
- 时间轴和 Stem 输出包含版本与来源。

## 8. 阶段 2：显式 MIR/DSP 基础特征

这一阶段优先处理已经验证或不需要人工标注的特征。

### 8.1 声学和响度

建议顺序：

1. Integrated LUFS；
2. Short-term Loudness；
3. True Peak/Peak dBFS；
4. Dynamic Range；
5. Sub Energy；
6. Bass Energy；
7. LowMid、Mid、HighMid、High Energy；
8. Spectral Centroid；
9. Spectral Flux；
10. Transient Density。

方法：DSP 直接计算，不训练分类器。

### 8.2 基础和声

建议顺序：

1. Global Key；
2. Mode；
3. Key Confidence；
4. Camelot；
5. Chroma/HPCP；
6. Bar-level Chroma；
7. Local Key Candidate。

Chord Candidate 和 Chord Change Activity 暂不作为强依赖。历史和弦变化指标来自隔离吉他数据，与当前商业混音分析方法不一致，需要在阶段 5 重新验证。

### 8.3 贝斯音符与声学状态

建议顺序：

1. Note Onset；
2. Note Offset；
3. Pitch；
4. Pitch Bend；
5. Note Confidence；
6. Bass Activity；
7. Sub Energy；
8. Attack；
9. Decay/Release Proxy；
10. Pitch Movement；
11. Note Density；
12. Bass Grid。

方法：Bass Stem + Basic Pitch + DSP。

### 8.4 人声声学状态

建议顺序：

1. Vocal Activity；
2. Vocal Density；
3. F0；
4. F0 Coverage；
5. Pitch Range；
6. Pitch Sustain；
7. Onset Density；
8. Melodic Contour。

方法：Vocal Stem + F0/Activity 模型 + DSP。

### 8.5 基础鼓事件

建议顺序：

1. Kick；
2. 广义高频打击乐；
3. Kick Grid；
4. 初步 Hat/Percussion Grid；
5. Drum Density。

### 与原 19 项入选规则的关系

原报告中四项声乐表达特征位于本阶段：

- 旋律轮廓；
- 音高持续比例；
- 人声密度；
- 人声音域。

它们应保留为可解释输出和模型输入，不再单独承担风格判定。

### 验收条件

- 单项特征在独立目标域样本上通过各自指标；
- Frame、Beat 和 Bar 聚合结果能够互相追溯；
- 没有把缺失值写成真实零值；
- 相同音频重复分析结果稳定。

## 9. 阶段 3：Bar Content V1

这是第一组真正需要 HarBeat 自己训练的任务。

### 训练目标

每个小节输出：

| 对象 | 第一版标签/数值 |
|---|---|
| Vocal | Absent、Background、Foreground、Entering、Ending、Activity、Density |
| Drum | Absent、Partial、Full、Fill、Entering、Ending、Density |
| Bass | Absent、Present、Entering、Ending、Activity、Low-frequency Occupancy |
| Melody | Absent、Background、Foreground、Entering、Ending、Activity、Density |
| Acoustic | Energy、Short-term Loudness、频段能量 |

### 模型

```text
Frozen MERT Bar Embedding
+ Stage 2 Explicit Features
+ Drum/Bass Grid
→ MLP/1D CNN Fusion
→ 小型 TCN
→ 多标签状态头 + 回归头
```

### 训练顺序

1. 先训练 Presence/Activity；
2. 再训练 Foreground/Background；
3. 再训练 Entry/Ending；
4. 最后增加 Drum Fill 等短时状态。

### 数据

- 20–30 首用于定义和工具试运行；
- 150–300 首用于第一个 PoC；
- 标注以 Section 或连续 Bar 范围为单位，自动展开为 Bar 标签；
- 抽取一部分歌曲进行双人标注和仲裁。

### 验收条件

- 每项状态报告 Macro/Micro F1；
- Entry/Ending 报告时间偏差；
- 相邻小节状态没有无法解释的频繁闪烁；
- 制作人可以从 `BarFeature[]` 看出每小节主要内容。

## 10. 阶段 4：基础 Phrase 和 Section

制作人当前最需要这一阶段。它不必等待 Rap、808 和 Groove 完成。

### 训练顺序

1. Phrase Boundary；
2. Section Boundary；
3. Phrase Start/End；
4. Section Start/End；
5. 粗粒度 Section；
6. Section Occurrence 和内部位置。

### 第一版 Section 标签

```text
intro
main
build
breakdown
outro
unknown
```

详细 Verse、Chorus、Drop 等标签先保存人工标注，第一版不一定全部进入模型。

### 模型

```text
前后 8–16 Bars
→ TCN 主模型
→ Phrase Boundary Head
→ Section Boundary Head
→ Coarse Section Head
```

对照模型：

- 当前规则版 Phrase/Section；
- All-In-One 候选；
- 不看上下文的 MLP；
- BiGRU。

### 验收条件

- 边界使用 ±1 Downbeat 容忍范围评估；
- 每类 Section 单独报告召回率；
- 制作人盲听确认边界是否可以直接用于混入/混出；
- 模型输出通过最短段落长度和标签持续性约束。

### 第一版可交付点

阶段 0–4 完成后，系统已经可以提供：

```text
准确 Beat/Bar
每小节 Vocal/Drum/Bass/Melody 状态
Phrase 和 Section 边界
粗粒度段落
能量、响度、频谱和基础调性
```

这是 Bar Understanding V1，也是第一版可用于 Planner 的音乐地图。

## 11. 阶段 5：精细鼓、人声、贝斯、旋律和局部和声

阶段 5 可以拆成多条并行数据线，但模型接入仍按依赖顺序进行。

### 11.1 Fine Drum Events

建议顺序：

1. Snare；
2. Clap；
3. Closed Hat；
4. Open Hat；
5. Cymbal；
6. Tom；
7. 其他 Percussion；
8. Drum Fill；
9. 短促金属音；
10. 持续金属音。

模型：Fine Drum Event Model，输出事件时间、类别、强度和置信度，再量化为 16 分网格。

### 11.2 Vocal Semantic

建议顺序：

1. Singing；
2. Rap；
3. Spoken；
4. Vocal Chop；
5. 混合状态和特殊 Vocal FX。

模型：MERT + Vocal Explicit + 多标签分类头。

先完成 Activity 和 Presence，避免在人声不存在的小节里强制分类。

### 11.3 Bass Semantic

建议顺序：

1. 808；
2. Synth Bass；
3. Electric Bass；
4. Other/Unknown；
5. Staccato；
6. Syncopation；
7. Bass Riff；
8. Riff Repetition。

模型：MERT + Bass Stem Explicit + Bass Grid + 多标签/回归头。

原报告中低频/贝斯四项入选规则位于这里：808 音色、Bass Riff 重复、Staccato 和切分。它们需要从手写规则证据升级为目标域训练任务。

### 11.4 Melody Semantic

建议顺序：

1. Melody Activity；
2. Melody Density；
3. Foreground/Background；
4. Melodic Stability；
5. Melody Entry；
6. Melody Ending。

Activity、Density 和 Pitch 优先使用显式模型；Entry、Ending 和 Stability 使用前后 Bar 上下文。

### 11.5 Local Harmony

建议顺序：

1. Bar Chroma 稳定性；
2. Local Key；
3. Harmonic Boundary；
4. Chord Candidate；
5. Chord Change Activity；
6. Harmonic Stability。

必须使用商业混音目标域重新标注和验证。历史 GuitarSet 指标只能作为研究参考。

### 验收条件

- 每个任务独立盲测；
- 多标签任务完成阈值校准；
- 没有人声或没有 Bass 时输出 Not Applicable，而不是某个类型；
- 细鼓事件报告时间偏差和类别混淆；
- 上游结果通过折外预测供后续模型使用。

## 12. 阶段 6：Groove 和节奏语法

Groove 依赖稳定的 Beat、Drum Grid、Bass Grid 和基础结构，所以排在精细事件之后。

### 12.1 先验证客观节奏语法

原报告中的八项节奏语法按下面顺序验证：

1. 四拍稳定；
2. 四拍踩底；
3. 2/4 反拍；
4. Quantized 程度；
5. Breakbeat；
6. Tresillo；
7. Two-step；
8. Tamborzão。

这些特征可以先由网格规则计算，再作为 Groove Head 的显式输入。规则输出必须保存置信度，不直接等同于风格。

### 12.2 再训练 Groove 语义

建议输出：

- Groove Type；
- Groove Strength；
- Swing；
- Syncopation Strength；
- Kick/Bass Lock；
- Groove Stability；
- Groove Change；
- Groove Embedding Candidate。

模型：

```text
Drum Grid + Bass Grid
→ 1D CNN/TCN
+ MERT Bar Embedding
→ Groove 分类头 + 回归头
```

### 标注建议

主观连续分数不容易标稳。Groove Strength、Swing Feel 和 Stability 可以优先采用成对比较：

```text
片段 A 和片段 B，哪个 Groove 更强或更稳定？
```

排序模型再把结果映射为连续分数。

### 验收条件

- 规则语法与 Groove 语义分别评估；
- 分类结果报告每类 F1；
- 连续分数报告排序一致性和制作人相关性；
- Groove 结果能够改善转场排序，不只是在离线指标上变好。

## 13. 阶段 7：Expanded Structure

基础 Phrase/Section 已在阶段 4 完成。阶段 7 使用精细语义重新训练详细结构模型。

### 新增输入

- Vocal Semantic；
- Bass Type；
- Fine Drum Events 和 Fill；
- Groove；
- Melody Ending；
- Local Harmony；
- Energy 和 Timbre Change。

### 新增输出

- Verse；
- Pre-Chorus；
- Chorus；
- Post-Chorus；
- Drop；
- Break；
- Bridge；
- Solo；
- Instrumental；
- Vocal Ending；
- Melody Ending；
- Style Change；
- DJ Phrase Boundary；
- Entry/Exit Candidate。

### 模型

第一版继续使用 TCN；BiGRU 做对照；Transformer Encoder 只在数据量和长距离重复任务证明有必要时加入。

### 防止训练泄漏

Expanded Structure 不能直接读取人工 Vocal、Bass 或 Groove 真值。它必须读取上游模型对训练歌曲产生的折外预测概率。否则训练时输入过于完美，运行时表现会明显下降。

### 验收条件

- 详细标签的 Macro F1 达到业务门槛；
- 边界仍保持阶段 4 的质量，不因增加标签而退化；
- 标签持续时间合理，不在相邻小节来回跳；
- Planner 使用模型边界后，制作人找点时间确实下降。

## 14. 阶段 8：Style、Production 和相似度

### 14.1 先保留现有 Style 基线

实验报告中的：

```text
Discogs-EffNet Embedding
→ Logistic Regression
→ 当前 13 类
```

应作为风格基线保留。它不等于已经完成 21 类、片段级和商业上线验证。

### 14.2 新 Style 模型的训练顺序

1. 当前 13 类全曲分类复现；
2. 21 类全曲多标签；
3. Primary/Secondary Style；
4. Section-level Style；
5. Local Style；
6. Style Stability；
7. Style Change；
8. Unknown/OOD。

模型：MERT 长时间表示 + Attention Pooling + MLP + Sigmoid 多标签分类头。

### 14.3 Production/Timbre

待制作人冻结定义后训练：

- Bright/Dark；
- Clean/Distorted；
- Acoustic/Electronic；
- Dense/Sparse；
- Hard/Soft；
- Dry/Spatial；
- Modern/Retro；
- 其他 HarBeat Production 标签。

### 14.4 Metric Embeddings

训练顺序：

1. Style Embedding；
2. Groove Embedding；
3. Timbre Embedding；
4. Rhythm Embedding；
5. Melody Embedding。

每种相似度使用独立投影头和成对/三元组训练数据。不要把它们压成一个“总体相似度向量”。

### 验收条件

- Style 使用 Song-disjoint 和 Artist-disjoint 盲测；
- 多标签概率完成校准；
- Unknown/OOD 使用专门样本评估；
- Metric Embedding 使用 Recall@K、成对准确率和制作人试听验证；
- 商业授权审查通过后才能进入产品。

## 15. 最后生成混音决策特征

混音决策特征不是独立听出来的原始事实，而是对前面分析结果的组合。

建议最后生成：

- Tempo Compatibility；
- Beat Phase Compatibility；
- Phrase Alignment；
- Section Role Compatibility；
- Harmonic Compatibility；
- Vocal Safety；
- Bass Safety；
- Loudness Safety；
- Spectral Conflict；
- Energy Continuity；
- Groove Similarity；
- Style Similarity；
- Entry Quality；
- Exit Quality；
- Transition Score。

这些结果进入 `TransitionCandidate`，并与精确的 `from_at_sec`、`to_at_sec` 和 `fade_sec` 绑定。Planner 评分、App 展示和 RK 执行必须使用同一候选。

## 16. 模型训练任务的实际先后顺序

| 训练编号 | 模型 | 前置条件 | 主要输出 |
|---|---|---|---|
| T0 | 无训练：MIR/DSP 和预训练模型接入 | 阶段 0 | 时间轴、Stem、显式特征 |
| T1 | Linear Probe 基线 | MERT Bar Embedding | 验证 MERT 是否包含目标信息 |
| T2 | Bar Content V1 | 阶段 1–2、每小节标签 | 元素 Presence、Activity、State |
| T3 | Basic Structure TCN | Bar Content 折外预测、边界标签 | Phrase/Section Boundary、粗标签 |
| T4 | Fine Drum Model | Drum Stem 和事件标注 | 精细鼓件和 Grid |
| T5 | Vocal Semantic Head | Vocal Activity 稳定 | Rap/Singing/Spoken/Chop |
| T6 | Bass Semantic Head | Bass Notes/Grid 稳定 | 808、Synth、Electric、Riff、Syncopation |
| T7 | Melody/Local Harmony Heads | Chroma、F0、Other Stem | Activity、Ending、Local Key/Harmony |
| T8 | Groove Head | Fine Drum、Bass Grid、MERT | Groove 类型、强度和变化 |
| T9 | Expanded Structure | T4–T8 折外预测 | 详细 Section、Ending、DJ Boundary |
| T10 | Style Head | 结构和语义稳定 | 21 类、Local/Global Style、OOD |
| T11 | Metric Heads | Style/Groove/Timbre/Melody 成对数据 | 多个相似度 Embedding |
| T12 | Transition Scorer | 所有必要 BarFeature 稳定 | Entry/Exit 和 Transition Score |

T4、T5、T6 和 T7 的数据准备可以并行，但 T8 依赖 T4/T6，T9 依赖 T4–T8，T10 和 T11 排在结构与语义稳定之后。

## 17. 每个训练任务必须保留的对照实验

每项高层语义至少比较：

```text
Explicit-only
MERT-only Linear Probe
MERT-only Nonlinear Head
MERT + Explicit Fusion
```

需要上下文的任务再比较：

```text
当前 Bar MLP
TCN
BiGRU
小型 Transformer（后期）
```

只有 Fusion 在盲测中稳定优于简单方案时，才增加生产复杂度。

## 18. 数据规模和扩展顺序

### Pilot：20–30 首

用途：标签定义、标注工具、双人一致性和时间轴校验。不能用于宣称模型已达到上线标准。

### PoC：150–300 首

用途：Bar Content、基础 Phrase/Section、模型结构和融合路线选择。重点覆盖目标曲库，不追求表面上的类别数量。

### 扩展：1000–2000 首以上

用途：详细 Vocal/Bass/Groove/Style、多标签校准、Artist-disjoint 测试和未知类别。

数据规模同时报告：

- 独立歌曲数；
- 独立艺人数；
- 每类歌曲数；
- 每类片段数；
- 标注人员数；
- 一致性和仲裁比例。

同一首歌切出几百个片段，仍然只算一首独立歌曲。

## 19. 三个产品版本

### V1：音乐结构地图

包含：

- Beat、Downbeat、Bar；
- BPM、Key、LUFS、能量和频谱；
- Vocal、Drum、Bass、Melody 每小节状态；
- Phrase/Section Boundary；
- 粗粒度 Section；
- 初步 Entry/Exit Candidate。

完成阶段：0–4。

### V2：详细音乐理解

新增：

- Fine Drum Events；
- Rap/Singing/Spoken；
- 808/Bass Type；
- Melody Ending；
- Local Harmony；
- Groove；
- 详细 Section 和 DJ Phrase Boundary。

完成阶段：5–7。

### V3：智能检索和自动混音

新增：

- 21 类 Style；
- Local Style 和 Style Change；
- Production/Timbre 语义；
- 多种 Metric Embedding；
- 完整 TransitionCandidate 和 Scorer；
- 人工反馈闭环。

完成阶段：8 和混音决策层。

## 20. 不应该采用的顺序

以下做法会浪费数据和工程时间：

- 先训练完整 21 类 Style，再补 Beat/Bar；
- 先判断 808 类型，却没有稳定 Bass Presence 和 Bass Grid；
- 先训练 Groove，却没有精细 Drum/Bass 时间证据；
- 先训练详细 Section，却没有一致的 Phrase/Section Boundary 标注；
- 直接微调 MERT，却没有冻结骨干基线；
- 训练下游模型时读取人工上游真值；
- 把 69 项全部塞给一个模型，不区分时间尺度和任务类型；
- 用同一首歌的不同片段分别放入训练集和测试集；
- 为了让字段完整，在不确定时输出伪造的确定答案。

## 21. 当前立即执行清单

1. 找回或导出 `reports/feature_selection.csv`，建立 69 行 Feature Registry。
2. 由制作人确认“8 拍、Bar、Phrase、Section”的书面定义。
3. 选择 20–30 首代表性歌曲，完成人工 Beat/Downbeat 修正和双人结构标注。
4. 把现有 BPM、Key、LUFS、Energy、Stem、Vocal/Bass Activity 映射到统一 `BarFeature`。
5. 固定 MERT 预处理、窗口、Layer Mixer 和 Bar Pooling 实现。
6. 训练 `MERT Bar Embedding + Logistic Regression` 线性基线。
7. 训练 Bar Content V1，再训练 Basic Structure TCN。
8. 让制作人用盲听方式验收每小节内容、Phrase 和 Section 边界。
9. V1 通过后，再启动 Fine Drum、Vocal Semantic、Bass Semantic 和 Groove。

## 22. 最终决策规则

每项特征进入正式系统前，必须同时满足：

- 定义清楚；
- 有目标域标签或可验证真值；
- 时间对齐正确；
- 比现有规则或简单基线更好；
- 通过独立盲测；
- 概率完成校准；
- 保存来源和版本；
- 失败时有 Unknown、Needs Review 或安全降级；
- 许可证允许目标用途；
- 能改善真实混音任务，而不只是提高离线分数。

这套顺序先得到可信的音乐时间轴和小节内容，再逐步增加语义。Style 和相似度很重要，但不能代替段落、元素状态和边界。HarBeat 第一项真正有产品价值的机器学习交付物，应当回答“每个小节发生了什么，以及哪里适合进入和退出”。
