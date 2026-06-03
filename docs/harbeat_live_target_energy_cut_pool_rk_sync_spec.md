# HarBeat 实时目标能量切歌与备选池 RK 预同步落地执行规格

版本：V1.0  
日期：2026-06-03  
读者：后端工程师、Flutter 工程师、RK3588 工程师、AI Agent  
状态：可直接执行  
范围：只修改 **DJ Control 实时播放中的目标能量切歌、歌曲池、备选池、RK 预同步与前端可用体验**。  
不修改：外部 metadata API、舞种选歌评分、普通 `/api/dj/styles/pick` 主逻辑、完整 DJ Set 编排、RK audio-engine DSP 算法。

---

## 0. 文档用途

本文件用于指导 AI Agent 对当前 HarBeat 项目进行一次可落地改造：

用户在 DJ Control 实时播放时，不再只能点击简单的“升能量 / 降能量”，而是可以选择下一首目标能量区间，例如：

```text
当前歌曲能量：62
用户选择下一首目标能量：80-90
系统从主播放队列 + 备选池中选择一首 80-90 分歌曲
该歌曲必须已经在 RK3588 缓存，或可以快速预取
系统把该歌曲插入当前播放位置的下一首
用户确认后立即切歌
```

本次修改必须实现：

1. 每首歌有统一的 `dance_energy_score`，范围 `0-100`。
2. 能量切歌调用新版街舞能量分析方式，而不是只读旧 `LibrarySong.energy`。
3. 用户可以选择具体目标能量段，每 10 分一段。
4. 歌曲池从固定歌单升级为：
   ```text
   Active Queue 主播放队列
   Reserve Pool 动态备选池
   Played Pool 已播放池
   Blocked Pool 禁用池
   ```
5. 备选池歌曲与用户主队列歌曲要在开始实时播放时同步到 RK3588，避免用户点击目标能量后等待下载。
6. 前端必须展示当前能量、可选目标能量段、目标区间候选数量、缓存状态、推荐理由、确认切歌按钮。
7. 必须补充后端、Flutter、RK 同步和真机验收测试，保证用户能直接使用。

---

## 1. 当前项目依据

当前项目已有以下能力：

```text
Flutter DJ Control
→ 后端 DJ Control 接口
→ manifest 获取原曲和 stems
→ RK sync-worker 下载 original/stems
→ RK edge-agent prefetch/play/xfade
→ audio-engine 实时播放
```

相关文件：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
mobile/lib/src/edge_agent_client.dart
mobile/lib/src/sync_worker_client.dart

app/modules/dj_control/router.py
app/modules/dj_control/energy_hiphop.py
app/modules/dj_control/sequencer.py
app/modules/dj_control/cut_strategy.py
app/modules/dj_control/mixer_rules.py
app/modules/dj_control/transition_strategy.py

app/modules/library/models.py
app/modules/manifest/__init__.py
app/modules/manifest/router.py

cypher-integration/rk3588-edge/sync-worker/main.py
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/audio-engine/engine.py
```

项目当前真实边界：

- `POST /api/dj/sequence`：对一批歌曲按能量曲线排序。
- `POST /api/dj/cut/plan`：现场快切 / 升能 / 降能。
- `energy_hiphop.py`：已有街舞能量拆分逻辑，如 BPM、kick、snare、groove、low-mid、vocal urgency 等。
- `sync-worker`：负责从 manifest 下载 original 和 stems 到 RK 本地 cache。
- `dj_control_page.dart`：开始播放前会同步当前歌，播放中会预取下一首，并触发 xfade。

本轮改造重点是：**把实时能量切歌升级为用户可控的目标能量区间选择，并确保备选歌提前同步到 RK。**

---

## 2. 目标用户体验

### 2.1 用户进入实时播放

用户流程保持原有 DJ Control 主路径：

```text
进入 DJ Control
→ 通过舞种 + 时长 / 歌单 / vibe search 选歌
→ 加入 DJ 池
→ 可选能量排序或手动排序
→ 点击开始实时播放
```

### 2.2 实时播放界面显示当前能量

播放中显示：

```text
当前播放：Song A
当前能量：62
当前能量段：60-70
```

能量值来自后端统一的 `dance_energy_score`，不是 Flutter 自己计算。

### 2.3 用户选择下一首目标能量段

每 10 分为一个能量段：

```text
0-10
10-20
20-30
30-40
40-50
50-60
60-70
70-80
80-90
90-100
```

UI 不需要一次显示全部 10 个段。推荐显示当前能量段上下 2 档。

例如当前能量为 62，显示：

```text
目标能量：
[40-50] [50-60] [60-70] [70-80] [80-90]
```

用户点击 `80-90` 后，不要立即切歌，先进入预览：

```text
正在寻找 80-90 能量区间的下一首...
```

返回后展示：

```text
推荐下一首：Song X
能量：84
来源：备选池
状态：已缓存，可立即切
原因：
- 目标能量 80-90，该歌曲能量 84
- 舞种匹配当前 Popping
- BPM 差较小
- 有 clean intro / transition window
- 人声和低频冲突风险较低

[确认切歌] [换一首] [取消]
```

### 2.4 没有精确命中时的体验

如果没有 80-90 的歌，系统可放宽：

```text
80-90
→ 75-90
→ 70-90
→ 70-100
→ 只要比当前能量高
```

前端显示：

```text
未找到 80-90 精确能量歌曲，已放宽到 70-90。
推荐：Song Y｜能量 76｜已缓存
```

用户仍可确认、换一首或取消。

---

## 3. 核心设计：歌曲池

本次将实时播放中的歌曲集合拆成四类。

### 3.1 Active Queue 主播放队列

用户已经确认要播放的主队列：

```text
A 当前播放
B 下一首
C
D
E
```

来源：

- 舞种 + 时长生成候选。
- 用户手动添加。
- 导入歌单。
- vibe search。
- 自动 set 生成。

### 3.2 Reserve Pool 动态备选池

系统提前准备的备选歌曲，不在默认播放顺序里，但用于目标能量切歌插队。

来源：

- 用户曲库中当前舞种分数较高的歌。
- 当前风格相似的歌。
- 当前 BPM 范围附近的歌。
- 不同能量段覆盖的歌。
- 未播放、未禁用、分析可用的歌。

Reserve Pool 必须按能量段组织：

```json
{
  "40-50": ["R1", "R2"],
  "50-60": ["R3", "R4"],
  "60-70": ["R5", "R6"],
  "70-80": ["R7", "R8"],
  "80-90": ["R9", "R10"]
}
```

建议每个可用能量段保留 1-3 首备选歌。

### 3.3 Played Pool 已播放池

已经播过的歌曲：

```text
played_song_ids
```

默认不得再次被选为目标能量候选，除非用户显式允许重复。

### 3.4 Blocked Pool 禁用池

不能被自动选中的歌曲：

```text
用户跳过的歌
同步失败的歌
最近刚播放过的歌
用户标记不适合当前舞种的歌
stems 缺失且当前策略必须使用 stems 的歌
文件不存在或 manifest 无 original 的歌
```

---

## 4. 统一能量分析

### 4.1 新增统一能量入口

在 `app/modules/dj_control/energy_hiphop.py` 中新增统一入口：

```python
def get_dance_energy_profile(song: LibrarySong) -> dict:
    ...
```

返回结构：

```json
{
  "dance_energy_score": 62,
  "bucket": "60-70",
  "components": {
    "base_energy": 0.61,
    "bpm_factor": 0.58,
    "kick_punch": 0.70,
    "snare_crack": 0.65,
    "groove": 0.72,
    "low_mid": 0.60,
    "vocal_urgency": 0.48
  },
  "curve": {
    "intro": 56,
    "mid": 64,
    "outro": 60
  },
  "source": "compute_dance_energy_v1"
}
```

要求：

1. 内部必须复用当前 `compute_dance_energy()` 或其新版逻辑。
2. 输出必须统一到 `0-100`。
3. 如果新特征缺失，允许 fallback 到 `LibrarySong.energy`，但必须标记：
   ```json
   "source": "fallback_library_energy"
   ```
4. 不允许 `cut_strategy.py` 直接只读 `song.energy` 作为最终判断。

### 4.2 能量分段函数

新增：

```python
def energy_bucket(score: float) -> str:
    ...
```

规则：

| 分数 | bucket |
|---:|---|
| 0-9.999 | `0-10` |
| 10-19.999 | `10-20` |
| ... | ... |
| 90-100 | `90-100` |

边界：

```text
score < 0 → clamp 到 0
score > 100 → clamp 到 100
100 属于 90-100
```

---

## 5. 后端接口设计

### 5.1 新增：创建实时播放池

新增接口：

```http
POST /api/dj/live/pool/prepare
```

作用：

```text
根据用户当前 DJ 池、当前舞种、目标能量覆盖要求，生成 active_queue、reserve_pool、sync_priority。
```

请求：

```json
{
  "active_queue_song_ids": ["A", "B", "C", "D"],
  "style": "popping",
  "target_reserve_per_bucket": 2,
  "include_buckets": ["30-40", "40-50", "50-60", "60-70", "70-80", "80-90"],
  "exclude_song_ids": []
}
```

返回：

```json
{
  "active_queue": ["A", "B", "C", "D"],
  "reserve_pool": {
    "30-40": ["R1", "R2"],
    "40-50": ["R3", "R4"],
    "50-60": ["R5", "R6"],
    "60-70": ["R7", "R8"],
    "70-80": ["R9", "R10"],
    "80-90": ["R11", "R12"]
  },
  "energy_profiles": {
    "A": {"score": 62, "bucket": "60-70"},
    "R11": {"score": 84, "bucket": "80-90"}
  },
  "sync_priority": {
    "p0": ["A"],
    "p1": ["B"],
    "p2": ["C", "D"],
    "p3": ["R1", "R3", "R5", "R7", "R9", "R11"]
  }
}
```

说明：

- P0：当前歌。
- P1：默认下一首。
- P2：主队列后续 2-4 首。
- P3：每个能量段至少 1 首备选。
- 后端只返回建议，实际同步由 Flutter 调 RK sync-worker。

### 5.2 扩展：目标能量切歌计划

扩展当前：

```http
POST /api/dj/cut/plan
```

新增支持 `intent = "target_energy_bucket"`。

请求：

```json
{
  "intent": "target_energy_bucket",
  "current_song_id": "A",
  "active_queue_song_ids": ["B", "C", "D"],
  "reserve_pool_song_ids": ["R1", "R2", "R3", "R4"],
  "played_song_ids": [],
  "blocked_song_ids": [],
  "target_energy_bucket": {
    "min": 80,
    "max": 90
  },
  "current_style": "popping",
  "prefer_cached": true,
  "mode": "preview"
}
```

返回：

```json
{
  "intent": "target_energy_bucket",
  "current_song": {
    "song_id": "A",
    "energy_score": 62,
    "bucket": "60-70"
  },
  "target_bucket": {
    "min": 80,
    "max": 90,
    "label": "80-90"
  },
  "selected_song": {
    "song_id": "R11",
    "title": "Song X",
    "artist": "Artist X",
    "energy_score": 84,
    "bucket": "80-90",
    "source": "reserve_pool",
    "cache_status": "ready"
  },
  "queue_action": {
    "type": "insert_next",
    "after_song_id": "A",
    "remove_from_reserve_pool": true
  },
  "candidate_score": 0.87,
  "score_breakdown": {
    "energy_match": 0.96,
    "style_match": 0.82,
    "bpm_compat": 0.78,
    "transition_window": 0.80,
    "risk_safety": 0.74,
    "cache_ready": 1.0
  },
  "recommended_transition_hint": "drop_swap",
  "reason": [
    "目标区间为 80-90，该歌曲能量 84，命中目标",
    "舞种匹配当前 popping",
    "BPM 差较小",
    "存在可用 transition window",
    "已在 RK 缓存，可立即切"
  ],
  "fallback": false
}
```

没有精确命中时：

```json
{
  "fallback": true,
  "fallback_reason": "未找到 80-90 区间歌曲，已放宽到 70-90",
  "selected_song": {
    "energy_score": 76,
    "bucket": "70-80"
  }
}
```

### 5.3 可选：确认插入队列

如果当前项目的播放队列只维护在 Flutter 内存，可以不新增后端确认接口，由 Flutter 本地插入。

如果后端已有 live session / queue 状态，则新增：

```http
POST /api/dj/live/queue/insert
```

请求：

```json
{
  "current_song_id": "A",
  "insert_song_id": "R11",
  "position": "next",
  "remove_from_reserve_pool": true
}
```

本轮最低要求：**Flutter 本地队列插入必须可用。后端持久化 live queue 可作为可选增强。**

---

## 6. 候选选择规则

### 6.1 查找顺序

用户选择目标能量段后，后端按以下顺序查找：

```text
1. active_queue 剩余歌曲中，已缓存且命中目标能量段
2. reserve_pool 中，已缓存且命中目标能量段
3. active_queue 中，未缓存但命中目标能量段
4. reserve_pool 中，未缓存但命中目标能量段
5. 从曲库扩展 reserve_pool，找同风格/同舞种且命中目标段歌曲
6. 放宽目标区间
7. 如果仍无可用，返回 fallback，让前端保持原下一首或仅改变 transition strategy
```

### 6.2 能量区间放宽策略

目标 80-90：

```text
80-90
→ 75-90
→ 70-90
→ 70-100
→ score > current_score
```

目标 30-40：

```text
30-40
→ 30-45
→ 25-50
→ 20-55
→ score < current_score
```

目标 50-60：

```text
50-60
→ 45-65
→ 40-70
→ 最接近目标中心点
```

### 6.3 候选总分

候选评分：

```text
candidate_score =
0.45 × energy_target_match
+ 0.20 × style_match
+ 0.15 × bpm_compat
+ 0.10 × transition_window_score
+ 0.05 × risk_safety
+ 0.05 × cache_ready
```

说明：

| 分项 | 说明 |
|---|---|
| `energy_target_match` | 越接近目标区间中心越高 |
| `style_match` | 当前舞种 / 风格匹配，读取 `dance_style_scores[current_style]` |
| `bpm_compat` | BPM 差越小越高，倍速关系可适当加分 |
| `transition_window_score` | 有 clean intro、cue、transition window 加分 |
| `risk_safety` | 人声 / 低频风险低加分 |
| `cache_ready` | RK 已缓存 original 加满分，正在同步次之，未同步低分 |

注意：

- `prefer_cached=true` 时，已缓存候选优先级必须显著提高。
- 不得为了完美能量分选择一个无法及时同步的歌。
- 如果所有目标候选都未缓存，应返回 `cache_status=synchronizing` 或选择相邻区间已缓存候选。

---

## 7. RK 预同步策略

### 7.1 同步目标

开始实时播放前，不只同步 Active Queue，还要同步 Reserve Pool 的代表歌。

分级：

| 优先级 | 内容 | 阻塞播放 |
|---|---|---|
| P0 | 当前歌 original | 必须 |
| P1 | 默认下一首 original | 必须 |
| P2 | 主队列后续 2-4 首 original | 不阻塞 |
| P3 | 每个能量段 1-2 首备选 original | 不阻塞 |
| Stems | 当前歌/下一首/高优先备选 stems | 不阻塞，后台补 |

最低要求：

```text
P0 original ready
P1 original ready
```

满足后即可开始播放。

### 7.2 Flutter 同步行为

在 `mobile/lib/src/dj_control_page.dart` 中修改：

```text
_startLiveMix()
  -> prepareLivePool()
  -> sync P0 current song
  -> sync P1 next song
  -> P0/P1 original ready 后 play
  -> background warm P2 active queue tail
  -> background warm P3 reserve pool by bucket
```

扩展现有：

```text
_warmAllRemainingTracks()
```

为：

```text
_warmActiveQueueAndReservePool()
```

要求：

1. 主队列优先。
2. Reserve Pool 每个能量段至少同步 1 首。
3. 同步状态写入前端内存：
   ```text
   ready / syncing / missing / failed
   ```
4. UI 显示：
   ```text
   80-90：1 首可立即切，1 首同步中
   ```

### 7.3 Sync-worker 要求

尽量复用现有 sync-worker：

```text
syncWorker.startSync(manifest)
syncWorker.syncAndWait()
syncWorker.cacheExists(song_id)
```

本轮不强制修改 sync-worker 的核心下载逻辑，但必须保证：

1. 可以连续提交多个 song manifest 同步任务。
2. `cacheExists(song_id)` 能区分：
   ```text
   original ready
   stems ready
   missing
   ```
   如果当前接口不能区分，至少前端能通过已有状态判断 original 是否 ready。
3. Reserve Pool 同步失败不会影响 P0/P1 播放。

---

## 8. 前端 UI 改造

### 8.1 实时播放区新增内容

显示：

```text
当前能量：62｜60-70
目标能量：
[40-50] [50-60] [60-70] [70-80] [80-90]
```

每个按钮可显示小状态：

```text
80-90｜可切 1
70-80｜可切 2
40-50｜同步中
```

### 8.2 点击目标能量段

点击后：

```text
POST /api/dj/cut/plan
intent=target_energy_bucket
mode=preview
```

展示返回推荐：

```text
推荐下一首：Song X
能量：84｜80-90
来源：备选池
缓存：已完成
原因：命中目标能量，BPM 接近，有可用切入窗口

[确认切歌] [换一首] [取消]
```

### 8.3 确认切歌

用户点击确认后：

1. 如果歌曲未在 active queue 中，将其插入当前播放位置之后。
2. 如果歌曲来自 reserve pool，从 reserve pool 移除。
3. 触发：
   ```text
   ensureRkCache(selectedSong)
   edgeClient.prefetch(selectedSong)
   djPlanTransition(current, selected)
   edgeClient.prewarmBeatmatch()
   edgeClient.beatReinforce()
   edgeClient.xfade()
   ```
4. 后台为该目标能量段补一个新的 reserve song。

### 8.4 换一首

用户点击“换一首”：

```text
POST /api/dj/cut/plan
```

请求中加入：

```json
{
  "exclude_song_ids": ["刚刚推荐的 song_id"]
}
```

后端返回同一目标区间的下一个候选。

---

## 9. 后端修改文件

### 9.1 必改文件

| 文件 | 修改 |
|---|---|
| `app/modules/dj_control/energy_hiphop.py` | 新增 `get_dance_energy_profile()`、`energy_bucket()` |
| `app/modules/dj_control/cut_strategy.py` | 新增目标能量段候选选择逻辑 |
| `app/modules/dj_control/router.py` | 扩展 `/api/dj/cut/plan`，新增 `/api/dj/live/pool/prepare` |
| `app/modules/dj_control/schemas.py` | 新增 live pool / target bucket request response schema |
| `app/modules/dj_control/sequencer.py` | 如已有能量 bucket 逻辑，复用 bucket 常量，避免重复定义 |
| `app/modules/manifest/__init__.py` | 确认 manifest 可供 Reserve Pool 歌曲同步 |
| `mobile/lib/src/api_client.dart` | 新增后端接口封装 |
| `mobile/lib/src/dj_control_page.dart` | UI、队列插入、Reserve Pool 同步、确认切歌 |
| `mobile/lib/src/sync_worker_client.dart` | 如需要，增强 cache 状态读取 |
| `mobile/lib/src/edge_agent_client.dart` | 确认 prefetch/xfade 调用兼容 |

---

## 10. 测试要求

本次必须补充测试，不能只靠手工点 UI。

### 10.1 后端单元测试：能量分段

新增：

```text
app/tests/test_energy_bucket.py
```

测试：

1. `0` → `0-10`
2. `9.9` → `0-10`
3. `10` → `10-20`
4. `62` → `60-70`
5. `100` → `90-100`
6. `<0` clamp 到 `0`
7. `>100` clamp 到 `100`

### 10.2 后端单元测试：目标能量候选选择

新增：

```text
app/tests/test_target_energy_cut_strategy.py
```

准备歌曲：

```text
current = 62
A = 55
B = 76
C = 84
D = 96
E = 42
```

测试 1：目标 `80-90`

期望：

```text
选择 C=84
不选择 D=96
```

测试 2：目标 `40-50`

期望：

```text
选择 E=42
```

测试 3：目标 `80-90` 但 C 未缓存、B 已缓存

如果 `prefer_cached=true`：

```text
可以选择 B=76，并返回 fallback_reason=目标区间未缓存，放宽到 70-90
```

测试 4：必须调用 `get_dance_energy_profile()`

用 monkeypatch 检测：

```text
cut_strategy 不能只读 song.energy
```

### 10.3 后端集成测试：Live Pool

新增：

```text
app/tests/test_live_pool_prepare.py
```

测试：

1. 输入 active queue 4 首。
2. 曲库中准备多个能量段歌曲。
3. 调用 `POST /api/dj/live/pool/prepare`。
4. 验证返回：
   ```text
   active_queue
   reserve_pool
   energy_profiles
   sync_priority.p0/p1/p2/p3
   ```
5. `reserve_pool` 每个目标段最多 N 首。
6. Played / blocked 歌不会进入 reserve pool。

### 10.4 后端集成测试：cut plan

新增：

```text
app/tests/test_dj_cut_plan_target_energy_bucket.py
```

测试：

```http
POST /api/dj/cut/plan
```

请求：

```json
{
  "intent": "target_energy_bucket",
  "current_song_id": "...",
  "active_queue_song_ids": ["..."],
  "reserve_pool_song_ids": ["..."],
  "target_energy_bucket": {"min": 80, "max": 90},
  "current_style": "popping",
  "prefer_cached": true,
  "mode": "preview"
}
```

验证返回：

```text
selected_song
current_song.energy_score
target_bucket.label
candidate_score
score_breakdown
reason
queue_action.type == insert_next
```

### 10.5 Flutter 静态测试

运行：

```bash
cd mobile
flutter analyze --no-fatal-infos --no-fatal-warnings
flutter build apk --debug
```

必须保证：

1. DJ Control 页面能编译。
2. 新增 API response model 不报错。
3. 目标能量按钮不会导致空指针。
4. 推荐结果为空时 UI 有提示。

### 10.6 RK 同步测试

准备：

```text
active queue 3 首
reserve pool 6 首
每个能量段至少 1 首
```

真机验证：

1. 点击开始实时播放。
2. P0/P1 original ready 后开始播放。
3. 后台继续同步 P2/P3。
4. 在 RK 上检查：
   ```text
   /home/cat/cypher/cache/{song_id}/original.*
   ```
5. 前端显示：
   ```text
   80-90 可切 1 首
   70-80 可切 1 首
   ```
6. 点击 `80-90`，推荐歌曲应为已缓存或正在同步的候选。

### 10.7 端到端真机验收

场景 1：目标能量命中

```text
当前歌能量 62
选择 80-90
系统推荐 84 分歌曲
状态 ready
确认切歌
RK 成功 xfade
```

验收：

```text
App 无崩溃
后端日志有 target_energy_bucket
RK 没有 409
audio-engine 正常播放
selected_song 插入下一首
```

场景 2：目标能量 fallback

```text
当前歌能量 62
选择 90-100
没有 90-100
系统 fallback 到 80-90 或 70-90
前端显示 fallback_reason
```

场景 3：备选池补位

```text
目标歌来自 reserve_pool
确认切歌后：
- 从 reserve_pool 移除
- 插入 active_queue 当前下一首
- reserve_pool 同 bucket 后台补新歌
```

场景 4：缓存不完整

```text
目标区间理论最佳歌未缓存
系统优先选择已缓存的次优候选
或提示正在同步
不得造成播放中断
```

---

## 11. 完成定义

本轮完成必须满足：

- [ ] 每首歌可得到 `dance_energy_score 0-100` 和 `bucket`。
- [ ] 实时切歌使用 `get_dance_energy_profile()`，不只读旧 `song.energy`。
- [ ] 前端显示当前能量和目标能量段。
- [ ] 用户可以点击具体目标能量段，如 `80-90`。
- [ ] 后端可从 Active Queue + Reserve Pool 中选择目标能量候选。
- [ ] 如果目标段无歌，后端会逐级放宽并返回 fallback reason。
- [ ] 选中的 Reserve Pool 歌曲可插入当前播放队列下一首。
- [ ] 开始实时播放时，Active Queue 和 Reserve Pool 代表歌会同步到 RK。
- [ ] 用户点击目标能量时，优先选择 RK 已缓存候选。
- [ ] 前端显示候选来源、能量分、缓存状态、推荐原因。
- [ ] 用户确认后可以完成 prefetch、transition plan、xfade。
- [ ] 后端单元测试和集成测试通过。
- [ ] Flutter analyze 和 build debug 通过。
- [ ] RK 真机至少完成一次 4 首歌 + 备选池切歌验收。
- [ ] 不提交 token、JWT、设备密码、`.env`。

---

## 12. 推荐提交顺序

### Phase 0：测试基线

```text
chore(energy-cut): establish baseline for live energy cut
```

- 跑现有后端测试。
- 跑 Flutter analyze。
- 确认当前 `/api/dj/cut/plan` 行为。

### Phase 1：统一能量画像

```text
feat(energy-cut): add unified dance energy profile and buckets
```

- 新增 `get_dance_energy_profile()`
- 新增 `energy_bucket()`
- 补 `test_energy_bucket.py`

### Phase 2：目标能量候选选择

```text
feat(energy-cut): select next track by target energy bucket
```

- 扩展 `cut_strategy.py`
- 扩展 `/api/dj/cut/plan`
- 补 `test_target_energy_cut_strategy.py`
- 补 `test_dj_cut_plan_target_energy_bucket.py`

### Phase 3：歌曲池与备选池

```text
feat(energy-cut): prepare active queue and reserve pool
```

- 新增 `/api/dj/live/pool/prepare`
- 生成 reserve pool by bucket
- 返回 sync priority
- 补 `test_live_pool_prepare.py`

### Phase 4：Flutter UI 与队列插入

```text
feat(mobile): add target energy bucket controls
```

- 展示当前能量
- 展示目标区间按钮
- 显示推荐结果
- 支持确认切歌 / 换一首 / 取消
- 插入 active queue

### Phase 5：Reserve Pool RK 预同步

```text
feat(mobile): warm active queue and reserve pool on rk
```

- 扩展 `_warmAllRemainingTracks()`
- 同步 P0/P1/P2/P3
- 展示每个 bucket 的缓存状态
- 真机测试 RK cache

### Phase 6：端到端验收

```text
test(energy-cut): add live target energy acceptance suite
```

- 4 首主队列 + 6 首备选池
- 测试目标命中、fallback、缓存未完成、reserve 插入
- 记录结果

---

## 13. 交接给 AI Agent 的执行提示

```text
请只修改实时目标能量切歌与备选池 RK 预同步相关链路。
不要改外部 metadata API、舞种选歌评分主逻辑、RK audio DSP 或完整 DJ set 编排。

目标：
1. 每首歌统一得到 0-100 dance_energy_score；
2. 实时播放中用户可以选择下一首目标能量段，每 10 分一段；
3. 后端从 Active Queue + Reserve Pool 中选目标能量候选；
4. Reserve Pool 歌曲要与主队列一起提前同步到 RK；
5. 用户点击目标能量时，优先返回已缓存候选；
6. 用户确认后，将候选插入下一首并完成 prefetch / transition plan / xfade；
7. 必须补充后端、Flutter、RK 真机测试。

严禁：
- 只读旧 song.energy 作为最终实时能量；
- 点击目标能量后才临时下载所有候选歌；
- 让 Flutter 自己计算能量分；
- 为了选择理论最优歌曲造成现场等待或 RK409；
- 提交 .env、token、JWT、设备密码。
```
