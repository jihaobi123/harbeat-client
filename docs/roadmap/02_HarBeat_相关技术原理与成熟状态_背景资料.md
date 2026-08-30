# HarBeat 技术背景资料：MERT、音乐表征与各专项模型的原理和成熟状态

> 版本：2026-08-29
> 文档定位：背景技术说明
> 读者：懂一些机器学习，但不是 MIR / Music AI 专业研究者
> 目标：解释 HarBeat 为什么采用“专项模型 + MERT + Task Head”的路线，各技术到底在做什么、成熟到什么程度，以及哪些是成熟工具、哪些仍然需要我们自己验证。

---

# 1. 先理解两个完全不同的问题

做音乐分析时，经常把两类任务混在一起。

## 第一类：可以比较明确地“测”

例如：

```text
Beat 在哪？
BPM 是多少？
Kick 在哪？
Bass 音高是多少？
这一段响度多大？
当前频谱低频能量是多少？
```

这些任务有明确的物理或时间定义。

适合：

```text
DSP
专项 MIR 模型
```

---

## 第二类：需要“理解”

例如：

```text
这段是 Rap 还是 Singing？
这个 Bass 是不是 808？
这几小节是什么 Groove？
这个位置是不是 Phrase 结束？
这首歌是什么 Style？
两段音乐的 Groove 听起来像不像？
```

这些问题没有简单的单一公式。

适合：

```text
预训练音乐表征
+
监督学习
```

HarBeat 采用的路线，就是把这两类问题分开。

---

# 2. 什么是 MIR

MIR 是：

> Music Information Retrieval，音乐信息检索 / 音乐信息处理。

可以简单理解成：

> 用信号处理和机器学习，从音频中提取结构化音乐信息。

典型任务包括：

```text
Tempo
Beat
Downbeat
Key
Chord
Melody
Instrument
Section
Genre
Mood
```

过去很多 MIR 系统都是：

```text
Audio
↓
手工声学特征
↓
规则 / 小分类器
↓
标签
```

现在越来越多任务改成：

```text
Audio
↓
大规模预训练音乐模型
↓
Representation
↓
小型下游模型
↓
标签
```

MERT 就属于后者。

---

# 3. 什么叫 Representation

假设一段音乐输入神经网络。

网络内部不会只保留：

```text
“这是 Trap”
```

它会把声音变成一个向量：

```text
[0.38, -1.21, 0.07, ...]
```

例如 768 维。

这个向量可以理解成：

> 模型对当前音乐片段的内部描述。

它可能同时包含：

```text
节奏
音色
和声
乐器
人声
结构
制作方式
```

但这些信息是混在高维空间里的。

这就是：

```text
Music Representation
```

或者：

```text
Embedding / Hidden Representation
```

---

# 4. MERT 是什么

MERT 的全名是：

> Acoustic Music Understanding Model with Large-Scale Self-supervised Training

它可以类比：

```text
BERT 是文本的预训练表示模型
MERT 是音乐音频的预训练表示模型
```

这只是帮助理解，并不表示架构完全相同。

MERT 的目标不是直接做一个任务，而是：

> 先从大量音乐中学习一个通用音乐表示，然后让不同任务使用这个表示。

---

# 5. MERT-v1-95M 大概长什么样

MERT-v1-95M：

```text
约 95M 参数
12 层 Transformer
每层 768 维
24 kHz 输入
75 Hz 特征率
预训练 context 5 s
```

输入 1 秒音乐，大约得到：

```text
75 个时间位置
```

每个位置：

```text
768D vector
```

所以：

```text
Audio
↓
MERT
↓
Time × 768
```

不是：

```text
Audio
↓
“Rap”
```

---

# 6. 为什么 MERT 能学到音乐信息

MERT 是自监督预训练。

简单理解：

> 在没有人工逐首标“这是 Groove、这是 Bass、这是 Chorus”的情况下，让模型通过预测被遮住的音乐内容、离散声学目标和音乐相关目标，从海量音乐中自行学习规律。

因此模型会逐渐发现：

```text
哪些声音模式经常一起出现
哪些音高关系相似
哪些节奏有重复结构
哪些音色在上下文中具有相似作用
```

它最终形成的高维空间，能够被很多下游任务重新利用。

---

# 7. MERT 不等于“自动得到特征”

这是最重要的理解。

MERT 输出：

```text
768维向量
```

而 HarBeat 需要：

```text
Rap = 0.82
808 = 0.74
Groove = ...
Style = ...
```

中间需要一个：

```text
Task Head
```

可以理解成：

> 一个很小的翻译器。

---

# 8. Head 是怎么把向量翻译成标签的

以：

```text
Rap / Singing
```

为例。

准备数据：

```text
音频A → Rap
音频B → Singing
音频C → Rap
...
```

MERT 把每段音频变成向量：

```text
Audio A → zA
Audio B → zB
```

然后训练一个小分类器：

```text
zA → Rap
zB → Singing
```

经过很多训练样本后，这个分类器会学到：

> MERT 高维空间中，哪些方向组合与 Rap 更相关，哪些组合与 Singing 更相关。

因此不是：

```text
MERT 第100维就是 Rap
```

而是：

\[
Rap=f(z_1,z_2,...,z_{768})
\]

这就是“向量变成具体语义”的原理。

---

# 9. 为什么还要加入显式特征

因为 MERT 是通用表示，不应该替代所有专业测量。

例如 Groove。

MERT 可以听出：

```text
整体节奏感觉
```

但 HarBeat 同时已经知道：

```text
Kick 精确落在哪个 16 分位置
Snare 精确落在哪
Bass onset 在哪
```

因此最合理的是：

```text
MERT context
+
Kick Grid
+
Snare Grid
+
Bass Grid
↓
Groove Head
```

这叫：

```text
Feature Fusion
```

优势是：

- MERT 提供“听感和上下文”；
- 专项特征提供“精确证据”。

---

# 10. 为什么不同 MERT 层可能不同

Transformer 有很多层。

可以粗略理解：

```text
浅层
↓
更接近局部声学信息

中层
↓
逐渐形成节奏 / 音色 / 音高模式

深层
↓
更抽象的上下文表示
```

但不能说：

```text
第4层一定是鼓
第8层一定是人声
```

不同任务要靠实验选择。

MERT 官方模型卡也明确建议：

> 不同 hidden layer 在不同 downstream task 中表现不同，需要经验选择。

---

# 11. MERT 的成熟度

从“能不能使用”看：

### 很成熟

```text
官方代码
Hugging Face checkpoint
直接输出 hidden states
可冻结做 feature extraction
```

### 已经被公开 benchmark 系统验证

MERT 在 MARBLE benchmark 中被用于多种音乐任务。

### 需要注意

当前常用 `MERT-v1-95M` checkpoint 标记：

```text
CC-BY-NC-4.0
```

因此：

> 很适合科研和产品技术路线 PoC，但不能不经授权直接默认用于商业部署。

---

# 12. MARBLE 是什么

MARBLE 不是另一个音乐模型。

它是：

> Music Audio Representation Benchmark for Universal Evaluation

可以简单理解成：

> 一个专门测试“音乐预训练模型到底学到了什么”的统一考场。

MARBLE 设计了 14 类任务，覆盖：

```text
声学
演奏
乐谱
高层音乐语义
```

包括：

```text
Genre
Key
Chord
Melody
Instrument
Vocal Technique
...
```

它的重要意义是：

> 它证明了“一个预训练音乐 representation + 小型 downstream Head”确实可以覆盖很多不同任务。

所以 HarBeat 的总体思路并不是从零发明。

---

# 13. MERIT：非常值得 HarBeat 参考的新案例

MERIT 是 2026 年的工作：

> Learning Disentangled Music Representations for Audio Similarity

它非常接近 HarBeat 的一个核心需求：

> 同一段音乐能不能拆出“旋律相似度、节奏相似度、音色相似度”。

MERIT 的结构很简单：

```text
Audio
↓
Frozen MERT-v1-330M
↓
抽取多个层
↓
Mean Pool
↓
拼成一个大向量
↓
三个小 Head
├── Melody Head
├── Rhythm Head
└── Timbre Head
```

每个 Head 输出：

```text
128D embedding
```

然后用 cosine similarity：

```text
A和B的 Melody 像不像
A和B的 Rhythm 像不像
A和B的 Timbre 像不像
```

---

# 14. MERIT 为什么对 HarBeat 很重要

它直接证明了一种思路：

> **同一个 MERT Backbone，不同小 Head 可以把原本混在一起的音乐信息变成不同用途的专用表示。**

这和 HarBeat 想做的：

```text
MERT
├── Vocal Head
├── Bass Head
├── Groove Head
├── Phrase Head
└── Style Head
```

非常接近。

当然，不能因为 MERIT 成功就说：

```text
HarBeat 808 一定成功
```

MERIT 本身做的是：

```text
melody / rhythm / timbre similarity
```

但架构原则是有现实依据的。

---

# 15. MAEST 是什么

MAEST 是另一类音乐表示模型。

与 MERT 的主要区别可以简化成：

### MERT

```text
自监督预训练
Waveform
通用 Music Representation
```

### MAEST

```text
监督训练
Spectrogram Transformer
大规模 Style / Tagging 数据
更直接面向高层语义
```

MAEST 的研究发现：

- 较长音频上下文有帮助；
- 不同 Transformer block 的 representation 表现不同；
- 中间 block 在下游 tagging 中可能比最后层更好；
- 可以通过 Patchout 提升特征提取速度。

因此 Style 模块不能只测试 MERT。

HarBeat 应该：

```text
MERT + Style Head
vs
MAEST fine-tune / representation
vs
Fusion
```

---

# 16. Beat This 是什么

Beat This 是专门做：

```text
Beat Tracking
```

的现代神经网络。

它输入音乐后输出：

```text
Beat 时间点
Downbeat 相关信息
```

其特点是：

- 专门为 Beat 任务设计；
- 有公开模型；
- 有训练 / 评估代码；
- 代码和公开模型权重为 MIT；
- 2026 年仍有公开 release。

这类模型与 MERT 的定位完全不同。

Beat This 回答：

> Beat 精确在哪。

MERT 回答：

> 这一段音乐的高层表示是什么。

所以不能用 MERT 代替 Beat This。

---

# 17. All-In-One Music Structure Analyzer 是什么

All-In-One 是一个结构分析模型。

它直接预测：

```text
Tempo
Beat
Downbeat
Functional Segment Boundary
Functional Segment Label
```

例如：

```text
Intro
Verse
Chorus
Bridge
Outro
```

因此它对 HarBeat 的价值非常明确：

> 我们不需要一开始自己训练一个 Verse / Chorus 模型。

第一阶段：

```text
All-In-One → 基础 Section
```

如果后面 HarBeat 还需要：

```text
Pre-Chorus
Post-Chorus
Drop
Break
```

再自己训练 Expanded Section Head。

---

# 18. Demucs 是什么

Demucs 是 Music Source Separation 模型。

输入：

```text
完整歌曲
```

输出：

```text
Vocals
Drums
Bass
Other
```

可以理解成：

> 把混在一起的一首歌，分成几个主要 Stem。

HarBeat 使用 Stem 的原因不是为了“听起来好玩”，而是降低分析难度。

例如：

```text
完整歌曲里直接找 Bass Pitch
```

很难。

分出：

```text
bass.wav
```

以后再跑 Basic Pitch，就会简单很多。

---

# 19. Demucs 成熟度

Demucs 是成熟、广泛使用的开源分轨方案。

但 Meta 原始仓库已经归档，原作者另有 fork，项目不再处于活跃功能开发状态。

这意味着：

> 可以继续作为稳定 baseline，但未来需要评估更现代 separator。

重要的是：

HarBeat 已经有很多下游结果基于 Demucs。

所以不能仅因为“新 separator 排名更高”就立刻替换。

必须验证：

```text
换 separator 后
Bass / Vocal / Drum 下游结果是否真正改善
```

---

# 20. Basic Pitch 是什么

Basic Pitch 是 Spotify 的：

> Automatic Music Transcription 模型。

输入音频：

```text
bass.wav
```

输出：

```text
音符 onset
pitch
duration
pitch bend
```

它的特点是：

- 模型较轻；
- 支持 polyphonic audio；
- 可以生成 MIDI；
- 官方明确说明“单一乐器输入”通常效果更好。

因此：

```text
Demucs Bass Stem
↓
Basic Pitch
```

是一条很自然的工程组合。

---

# 21. ADTOF 是什么

ADTOF 是 Automatic Drum Transcription 相关工作和数据集。

目标是：

```text
什么时候发生了 Kick？
什么时候发生了 Snare？
什么时候发生了 Hi-hat？
```

它提供了大规模非合成音乐 Drum Transcription 数据，公开说明约有 359 小时注释数据。

因此它非常适合：

```text
当前 drum event baseline
模型 teacher
Fine Drum 研究参考
```

但其仓库许可是：

```text
CC BY-NC-SA 4.0
```

所以商业部署不能直接默认使用。

---

# 22. Drum Event 和 Groove 是两个不同任务

这是很重要的区分。

### Drum Event

回答：

```text
32.1 s 是 Kick
32.5 s 是 Hat
33.0 s 是 Snare
```

是“事件检测”。

### Groove

回答：

```text
这几小节整体是什么律动？
```

是“高层音乐语义”。

有了准确 Drum Event：

```text
并不等于
```

自动就有准确 Groove。

HarBeat 之前很多人工规则失败，本质上就出现在这一层。

---

# 23. pYIN 是什么

pYIN 是经典的 Pitch / F0 估计方法之一。

它回答：

```text
这一时刻的人声基础频率是多少？
```

例如：

```text
220 Hz
```

再从 F0 可以推导：

```text
pitch range
sustain
melodic contour
```

这些都是可解释的物理 / 音高证据。

因此 Rap / Singing 不应该完全交给 MERT。

更好的方案：

```text
MERT
+
pYIN / Vocal DSP
↓
Vocal Head
```

---

# 24. Chroma / HPCP 是什么

假设不关心一个音到底在哪个八度。

把所有：

```text
C2
C3
C4
C5
```

归到：

```text
C
```

最终得到 12 个 pitch class 的能量：

```text
C
C#
D
...
B
```

这就是 Chroma / HPCP 类表示。

可以理解成：

> 当前音乐里 12 个音名分别有多强。

它对：

```text
Key
Harmony
局部和声相似度
```

非常有用。

---

# 25. 为什么 Chroma 对接歌很有价值

如果 A 出口和 B 入口：

```text
Global Key 相同
```

但局部和声完全不一样，仍可能发生冲突。

所以：

```text
Global Key
```

解决粗筛。

```text
Local Chroma
```

解决真实 transition window 的局部比较。

因此很多情况下：

> Chroma 比“精确识别每一个复杂和弦名称”更实用。

---

# 26. Key Model 和 Chord Model

Key：

```text
整段主要调性是什么？
```

Chord：

```text
这一小段具体和弦是什么？
```

Chord 的时间粒度更细，也更难。

对于 HarBeat：

### Key

属于强需求。

### Chord

是否必须要做到非常准确，需要音乐人评估。

因为真正的接歌也可以先使用：

```text
Key
+
Chroma
+
Harmonic Stability
```

完成很多和声安全判断。

---

# 27. 为什么“规则”以前容易失败

例如想识别 808。

人工可能写：

```text
低频高
+
Decay 长
+
Pitch 比较稳定
=
808
```

问题是：

现实里：

```text
808 可以失真
808 可以短
Synth Bass 可以低频很高
Electric Bass 也可能有长 sustain
```

所以高层概念很难写成几个固定阈值。

监督学习的作用是：

> 从大量正负例中自动学习复杂边界。

---

# 28. 为什么 MERT + Explicit 往往比只用其中一个合理

MERT 擅长：

```text
复杂上下文
整体听感
高层语义
```

Explicit 擅长：

```text
精确时间
物理量
可解释结构
```

例如 Groove：

```text
MERT
→ “听起来是什么律动”

Drum Grid
→ “鼓到底落在哪里”
```

结合：

```text
更有可能稳定
```

而不是强迫其中一个完成全部工作。

---

# 29. Classification 和 Embedding 有什么区别

这是 HarBeat 后面很重要的一点。

## Classification

输出：

```text
Trap = 0.8
Rage = 0.6
```

回答：

> 它叫什么？

---

## Embedding

输出：

```text
[128维向量]
```

然后比较：

```text
cos(A,B)
```

回答：

> A 和 B 像不像？

对于 DJ 系统，后者经常非常重要。

因为两首歌：

```text
标签不同
```

不代表：

```text
听感一定不兼容。
```

---

# 30. 为什么 MERIT 的 factor embedding 很适合参考

MERIT 已经提供：

```text
Melody embedding
Rhythm embedding
Timbre embedding
```

所以 HarBeat 可以优先直接评估：

```text
MERIT rhythm similarity
MERIT timbre similarity
MERIT melody similarity
```

是否能帮助：

```text
候选歌曲筛选
drum/groove similarity
melody conflict
```

这类功能甚至可能不需要重新人工定义几十个标签。

---

# 31. 什么是 Phrase Boundary

音乐不会只是：

```text
Bar 1
Bar 2
Bar 3
...
```

通常会形成：

```text
一个完整音乐句子
```

例如：

```text
8 Bar Phrase
```

DJ 的切歌通常希望发生在：

```text
句尾
```

而不是任意 Bar。

所以 Phrase Boundary 的目标是：

> 找音乐语义上真正“说完一句话”的位置。

这不是简单：

```text
每8小节切一次
```

因为真实歌曲可能：

```text
4 Bar
8 Bar
16 Bar
非常规 Phrase
```

---

# 32. Phrase 为什么需要序列模型

要判断 Bar 32 是不是 Phrase End，需要看：

```text
前面的发展
当前能量
Vocal 是否结束
Drum 是否填充
Harmony 是否变化
下一 Bar 是否进入新状态
```

所以模型必须看一段 Bar 序列。

常见方案：

```text
BiGRU
TCN
Transformer
```

HarBeat 第一版选择：

```text
BiGRU / TCN
```

是因为模型更小、数据需求更低、容易验证。

---

# 33. 什么是 Calibration

神经网络输出：

```text
Rap = 0.95
```

不一定意味着：

```text
它真的有 95% 可信。
```

有些模型天然非常“自信”。

Calibration 就是：

> 让概率和真实正确率尽量对应。

例如经过校准：

```text
confidence ≈ 0.8
```

的样本，长期看大约真的有：

```text
80%
```

是正确的。

这对产品非常重要。

---

# 34. 什么是 OOD

OOD：

> Out of Distribution，分布外样本。

比如训练集只有：

```text
Rap
Singing
Spoken
```

突然输入：

```text
极端 Auto-Tune Sing-Rap + Granular Vocal FX
```

模型不能假装自己一定认识。

所以系统应该允许：

```text
Unknown
Uncertain
OOD
```

而不是强制选一个类别。

---

# 35. 为什么要冻结 MERT

如果数据只有几千条，而 MERT 有 95M 参数。

直接全部训练：

```text
很容易过拟合
```

而且很难判断：

> 是 MERT 原本学到了这个信息，还是模型重新记住了小数据集。

所以第一阶段：

```text
Freeze MERT
```

只训练：

```text
很小的 Head
```

是最稳妥的验证办法。

---

# 36. 什么情况下才 Fine-tune MERT

只有当：

```text
Frozen MERT
+
合理 Head
+
高质量数据
```

已经证明任务有潜力，但效果仍不足时，再考虑：

```text
Unfreeze top layers
LoRA
Partial Fine-tuning
```

不应该第一天就 Full Fine-tune。

---

# 37. 成熟度总表

| 技术 | 解决问题 | 成熟度 | HarBeat 建议 |
|---|---|---|---|
| Beat This | Beat / rhythm grid | 高 | 生产 baseline |
| Demucs | 4 Stem separation | 高，但维护弱化 | 当前保留 |
| Basic Pitch | Note / pitch transcription | 高 | Bass 主链 |
| pYIN | F0 | 高 | Vocal 主链 |
| Chroma / HPCP | Tonal representation | 高 | Harmony 主链 |
| Global Key | Key recognition | 中高 | 高置信门控 |
| ADTOF | Drum event | 中高 | baseline / teacher |
| All-In-One | Section structure | 中高 | 第一版 Section |
| MERT | 通用音乐 representation | 高研究成熟度 | 共享 semantic backbone PoC |
| MARBLE | representation benchmark | 高 | 技术依据，不是生产模型 |
| MAEST | Style / tagging representation | 中高 | Style 强 baseline |
| MERIT | Melody/Rhythm/Timbre embedding | 新但直接相关 | 值得重点评估 |
| MERT → Rap/Singing | 自定义 vocal semantic | 中 | 需自建数据 |
| MERT → 808 | 自定义 bass semantic | 研究型 | 必须 PoC |
| MERT + Grid → Groove | 自定义 groove | 研究型 | 必须 PoC |
| MERT → DJ Phrase | 自定义 sequence task | 研究型 | 必须 PoC |

---

# 38. 许可成熟度也要单独看

“技术成熟”不代表“可以商用”。

例如：

### Beat This

代码和公开模型权重：

```text
MIT
```

但训练数据来源仍需使用方自己评估。

### MERT-v1-95M

Hugging Face checkpoint：

```text
CC-BY-NC-4.0
```

因此不能直接假定商业可用。

### ADTOF

仓库：

```text
CC BY-NC-SA 4.0
```

也存在商业限制。

### MERIT

公开 Head 标记 MIT，但它基于 MERT-v1-330M，且训练数据集本身存在非商业许可，因此商业链仍需逐项审查。

所以必须分开：

```text
代码 License
权重 License
训练数据 License
```

---

# 39. 为什么整体方案有可行性

这套方案不是要求一个未经验证的新模型做所有事情。

实际是：

```text
Beat
Stem
Pitch
DSP
Key
Section baseline
```

尽量使用成熟技术。

只把：

```text
808
Rap/Singing
Groove
Phrase
Style
```

这些原来最难用规则稳定解决的问题，变成：

```text
预训练 representation + 小 Head + 项目数据
```

所以风险被拆成很多小的独立实验。

---

# 40. 如何判断一个新 Head 是否值得上线

任何任务都比较：

```text
Explicit Only
MERT Only
Fusion
```

例如：

```text
Explicit F1 = 0.82
MERT F1     = 0.86
Fusion F1   = 0.91
```

说明 MERT 有明显价值。

如果：

```text
Explicit = 0.91
Fusion   = 0.91
```

则没必要增加 MERT 依赖。

这样系统不会越来越复杂而没有收益。

---

# 41. 最后用一个简单类比理解整个系统

可以把 HarBeat 看成一个音乐制作团队。

### 专项 MIR / DSP

像：

> 节拍器、调音器、频谱仪、MIDI 转录员。

它们告诉你：

```text
Beat在哪
音高多少
低频多强
```

### MERT

像：

> 一个听过大量音乐、但不会直接给你结论的音乐理解助手。

它提供：

```text
高维音乐经验表示
```

### Task Head

像：

> 经过你们项目培训的专业岗位。

例如：

```text
Vocal Head → 专门判断 Vocal delivery
Bass Head  → 专门判断 Bass type
Groove Head→ 专门判断 Groove
Style Head → 专门判断 Style
```

### Transition Engine

像：

> DJ。

它不重新听原始音频，而是拿前面所有人的分析结果决定：

```text
A和B能不能接
在哪里接
怎么接
```

这就是 HarBeat 最终的技术分工。

---

# 42. 参考资料

## MERT

**MERT: Acoustic Music Understanding Model with Large-Scale Self-supervised Training**

- Paper: https://arxiv.org/abs/2306.00107
- Official code: https://github.com/yizhilll/MERT
- MERT-v1-95M: https://huggingface.co/m-a-p/MERT-v1-95M

---

## MARBLE

**MARBLE: Music Audio Representation Benchmark for Universal Evaluation**

- Paper: https://arxiv.org/abs/2306.10548

---

## MERIT

**MERIT: Learning Disentangled Music Representations for Audio Similarity**

- Paper: https://arxiv.org/abs/2605.27346
- Code: https://github.com/AMAAI-Lab/MERIT
- Model: https://huggingface.co/amaai-lab/merit

---

## MAEST

**Efficient Supervised Training of Audio Transformers for Music Representation Learning**

- Paper: https://arxiv.org/abs/2309.16418
- Code: https://github.com/palonso/MAEST

---

## Beat This

- Code: https://github.com/CPJKU/beat_this

---

## All-In-One Music Structure Analyzer

- Code: https://github.com/infsys-lab/all-in-one-original

---

## Demucs

- Repository: https://github.com/facebookresearch/demucs

---

## Basic Pitch

- Repository: https://github.com/spotify/basic-pitch
- Paper: https://arxiv.org/abs/2203.09893

---

## ADTOF

- Repository: https://github.com/MZehren/ADTOF
