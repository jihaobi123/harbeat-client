# GrooveEngine DJ roadmap (必看)

> 本文档为本次接入 `experimental/GrooveEngine` 时的必看说明，概述当前项目对标真实 DJ 排歌/选歌能力的现状、缺口与优先级。

## 当前已经做到什么

### 1. 基础 DJ 语法已具备
- 基于 BPM、bar、phrase、energy、harmonic/camelot 做两曲转场评分
- 可根据结构选择不同 transition strategy
- 已支持多曲自动排序与 medley 导出

### 2. 多曲自动排序 MVP
当前排序逻辑采用快速可落地 heuristic：
- 起始曲偏向 intro / 低能量
- 后续采用 nearest-neighbor 方式，综合 transition score、BPM 差、Camelot 邻接、平均能量选下一首

### 3. 多曲自动渲染 MVP
- 支持多首真实本地音频自动排序
- 按 transition plan 逐段拼接并导出 medley wav
- 适合快速验证自动 DJ pipeline

---

## 对标真实 DJ，还差什么

### P0：最优先
#### P0-1. 缺少全局 set 结构设计
当前是“当前歌 -> 下一首最优”的局部最优，缺少整场 set 的：
- 开场
- build
- peak
- reset
- close

需要从 greedy 升级到 set-level objective / beam search / constrained graph search。

#### P0-2. 缺少真正专业 beat-aware mixing
当前渲染还是简化离线 crossfade + 少量 FX，不是真正 deck-based DJ mixing：
- 缺 tempo sync / phase alignment
- 缺更细粒度 automation
- 缺 loudness / EQ / dynamics 的专业控制

应逐步把 `audio/engine.py` 和 `audio/mixer_fx.py` 串到主渲染链路。

#### P0-3. 缺少真正的“选歌”
目前是“给定候选 -> 自动排序”，还不是：
- 过滤不适合的歌
- 给出替代曲
- 依据场景决定哪些歌进入 set

---

### P1：第二优先级
#### P1-1. 缺少更丰富的音乐语义 / 风格理解
目前 style fit 偏粗：
- 还缺 groove、texture、vocal presence、genre adjacency、mood 等

#### P1-2. 缺少场景目标 / 风格目标
应支持：
- battle / cypher / showcase / afterparty
- safe / hype / reset-heavy / smooth journey 等任务模式

#### P1-3. 缺少更稳的 harmonic mixing
应增强：
- same key
- relative major/minor
- adjacent Camelot
- modulation tolerance

#### P1-4. 缺少 transition memory
整场 set 还没有约束：
- 避免连续同类策略
- 避免整场过度单调

---

### P2：第三优先级
#### P2-1. 缺少反馈学习
当前权重偏手工，需要后续接：
- pairwise preference learning
- 人工评价回灌
- 历史 transition 成功率

#### P2-2. 缺少真实世界脏数据容错
需要更稳地处理：
- beatgrid 漂移
- phrase/key 误识别
- remix/live 版本差异

#### P2-3. 缺少实时 performance 层
当前更像离线 medley，不像现场 DJ 助手：
- 还缺实时 re-plan
- loop extend
- emergency transition
- crowd feedback

---

## 推荐开发优先级
1. **全局排歌目标函数**
2. **专业化渲染/混音链路**
3. **接入自有模型分数（小姐模型 / 阶段类型模型等）**
4. **做真正的选歌系统**
5. **加入实时反馈与现场化能力**

---

## 当前定位
一句话总结：

> 目前 `GrooveEngine` 更像“结构感知 + 转场感知的自动 medley 原型”，
> 已经有 DJ 基础语法，但还不是可替代真实 DJ 决策的系统。

在本仓库中，它当前以 **实验性模块** 形式接入，后续建议逐步与主仓库已有 `music` / `playlists` / `sessions` 能力融合，而不是长期平行维护。
