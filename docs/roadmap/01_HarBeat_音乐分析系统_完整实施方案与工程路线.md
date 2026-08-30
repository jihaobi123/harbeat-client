# HarBeat 音乐分析系统：完整实施方案、Pipeline、数据集与工程路线

> 版本：2026-08-29
> 文档定位：项目实施主文档
> 读者：项目负责人、开发人员、音乐制作人、算法人员
> 目标：从“输入一首歌”开始，完整说明 HarBeat 如何得到可用于自动接歌的结构化音乐特征；明确当前已经具备的能力、还缺什么、MERT 在哪里进入、数据集怎么准备、各模型如何训练、结果如何验证，以及整个项目的工程量和风险。

---

# 0. 先看结论：我们到底要做什么

HarBeat 不是要训练一个“万能模型”直接从音频输出所有结果。

最终方案是：

```text
                                一首完整歌曲
                                     │
               ┌─────────────────────┴─────────────────────┐
               │                                           │
        专项 MIR / DSP                                MERT Backbone
               │                                           │
     精确、可解释的底层测量                         通用音乐上下文表示
               │                                           │
 BPM / Beat / Downbeat                            高维时序向量
 Drum Events / Bass Notes                         不是具体标签
 Vocal F0 / Chroma / LUFS                              │
               │                                           │
               └─────────────────────┬─────────────────────┘
                                     ↓
                            统一时间轴 + 特征对齐
                            Frame / Beat / Bar / Segment
                                     ↓
                                Feature Fusion
                                     ↓
                      ┌──────────────┼──────────────┐
                      ↓              ↓              ↓
                  Vocal Head      Bass Head      Groove Head
                      ↓              ↓              ↓
                Rap/Singing       808/Bass       Groove语义
                      │              │              │
                      ├──────── Phrase / Section Head
                      │
                      └──────── Style Head
                                     ↓
                               BarFeature[]
                                     ↓
                              Transition Engine
                                     ↓
                           候选点评分 + 混音执行
```

核心思想只有三句话：

1. **能精确测量的，不让 MERT 猜。**
2. **人工规则难以稳定表达的音乐语义，使用 MERT 表征 + 监督 Head 学习。**
3. **最终所有结果必须落到统一的时间轴和 BarFeature，而不是停留在模型 embedding。**

---

# 1. 项目当前状态

目前 HarBeat 并不是从零开始。

根据现有验证体系，当前已经有一套较完整的 MIR / DSP 基础分析链。现有高层输出约 69 项，状态大致分为：

| 状态 | 数量 | 含义 |
|---|---:|---|
| `validated` | 9 | 已达到当前独立验证门槛 |
| `failed_validation` | 11 | 实现存在，但验证未达标 |
| `provisional` | 23 | 有工程价值，但证据仍不足 |
| `candidate_only` | 20 | 候选语义，只允许软使用 |
| `deprecated` | 5 | 不再作为正式能力 |
| `unavailable` | 1 | 当前技术链无法可靠输出 |

当前可靠基础主要包括：

```text
BPM
Beat
高置信 Downbeat
Meter / Bar
高置信 Global Key
Demucs 4 Stem
Basic Pitch Bass Note / Pitch
Kick
广义高频打击乐事件
Vocal Density
Vocal Pitch Range
Pitch Sustain
Melodic Contour
客观频谱 / 动态 / 响度特征
```

当前主要短板集中在：

```text
Section / Phrase
Open / Closed Hat
Snare / Clap 等细鼓件
808 / Bass Type
Bass Syncopation / Riff 等语义
Rap / Singing / Spoken
Groove 语义
商业混音中的 Chord / Local Harmony
Production / Timbre 语义
21 类 Style
```

因此下一阶段不是推翻现有系统，而是：

> **保留可靠底层测量，把失败最多的“人工语义规则层”改造成可训练、可验证的表示学习层。**

---

# 2. 最终产品目标

Music Analyzer 对每一首歌最终应得到五个层级的数据。

## 2.1 Global：全曲级

```text
bpm_global
bpm_confidence
bpm_candidates
global_key
global_mode
camelot
primary_style
style_probs[21]
global_style_embedding
integrated_lufs
true_peak
```

---

## 2.2 Section：段落级

```text
sections = [
    {
        start,
        end,
        start_bar,
        end_bar,
        label,
        confidence,
        occurrence
    }
]
```

典型标签：

```text
intro
verse
pre_chorus
chorus
post_chorus
drop
break
bridge
solo
instrumental
outro
unknown
```

最终是否保留全部标签，由音乐制作人确认。

---

## 2.3 Phrase / Bar：接歌主工作层

这是系统最重要的输出。

```text
Bar 128
├── start / end
├── beat positions
├── section
├── phrase boundary
├── local style
├── local key / chroma
├── drum grid
├── groove
├── vocal state
├── bass state
├── melody state
├── loudness / band energy
└── confidence / source / validation status
```

接歌引擎主要比较的是两首歌的 `BarFeature[]`。

---

## 2.4 Beat / Event：精细节奏级

```text
beats[]
downbeats[]

drum_events[]:
    time
    class
    strength
    confidence

bass_notes[]:
    onset
    offset
    pitch
    bend
    confidence
```

---

## 2.5 Frame：短时连续特征

例如每 50–100 ms 或模型原始帧率：

```text
vocal_activity_curve
sub_energy_curve
short_term_loudness
chroma
MERT hidden states
melody_activity
```

Frame 主要服务上层聚合，不是直接给 Transition Engine 使用。

---

# 3. 完整 End-to-End Pipeline

---

# Stage 0：先冻结“特征定义”

这是整个项目最容易被低估、但最重要的一步。

在开发任何新 Head 前，音乐制作人必须确认：

```text
哪些特征必须做
哪些第二阶段再做
哪些不需要
每个特征到底如何定义
是否允许多标签
边界样本怎么处理
unknown 怎么定义
```

例如“808”必须先回答：

```text
什么算 808？
普通 sub-heavy synth bass 算不算？
有 pitch slide 但不是 808 的 Bass 怎么标？
短 decay 的 808 是否仍属于 808？
```

如果标签定义本身不稳定，任何模型都无法稳定学习。

因此每个任务都要有：

```text
taxonomy_v1.md
annotation_guideline_v1.md
```

然后再开始标数据。

---

# Stage 1：歌曲输入与基础预处理

## 输入

```text
wav / flac / mp3
```

生产数据库至少保存：

```json
{
  "song_id": "...",
  "source_path": "...",
  "duration_sec": 212.31,
  "sample_rate_original": 44100,
  "channels": 2
}
```

## 关键原则

不同模型可以拥有不同的内部输入规格。

例如：

```text
MERT      → 24 kHz mono
Demucs    → 自己要求的输入格式
Beat This → 自己的声谱处理
BasicPitch→ 独立预处理
```

不能为了“统一”强制所有模型共用一个重采样后的文件。

真正统一的是：

\[
\boxed{\text{绝对时间坐标：秒}}
\]

所有输出必须能够回到：

```text
start_sec
end_sec
```

---

# Stage 2：Canonical Timeline

## 目的

先回答：

```text
这首歌多快？
Beat 在哪里？
Downbeat 在哪里？
一个 Bar 从哪里到哪里？
```

## 输入

```text
Original Mix
```

## 主模型

```text
Beat This
+
现有 BPM consensus / calibration
```

## 输出

```json
{
  "bpm_global": 139.8,
  "bpm_candidates": [69.9, 139.8, 279.6],
  "beats": [0.412, 0.841, 1.270],
  "downbeats": [0.412, 2.128, 3.844],
  "meter": 4,
  "bars": [...]
}
```

## 派生

Local tempo：

\[
IBI_i=t_{beat,i+1}-t_{beat,i}
\]

\[
BPM_i=\frac{60}{IBI_i}
\]

再通过：

```text
median filter / robust smoothing
```

得到：

```text
local_tempo_curve
```

## 为什么不使用 MERT

这是精确时间事件定位问题。

已有专项模型比通用 representation 更合适，也更容易校准到毫秒级时间戳。

---

# Stage 3：Stem Separation

## 输入

```text
Original Mix
```

## 当前主模型

```text
Demucs / htdemucs
```

## 输出

```text
vocals.wav
drums.wav
bass.wav
other.wav
```

## 用途

```text
vocals → Vocal analysis
drums  → Drum transcription
bass   → Basic Pitch + Bass DSP
other  → Melody / Harmony 辅助
```

## 当前策略

第一阶段不替换现有 Demucs。

原因不是 Demucs 一定是最终最佳 separator，而是当前大量下游验证已经基于它完成。

未来若测试 BS-RoFormer / MelBand RoFormer 等新 separator，必须比较：

```text
分离指标
+
下游 Bass / Vocal / Drum 特征是否更好
```

而不是只看 SI-SDR 就直接替换。

---

# Stage 4：Explicit MIR / DSP Layer

这一层专门负责“能明确测量的音乐证据”。

---

## 4.1 Rhythm

输入：

```text
Original Mix
```

输出：

```text
BPM
Beat
Downbeat
Meter
Bar
Local Tempo
```

---

## 4.2 Drum Event

输入：

```text
drums stem
```

第一版：

```text
ADTOF / 现有 drum event chain
```

输出：

```json
{
  "time": 32.521,
  "instrument": "kick",
  "confidence": 0.91
}
```

再根据 Canonical Timeline 映射到：

```text
bar_index
beat_index
16th subdivision
```

形成：

```text
kick_grid[16]
snare_grid[16]
hat_grid[16]
percussion_grid[16]
```

后续如果音乐人确认：

```text
Snare
Clap
Closed Hat
Open Hat
Cymbal
Tom
Percussion
```

都是必须，则需要训练 Fine Drum Event Model。

---

## 4.3 Bass Note / Pitch

输入：

```text
bass stem
```

模型：

```text
Basic Pitch
```

输出：

```text
onset
offset
pitch
pitch bend
confidence
```

再计算：

```text
bass_activity
sub_energy
attack
decay / release proxy
pitch movement
note density
bass grid
```

这些是后面 Bass Semantic Head 的显式证据。

---

## 4.4 Vocal

输入：

```text
vocals stem
```

输出：

```text
vocal_activity
vocal_density
F0
F0_coverage
pitch_range
pitch_sustain
onset_density
melodic_contour
```

这部分已有较强基础。

---

## 4.5 Harmony

输入：

```text
Original Mix
必要时 other stem
```

输出：

```text
global_key
mode
key_confidence
chroma / HPCP
local_key candidate
chord candidate
```

第一阶段：

- Global Key 保留现有高置信门控。
- Chroma / HPCP 做 Bar-level 聚合。
- Chord 暂不作为强依赖，除非音乐制作人确认必须。

---

## 4.6 Acoustic / DSP

直接计算：

```text
Integrated LUFS
Short-term Loudness
True Peak
Dynamic Range
Sub / Bass / LowMid / Mid / HighMid / High Energy
Spectral Centroid
Spectral Flux
Transient Density
```

这部分不需要训练数据。

---

# Stage 5：MERT Shared Representation

这一层是下一阶段真正新增的基础设施。

## 5.1 输入

默认使用：

```text
Original Mix
```

而不是直接只用 Stem。

原因：

MERT 本身是在完整音乐录音域上做预训练，完整 Mix 更接近原始训练分布。

对于 Vocal / Bass 等任务，可以额外做：

```text
Full Mix MERT
vs
Stem MERT
vs
Full Mix + Stem
```

A/B 实验。

第一版不能假定 Stem 输入一定更好。

---

## 5.2 MERT 输出到底是什么

MERT-v1-95M 的典型输出：

```text
13 × T × 768
```

可以理解为：

```text
13组不同层级的音乐表示
每个时间点一个768维向量
```

不是：

```text
808 = 0.8
Rap = 0.9
```

真正的结构是：

\[
H^{(l)}=
[h_1^{(l)},h_2^{(l)},...,h_T^{(l)}]
\]

每个：

\[
h_t^{(l)}\in R^{768}
\]

这些向量只表示：

> 当前时间附近的音乐状态在模型内部如何编码。

---

# Stage 6：MERT 向量变成可训练的音乐表示

这是整个方案最关键、也最容易产生误解的步骤。

## 6.1 Layer Selection

MERT 不同层包含不同抽象程度的信息。

我们不能人为规定：

```text
第4层 = Drum
第8层 = Vocal
第12层 = Style
```

正确方式是验证。

第一阶段：

```text
L4
L6
L8
L10
L12
```

分别训练同样的 Head，看 Validation 表现。

第二阶段可以使用 Learnable Layer Mixer：

\[
z_t=\sum_l\alpha_lh_t^{(l)}
\]

\[
\alpha_l=softmax(a_l)
\]

即：

> 让一个任务自己学“哪些 MERT 层更有用”。

---

## 6.2 长歌曲切片

MERT-v1 预训练 context 为 5 s。

第一版建议：

```text
window = 5 s
hop = 2.5 s
```

例如：

```text
0.0 ───────── 5.0
      2.5 ───────── 7.5
            5.0 ───────── 10.0
```

重叠区域做平均或中心加权。

最终拼成：

```text
整首歌时间轴上的 MERT representation
```

这属于 HarBeat 的工程参数，需要通过任务效果和 GPU 开销实测调整。

---

## 6.3 对齐到 Beat / Bar

假设：

```text
Bar 18
start = 32.120 s
end   = 33.836 s
```

选择所有：

\[
t_k\in[32.120,33.836]
\]

的 MERT token：

\[
Z_{18}=\{z_k\}
\]

然后 Mean Pool：

\[
e^{bar}_{18}
=
\frac1N\sum_{k\in Bar18}z_k
\]

结果：

```text
Bar 18 → 768D MERT Bar Embedding
```

同理得到：

```text
Beat Embedding
Bar Embedding
4-Bar Context Embedding
8-Bar / Section Embedding
```

---

## 6.4 为什么需要多个时间尺度

不同特征需要不同上下文。

| 任务 | 推荐上下文 |
|---|---|
| Vocal Activity | frame / 1–3 s |
| Rap / Singing | 3–5 s / 1–2 Bar |
| Bass Type | 1–4 Bar |
| Groove | 2–4 Bar |
| Phrase | 前后 8–16 Bar 序列 |
| Section | 长序列 |
| Style | 8–16 Bar / Section / 30 s |

不能用“所有任务统一 5 秒平均”的方式。

---

# Stage 7：从 MERT 表示变成具体音乐特征

这里必须明确一个核心概念：

> **MERT 向量本身没有固定的“物理含义名称”。**

不是：

```text
第 100 维 = Rap
第 200 维 = 808
第 500 维 = Groove
```

真正发生的是：

```text
MERT 向量
+
标签数据
↓
监督训练
↓
Head 学会一个映射函数
↓
具体语义
```

数学上：

\[
y=f_\theta(z_{\text{MERT}},x_{\text{explicit}})
\]

也就是说：

> “物理/音乐语义”来自训练标签对高维表示空间的约束，而不是人工解释单个维度。

---

# 8. 四种统一 Head

后续所有任务尽量复用四种 Head 模板。

---

## 8.1 Classification Head

适用于：

```text
Rap / Singing / Spoken
808 / Synth Bass / Electric Bass
Section Label
Groove Label
Style
```

MERT 首先投影：

\[
m=GELU(W_pz+b_p)
\]

例如：

```text
768 → 256
```

显式特征标准化：

\[
\tilde x=(x-\mu)/\sigma
\]

融合：

\[
u=[m;\tilde x]
\]

然后：

```text
Linear
→ GELU
→ Dropout
→ Linear
```

### 单标签

例如 Bass Type：

```text
808
Synth Bass
Electric Bass
Other
```

使用 Softmax。

### 多标签

例如 Style / Groove：

```text
Trap = yes
Rage = yes
Hip-Hop = yes
```

使用 Sigmoid。

---

## 8.2 Regression / Score Head

适用于：

```text
style_stability
groove_strength
melody_activity
harmonic_stability
```

输出：

\[
s\in[0,1]
\]

---

## 8.3 Sequence / Boundary Head

适用于：

```text
Phrase Boundary
Section Boundary
Vocal Ending
Melody Ending
Style Change
```

输入不是一个 Bar：

```text
Bar i-8 ... Bar i ... Bar i+8
```

使用：

```text
BiGRU
或
TCN
```

输出：

```text
P(boundary at Bar i)
```

---

## 8.4 Metric Embedding Head

适用于：

```text
Groove Similarity
Timbre Similarity
Melody Similarity
Style Similarity
```

输出：

```text
128D / 256D embedding
```

L2 normalize：

\[
\hat e=e/\|e\|_2
\]

比较：

\[
similarity(A,B)=cos(\hat e_A,\hat e_B)
\]

这类结果不需要强行命名成“具体鼓是什么”，只回答：

> A 和 B 在某个音乐维度上像不像。

对于接歌，这是非常有价值的输出。

---

# 9. 每个核心语义特征如何实现

---

# 9.1 Vocal Semantic：Rap / Singing / Spoken / Vocal Chop

## 输入数据

音频：

```text
Original Mix 3–5 s
```

显式特征：

```text
vocal_activity
vocal_density
F0_coverage
pitch_range
pitch_sustain
onset_density
melodic_contour
```

MERT：

```text
3–5 s MERT representation
```

## 路线

```text
Full Mix
   ↓
MERT
   ↓
LayerMix
   ↓
Temporal Pool
   ↓
MERT 256D
      │
      ├────────────┐
      │            │
Vocal Explicit     │
      │            │
      └── Fusion ──┘
            ↓
        Vocal Head
            ↓
Rap / Singing / Spoken / Chop
```

## 输出

```json
{
  "rap_probability": 0.82,
  "singing_probability": 0.13,
  "spoken_probability": 0.03,
  "vocal_chop_probability": 0.02
}
```

如果音乐制作人认为 Sing-Rap 可以同时成立，则改为 Multi-label。

## 数据集

单位：

```text
3–5 s clip
```

Pilot：

```text
500–1000 clips / class
```

建议第一轮总计：

```text
约 2000–4000 条
```

---

# 9.2 Bass Semantic：808 / Synth Bass / Electric Bass

## 输入

```text
Original Mix MERT
+
Bass Stem Explicit
```

Explicit：

```text
pitch
pitch bend
sub_energy
attack
decay
release
spectral centroid
spectral flatness
note density
pitch movement
```

## 路线

```text
Original Mix → MERT → 256D ────────┐
                                    ↓
Bass Stem → Basic Pitch / DSP → Fusion
                                    ↓
                                Bass Head
                                    ↓
                         808 / Synth / Electric / Other
```

## 输出

```json
{
  "808": 0.81,
  "synth_bass": 0.14,
  "electric_bass": 0.03,
  "other": 0.02
}
```

## 数据

1–4 Bar 一条样本。

Pilot：

```text
300–500 clips / class
```

正式：

```text
1000–3000 / class
```

重点必须有 Hard Negative：

```text
sub-heavy synth but not 808
short 808
distorted 808
pitch-slide non-808 bass
```

---

# 9.3 Groove

## 输入

MERT：

```text
2–4 Bar
```

Explicit：

```text
kick_grid
snare_grid
hat_grid
percussion_grid
bass_grid
microtiming
drum_density
bass_density
```

## 路线

```text
Drum / Bass Grid
       ↓
   Grid Encoder
       │
       ├──────────────┐
                      ↓
MERT Rhythm Context → Fusion
                      ↓
                 Groove Head
                      ↓
             Groove probabilities
```

## 输出

```json
{
  "four_on_floor": 0.91,
  "halftime": 0.08,
  "breakbeat": 0.11
}
```

## 数据

单位：

```text
2 / 4 Bar window
```

Pilot：

```text
300–500 windows / class
```

正式：

```text
1000+ / class
```

Groove taxonomy 必须在音乐制作人确认后才能正式定。

---

# 9.4 Phrase Boundary

## 输入

每个 Bar：

```text
MERT Bar Embedding
Vocal Activity
Bass Activity
Drum Density
Chroma Change
Energy Change
Section Candidate
```

然后形成序列：

```text
Bar i-8 ... Bar i ... Bar i+8
```

## 模型

```text
BiGRU / TCN
```

## 输出

\[
P(phrase\_boundary_i)
\]

例如：

```text
Bar 24 → 0.10
Bar 25 → 0.92
Bar 26 → 0.06
```

再根据边界间距离计算：

```text
phrase_length_bars
```

因此不是：

```text
每8小节强行切一次
```

而是：

```text
先检测边界
再统计长度
```

## 数据

音乐人只需要标：

```json
{
  "song_id": "001",
  "phrase_boundary_bars": [1, 9, 17, 25, 41]
}
```

Pilot：

```text
100–200 songs
```

正式：

```text
500–1000 songs
```

---

# 9.5 Section

基础 Section 第一版优先使用：

```text
All-In-One
```

直接得到：

```text
segment boundary
intro / verse / chorus / bridge / outro
```

如果音乐制作人要求：

```text
pre_chorus
post_chorus
drop
break
...
```

则：

```text
All-In-One Candidate
+
MERT Bar Sequence
+
Energy / Vocal / Drum / Harmony
↓
Expanded Section Head
```

这样不是让 MERT 从零做结构，而是：

> 用成熟结构模型做 baseline，再用 HarBeat 数据扩充项目需要的语义。

---

# 9.6 Style 21 类

Style 是标准 Multi-label Task。

推荐输入时间尺度：

```text
8 Bar
16 Bar
Section
30 s
```

## 输入

```text
MERT Segment Representation
+
Groove
+
Bass Semantic
+
Vocal Semantic
+
Harmony
```

## 输出

```json
{
  "style_probs": [
    ...
  ],
  "primary_style": "...",
  "style_embedding": [...]
}
```

Style 分类回答：

> 它属于哪些类？

Style Embedding 回答：

> 两段音乐连续意义上有多像？

两者都要保留。

---

# 9.7 Melody

第一阶段不要直接把“完整主旋律转录”设成硬目标。

优先输出：

```text
melody_activity
melody_density
melody_ending_probability
```

如果专项 melody extraction 能稳定给出：

```text
pitch + voicing
```

则这些指标优先从专项模型推导。

MERT 只作为：

```text
辅助 semantic context
```

或后续 similarity embedding。

---

# 9.8 Timbre / Rhythm / Melody Similarity

这类功能不一定需要人工给出复杂类别名称。

例如：

```text
A的鼓音色与B是否相近
A和B的Groove是否相近
A和B的旋律是否相近
```

可以直接使用 Metric Head：

```text
MERT
↓
Factor Projection Head
↓
128D
↓
Cosine Similarity
```

MERIT 2026 已经公开演示：

```text
Frozen MERT-v1-330M
→ Melody Head
→ Rhythm Head
→ Timbre Head
```

因此这条路线成熟度比“自己定义十几个鼓音色标签再分类”更高，也更符合接歌用途。

---

# 10. 统一 BarFeature 格式

最终 Music Analyzer 必须输出统一结构。

```json
{
  "bar_index": 128,
  "start_sec": 201.32,
  "end_sec": 203.18,

  "timing": {
    "bpm": 139.8,
    "beat_positions": [],
    "downbeat_confidence": 0.94
  },

  "structure": {
    "section": "chorus",
    "section_confidence": 0.88,
    "phrase_end_probability": 0.91
  },

  "harmony": {
    "local_key": "F# minor",
    "key_confidence": 0.82,
    "chroma": []
  },

  "rhythm": {
    "kick_grid": [],
    "snare_grid": [],
    "hat_grid": [],
    "drum_density": 0.76,
    "groove_probs": {},
    "groove_embedding": []
  },

  "vocal": {
    "activity": 0.21,
    "density": 0.34,
    "rap_probability": 0.81,
    "singing_probability": 0.11
  },

  "bass": {
    "activity": 0.42,
    "sub_energy": 0.71,
    "bass_type": "808",
    "808_probability": 0.78
  },

  "melody": {
    "activity": 0.38,
    "density": 0.22,
    "ending_probability": 0.67
  },

  "acoustic": {
    "short_term_loudness": -10.3,
    "sub_energy": 0.61,
    "bass_energy": 0.72,
    "mid_energy": 0.49,
    "high_energy": 0.38
  },

  "style": {
    "style_probs": [],
    "embedding": []
  },

  "quality": {
    "validation_status": {},
    "uncertain": false,
    "ood": false
  }
}
```

---

# 11. 每个特征必须保存来源

不能只保存：

```text
808 = 0.82
```

而要保存：

```json
{
  "value": 0.82,
  "model": "bass_semantic_head_v1",
  "backbone": "mert_v1_95m",
  "dataset_version": "bass_semantic_v1",
  "calibration_version": "v1",
  "validation_status": "provisional",
  "confidence": 0.76
}
```

否则以后模型更新后无法追踪结果来源。

---

# 12. 数据集总体设计

下一阶段最大的人力工作确实在数据集。

但不能为每个 Head 建一套完全孤立的数据。

推荐：

```text
Shared Music Pool
      │
      ├── Global metadata
      ├── Style annotation
      ├── Section annotation
      ├── Phrase annotation
      ├── Vocal annotation
      ├── Bass annotation
      └── Groove annotation
```

一首歌尽可能同时贡献多个任务标签。

---

# 13. 数据池规模

第一阶段核心目标域：

```text
约 1000–2000+ 首
```

它是共享歌曲池，不代表所有任务都要完整标注所有歌曲。

实际会是：

```text
Song A → Style + Section + Phrase
Song B → Vocal + Style
Song C → Bass + Groove
...
```

重点是：

```text
高质量标签
目标域覆盖
难例覆盖
```

而不是盲目扩大未标歌曲数量。

---

# 14. Dataset 文件结构

```text
dataset/
├── audio/
│   ├── song_0001.wav
│   └── ...
│
├── metadata.jsonl
│
├── annotations/
│   ├── style.jsonl
│   ├── section.jsonl
│   ├── phrase.jsonl
│   ├── vocal_semantic.jsonl
│   ├── bass_semantic.jsonl
│   └── groove.jsonl
│
└── splits/
    ├── train.json
    ├── val.json
    └── test.json
```

---

# 15. Dataset 标注 Schema

## Vocal

```json
{
  "song_id": "song_001",
  "start_sec": 21.5,
  "end_sec": 26.5,
  "labels": ["rap"],
  "annotator": "producer_01",
  "confidence": 1.0
}
```

## Bass

```json
{
  "song_id": "song_001",
  "start_bar": 17,
  "end_bar": 20,
  "label": "808",
  "annotator": "producer_01"
}
```

## Groove

```json
{
  "song_id": "song_001",
  "start_bar": 17,
  "end_bar": 20,
  "labels": ["halftime"]
}
```

## Phrase

```json
{
  "song_id": "song_001",
  "phrase_boundary_bars": [1, 9, 17, 25]
}
```

## Section

```json
{
  "song_id": "song_001",
  "segments": [
    {
      "start_bar": 1,
      "end_bar": 8,
      "label": "intro"
    }
  ]
}
```

---

# 16. 数据准备流程

数据集不应该直接：

```text
人工从零标
```

而应尽量：

```text
现有模型预分析
↓
生成候选标签 / 候选边界
↓
音乐制作人修正
↓
第二人抽样复核
↓
一致性统计
↓
Dataset Version
```

例如 Phrase：

```text
Section / Energy / Existing Rule
→ 自动给出候选 Phrase Boundary
→ 音乐人拖动 / 删除 / 添加
```

Fine Drum：

```text
ADTOF
→ 自动事件
→ 人工修正 Snare / Clap / Hat
```

可以显著降低标注成本。

---

# 17. Train / Validation / Test

必须避免同歌泄漏。

最低：

\[
Song_{train}\cap Song_{test}=\emptyset
\]

Style / Production / Timbre 等任务建议：

\[
Artist_{train}\cap Artist_{test}=\emptyset
\]

如果存在 Remix：

```text
Original
Remix
Radio Edit
Live Version
```

最好作为同一 Group 切分。

否则模型可能记住歌曲，而不是学到真正特征。

---

# 18. 每个任务必须做三组实验

这是整个 MERT 路线的 Go / No-Go 核心。

## A：Explicit Only

```text
DSP / MIR
↓
Head
```

## B：MERT Only

```text
MERT
↓
Head
```

## C：Fusion

```text
MERT + DSP/MIR
↓
Head
```

例如 Bass：

| 实验 | 输入 |
|---|---|
| A | Pitch + Sub + Envelope |
| B | MERT |
| C | MERT + Pitch + Sub + Envelope |

如果：

```text
A = 0.78
B = 0.83
C = 0.90
```

说明 Fusion 有意义。

如果：

```text
A = 0.90
C = 0.90
```

则这个特征没必要依赖 MERT。

---

# 19. Layer / Pooling / Context 也必须做 Ablation

每个重要任务自动测试：

## Layer

```text
L4
L6
L8
L10
L12
Learnable Mix
```

## Pool

```text
Mean
Mean + Std
Attention
```

## Context

```text
1 Bar
2 Bar
4 Bar
8 Bar
```

最终用 Validation 数据选择，而不是人工猜。

---

# 20. 第一阶段 MERT 必须冻结

```text
MERT.requires_grad = False
```

只训练：

```text
LayerMixer
Projection
TaskHead
```

原因：

- 数据少；
- 训练成本低；
- 不容易过拟合；
- 能真正判断 pretrained representation 是否有价值。

只有 Frozen Backbone 已验证有效以后，再考虑：

```text
Unfreeze Top Layers
LoRA
Partial Fine-tuning
```

---

# 21. Confidence 和 Calibration

Raw probability 不能直接当可靠度。

例如：

```text
rap = 0.95
```

不能解释成：

```text
95% 真实可靠
```

需要 Calibration。

第一版：

```text
Temperature Scaling
Per-class threshold
```

最终：

```json
{
  "rap_probability": 0.88,
  "confidence": 0.79,
  "calibrated": true
}
```

---

# 22. Unknown / OOD

必须允许：

```text
unknown
uncertain
ood
```

例如：

```text
Sing-Rap
特殊 Vocal FX
极端 Bass Processing
新型 Groove
```

如果模型没有学过，宁可输出：

```text
unknown
```

也不能强行映射到已有标签。

OOD 可以结合：

```text
max probability
entropy
embedding distance
class conflict
```

判断。

---

# 23. Transition Engine：单曲分析之后才计算

当 A/B 两首歌都完成 Music Analysis：

```text
A.BarFeature[]
B.BarFeature[]
```

Transition Engine 再计算：

```text
tempo_compatibility
style_similarity
groove_similarity
drum_overlap
drum_timbre_similarity
harmonic_compatibility
local_chroma_similarity
vocal_overlap_risk
melody_overlap_risk
bass_conflict_risk
loudness_difference
spectral_conflict
exit_safety_score
entry_safety_score
transition_window_score
```

这些不是 MERT 的单曲输出。

---

# 24. 工程代码结构

建议：

```text
app/modules/library/
│
├── timeline/
│   ├── canonical_timeline.py
│   ├── feature_alignment.py
│   └── bar_feature_builder.py
│
├── representation/
│   ├── mert_encoder.py
│   ├── mert_chunker.py
│   ├── mert_cache.py
│   ├── layer_mixer.py
│   └── temporal_pooling.py
│
├── learned_features/
│   ├── common/
│   │   ├── projection.py
│   │   ├── fusion.py
│   │   ├── calibration.py
│   │   └── ood.py
│   │
│   ├── vocal/
│   ├── bass/
│   ├── groove/
│   ├── phrase/
│   ├── section/
│   └── style/
│
├── experiments/
│   ├── explicit_only.py
│   ├── mert_only.py
│   ├── fusion.py
│   ├── layer_ablation.py
│   └── context_ablation.py
│
└── model_registry/
```

---

# 25. 每个 Task Head 的标准训练 Pipeline

```text
Dataset
↓
Group Split
↓
Precompute MERT Embedding
↓
Compute Explicit Features
↓
Normalize
↓
Train Head
↓
Validation
↓
Threshold / Calibration
↓
Blind Test
↓
Error Analysis
↓
Music Producer Review
↓
Model Registry
```

---

# 26. 评价指标

## Single Label

```text
Macro F1
Balanced Accuracy
Per-class Precision
Per-class Recall
Confusion Matrix
```

## Multi-label

```text
Macro F1
Micro F1
mAP
Per-class Precision / Recall
```

## Boundary

```text
Precision
Recall
F1
±1 Downbeat
```

## Similarity Embedding

```text
Recall@K
Ranking Accuracy
Human Preference Correlation
```

## Calibration

```text
ECE
Brier Score
Reliability Curve
```

---

# 27. 当前发布状态体系继续保留

所有新模型必须进入：

```text
candidate_only
provisional
validated
failed_validation
```

不能：

```text
Train F1 很高
→ validated
```

必须有：

```text
独立 Blind Target-Domain Test
```

---

# 28. 开发阶段建议

---

## Phase 0：Feature Requirement Freeze

音乐制作人完成 A/B/C 特征确认。

产物：

```text
feature_requirement_v1
taxonomy_v1
annotation_guideline_v1
```

---

## Phase 1：基础架构

完成：

```text
CanonicalTimeline
BarFeature
统一 provenance
MERT cache schema
Dataset schema
```

---

## Phase 2：MERT Infrastructure

完成：

```text
MERT-v1-95M Adapter
5 s chunk / overlap
hidden state cache
Layer selection
LayerMixer
Beat / Bar alignment
```

暂时不训练 Style。

---

## Phase 3：Vocal Semantic PoC

第一项：

```text
Rap / Singing / Spoken
```

原因：

- 数据相对好标；
- 已有 Vocal explicit；
- 当前高层规则不稳定；
- 有公开 vocal downstream precedent。

Go / No-Go：

```text
Fusion 是否明显优于 Explicit
```

---

## Phase 4：Bass / 808

验证 timbre semantic。

---

## Phase 5：Groove

验证：

```text
Drum Grid + Bass Grid + MERT
```

---

## Phase 6：Section / Phrase

Section：

```text
All-In-One baseline
```

Phrase：

```text
Bar sequence + MERT + explicit
```

---

## Phase 7：Style

最后：

```text
MERT Style Head
MAEST baseline
Fusion
```

---

# 29. 工程量评估

以下是基于“现有基础链已经存在”的粗略量级，用于评估项目资源，不是固定工期承诺。

| 工作包 | 软件工程量 | 数据工作量 | 风险 |
|---|---|---|---|
| Canonical Timeline / BarFeature | 中 | 低 | 低 |
| MERT Adapter / Cache / Alignment | 中 | 无 | 低-中 |
| 通用 Training Framework | 中 | 低 | 低 |
| Vocal Semantic Head | 小-中 | 中 | 中 |
| Bass / 808 Head | 小-中 | 中-高 | 中 |
| Groove Head | 中 | 高 | 中-高 |
| Phrase Head | 中 | 高 | 中-高 |
| Expanded Section | 中 | 中 | 中 |
| 21 Style | 中 | 高 | 中 |
| Fine Drum Event | 中-高 | 很高 | 高 |
| Stem Quality | 中 | 高 | 高 |
| Transition Engine | 中 | 需要音乐人评价数据 | 中 |

如果只看代码：

> 绝大多数模块属于标准 PyTorch / MIR 工程，Codex 可以高比例协助完成。

真正耗费人的部分：

```text
标签定义
数据筛选
人工标注
难例复核
音乐听感验收
商业目标域 blind test
```

---

# 30. 项目最大的风险

## 风险 1：标签本身不一致

这是最大风险。

如果两个音乐制作人对：

```text
808
Groove
Phrase
Style
```

长期无法达成一致，模型上限就会被标签噪声限制。

---

## 风险 2：公开数据和真实产品音乐不一致

例如：

```text
孤立 Bass 数据
```

不能直接证明：

```text
商业混音中也能识别 808
```

必须有 HarBeat target-domain test。

---

## 风险 3：MERT 不一定对所有任务有增益

因此必须做：

```text
Explicit
MERT
Fusion
```

三组实验。

---

## 风险 4：许可

目前 MERT-v1-95M Hugging Face checkpoint 标记为：

```text
CC-BY-NC-4.0
```

因此适合作为研发 PoC backbone，但不能默认作为最终商业产品权重。

需要分别核验：

```text
代码 License
Checkpoint License
训练数据 License
下游数据 License
```

Beat This 的公开代码和模型权重是 MIT，但其训练数据来源仍需按项目用途单独审查。

ADTOF 仓库为 CC BY-NC-SA 4.0，也不能直接默认进入商业产品。

---

# 31. 最终可行性判断

这套路线不是：

> “相信 MERT 可以把所有问题解决”。

而是把风险拆开：

### 已成熟、继续使用

```text
Beat / Tempo
Stem Separation
Bass Note/Pitch
DSP
基础 Key
基础 Section Model
```

### 有公开 representation learning 依据，需要项目数据训练

```text
Vocal Semantic
Bass Type
Style
Expanded Section
Similarity Embedding
```

### 必须重点 PoC

```text
808
HarBeat Groove taxonomy
DJ Phrase Boundary
Vocal / Melody Ending
部分 Production Semantic
```

因此整体工程是可落地的。

真正决定项目是否成功的，不是“能不能写出模型代码”，而是：

\[
\boxed{
\text{是否能定义并构建足够可靠的目标域 Ground Truth}
}
\]

---

# 32. 最终一句话路线

> **先保留已经验证的底层音乐测量能力，建立统一 Bar 时间轴；再引入冻结的 MERT 作为共享音乐表示，通过任务专用 Head 把高维向量与 Beat、Drum、Bass、Vocal、Harmony 等显式证据融合，学习 Rap、808、Groove、Phrase、Style 等高层语义；所有新能力必须经过目标域数据、三路 Ablation、Calibration 和 Blind Test 后才进入正式接歌系统。**
