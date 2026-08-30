# HarBeat 后续音乐分析与神经网络路线

本目录保存历史工作之后形成的完整方案构想。它描述目标架构、数据要求和阶段计划，**不是当前代码已经全部实现的能力清单**。

## 文档

- [完整实施方案、Pipeline、数据集与工程路线](01_HarBeat_音乐分析系统_完整实施方案与工程路线.md)
- [MERT、音乐表征与专项模型的技术背景和成熟状态](02_HarBeat_相关技术原理与成熟状态_背景资料.md)

## 与现有工作的关系

```text
当前可复用基础
├─ Beat / Downbeat / Bar 共识时间轴
├─ Demucs 四分轨
├─ 69 项显式特征及验证门禁
├─ All-In-One 段落候选
└─ Discogs-EffNet 13 类原型实验
        ↓
后续建设
├─ Canonical Frame / Beat / Bar / Section 数据合同
├─ MERT / MAEST / Discogs-EffNet 表示缓存与对比
├─ Classification / Regression / Boundary / Metric Heads
├─ Vocal、Bass、Groove、Phrase、Section、Style 任务族
├─ Calibration、OOD、可靠度和 availability mask
└─ 统一 BarFeature → Transition Engine
```

## 当前启动顺序

1. 先完成正式 `sections[]` 合同和 30 首人工段落真值。
2. 建立预训练表示缓存、Layer Mixer、Bar 对齐和版本元数据。
3. 对段落任务分别做 Explicit Only、Representation Only、Fusion 三组实验。
4. 先做线性 Probe/小型 Head；只有证明确有瓶颈且数据足够时才微调 Backbone。
5. Boundary Head 和 Label Head 分开训练、分开评价。
6. 独立盲测通过后再影响自动接歌硬决策。

## 方案状态

| 部分 | 当前状态 |
|---|---|
| Beat/Downbeat/Bar、分轨和部分显式特征 | 已实现，按各自验证范围使用 |
| Discogs-EffNet 风格表示原型 | 已实验，未批准上线 |
| All-In-One 功能段落 | 已接通，未完成人工真值验证和完整落库 |
| MERT 共享表示基础设施 | 方案阶段 |
| Vocal/Bass/Groove 语义 Head | 方案阶段 |
| Phrase/Section Boundary 与 Label Head | 方案阶段 |
| 21 类正式模型、OOD、校准 | 方案阶段，缺数据 |
| 因子化相似度与 Transition Engine 融合 | 方案阶段 |
