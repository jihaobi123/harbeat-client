# HarBeat Live DJ Control — AI 可读移交文档

版本: V2.0 | 日期: 2026-05-31 | 为 AI Agent 编写的完整系统概述

---

## 1. 项目概述

HarBeat 是一个面向无 DJ 场景（街舞 cypher、练习局、party）的轻量 DJ-like 控乐系统。完整产品、软硬件和部署规格以 [`docs/DEVELOPMENT_SPEC.md`](DEVELOPMENT_SPEC.md) 为准。

目标架构：

```
实体意图控制器 ──USB HID──> RK3588 input-daemon
手机 App (Flutter) ──HTTP──> RK3588 edge-agent ──Unix socket──> audio-engine ──> 音响
     │                              │
     └──HTTPS──> 云端网关            └── 本地 cache
                       ▲
                       └── Jetson：歌曲分析、stems、manifest、MixPlan
```

核心原则：**人做判断，系统做执行**。MC / 组织者通过 App 或桌面控制器表达意图，系统自动完成选歌、对齐、转场和兜底。RK3588 是 P0 现场音频主机；手机直出只保留为无 RK 场景的降级模式。

P0 控制器不是缩水 DJ 台。它只保留 `下一首`、`现场能量`、`延长`、`Talk`、`撤销`、`总音量` 六个控件，不暴露 EQ、gain、pitch、crossfader 或 stem mixer。

---

## 2. 模块架构（8 类功能）

模块间通过标准化 schema 通信，**不直接 import 对方内部实现**。

```
C5 交互层 (App UI + 硬件按钮)
  → 用户意图 → ButtonIntent
     ↓
C6 Session 协调器 (app/modules/session/)
  → 状态机 + 队列Buffer + 安全歌池 + 撤销栈
  → 接收意图 → 查 C3 → 发指令给 C4
     ↓ candidate query        ↓ control command
C3 推荐引擎                      C4 播放引擎
  (candidate_selector.py)         (stem_automix.py)
     ↓ reads (只读)                 ↓ reads (只读)
C1 音乐分析 (app/modules/library/analysis.py)
  → 20+ 分析维度 → TrackAnalysis schema
     ↓ labeled by
C2 街舞语义曲库 (文化标签)
```

**关键边界规则：**
- C1 只产出数据，不消费数据 — 改分析方法不影响 C3/C4/C6
- C3 产出候选列表，不执行播放 — 改推荐策略不影响播放引擎
- C4 接收 ControlCommand，执行声音操作 — 不关心候选怎么选的
- C6 通过 Protocol 依赖注入 C3/C4，不 import 内部实现

---

## 3. C1 音乐分析层 — 已可用于策略选择，仍需真机校准

### 3.1 核心文件

| 文件 | 作用 |
|------|------|
| `app/modules/library/analysis.py` | **主分析引擎** (~1450行) — analyze_audio_file() 入口 |
| `app/modules/library/stem_analysis.py` | Demucs stems 分析 — 真实 stem 活跃度、质量评分 |
| `app/modules/library/dj_feature_extractor.py` | 25维 DJ 指纹提取 |
| `app/modules/library/genre_classifier.py` | 多源流派分类器（音频特征 + Spotify） |
| `app/modules/dj_control/dance_style.py` | 7种街舞风格加权指纹评分 |
| `app/modules/library/background_tasks.py` | 后台分析管线（Phase 1-5） |
| `scripts/jetson_analysis_pipeline.py` | Jetson 端批量分析脚本 |

### 3.2 已实现的 25 项分析

| # | 分析项 | 函数 | 输出字段 |
|---|--------|------|---------|
| 1 | BPM | librosa beat_track | `bpm` (float) |
| 2 | BPM 曲线 | `_build_bpm_curve()` | `bpm_curve[{start,end,bpm,stability}]` |
| 3 | Tempo 稳定性 | 同上 | `tempo_stability` (0-1) |
| 4 | Beatgrid | `_summarize_beatgrid()` | `beat_points[], beat_confidence, beat_grid_offset, beat_grid_interval, beat_needs_review` |
| 5 | Downbeat | `_detect_downbeats()` | `downbeats[]` |
| 6 | 拍号 | `_detect_downbeats_with_meter()` | `time_signature{numerator,denominator,confidence,needs_review}`；弱证据保守回退 4/4 |
| 7 | 调性 + Camelot | `_analyze_key()` | `key, camelot_key, key_confidence` |
| 8 | 调性候选 + 歧义检测 | 同上 | `key_profile{tonal_clarity, relative_ambiguity, candidates[3]}` |
| 9 | 全曲能量 | RMS tanh 归一化 | `energy` (0-1) |
| 10 | 能量曲线 | `_build_energy_curve()` | `energy_curve[{start,end,energy,relative_energy}]` |
| 11 | LUFS + ReplayGain | `_analyze_loudness()` | `loudness_profile{integrated_lufs, replay_gain_db, clipping_risk}` |
| 12 | 段落结构 | `_detect_phrase_structure()` | `phrase_map[{label,start,end,intensity,is_peak_section,is_valley_section}]` |
| 13 | 段落强度评分 | `_score_section_intensity()` | phrase_map 中的 `intensity, is_peak_section, is_valley_section` |
| 14 | Groove 评分 | `_compute_groove_score()` | `groove_profile{score,label,breakdown}` |
| 15 | Stem 活跃度 | `stem_analysis.py` | `stem_activity{ vocals,drums,bass,other }` |
| 16 | Stem 质量评分 | 同上 | `stem_quality_score`, `stem_quality_profile{completeness,reconstruction_score}` |
| 17 | 人声事件检测 | `_detect_vocal_events()` | `vocal_events[{time,type:"enter"|"exit",confidence}]` |
| 18 | Bass 风险窗口 | `_compute_bass_risk_windows()` | `bass_risk_windows[{start,end,bass_level,risk}]` |
| 19 | 过渡窗口评分 | `_build_transition_windows()` + `_enhance_transition_windows()` | `transition_windows[{mix_in_score,mix_out_score,stem_tags,clean_candidate}]` |
| 20 | 流派分类 (20种) | `genre_classifier.py` | `genre_profile{primary_genre,genres[{name,confidence,source}]}` |
| 21 | DJ Hot Cue (5点) | `_generate_dj_hot_cues()` | `dj_hot_cues[{name,time}]` — intro_end, main_groove, first_drop, best_loop, outro_start |
| 22 | **段落混音推荐** | `_recommend_transition_techniques()` | `transition_recommendations[{start,end,type,best_for_mix_in[],best_for_mix_out[]}]` |
| 23 | Intro / Outro 干净度评分 | `stem_analysis.py` | `intro_clean_score`, `outro_clean_score`；stems 不完整时不冒进 |
| 24 | 舞池画像 | `_analyze_dancefloor_profile()` | `danceability_score`, `physical_energy`, `tension`, `peakness`, `fatigue_risk` |
| 25 | Mood 标签 | 同上 | `dancefloor_profile.mood_tags[]`，当前为可解释规则标签 |

### 3.3 analyze_audio_file() 返回的完整 schema

```python
{
    "bpm": float, "duration": float, "energy": float,
    "key": "C major", "camelot_key": "8B", "key_confidence": float,
    "key_profile": {tonal_clarity, relative_ambiguity, candidates[], method},
    "beat_points": [float], "bpm_curve": [{start,end,bpm,stability}],
    "tempo_stability": float,
    "beat_confidence": float, "beat_confidence_details": {},
    "beat_grid_offset": float, "beat_grid_interval": float,
    "beat_engines_used": ["librosa"], "beat_needs_review": bool,
    "downbeats": [float],
    "cue_points": [{time,label,color}],
    "phrase_map": [{label,start,end,bars,energy,intensity,is_peak_section,is_valley_section}],
    "energy_curve": [{start,end,energy,relative_energy}],
    "loudness_profile": {integrated_lufs,peak_dbfs,replay_gain_db,clipping_risk},
    "time_signature": {numerator,denominator,confidence,candidates[],needs_review},
    "groove": {score,label,breakdown},
    "transition_windows": [{start,end,label,mix_in_score,mix_out_score,stem_tags,clean_candidate}],
    "transition_recommendations": [{start,end,label,position,type,best_for_mix_in[],best_for_mix_out[],role_scores_in{},role_scores_out{}}],
    "dj_hot_cues": [{name,label,time,color,confidence,source}],
}
```

加上 stem 分析后（Phase 2, Demucs GPU）额外产生：
```python
{
    "stem_activity": {vocals,drums,bass,other},
    "stem_activity_windows": [{start,end,vocals,drums,bass,other}],
    "stem_quality_score": float,
    "stem_quality_profile": {method,completeness,reconstruction_score},
    "intro_is_clean": bool, "outro_is_clean": bool,
    "intro_clean_score": float, "outro_clean_score": float, "has_drum_loop": bool,
    "vocal_events": [{time,type,confidence}],
    "bass_risk_windows": [{start,end,bass_level,risk}],
}
```

### 3.4 已知精度边界

- 实时 stem 分离（当前仅离线 Demucs GPU）
- 多引擎 BPM 交叉验证（仅用 librosa，未用 madmom/Essentia）
- 风格/流派 CNN 分类器（当前基于规则+Spotify，无训练模型）
- Mood 当前是规则标签，不是训练后的情绪分类模型
- 拍号遇到弱证据时会回退 `4/4` 并标 `needs_review`；这是现场安全策略，不代表已经完成专业级拍号识别
- Intro / Outro clean score 已基于真实 stems 计算，但还需要用更多曲库和 DJ 人工标注校准阈值

---

## 4. C3 推荐引擎 — 已实现（60% 完成）

### 4.1 核心文件

| 文件 | 作用 |
|------|------|
| `app/modules/session/candidate_selector.py` | **规则引擎** (~320行) — 8维排序 |
| `app/modules/dj_control/dance_style.py` | 7种街舞风格评分 |
| `app/modules/playlists/stem_automix.py` | Transition 评分 + preset 选择 |

### 4.2 8 维评分规则

```python
track_score =
    0.25 * scene_fit          # 舞种匹配 + 流派匹配
  + 0.20 * danceability       # 优先 danceability_score，旧数据回退 groove_score
  + 0.15 * energy_fit         # 目标能量匹配 (+intent偏移)
  + 0.15 * transition_compat  # BPM ratio + Camelot distance + stem冲突
  + 0.10 * group_preference   # 场景偏好/禁忌标签
  + 0.10 * diversity_bonus    # 与当前曲目流派不同的加分
  - 0.10 * repetition_penalty # 30min内播放过/同artist降权
  - 0.10 * cold_start_risk    # 长intro/弱beat/低能在peak
```

### 4.3 CandidateSelector 接口

```python
class CandidateSelector:
    def select_candidates(
        current_track_id, session_state, target_energy,
        current_energy, avoid_ids, intent, scene
    ) -> CandidateList:
        # Returns: {candidates[5], best, safe, diverse, fallback_track_id}
```

### 4.4 尚未实现

- 场景歌单自动生成（30-60min playlist）
- ML-based 个性化推荐
- 多人偏好融合

---

## 5. C4 转场/混音引擎 — 已实现 Preset 库

### 5.1 核心文件

`app/modules/playlists/stem_automix.py` (~2150行)

### 5.2 19 种独特 Transition Preset（去重）

**基础过渡 (5):**
| Preset | djay 对应 | Stem | Non-Stem Fallback |
|--------|----------|------|-------------------|
| `fade` | 淡入淡出 | 4轨独立 fade | master crossfade |
| `filter_sweep` | 过滤器 | 4轨 HPF/LPF 扫频 | master HPF sweep |
| `eq_bass_swap` | EQ低频交换 | bass 轨精确交换 | master low_eq 淡化 |
| `echo_freeze` | 回声淡出 | A.vocals/drums echo | master echo + xfade |
| `auto` | 自动 | auto_select_preset() 8规则 | 同 |

**创意效果 (8):**
| Preset | djay/Spotify 对应 | 手法 |
|--------|------------------|------|
| `dissolve` | djay Dissolve | 步进式 gain gating + reverb wash |
| `melt` | Spotify Melt | 极慢 S-curve + 大量 reverb, 16-24 bar |
| `wave` | Spotify Wave | LFO 节奏脉冲 8次, HPF/LPF 交替呼吸 |
| `tremolo` | djay Tremolo | 周期性 gain 调制, 节奏同步 |
| `lunar_echo` | djay Lunar Echo | echo_send + reverb_send 空间化 |
| `riser` | djay Riser | HPF 爬升 + gain 推高 + B 冲击进入 |
| `sweep` | djay Sweep | A lowpass↓ + B lowpass↑ 交叉 |
| `hydrant` | djay Hydrant | echo+reverb+HPF+gain push 组合 |

**Neural Mix / Stem-aware (3):**
| Preset | djay 对应 | 手法 |
|--------|----------|------|
| `neural_fade` | Neural Mix Fade | 3阶段: bass→vocal→drum 独立 fade |
| `neural_echo_out` | Neural Mix Echo Out | vocals+other echo, drums hold→exit |
| `harmonic_sustain` | Harmonic Sustain | A harmony sustain(reverb), B rhythm 从下进入 |

**结构型 (3):**
| Preset | 说明 |
|--------|------|
| `hard_cut` | 直接切 |
| `breakdown_drop` | 结构断点切入 |
| `loop_bridge` | Loop 桥接 |

**Legacy 别名 (6):** bass_swap, vocal_handoff, drum_bridge, acapella_overlay, instrumental_under_vocal, fallback_crossfade

### 5.3 关键：全部 19 种都可以无 stems 触发

- 8 种原生 non-stem（主设计不依赖 stems）：fade, filter_sweep, dissolve, melt, wave, tremolo, riser, sweep
- 11 种有 stem 增强 + non-stem fallback：有 stems→分轨精确；没有→master EQ/echo/reverb 模拟

### 5.4 每个 Preset 的数据结构

```python
class AutomationCurve:
    target: CurveTarget  # A.vocals, A.drums, A.bass, A.other, B.*, master
    param: CurveParam    # gain, low_eq, mid_eq, high_eq, highpass, lowpass, echo_send, reverb_send, mute
    points: [(t, value)]  # t∈[0,1], 0=transition start, 1=end
    shape: CurveShape    # linear, equal_power, exponential, s_curve
```

### 5.5 Auto Selector 规则（`auto_select_preset`）

```python
if BPM ratio > 1.12 → hydrant / neural_echo_out
elif > 1.06       → echo_freeze / lunar_echo
elif energy_up + jump > 0.15 + B>120 → riser
elif key_dist ≤ 1 + stems            → harmonic_sustain
elif 双人声 (vocal_a>0.5 && vocal_b>0.5) → neural_fade / echo_freeze
elif 双bass (bass_a>0.5 && bass_b>0.5)   → eq_bass_swap / filter_sweep
elif energy_jump > 0.3 + B>125           → riser
elif 双低能 < 0.35                        → dissolve
else → neural_fade(stems) / fade(non-stem)
```

### 5.6 C6→C4 桥接函数

```python
def select_transition(from_ctx, to_ctx, *, user_preset="auto", intent=None):
    # Returns (TransitionPreset, curves: list[AutomationCurve], meta)
```

### 5.7 RK 执行层现状

- RK3588 `audio-engine` 已有本地实时执行 MVP：双 deck、自动 crossfade、stem-aware / non-stem 降级和 `playback_tier`。
- 已修复 `slam` 中段静音洞，并放缓 `vocal_handoff` 的 B bass 进入，避免双 bass 叠满。
- 待补：Time-stretch 分级执行、Loop/延长实时控制，以及 RK 真机四首连续试听验收。

---

## 6. C6 Session 编排 — 已实现

### 6.1 核心文件

`app/modules/session/` 目录 (~1000行，6个文件)：

| 文件 | 作用 |
|------|------|
| `schemas.py` | 所有跨模块通信的数据类 |
| `state_machine.py` | Session 状态机: setup→warmup→build→peak→recover→hold→emergency→close |
| `queue_manager.py` | 队列 Buffer + play history + repetition penalty |
| `safety_pool.py` | 安全歌池 (10-30首 fallback) |
| `undo_stack.py` | 撤销栈 (max 10 actions) |
| `coordinator.py` | **中央协调器**：C5意图→查C3候选→发C4指令→记undo |

### 6.2 接口

```python
coord = SessionCoordinator(config, candidate_selector, playback_controller)
coord.start(scene_config)

# C5 → C6
cmd = coord.handle_intent(ButtonIntent(action="energy_up"))

# C4 → C6 (feedback)
coord.on_track_changed(track_id, energy=0.65)

# Get UI state
snap = coord.snapshot()  # → SessionSnapshot
```

### 6.3 状态机 transitions

```
warmup → build (energy_up / auto after 4 tracks)
build → peak (energy_up / auto after 5 tracks)
peak → recover (energy_down / auto after 6 tracks)
recover → build (energy_up)
any → emergency (emergency_next / force)
any → hold (hold intent)
```

---

## 7. 数据库模型（LibrarySong）

`app/modules/library/models.py` — 45+ 字段，核心分析字段：

```python
bpm, key, camelot_key, key_confidence, key_profile,
energy, energy_curve, loudness_profile,
beat_points, bpm_curve, tempo_stability,
beat_confidence, beat_grid_offset, beat_grid_interval, beat_needs_review,
downbeats, phrase_map, cue_points,
transition_windows, transition_recommendations,
stem_activity, stem_activity_windows, stem_quality_score, stem_quality_profile,
vocal_events, bass_risk_windows,
groove_score, groove_profile, time_signature, genre_profile,
music_features (25-dim DJ fingerprint),
dance_styles, dance_style_scores, dance_style_status,
intro_is_clean, outro_is_clean, intro_clean_score, outro_clean_score, has_drum_loop,
```

---

## 8. 后端 API 端点

### 8.1 RK 已有端点

| 方法 | 路径 | 作用 | 位置 |
|------|------|------|------|
| GET | `/health`, `/state`, `/api/edge/status` | RK 健康和真实播放状态，包含 `playback_tier` | RK `edge-agent/main.py` |
| POST | `/load_plan`, `/play`, `/pause`, `/resume`, `/seek`, `/xfade`, `/prefetch`, `/trigger` | 计划同步和基础播放控制 | RK `edge-agent/main.py` |
| POST | `/stem_solo`, `/eq` | 工程与高级入口，不进入普通 UI | RK `edge-agent/main.py` |
| POST | `/transition/plan` | 批量歌曲转场规划 | RK `edge_agent/transition_api.py` |
| WS | `:9001/ws` | `playback_state`、`device_info`、`key_event` | RK `edge_agent/ws_server.py` |

### 8.2 C6 意图 API（尚未部署）

Flutter 客户端已经预留 `/live/override` 和 `/live/intent` 调用，但 RK `edge-agent` 还没有注册对应 router。下一步需要把 `app/modules/session/` 的 Coordinator 接入 RK，并新增：

| 方法 | 路径 | 作用 |
|------|------|------|
| POST | `/live/intent` | `next`、`energy_up/down`、`hold`、`talk`、`undo` |
| GET | `/live/session` | 返回状态机、候选、待执行动作 |
| POST | `/live/session/start` `/live/session/stop` | 创建和结束现场 session |
| POST | `/controller/event` | 接收控制器语义事件 |

---

## 9. Flutter App 端

| 文件 | 作用 |
|------|------|
| `mobile/lib/src/edge_agent_client.dart` | RK HTTP 客户端（state polling, override, intent） |
| `mobile/lib/src/live_deck_page.dart` | Live Deck UI（连接状态、当前播放、过渡信息、按钮） |
| `mobile/lib/src/live_models.dart` | Live 模型类 |
| `mobile/lib/src/home_page.dart` | 导航（含 Live tab + RK URL 配置） |
| `mobile/lib/src/app.dart` | App 根（RK URL 持久化） |

---

## 10. 测试覆盖

```
221 tests passed, 0 failed
```

测试文件：
- `app/tests/test_analysis_features.py` — BPM curve, beatgrid, energy, transition
- `app/tests/test_key_analysis.py` — Key/Camelot 检测
- `app/tests/test_loudness_analysis.py` — LUFS/ReplayGain
- `app/tests/test_stem_analysis.py` — Stem 分析
- `app/tests/test_genre_classifier.py` — 流派分类
- `app/tests/test_extended_analysis.py` — 拍号, Groove, 人声事件, Bass风险, Stem过渡
- `app/tests/test_session.py` — C6 状态机, Undo, Queue, SafetyPool, Coordinator (41 tests)
- `app/tests/test_candidate_selector.py` — C3 推荐规则引擎 (20 tests)
- `app/tests/test_c3_c6_integration.py` — C3↔C6 集成 (7 tests)
- `app/tests/test_analysis_manifest.py` — Manifest 导出
- `app/tests/test_dj_fingerprint.py` — DJ 指纹
- `app/tests/test_transition_planner.py` — Transition 评分
- `app/tests/test_stem_automix_bridge.py` — Stem automix 桥接

---

## 11. 剩余关键缺口（按优先级）

### P0 — 核心体验
- [ ] **C4 真机验收**：RK3588 audio-engine 已有本地实时 MVP，需部署后完成四首连续试听、stems FX 和降级路线验收
- [ ] **C6 Session API**：将 session coordinator 注册为 RK `edge-agent` router，接收 App 和控制器意图
- [ ] **C3 接入真实曲库**：CandidateSelector 目前用 dict registry，需接 DB query
- [ ] **控制器样机协议**：先做 USB HID 桌面小控台，六控件发送语义事件，不发送 DJ 参数

### P1 — 完善
- [ ] 场景歌单自动生成（30-60min playlist）
- [ ] Time-stretch 分级策略（0-3/3-6/6-12/12+%）
- [ ] Loop/延长 实时控制
- [ ] Ducking/Talkover
- [ ] 控制器 BLE、灯光、震动和断连恢复

### P2 — 增强
- [ ] 街舞标签体系 + 人工审核后台
- [ ] 反馈学习闭环
- [ ] 实时 stem 分离
- [ ] ML 个性化推荐

---

## 12. 开发约定

1. **模块间通信通过标准化 schema**，不直接 import 内部实现
2. **C6 通过 Protocol 依赖注入 C3/C4**，修改推荐算法不改协调器代码
3. **C1 数据只读**，所有模块通过 TrackAnalysis schema 消费
4. **Python 版本**：当前代码使用 `str | None`，运行环境至少需要 Python 3.10
5. **所有新分析函数返回 JSON-serializable** 的 Python 原生类型（float 不 numpy）
6. **每个 preset 必须有 non-stem fallback** — stems 是增强不是前置条件
7. **Git 仓库**：`github.com/jihaobi123/harbeat-client`，分支 `codex/dev-flutter-native-mobile`
8. **控制器只发送语义意图** — 不在普通硬件表面增加 EQ、gain、pitch、crossfader 或 stem mixer

---

## 13. 本轮真实批量验证

执行命令：

```bash
NUMBA_CACHE_DIR=/private/tmp/numba-cache \
python3 scripts/jetson_analysis_pipeline.py \
  --tracks-dir data/tracks \
  --output data/jetson_analysis_v9.json
```

结果：7 首测试曲目全部完成分析。每首歌都有 BPM、BPM 曲线、beatgrid、key、Camelot、能量曲线、LUFS、phrase map、拍号、groove、danceability、mood、genre、transition windows、DJ hot cues 和段落混音推荐。

两首拍号证据较弱的曲目会回退到 `4/4`，并在 `time_signature.needs_review` 标记人工复核。部署时不要把这个标记吞掉。

迁移脚本：

```bash
python3 scripts/migrate_library_analysis_fields.py
```

已验证可重复执行：旧表第一次新增 35 个 DJ 分析字段，第二次执行不会重复修改表结构。
