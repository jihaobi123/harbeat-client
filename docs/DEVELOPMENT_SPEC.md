# HarBeat Live DJ Control — 完整开发规格文档

版本：V1.0 | 日期：2026-05-31
基于：《功能类别架构拆解文档》+《产品语言到产品功能落地实现版》

---

## 当前实现快照

这份文档同时承担“目标规格”和“落地状态表”的作用。读代码时以这一节为准，不要只看后面的长期规划。

| 模块 | 当前已经存在 | 还没有完成 |
|------|--------------|------------|
| C1 音乐分析 | BPM 曲线、beatgrid 质量、downbeat、弱证据拍号回退、key/Camelot、LUFS、energy、groove、真实 stems 活跃度、stem 质量 profile、vocal events、bass risk、clean intro/outro 分数、danceability、mood、genre、hot cues、transition windows | 多引擎 BPM 交叉验证、训练后的 genre/mood 模型、DJ 人工校准工具 |
| C3 推荐 | `CandidateSelector` 规则引擎、best/safe/diverse 候选、显式 danceability 消费、安全池 clean score 门槛 | 真实曲库 DB adapter、完整 30-60 分钟场景排歌、个性化学习 |
| C4 转场 | `stem_automix.py` 已有 preset 库；RK3588 已有双 deck、实时 crossfade、stem-aware / non-stem 降级 MVP | RK 真机四首连续试听、time-stretch 分级、loop |
| C6 Session | 状态机、队列、SafetyPool、UndoStack、Coordinator 原型 | 注册到边缘端 API、接真实播放器、断电恢复和连续播放真机验收 |
| C5/C7/C8 | Flutter Live Deck 和部分 RK live API 已有草稿 | 现场控制体验、日志闭环、硬件按钮协议和设备状态完整联调 |

---

## 0. 架构总则与模块边界

### 核心模块与职责

```
C5 现场交互 (App UI + 硬件按钮)
  → 用户意图 → 动作派发
     ↓ intent
C6 Session 编排 (状态机 + 安全兜底)
  → 接收意图 → 状态判断 → 执行时机 → 队列管理 → 撤销栈
     ↓ candidate query        ↓ control command
C3 推荐与排歌决策              C4 DJ-like 播放与音乐控制
  → 候选排序 → 规则引擎         → 双 deck → crossfade → loop
     ↓ reads (只读)              ↓ reads (只读)
C1 音乐资产与预处理 (数据源)
  → BPM/beatgrid/key/energy/stem → 结构化 TrackAnalysis
     ↓ labeled by
C2 街舞语义曲库 (文化标签)
```

### 关键边界规则（不可违反）

1. **C1 只产出数据，不消费数据** — 修改分析算法不影响播放或推荐
2. **C3 产出候选列表，不执行播放** — 推荐逻辑变更不触动播放引擎
3. **C4 接收控制指令，执行声音操作** — 不关心候选怎么选的
4. **C6 是唯一调度中心** — 所有模块间通信通过 C6 协调
5. **模块间通过标准化 schema 通信** — 不直接 import 对方内部实现

### 标准化接口 Schema

**C1 → 其他模块 (TrackAnalysis):**
```json
{
  "track_id": "str",
  "bpm": "float", "bpm_curve": "[{start, end, bpm, stability}]",
  "key": "str", "camelot_key": "str", "key_confidence": "float",
  "key_profile": "{tonal_clarity, relative_ambiguity, candidates[]}",
  "energy": "float", "energy_curve": "[{start, end, energy}]",
  "loudness_profile": "{integrated_lufs, replay_gain_db, clipping_risk}",
  "beat_points": "[float]", "downbeats": "[float]",
  "beat_confidence": "float", "beat_needs_review": "bool",
  "phrase_map": "[{label, start, end, intensity, is_peak_section}]",
  "transition_windows": "[{mix_in_score, mix_out_score, stem_tags}]",
  "stem_activity": "{vocals, drums, bass, other}",
  "stem_activity_windows": "[{start, end, vocals, drums, bass, other}]",
  "stem_quality_score": "float",
  "stem_quality_profile": "{method, completeness, reconstruction_score}",
  "vocal_events": "[{time, type, confidence}]",
  "bass_risk_windows": "[{start, end, risk}]",
  "groove_profile": "{score, label, breakdown}",
  "danceability_score": "float",
  "dancefloor_profile": "{physical_energy, tension, peakness, fatigue_risk, mood_tags[]}",
  "time_signature": "{numerator, denominator, confidence, needs_review}",
  "genre_profile": "{primary_genre, genres[], method}",
  "dj_hot_cues": "[{name, label, time, confidence, source}]",
  "cue_points": "[{time, label}]",
  "intro_is_clean": "bool", "outro_is_clean": "bool",
  "intro_clean_score": "float", "outro_clean_score": "float"
}
```

**C3 → C6 (CandidateList):**
```json
{
  "candidates": "[{track_id, score, reason, template}]",
  "fallback_track_id": "str",
  "context": "{current_energy, target_energy}"
}
```

**C6 → C4 (ControlCommand):**
```json
{
  "action": "xfade|loop|duck|emergency_next|pause",
  "params": "{to_track_id, style, fade_sec, execute_at}"
}
```

---

## 1. C1 音乐资产与预处理 — 详细开发路径

### 1.1 BPM 检测
- **DJ 怎么做**: 耳朵听 + rekordbox/Serato 分析；手动 tap tempo；处理 half-time/double-time
- **竞品**: Mixed In Key 多算法交叉验证；rekordbox 自研引擎
- **技术方案**: librosa beat_track + onset_strength → BPM + bpm_curve (16-beat滑动窗口) + tempo_stability
- **输出**: `bpm`, `bpm_curve[{start,end,bpm,stability}]`, `tempo_stability`
- **状态**: ✅ 已实现

### 1.2 Beatgrid 生成
- **DJ 怎么做**: rekordbox 自动分析 → 手动调第一拍 → 确认 grid 对齐
- **竞品**: rekordbox 动态 beatgrid；Serato 灵活 grid 编辑
- **技术方案**: beat_times → beat_confidence (tempo_stability×0.50 + phase_consistency×0.30 + count×0.15 + curve×0.05)；flag beat_needs_review < 0.72
- **输出**: `beat_points[]`, `beat_confidence`, `beat_grid_offset`, `beat_grid_interval`, `beat_needs_review`
- **状态**: ✅ 已实现

### 1.3 Downbeat / Phrase 检测
- **DJ 怎么做**: 数 8/16 bar → 设 memory cue 标段落边界
- **竞品**: rekordbox Phrase 分析；djay Pro 自动波形分段
- **技术方案**: onset 能量相位推演 → 8-bar 分组 → energy 归一化标注 (intro/buildup/drop/breakdown/outro) → intensity scoring
- **输出**: `downbeats[]`, `phrase_map[{label,start,end,intensity,is_peak_section}]`
- **状态**: ✅ 已实现

### 1.4 Key 检测 + Camelot
- **DJ 怎么做**: Mixed In Key 分析 → Camelot wheel 选下一首
- **竞品**: Mixed In Key 专利算法（最准）；rekordbox 内置（较弱）
- **技术方案**: CQT + CENS 双 chroma → K-S 模板匹配 → top 3 候选 + tonal_clarity + relative_ambiguity
- **输出**: `key`, `camelot_key`, `key_confidence`, `key_profile`
- **状态**: ✅ 已实现

### 1.5 LUFS 响度分析
- **DJ 怎么做**: 看 mixer 电平 → 调 gain/trim
- **竞品**: Platinum Notes 自动 normalize
- **技术方案**: peak_dbfs + RMS + pyloudnorm(optional) → integrated_lufs + replay_gain + clipping_risk
- **输出**: `loudness_profile{integrated_lufs, replay_gain_db, clipping_risk}`
- **状态**: ✅ 已实现

### 1.6 Energy / Groove 评分
- **DJ 怎么做**: 听感判断 energy 1-10 档 + 跳感
- **竞品**: Mixed In Key Energy Level 1-10；Spotify audio-features danceability/energy
- **技术方案**: 全曲 RMS→tanh 归一化；energy_curve: 2s 窗口；groove: steady_beat×0.30 + syncopation×0.30 + downbeat_clarity×0.22 + tempo_lock×0.18
- **输出**: `energy`, `energy_curve[]`, `groove_profile{score,label}`
- **状态**: ✅ 已实现

### 1.7 拍号检测
- **DJ 怎么做**: 听拍子 → 绝大多数舞曲 4/4
- **技术方案**: 对每拍 onset accent 做周期性推断；证据不足时保守回退 4/4，并保留原始候选供人工复核
- **输出**: `time_signature{numerator, denominator, confidence, candidates, needs_review}`
- **状态**: ✅ 已实现

### 1.8 Stem 分离与分析
- **DJ 怎么做**: EQ 操作等价 stem 控制（不实时分离）
- **竞品**: djay Pro Neural Mix (本地 GPU 实时)；Virtual DJ stem 分离
- **技术方案**: Demucs htdemucs (GPU 离线) → stem_analysis.py: RMS + 2s activity + quality + vocal events + bass risk
- **输出**: `stem_activity`, `stem_activity_windows[]`, `stem_quality_score`, `stem_quality_profile`, `intro_clean_score`, `outro_clean_score`, `vocal_events[]`, `bass_risk_windows[]`
- **状态**: ✅ 已实现 (离线 Demucs)

### 1.9 流派识别
- **DJ 怎么做**: 听歌分类 crate；查 Beatport/Spotify
- **竞品**: Spotify audio-features + 人工标注；Beatport 人工分类
- **技术方案**: 多源: (1) 手动 SongTag.style 最高优先; (2) Spotify API → artist/album genres; (3) 音频特征推理: BPM+stem+spectral+groove → 20种 DJ 流派
- **输出**: `genre_profile{primary_genre, genres[{name,confidence,source}], method}`
- **状态**: ✅ 已实现

### 1.10 Transition Windows 评分
- **DJ 怎么做**: 预听判断兼容性 → 选 blend/cut/swap
- **技术方案**: phrase label×energy + stem activity → mix_in_score/mix_out_score/stem_tags/clean_candidate
- **输出**: `transition_windows[{mix_in_score, mix_out_score, stem_tags, clean_candidate}]`
- **状态**: ✅ 已实现

### 1.11 DJ Hot Cue 语义化
- **DJ 怎么做**: intro_end, main_groove, first_drop, best_loop, outro_start
- **技术方案**: 从 phrase_map + transition_windows + intensity 定位 5 个 DJ hot cue 点
- **输出**: `dj_hot_cues: [{name: "intro_end"|"main_groove"|"first_drop"|"best_loop"|"outro_start", time, confidence}]`
- **状态**: ✅ 已实现

### 1.12 舞池画像与 Mood 标签
- **DJ 怎么做**: 不只判断“响不响”，还会判断这首歌是否好跳、是否太累、适不适合继续推高
- **技术方案**: 结合 BPM、energy、groove、stem 活跃度、频谱亮度和 peak section，生成 explainable profile
- **输出**: `danceability_score`, `dancefloor_profile{physical_energy,tension,peakness,fatigue_risk,mood_tags[]}`
- **状态**: ✅ 已实现规则版；训练模型仍是后续增强

---

## 2. C3 推荐与排歌决策 — 详细开发路径

### 2.1 Next Track Selector
- **DJ 怎么做**: 脑中回想 crate → 预听 → 决定
- **竞品**: Spotify Smart Reorder (BPM+Key)；djay Pro Automix
- **技术方案**: 规则引擎打分 (scene_fit×0.25 + danceability×0.20 + energy_fit×0.15 + transition_compat×0.15 + group_pref×0.15 + diversity×0.10 - repetition×0.10)；输出 3 候选: best/safe/diverse
- **状态**: 🟡 已有规则引擎原型；待接真实 DB 曲库和设备 API

### 2.2 场景歌单生成 🔴
- **DJ 怎么做**: 根据 cypher/party/practice 从 crate 挑歌排顺序
- **技术方案**: 场景 → BPM范围 + energy曲线 + 舞种过滤 → 规则排 30-60min 队列
- **状态**: ❌ 待实现

### 2.3 重复疲劳控制
- **DJ 怎么做**: 记住最近放的歌
- **技术方案**: 降权: 30min内播放×0、同artist×0.5、同remix×0.3、同鼓型×0.7
- **状态**: 🟡 已有 avoid list、同 artist 降权和队列历史；同 remix、同鼓型仍待补

---

## 3. C4 DJ-like 播放控制 — 详细开发路径

### 3.1 6 种转场模板 🔴

| 模板 | 适用场景 | DJ 做法 | 技术实现 |
|------|---------|---------|---------|
| Safe Blend | BPM<6% 差 | 16-32拍推进，EQ控低频 | time-stretch对齐→phrase边界crossfade→EQ淡化 |
| Drop In | 前奏太长 | 从hot cue直接进鼓点 | intro skip→定位main_groove→4-bar xfade |
| Energy Lift | 需要炸 | 句尾切到下一首peak | 预留4-8拍buildup→drop进入 |
| Recovery Blend | 需要稳 | 长crossfade+低频淡出 | 更长fade(16-32s), 低能候选 |
| Style Change | BPM>6% | break/echo/clean cut | echo out→hard cut→new track drop |
| Emergency Next | 歌不对 | 立刻切安全歌 | 2秒hard cut→安全池hot cue |

### 3.2 Time-stretch 分级策略 🔴
- 0-3%: 自然 blend
- 3-6%: time-stretch + 转场后回原速
- 6-12%: 不 blend, drop cut / echo out
- 12%+: hard cut

### 3.3 Loop / 延长 🔴
- **DJ 怎么做**: 开 8/16 beat loop → 延长好跳段落
- **技术方案**: beat-quantized, phrase-aware, zero-crossing, tail crossfade

---

## 4. C6 Session 编排 — 已有原型，下一步接设备

### 4.1 Session 状态机
```
Setup → Warmup → Build → Peak → Recover → Hold → Emergency → Close
```
- 每次切歌更新状态
- 按钮触发状态转换
- 能量状态自动衰减（长时间无操作 → 渐进式回落）

### 4.2 队列 Buffer
- 始终预加载 2-3 首候选
- 当前歌剩余 30s 自动准备转场
- 队列为空时从安全歌池补充

### 4.3 安全歌池
- 每个场景 10-20 首"不会太错"的歌
- 离线缓存 P0 歌曲
- 网络失败时切本地缓存

### 4.4 撤销/恢复栈
- 维护操作栈 (max 10 actions)
- undo: 恢复 prev track + position
- 所有非紧急动作可取消

### 4.5 Button Quantization
- 按钮动作默认在下一个 bar/phrase 执行
- 紧急动作(长按)可 1-2 秒内执行
- 每次操作给出倒计时反馈

---

## 5. 差距矩阵总表

| 模块 | 功能 | 状态 | 优先级 |
|------|------|------|--------|
| **C1** | BPM/Beatgrid/Key/Energy/Groove/Stem/Genre/Mood | ✅ 规则版完成 | 校准 |
| **C1** | DJ Hot Cue 语义化 | ✅ | 校准 |
| **C3** | Next Track Selector (规则引擎) | 🟡 原型完成 | P0 |
| **C3** | 场景歌单生成 | ❌ | P1 |
| **C3** | 重复疲劳控制 | 🟡 部分完成 | P1 |
| **C4** | 6 种转场模板 | 🟡 30% | P0 |
| **C4** | Time-stretch 分级 | ❌ | P1 |
| **C4** | Loop/延长 | ❌ | P1 |
| **C4** | Ducking/Talkover | ❌ | P2 |
| **C6** | Session 状态机 | 🟡 原型完成，待部署 | **P0** |
| **C6** | 队列 Buffer | 🟡 原型完成，待真机 | P0 |
| **C6** | 安全歌池 | 🟡 原型完成，待真机 | P0 |
| **C6** | 撤销/恢复栈 | 🟡 原型完成，待接播放器 | P0 |
| **C6** | Button Quantization | ❌ | P0 |
| **C5** | App 控制台完善 | 🟡 50% | P1 |
| **C2** | 街舞标签体系 | 🟡 20% | P1 |
| **C7** | 反馈日志 | ❌ | P2 |
| **C8** | 硬件按钮 | ❌ | P2 |

---

## 6. 下一步执行计划

**C1 规则版已经收口，RK3588 实时链路已有 MVP。下一轮重点是真机四首连续试听，并继续收敛现场控制。**

```
Step 1: 部署 RK audio-engine，完成四首连续试听，确认真实播放不断气
Step 2: 将 C6 Coordinator 注册为 RK API，接入真实状态、队列和安全歌池
Step 3: 给 CandidateSelector 接真实曲库 adapter，跑 7 首及更大曲库连续播放
Step 4: 实现 time-stretch 分级、loop 延长和 button quantization
Step 5: 用 DJ 人工听感记录校准 clean score、拍号复核、转场模板和 mood 标签
```
