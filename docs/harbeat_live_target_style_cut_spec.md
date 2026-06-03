# HarBeat 实时舞种风格切歌落地执行规格

版本：V1.0  
日期：2026-06-03  
读者：后端工程师、Flutter 工程师、RK3588 工程师、AI Agent  
状态：可直接执行  
范围：只修改 **DJ Control 实时播放中的舞种风格切歌、风格备选池、RK 预同步与前端可用体验**。  
不修改：目标能量切歌主逻辑、外部 metadata API 主链路、普通 `/api/dj/styles/pick` 选歌入口、完整 DJ Set 编排、RK audio-engine DSP 算法。

---

## 0. 文档用途

本文件用于指导 AI Agent 对当前 HarBeat 项目新增一个独立模块：

```text
实时舞种风格切歌 Target Dance Style Cut
```

它和“目标能量切歌”是两个独立模块：

```text
能量切歌：用户选择下一首目标能量段，例如 70-80、80-90
风格切歌：用户选择下一首目标舞种，例如 Popping、Locking、House
```

本轮只做大的舞种分类，不做子风格细分。

支持舞种：

```text
breaking
hiphop
popping
locking
house
krump
waacking
```

目标效果：

```text
当前正在播放 Hip-hop
用户点击 Popping
系统从主播放队列 + 风格备选池 + 用户曲库兜底中找 Popping 适配分高、已缓存、可安全切入的歌曲
系统返回推荐下一首和原因
用户确认后，该歌曲插入当前播放位置的下一首，并由 RK 预取 / xfade 执行
```

---

## 1. 当前项目依据

当前项目已有以下能力：

```text
GET /api/dj/styles
POST /api/dj/styles/pick
POST /api/dj/live/pool/prepare
POST /api/dj/cut/plan
POST /api/dj/transitions/plan
```

已有相关字段：

```text
LibrarySong.genre_profile
LibrarySong.genre_profile.style_evidence_v1
LibrarySong.dance_styles
LibrarySong.dance_style_scores
LibrarySong.dance_style_status
LibrarySong.energy
LibrarySong.energy_curve
LibrarySong.bpm
LibrarySong.transition_windows
LibrarySong.vocal_events
LibrarySong.bass_risk_windows
```

已有相关文件：

```text
app/modules/dj_control/router.py
app/modules/dj_control/schemas.py
app/modules/dj_control/dance_style.py
app/modules/dj_control/style_taxonomy.py
app/modules/dj_control/style_reference_profiles.py
app/modules/dj_control/cut_strategy.py
app/modules/dj_control/transition_strategy.py
app/modules/dj_control/mixer_rules.py
app/modules/dj_control/energy_hiphop.py

mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
mobile/lib/src/sync_worker_client.dart
mobile/lib/src/edge_agent_client.dart
```

当前项目中，`/api/dj/styles/pick` 已用于舞种 + 目标时长选歌，读取持久化的 `genre_profile.style_evidence_v1[style]` 和 `dance_style_scores[style]`。本轮不重写它，而是复用这些舞种分数做实时风格切歌。

当前项目中，`/api/dj/cut/plan` 已用于现场快切和目标能量切歌。本轮新增一个新的 intent：

```text
target_dance_style
```

这样风格切歌和能量切歌都属于“实时切歌控制”，但内部策略独立。

---

## 2. 用户体验目标

### 2.1 实时播放界面新增“风格切歌”区

播放中显示：

```text
当前播放：Song A
当前识别舞种：Hip-hop
当前能量：68

目标风格：
[Breaking] [Hip-hop] [Popping] [Locking] [House] [Waacking] [Krump]
```

每个按钮显示可用状态：

```text
Popping｜可切 2
Locking｜可切 1
House｜搜索曲库
Krump｜暂无
```

含义：

```text
可切 N：后续主队列 + 风格备选池中已有 N 首可用且优先缓存的候选
搜索曲库：本地队列/备选池暂无，但点击后后端会从完整曲库兜底
暂无：当前曲库没有足够可信候选
```

### 2.2 用户点击目标舞种

例如用户点击：

```text
Popping
```

前端进入 preview，不要立即切歌：

```text
正在寻找适合 Popping 的下一首...
```

后端返回：

```text
推荐下一首：Song X
目标舞种：Popping
匹配度：92%
能量：78
缓存：已完成，可立即切
推荐切法：percussion_bridge

原因：
- Popping 适配分 0.92
- 命中 Electro / Funk / Boogie 标签
- 当前能量 68，下一首 78，变化可控
- BPM 差较小
- 已在 RK 缓存
```

前端显示按钮：

```text
[确认切歌] [换一首] [取消]
```

---

## 3. 模块边界

### 3.1 风格切歌不是能量切歌

风格切歌只接收：

```text
target_style
```

不接收：

```text
target_energy_bucket
```

但风格切歌内部可以把能量作为安全因素，避免风格切换时能量断层。

例如：

```text
当前 Hip-hop 能量 70
目标 Popping
系统优先找 Popping 且能量 55-85 的歌
不优先找 Popping 但能量 20 或 100 的歌
```

### 3.2 风格切歌不是重新排歌

风格切歌是局部插队：

```text
当前播放 A
原队列：A → B → C → D
用户选择 Popping
系统选中 X
新队列：A → X → B → C → D
```

不是重新生成整套 DJ Set。

---

## 4. 风格备选池设计

### 4.1 Style Reserve Pool

在当前 Live Pool 基础上新增或扩展：

```text
style_reserve_pool
```

结构：

```json
{
  "breaking": ["B1", "B2"],
  "hiphop": ["HH1", "HH2"],
  "popping": ["P1", "P2", "P3"],
  "locking": ["L1", "L2"],
  "house": ["H1", "H2"],
  "krump": ["K1", "K2"],
  "waacking": ["W1", "W2"]
}
```

每个大舞种建议保留：

```text
最低 1 首
推荐 2-3 首
```

如果曲库中某舞种候选不足，可以少于目标数量，但必须在返回中标记：

```text
status = insufficient
```

### 4.2 候选来源

Style Reserve Pool 候选来自用户曲库，但必须排除：

```text
active_queue 中已经存在的歌
played_pool 中已播放的歌
blocked_pool 中禁用的歌
文件缺失或 manifest 无 original 的歌
dance_style_scores[target_style] 低于阈值的歌
```

候选优先级：

```text
dance_style_scores[target_style] 高
style_evidence_v1[target_style].confidence 高
当前风格跨度可控
BPM 差可控
能量变化可控
transition_windows 可用
RK 已缓存或适合提前同步
```

---

## 5. 后端接口设计

### 5.1 扩展 Live Pool Prepare

现有：

```http
POST /api/dj/live/pool/prepare
```

在返回中新增：

```json
{
  "style_reserve_pool": {
    "breaking": ["B1", "B2"],
    "hiphop": ["HH1", "HH2"],
    "popping": ["P1", "P2"],
    "locking": ["L1"],
    "house": ["H1"],
    "krump": [],
    "waacking": ["W1"]
  },
  "style_pool_status": {
    "popping": {
      "available": 2,
      "cached": 1,
      "syncing": 1,
      "status": "ready"
    },
    "krump": {
      "available": 0,
      "cached": 0,
      "syncing": 0,
      "status": "empty"
    }
  }
}
```

请求新增可选字段：

```json
{
  "target_style_reserve_per_style": 2,
  "include_styles": ["breaking", "hiphop", "popping", "locking", "house", "krump", "waacking"]
}
```

如果已有能量备选池，本接口可以同时返回：

```text
reserve_pool_by_energy
style_reserve_pool
```

但二者是独立用途，不要混成一个字段。

### 5.2 扩展 Cut Plan：target_dance_style

扩展现有：

```http
POST /api/dj/cut/plan
```

新增 intent：

```text
target_dance_style
```

请求：

```json
{
  "intent": "target_dance_style",
  "current_song_id": "A",
  "target_style": "popping",
  "active_queue_song_ids": ["B", "C", "D"],
  "style_reserve_pool_song_ids": ["P1", "P2", "P3"],
  "played_song_ids": [],
  "blocked_song_ids": [],
  "current_style": "hiphop",
  "prefer_cached": true,
  "mode": "preview"
}
```

返回：

```json
{
  "intent": "target_dance_style",
  "current_song": {
    "song_id": "A",
    "dominant_style": "hiphop",
    "energy_score": 68
  },
  "target_style": "popping",
  "selected_song": {
    "song_id": "P2",
    "title": "Song X",
    "artist": "Artist X",
    "style_score": 0.92,
    "confidence": 0.86,
    "matched_labels": ["electro", "funk", "boogie"],
    "energy_score": 78,
    "cache_status": "ready",
    "source": "style_reserve_pool"
  },
  "queue_action": {
    "type": "insert_next",
    "after_song_id": "A",
    "remove_from_style_reserve_pool": true
  },
  "candidate_score": 0.88,
  "score_breakdown": {
    "target_style_match": 0.92,
    "transition_safety": 0.81,
    "energy_continuity": 0.78,
    "bpm_compat": 0.74,
    "cache_ready": 1.0,
    "novelty": 0.80
  },
  "recommended_transition_hint": "percussion_bridge",
  "reason": [
    "该歌曲 Popping 适配分 0.92",
    "命中 electro / funk / boogie 标签",
    "能量从 68 到 78，变化可控",
    "BPM 差较小",
    "已在 RK 缓存，可立即切",
    "推荐使用 percussion_bridge 进行风格过渡"
  ],
  "fallback": false
}
```

没有精确候选时：

```json
{
  "fallback": true,
  "fallback_reason": "未找到 Popping 高置信候选，已从曲库中选择 Electro/Funk 标签相近歌曲",
  "selected_song": {
    "style_score": 0.67,
    "source": "library_fallback"
  }
}
```

---

## 6. 候选选择逻辑

### 6.1 查找顺序

用户选择目标舞种后，后端按顺序找：

```text
1. active_queue 剩余歌曲中，目标舞种分高且 RK 已缓存的歌
2. style_reserve_pool 中，目标舞种分高且 RK 已缓存的歌
3. active_queue 中，目标舞种分高但未缓存的歌
4. style_reserve_pool 中，目标舞种分高但未缓存的歌
5. 从完整用户曲库中兜底查找目标舞种高分歌
6. 如果目标舞种候选不足，找目标舞种相关标签高的歌
7. 如果仍无，返回 no_candidate
```

### 6.2 目标舞种匹配分

优先读取：

```text
LibrarySong.dance_style_scores[target_style]
```

如果缺失，读取：

```text
LibrarySong.genre_profile["style_evidence_v1"][target_style]["final_score"]
```

如果仍缺失，降级：

```text
dance_style.score_song_multisource(song, target_style)
```

最低阈值建议：

```text
high_confidence >= 0.75
usable >= 0.55
fallback >= 0.40
```

如果低于 0.40，不应作为目标风格切歌候选，除非用户强制。

---

## 7. 候选评分公式

```text
candidate_score =
0.45 × target_style_match
+ 0.20 × transition_safety
+ 0.15 × energy_continuity
+ 0.10 × bpm_compat
+ 0.05 × cache_ready
+ 0.05 × novelty
```

### 7.1 target_style_match

来源：

```text
dance_style_scores[target_style]
style_evidence_v1[target_style].final_score
```

命中标签可加入解释：

```text
matched_labels
external_sources
reason
```

### 7.2 transition_safety

参考：

```text
transition_windows
vocal_events
bass_risk_windows
stemsAvailable
phraseBarsAvailable
```

要求：

```text
人声冲突风险越低越好
低频风险越低越好
有 clean intro / cue / transition window 加分
```

### 7.3 energy_continuity

风格切歌不是能量切歌，但不能造成能量断层。

推荐：

```text
当前能量与候选能量差 <= 20：高分
差 20-35：中分
差 > 35：低分，除非 recommended_transition_hint 是 reset / impact 类
```

### 7.4 bpm_compat

优先：

```text
BPM 差小
half-time / double-time 关系明确
tempo stability 高
```

### 7.5 cache_ready

```text
ready = 1.0
syncing = 0.6
not_cached = 0.2
failed = 0
```

`prefer_cached=true` 时，cache_ready 应有更强影响，避免现场等待下载。

### 7.6 novelty

避免：

```text
连续同一歌手
连续过于相同标签
刚刚播放过
用户刚刚跳过
```

---

## 8. 过渡策略选择

风格切歌选中下一首后，仍然调用现有 transition plan：

```text
POST /api/dj/transitions/plan
```

但 cut plan 可以给出 hint：

```text
recommended_transition_hint
```

参考：

| 风格变化 | 推荐 hint |
|---|---|
| hiphop → popping | `percussion_bridge` / `echo_out_hard_drop` |
| popping → locking | `eq_swap_4bar` / `harmonic_blend` |
| locking → house | `auto_bpm_ramp` / `percussion_bridge` |
| house → waacking | `harmonic_blend` |
| hiphop → krump | `impact_slam_cut` / `breakdown_reset` |
| krump → house | `neutral_fx_bridge` / `echo_out_hard_drop` |

最终真实切法由：

```text
mixer_rules.py
transition_strategy.py
```

决定。不要在风格切歌模块里重复实现 DSP 时间线。

---

## 9. RK 预同步策略

### 9.1 新增同步优先级

在现有同步优先级中加入风格备选：

```text
P0 当前歌
P1 默认下一首
P2 主队列后续
P3 目标能量备选池
P4 目标风格备选池
```

P4 规则：

```text
每个大舞种至少同步 1 首 original
当前主要场景相关舞种同步 2-3 首 original
stems 后台补，不阻塞
```

例如当前主要场景是 hiphop：

```text
popping: 2 首
breaking: 1 首
locking: 1 首
house: 1 首
waacking: 1 首
krump: 1 首
```

### 9.2 前端同步要求

在 `mobile/lib/src/dj_control_page.dart` 中扩展：

```text
_warmActiveQueueAndReservePool()
```

同步内容：

```text
active_queue P0/P1/P2
energy reserve pool P3
style reserve pool P4
```

UI 显示：

```text
Popping｜可切 2
House｜可切 1
Krump｜同步中
```

点击目标舞种时，优先返回已缓存候选。

---

## 10. Flutter UI 要求

### 10.1 新增风格切歌面板

与目标能量切歌并列，不能混在一起。

```text
目标能量：
[50-60] [60-70] [70-80] [80-90]

目标风格：
[Breaking] [Hip-hop] [Popping] [Locking] [House] [Waacking] [Krump]
```

### 10.2 点击目标风格

调用：

```text
POST /api/dj/cut/plan
intent=target_dance_style
mode=preview
```

展示：

```text
推荐下一首：
Song X
目标风格：Popping
匹配度：92%
能量：78
缓存：已完成
推荐切法：percussion_bridge
原因：...
```

按钮：

```text
[确认切歌] [换一首] [取消]
```

### 10.3 确认切歌

确认后：

```text
1. 如果目标歌不在 active queue 中，插入当前播放位置下一首
2. 如果来自 style_reserve_pool，从 style_reserve_pool 移除
3. ensureRkCache(selectedSong)
4. edgeClient.prefetch(selectedSong)
5. djPlanTransition(current, selected)
6. edgeClient.xfade()
7. 后台为该 style 补充新的 reserve candidate
```

### 10.4 换一首

请求中加入：

```json
{
  "exclude_song_ids": ["刚刚推荐的 song_id"]
}
```

后端返回同一目标舞种的下一个候选。

---

## 11. 后端修改文件

| 文件 | 修改 |
|---|---|
| `app/modules/dj_control/schemas.py` | 新增 `target_dance_style` request/response 字段 |
| `app/modules/dj_control/router.py` | `/api/dj/cut/plan` 支持 `intent=target_dance_style` |
| `app/modules/dj_control/cut_strategy.py` | 新增目标舞种候选选择逻辑 |
| `app/modules/dj_control/dance_style.py` | 复用舞种分数读取函数，必要时提供 `get_style_score(song, style)` |
| `app/modules/dj_control/style_taxonomy.py` | 确认 7 个大舞种合法值和显示名 |
| `app/modules/dj_control/transition_strategy.py` | 不重写，只确认 hint 映射 |
| `mobile/lib/src/api_client.dart` | 新增 `djPlanTargetStyleCut()` 或扩展 `djCutPlan()` |
| `mobile/lib/src/dj_control_page.dart` | 新增风格切歌面板、预览、确认、换一首、队列插入 |
| `mobile/lib/src/sync_worker_client.dart` | 如需显示 cache 状态，复用或扩展查询 |
| `mobile/lib/src/edge_agent_client.dart` | 确认 prefetch / xfade 调用兼容 |

---

## 12. 测试要求

### 12.1 后端单元测试：目标风格候选选择

新增：

```text
app/tests/test_target_style_cut_strategy.py
```

测试：

1. 当前歌 hiphop，目标 popping。
2. 候选 A：popping=0.92，ready。
3. 候选 B：popping=0.95，但 not_cached 且 BPM 风险高。
4. 候选 C：locking=0.90，popping=0.30。
5. 期望选择 A。

测试 fallback：

1. 没有 popping >= 0.75。
2. 有 electro/funk 标签且 popping=0.58。
3. 返回 fallback=true，selected_song 为可用近似候选。

测试 played/blocked：

1. 候选在 played_pool 或 blocked_pool 中。
2. 不得被选中。

### 12.2 后端集成测试：cut plan target_dance_style

新增：

```text
app/tests/test_dj_cut_plan_target_style.py
```

请求：

```json
{
  "intent": "target_dance_style",
  "current_song_id": "...",
  "target_style": "popping",
  "active_queue_song_ids": ["..."],
  "style_reserve_pool_song_ids": ["..."],
  "played_song_ids": [],
  "blocked_song_ids": [],
  "prefer_cached": true,
  "mode": "preview"
}
```

验证返回：

```text
intent == target_dance_style
target_style == popping
selected_song.style_score 存在
score_breakdown.target_style_match 存在
recommended_transition_hint 存在
queue_action.type == insert_next
reason 非空
```

### 12.3 Live Pool Prepare 测试

扩展：

```text
app/tests/test_live_pool_prepare.py
```

新增验证：

```text
返回 style_reserve_pool
返回 style_pool_status
7 个大舞种 key 存在
played / blocked 不进入 style_reserve_pool
active_queue 中已有歌曲不重复进入 style_reserve_pool
```

### 12.4 Flutter 测试

运行：

```bash
cd mobile
flutter analyze --no-fatal-infos --no-fatal-warnings
flutter build apk --debug
```

要求：

```text
风格切歌面板可显示
目标风格按钮可点击
无候选时有提示
返回推荐后可确认/换一首/取消
确认后 active queue 被插入
```

### 12.5 RK 同步和真机验收

准备：

```text
主队列 4 首
style reserve pool 至少 7 首，每个大舞种 1 首
```

验收：

1. 开始播放前同步 P0/P1。
2. 后台同步 P2/P4。
3. 前端显示：
   ```text
   Popping 可切 1
   House 可切 1
   ```
4. 点击 Popping。
5. 返回已缓存候选。
6. 确认切歌。
7. RK 不报 409。
8. audio-engine 正常播放。
9. selected_song 插入当前下一首。

---

## 13. 完成定义

- [ ] 风格切歌与能量切歌是两个独立 UI 模块。
- [ ] 风格切歌只支持 7 个大舞种分类。
- [ ] `/api/dj/cut/plan` 支持 `intent=target_dance_style`。
- [ ] 后端可从 active queue + style reserve pool + 曲库兜底中选目标舞种歌曲。
- [ ] 候选选择使用 `dance_style_scores[target_style]` / `style_evidence_v1[target_style]`。
- [ ] 候选评分包含 style、transition safety、energy continuity、BPM、cache、novelty。
- [ ] 选中歌曲可插入当前下一首。
- [ ] 风格备选池随 live pool prepare 返回。
- [ ] 风格备选池 representative songs 会提前同步到 RK。
- [ ] 前端展示目标风格按钮、可切数量、推荐原因、确认/换一首/取消。
- [ ] 后端测试、Flutter build、RK 真机验收通过。
- [ ] 不提交 `.env`、token、JWT、设备密码。

---

## 14. 推荐提交顺序

### Phase 0：确认当前能量切歌基线

```text
chore(style-cut): confirm live cut baseline
```

- 不修改能量切歌。
- 确认现有 `/api/dj/cut/plan intent=target_energy_bucket` 正常。

### Phase 1：后端 target_dance_style intent

```text
feat(style-cut): add target dance style cut planning
```

- 扩展 schema/router。
- 新增 cut_strategy target style 选择。
- 单元测试。

### Phase 2：style reserve pool

```text
feat(style-cut): prepare style reserve pool
```

- live pool prepare 返回 style_reserve_pool。
- 返回 style_pool_status。
- 集成测试。

### Phase 3：Flutter 风格切歌 UI

```text
feat(mobile): add target style cut controls
```

- 新增风格按钮。
- preview / confirm / swap / cancel。
- active queue 插入。

### Phase 4：RK 预同步 P4

```text
feat(mobile): warm style reserve pool on rk
```

- P4 同步风格备选。
- UI 展示缓存状态。
- 真机验证。

### Phase 5：端到端验收

```text
test(style-cut): verify target style cut on device
```

- 点击 Popping / House / Krump 等目标风格。
- 验证插入、预取、xfade。

---

## 15. 交接给 AI Agent 的执行提示

```text
请新增“实时舞种风格切歌”模块。
它必须与“目标能量切歌”独立，二者不要合并。
本轮只支持 7 个大舞种：breaking、hiphop、popping、locking、house、krump、waacking。

复用当前能量切歌的实现模式：
- live pool prepare 返回 reserve pool 和同步优先级；
- cut plan 使用 intent 分流；
- preview 后用户确认；
- 确认后插入当前下一首；
- 优先选择已缓存候选；
- RK 预同步 reserve pool representative songs。

不要修改外部 metadata API 主链路。
不要重写 /api/dj/styles/pick。
不要改 RK audio-engine DSP。
不要让 Flutter 自己计算舞种分数。
不要在点击目标风格时临时调用外部 API。
不要提交 .env、token、JWT、设备密码。
```
