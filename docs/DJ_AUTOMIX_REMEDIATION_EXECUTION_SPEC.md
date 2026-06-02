# HarBeat DJ Automix 缺口修复与验收执行规格

版本：V1.0
日期：2026-06-02
读者：后端、Flutter、Jetson、RK3588 工程师，以及接手开发的 AI Agent
状态：可直接执行

---

## 0. 文档用途

这份文档只处理一件事：把当前 HarBeat Automix 已知的不足逐项修掉，并建立一条可以重复验收的完整链路。

它不是产品愿望清单，也不要求推倒重做。当前系统已经有导歌、音频分析、Demucs 分轨、DJ Set 编排、转场计划、RK 双 deck 播放和降级逻辑。接下来的工作重点是收口：让已经计算出来的分析结果真正进入 RK 的声音执行。

本规格基于远端最新集成分支：

```text
origin/codex/integrate-analysis-session
HEAD: 7e7b57f docs: explain song style analysis pipeline
```

执行前创建新分支：

```bash
git fetch origin --prune
git switch -c codex/dj-automix-remediation origin/codex/integrate-analysis-session
```

不要直接在用户当前工作区覆盖文件。用户工作区存在未提交改动。新 clone 或独立 worktree 更稳妥。

---

## 1. 当前系统的真实状态

### 1.1 已经存在的主链路

```text
授权音源导入
→ LibrarySong 入库
→ BPM / beatgrid / key / LUFS / phrase / energy 分析
→ Demucs 四路 stems 分离
→ stem 活跃窗口和 clean intro / outro 分析
→ DJ Set Planner 计算 A → B 关系矩阵
→ Beam Search 编排播放顺序
→ 为每次换歌生成 canonical transition plan
→ Flutter App 预取下一首并调用 RK /xfade
→ RK audio-engine 播放、混音和降级
```

### 1.2 已经做得比较扎实的部分

| 模块 | 当前能力 |
|---|---|
| 单曲分析 | BPM、BPM curve、tempo stability、beat points、downbeats、拍号、key、Camelot、key confidence、LUFS、peak、clipping risk、energy curve、groove、danceability |
| 结构分析 | cue points、8 小节 phrase map、intro、verse、buildup、drop、breakdown、outro、DJ hot cues |
| Stems | Demucs `vocals`、`drums`、`bass`、`other`，activity windows、vocal events、bass risk windows、质量 proxy |
| Set Planner | 全曲库 directed pair matrix、角色分类、五种 Set 模板、beam search、quality gate |
| 转场模板 | `blend`、`filter`、`echo_freeze`、`rise`、`melt`、`cut`、`slam`、`vocal_handoff`、`vocal_ducking`、`bass_swap`、`drum_swap`、`instrumental_only`、`vocal_solo_intro` |
| RK | 双 deck、prefetch、`/load_plan`、`/xfade`、sync-worker、original + stems 下载、sha256、`playback_tier` |
| 降级路线 | stems 不完整时可以退回 `non_stem`，分析不足时保留 raw crossfade fallback |

### 1.3 当前结论

系统可以演示，也能听到比单纯淡入淡出更丰富的接歌方式。但它还不能宣称达到 djay Automix 或成熟 DJ 软件的稳定度。

目前最影响听感的不是“模板数量不够”，而是四个断点：

1. Flutter 实时同步到 RK 时通常只发 original，没有发四路 stems。
2. App 已经下发 `stem_curves` 和 `eq_curves`，RK engine 音频回调仍使用静态模板。
3. Planner 已经拿到真实 stem 分析，但部分评分继续使用 phrase proxy。
4. 每对歌曲只挑一个 entry 和 exit，缺少多个候选窗口的比较与离线听感验收。

---

## 2. P0：必须先修的播放问题

P0 问题会直接导致声音动作错误。完成 P0 前，不要继续扩充更多转场模板。

## 2.1 Flutter 同步 RK 时缺少 stems

### 现状

`mobile/lib/src/dj_control_page.dart::_ensureRkCache()` 手工构造 manifest，目前只包含：

```json
{
  "files": {
    "original": {"url": "...", "format": "mp3"}
  }
}
```

但后端已经有可用的单曲 manifest：

```text
app/modules/manifest/__init__.py::build_song_manifest()
```

它会返回：

```text
files.original
files.stems.vocals
files.stems.drums
files.stems.bass
files.stems.other
size
sha256
format
```

### 影响

Planner 可以选择 `stem_aware`，App 也可以显示 `vocal_handoff` 或 `bass_swap`，但 RK 没有收到 stems 文件。真实播放只能退化，或者依赖 RK 上碰巧存在的历史缓存。

### 修改

| 文件 | 任务 |
|---|---|
| `app/modules/manifest/router.py` | 单曲 manifest 使用 RK 可访问的外部 base URL，不要写死 `localhost` |
| `mobile/lib/src/api_client.dart` | 新增或补全获取 `/api/manifest/song/{song_id}` 的方法 |
| `mobile/lib/src/dj_control_page.dart` | `_ensureRkCache()` 改为使用后端 manifest，不再手工拼 original-only payload |
| `mobile/lib/src/library/song_detail_page.dart` | 复用同一份 manifest，避免曲库详情页和 DJ Live 两套同步逻辑 |

### 验收

1. 对一首 stems 完整歌曲调用同步。
2. RK sync-worker 状态应显示 5 个文件：original + 4 stems。
3. RK cache 中存在：

```text
<song_id>/original.*
<song_id>/vocals.wav
<song_id>/drums.wav
<song_id>/bass.wav
<song_id>/other.wav
```

4. `/state` 返回 `playback_tier=stem_aware`。

---

## 2.2 RK engine 没有执行动态 curves

### 现状

字段已经从 App 进入 RK：

```text
stem_curves
eq_curves
phase_anchor_sec
fallback_style
tempo_ratio
```

edge-agent 和 socket server 也已经转发这些字段。

问题出在：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py::_callback()
```

音频回调仍然根据 `style` 调用 `_style_envelopes()`，没有读取 `Transition.stem_curves` 和 `Transition.eq_curves`。

### 影响

App 显示“bass 互换”“鼓桥接”“人声后入”，扬声器却只执行 RK 内建静态曲线。元数据已经很聪明，声音动作还没跟上。

### 修改

| 文件 | 任务 |
|---|---|
| `cypher-integration/rk3588-edge/audio-engine/mix_plan.py` | 明确 curve schema，保持旧字段兼容 |
| `cypher-integration/rk3588-edge/audio-engine/engine.py` | 新增 curve evaluator；按 `progress=0..1` 读取 per-stem 和 EQ automation |
| `app/modules/dj_control/mixer_rules.py` | 将现有语义型 curve 转换为明确的时间点和 gain 值 |
| `app/modules/dj_control/transition_strategy.py` | 输出同一套 automation schema |

建议统一为数值 keyframes：

```json
{
  "stem_curves": {
    "prev": {
      "vocals": [[0.0, 1.0], [0.45, 1.0], [0.5, 0.0]],
      "bass": [[0.0, 1.0], [0.35, 0.0]],
      "drums": [[0.0, 1.0], [0.75, 1.0], [1.0, 0.0]],
      "other": [[0.0, 1.0], [1.0, 0.0]]
    },
    "next": {
      "vocals": [[0.0, 0.0], [0.55, 0.0], [0.75, 1.0]],
      "bass": [[0.0, 0.0], [0.42, 1.0]],
      "drums": [[0.0, 0.0], [0.2, 1.0]],
      "other": [[0.0, 0.0], [1.0, 1.0]]
    }
  },
  "eq_curves": {
    "prev_low_db": [[0.0, 0.0], [0.4, -24.0]],
    "next_low_db": [[0.0, -24.0], [0.45, 0.0]]
  }
}
```

约束：

- keyframe 时间范围必须是 `0..1`。
- gain 范围必须是 `0..1`。
- EQ dB 范围应限制在安全区间。
- 缺少动态曲线时，继续使用 `_style_envelopes()`。
- audio callback 内不得进行磁盘 IO、JSON 解析或重计算。

### 验收

1. 单元测试验证线性插值、边界值和缺失字段 fallback。
2. 离线渲染验证 `bass_swap` 不会出现双 bass 满增益。
3. `vocal_handoff` 的人声切换落在 beat 或 bar boundary。
4. callback 峰值受 limiter 控制，无长时间静音。

---

## 2.3 Planned fallback 没有成为 RK 的真实降级策略

### 现状

`Transition.fallback_style` 已经传入 RK，但：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py::_resolve_style()
```

仍然使用硬编码 fallback map。

### 影响

Planner 可能根据 BPM、调性和双人声风险选择 `echo_freeze`，RK 却退回固定 `blend` 或 `filter`。这会让跨风格歌曲再次出现突兀感。

### 修改

1. `_resolve_style()` 接收完整 `Transition`，而不是只有 requested style。
2. stems 缺失时优先使用 `tr.fallback_style`。
3. 如果 planned fallback 不受 RK 支持，再使用硬编码安全 map。
4. edge-agent 响应增加：

```json
{
  "actual_style": "echo_freeze",
  "degraded": true,
  "degrade_reason": "missing_stems"
}
```

### 验收

- 强制移除 stems，发送 `style=vocal_handoff`、`fallback_style=echo_freeze`。
- 响应必须返回 `actual_style=echo_freeze` 和 `degraded=true`。

---

## 2.4 Beatmatch ratio 必须用测试确认方向

### 现状

后端：

```text
app/modules/dj_control/mixer_rules.py
tempo_ratio = prev_bpm / next_bpm
```

RK：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py::_beatmatch_time_ratio()
```

RK 注释将 fallback ratio 描述为 `tempo_B / tempo_A`。两端语义存在冲突。

### 风险

如果 rubberband 接收的是 time ratio 而不是 tempo multiplier，方向写反会让 B 越拉越偏。

### 修改

1. 为 ratio 建立唯一术语：

```text
tempo_multiplier = target_bpm / source_bpm
time_ratio = source_bpm / target_bpm
```

2. API 中只允许一种字段。推荐使用 `tempo_multiplier`。
3. 在调用 rubberband 的最后一层转换为它需要的参数。
4. 旧 `tempo_ratio` 保留兼容读取，但要记录 deprecation。

### 必须增加的测试

| A BPM | B BPM | 目标 |
|---:|---:|---|
| 100 | 102 | B 输出约为 100 BPM |
| 128 | 124 | B 输出约为 128 BPM |
| 100 | 130 | 超过安全阈值，不做长 beatmatch |

测试不能只检查数字。离线渲染后重新测一次输出 BPM。

---

## 2.5 App 调用的两个 RK 路由不存在

### 现状

Flutter 已经调用：

```text
POST /prewarm_beatmatch
POST /beat_reinforce
```

当前 edge-agent 没有对应路由。App 捕获异常后静默继续。

### 修改

| 文件 | 任务 |
|---|---|
| `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py` | 新增请求模型 |
| `cypher-integration/rk3588-edge/edge-agent/main.py` | 新增路由，转发给 audio-engine |
| `cypher-integration/rk3588-edge/audio-engine/socket_server.py` | 接收命令 |
| `cypher-integration/rk3588-edge/audio-engine/engine.py` | 实现预热缓存和 beat reinforce 调度 |

如果本轮不准备实现 beat reinforce DSP，也必须明确返回：

```json
{"ok": false, "supported": false, "reason": "not_implemented"}
```

不要继续静默吞掉。

---

## 3. P1：分析与 Planner 收口

## 3.1 所有导入入口必须进入同一条 ingest pipeline

### 现状

- 方皮 / 酷我下载后会调用 `run_analysis_and_separation()`。
- 本地上传只保存文件。
- Flutter 曲库详情页允许用户手工点击重新分析和分轨。

### 问题

同一首歌换一种导入方式后，系统能力不同。用户很难理解为什么有的歌曲能用 stem-aware，有的歌曲只能淡入淡出。

### 修改

建立统一入口：

```text
enqueue_library_song_processing(song_id, requested_phases=None)
```

所有导入路径都调用它：

- 本地上传
- 方皮 / 酷我下载
- 歌单批量导入
- 管理员补录
- 手工重新分析

建议状态拆分：

```text
ingest_status
analysis_status
stem_status
genre_status
planner_ready_status
```

当前 `run_analysis_and_separation()` 无论 stems 是否失败，最后都会把 `analysis_status` 标为 `completed`。需要修正。

### 验收

1. 上传本地 MP3 后自动开始分析。
2. 基础分析成功但 Demucs 失败时：

```text
analysis_status=completed
stem_status=error
planner_ready_status=non_stem_ready
```

3. Demucs 成功时：

```text
planner_ready_status=stem_ready
```

---

## 3.2 Track profiler 应优先使用真实 stems 证据

### 现状

`app/modules/dj_set/track_analysis_adapter.py` 已经整理出 `TrackAnalysisV2`，其中包含：

```text
stem_quality_score
stem_activity_windows
vocal_events
bass_risk_windows
transition_windows
evidence_level
```

但 `app/modules/dj_set/track_profiler.py` 仍然：

- 从 phrase label 估算 vocal density。
- 只要 stems 路径存在，就给每路 stem 质量 `1.0`。
- 使用 proxy section energy，而不是优先消费真实窗口。

### 修改

1. `build_track_profile()` 优先读取 `TrackAnalysisV2`。
2. 只有 measured 字段不存在时，才使用 proxy。
3. 为每项派生值保留 `evidence_level`：

```text
measured
proxy
needs_review
```

4. quality gate 对 `needs_review` 降低激进模板权重。

### 验收

- 同一首歌提供真实 `stem_activity_windows` 后，profile 中 vocal density 必须发生变化。
- `stem_quality_score=0.42` 时，不允许 profiler 覆盖为 `1.0`。
- 缺少 stems 时仍能生成 non-stem profile。

---

## 3.3 每对歌曲需要 Top-K 候选窗口

### 现状

`app/modules/dj_set/edge_analyzer.py` 当前行为：

- A：选择最后一个 safe exit。
- B：选择第一个 safe entry。
- 对这一组窗口打分。

### 问题

真实 DJ 不会机械地使用“最后一个 outro + 第一个 intro”。有时更早的 breakdown 更适合退出，有时 B 的第二个 groove 比文件开头更适合进入。

### 修改

1. 为 A 生成最多 5 个 exit candidates。
2. 为 B 生成最多 5 个 entry candidates。
3. 对 A → B 的窗口组合评分。
4. 每对歌曲保留 Top 3：

```json
{
  "pair_id": "a->b",
  "candidates": [
    {
      "from_at_sec": 176.0,
      "to_at_sec": 16.0,
      "fade_sec": 12.0,
      "score": 0.87,
      "tags": ["clean_outro", "drum_bridge"],
      "risks": []
    }
  ]
}
```

5. Set optimizer 使用最佳候选，但保留另外两个候选供现场 `Safer`、`Delay 8 Bars` 切换。

### 候选评分至少包含

```text
phrase_alignment
beat_compatibility
tempo_stability
key_compatibility
energy_continuity
vocal_safety
bass_safety
loudness_safety
stem_quality
transition_duration_fit
```

### 验收

- 为至少 6 首歌生成 all-pairs matrix。
- 每个可用 A → B 至少生成 1 个候选。
- 高质量 pair 尽量保留 3 个候选。
- 每个候选的 entry 和 exit 必须落在 beat 或 phrase boundary 容差内。

---

## 3.4 Intro / Outro 分析需要升级为“最佳可混片段”

### 现状

系统已经会识别 intro、outro，也会输出 clean score。但 stems 后处理主要查看歌曲最前和最后的短窗口。

### 问题

“歌曲开头很干净”不等于“最适合混入的位置就在 0 秒”。专业接歌需要找完整的 8 或 16 小节：

- 鼓稳定
- 人声少
- bass 风险可控
- 能量连续
- 进入主段落时不会显得突然

### 修改

新增：

```text
mix_in_regions[]
mix_out_regions[]
```

每个区域包含：

```text
start_sec
end_sec
bars
clean_score
vocal_density
drum_stability
bass_density
energy_slope
phrase_role
recommended_styles[]
```

注意：当前系统做的是区域识别，不是把 intro / outro 物理切割成单独音频文件。只有离线预览或产品明确需要时，才导出切片 WAV。

---

## 3.5 风格字段需要拆开

### 现状

系统同时存在：

```text
genre
dance style
transition style
manual tag
```

部分旧代码使用 `SongTag.style` 保存逗号分隔标签，也把它当作 genre 手工覆盖值。

### 风险

`hiphop` 可能表示音乐流派，也可能表示舞种偏好。`locking` 是舞种，不应进入音乐 genre 分类器。`vocal_handoff` 则是执行模板，不能和前两类混在一起。

### 修改

拆分为：

```text
genre_profile
dance_style_profile
manual_tags
transition_preferences
```

迁移策略：

1. 旧 `SongTag.style` 保留读取兼容。
2. 新写入使用拆分字段。
3. 增加一次性迁移脚本。
4. Flutter 曲库详情页增加人工标签编辑入口。

### Spotify 与 Discogs

现有代码已经具备 Spotify 和 Discogs 元数据增强逻辑，但部署仍需检查：

- `.env.example`
- deploy 环境变量
- `requirements.txt`
- `spotipy`
- Discogs token

没有外部凭据时，分类器必须回落到 audio features，不得阻塞分析队列。

---

## 4. P1：Manifest、同步和 Session

## 4.1 Playlist manifest 仍是占位实现

### 现状

`app/modules/manifest/__init__.py::build_playlist_manifest()` 中：

- playlist join 被 `if False` 禁用。
- 没有歌曲时会回退为任意 20 首 ready 曲目。
- `plan_id` 分支只有 `pass`。

### 风险

RK 预取整套歌单时可能下载错误歌曲。单曲同步能工作，不代表完整 playlist 同步可靠。

### 修改

1. 使用真实 `PlaylistSong` join。
2. 如果提供 `plan_id`，按 MixPlan tracks 顺序生成 manifest。
3. 保持歌曲顺序。
4. 每首歌曲必须包含 original；stems 缺失可以降级，但要显式写入 flags。
5. playlist 不存在时返回 404，不得回退到任意曲目。

### 验收

- 创建 4 首歌 playlist。
- manifest 只返回这 4 首，顺序一致。
- stems 完整歌曲返回 5 个文件。
- stems 缺失歌曲返回 original 和 `stemStatus`。

---

## 4.2 Manifest URL 不能写死 localhost

### 现状

`app/modules/manifest/router.py` 使用：

```python
base_url = f"http://localhost:{settings.app_port}"
```

RK 无法通过自己的 localhost 下载 Jetson 或网关资源。

### 修改

优先级：

```text
HARBEAT_PUBLIC_ASSET_BASE_URL
→ 请求 Host / forwarded headers
→ 相对 URL
```

sync-worker 已经支持相对 URL 拼接。部署环境优先配置明确的公开 base URL。

---

## 4.3 Sync-worker sidecar 不能跳过真实校验

### 现状

`sync-worker/main.py::_already_valid()` 发现 `.sha256` sidecar 内容与期望值相同时，直接返回 `True`。

### 风险

如果音频文件后来损坏、被截断或被人工覆盖，陈旧 sidecar 会误报缓存有效。

### 修改

1. sidecar 保存：

```json
{"sha256": "...", "size": 123, "mtime_ns": 123}
```

2. 文件 size 或 mtime 改变时重新算 sha256。
3. 对 legacy sidecar 至少先检查 size。
4. 增加 `verify=full` 调试模式，强制计算全部 hash。

### 验收

- 下载一首歌。
- 手工截断缓存文件，但保留 sidecar。
- 再次同步时必须重新下载，不得命中缓存。

---

## 4.4 RK SessionEvent 目前只接收，不持久化

### 现状

RK edge-agent 已经支持事件批量 flush、失败落盘和启动恢复。

但：

```text
app/modules/sessions/router.py::ingest_rk_session_events_endpoint()
```

只打印日志并返回 accepted，没有写入数据库。

### 修改

1. 建立支持字符串 session id 的 RK session event 表，或扩展现有 schema。
2. 写入：

```text
session_id
rk_id
event_id
event_type
event_value
timestamp
received_at
```

3. 使用 `event_id` 做幂等去重。
4. 增加查询接口，支持按 session 查看：

```text
load
play_started
crossfade_start
crossfade_end
key_press
degraded
sync_error
```

### 验收

1. RK flush 5 个事件。
2. 云端查询到 5 个事件。
3. 重复 flush 同一批，不得重复写入。
4. RK 断网后落盘；恢复网络后补发成功。

---

## 5. P2：听感质量闭环

## 5.1 建立批量离线 A/B 渲染

### 目标

不要只看单元测试。音频算法最终要听，并且要能量化比较。

仓库已有：

```text
cypher-integration/rk3588-edge/audio-engine/scripts/render_mix_quality.py
cypher-integration/rk3588-edge/audio-engine/scripts/batch_library_mix.py
```

把它们收敛成固定 runner：

```bash
python3 cypher-integration/rk3588-edge/audio-engine/scripts/batch_library_mix.py \
  --library-report data/library-analysis.json \
  --output-dir tmp/mix-quality
```

### 每个最终相邻 pair 至少渲染

```text
selected stem-aware 方案
selected non-stem fallback
baseline blend
```

### 每个 WAV 输出指标

```text
peak_dbfs
rms
integrated_lufs
segment_loudness
silence_ratio
clip_ratio
low_frequency_overlap
vocal_overlap
bass_overlap
energy_curve_before
energy_curve_during
energy_curve_after
verdict
```

### 基线门槛

| 指标 | 最低要求 |
|---|---|
| clipping | 不允许 |
| 长静音 | 不允许 |
| 双 bass 满增益 | 不允许 |
| 双人声高风险 | stem-aware 方案应明显低于 baseline |
| 响度突跳 | 转场前中后不能出现明显台阶 |
| bar boundary | hard cut、vocal handoff、bass swap 必须落在节拍边界 |

---

## 5.2 建立人工盲听数据集

至少准备 20 到 50 首授权测试歌曲，覆盖：

```text
流行
hip-hop
house
EDM
中文流行
真人鼓
速度漂移
纯器乐
高人声密度
低频很重
缺 stems
stem 质量较差
```

人工对每段转场记录：

```text
是否突兀
人声是否打架
低频是否发糊
节拍是否漂移
进入点是否自然
能量变化是否符合预期
是否需要换一种 preset
```

这些结果用于校准阈值，不要一开始就训练复杂模型。先让规则系统可靠。

---

## 5.3 给现场控制保留重新规划能力

App 第一版不应该变成传统 DJ 控制台。不要暴露高频、低频和 stem gain 旋钮给普通用户。

Planner 需要支持这些意图：

```text
Mix Now
Next Phrase
Energy Up
Energy Down
Safer
Delay 8 Bars
Talk
Undo
```

对应行为：

| 用户意图 | 系统动作 |
|---|---|
| Mix Now | 在最近的安全 phrase 执行当前最佳候选 |
| Next Phrase | 延后到下一个 8 小节边界 |
| Energy Up | 重排下一首或选择更强落点 |
| Energy Down | 选择 breakdown、echo 或更柔和歌曲 |
| Safer | 从 Top 3 切换到风险最低候选，必要时使用 non-stem |
| Delay 8 Bars | 延迟当前 transition，重新对齐 beat 和 phrase |
| Talk | 压低音乐并避免此时启动激进转场 |
| Undo | 撤回最近一次现场意图 |

---

## 6. 推荐提交顺序

每个阶段单独提交。不要把所有修改塞进一个 commit。

### Phase 0：安全分支和测试基线

```text
chore(automix): establish remediation test baseline
```

- 从最新集成分支创建工作分支。
- 跑当前测试并保存结果。
- 检查仓库中是否存在凭据。

### Phase 1：统一 ingest 状态机

```text
feat(library): unify import analysis and stem processing states
```

- 本地上传自动排队。
- 状态拆分。
- Demucs 失败不阻塞 non-stem。

### Phase 2：收敛 TrackAnalysisV2 和 Top-K 窗口

```text
feat(automix): score measured stem evidence and top-k transition windows
```

- profiler 优先真实 stems 数据。
- intro / outro 升级为 region。
- 每对歌曲保留 Top 3 候选。

### Phase 3：修 manifest 和 RK 同步

```text
fix(sync): deliver complete manifests and validate rk cache safely
```

- App 使用单曲 manifest。
- playlist manifest 使用真实 join。
- base URL 可部署。
- sidecar 校验修复。

### Phase 4：让 RK DSP 执行 canonical automation

```text
feat(rk): execute canonical stem eq and fallback automation
```

- 数值 keyframes。
- planned fallback。
- ratio 语义统一。
- prewarm 和 beat reinforce 路由。

### Phase 5：持久化 SessionEvent

```text
feat(session): persist rk playback events with idempotent flush
```

- 云端写库。
- 查询接口。
- 断网补发。

### Phase 6：批量离线评测和真机验收

```text
test(automix): add library batch render and rk playlist acceptance suite
```

- 6 首歌 all-pairs matrix。
- 4 首歌连续播放。
- stem-aware 与 non-stem 双路线。
- 人工试听记录。

---

## 7. 测试清单

## 7.1 本地后端

```bash
python3 -m py_compile \
  app/modules/library/analysis.py \
  app/modules/library/background_tasks.py \
  app/modules/manifest/__init__.py \
  app/modules/dj_set/track_profiler.py \
  app/modules/dj_set/edge_analyzer.py \
  app/modules/dj_control/mixer_rules.py

python3 -m pytest app/tests -q
```

必须增加：

- 本地上传自动排队。
- 基础分析成功、stems 失败时状态正确。
- profiler measured 优先于 proxy。
- Top-K entry / exit 评分。
- playlist manifest 顺序和文件完整度。
- SessionEvent 幂等。

## 7.2 RK 本地测试

```bash
python3 -m py_compile \
  cypher-integration/rk3588-edge/edge-agent/main.py \
  cypher-integration/rk3588-edge/sync-worker/main.py \
  cypher-integration/rk3588-edge/audio-engine/engine.py

python3 -m pytest cypher-integration/rk3588-edge/tests -q
```

必须增加：

- 动态 stem keyframes 插值。
- EQ curve 插值。
- planned fallback。
- sidecar 陈旧缓存。
- 100 → 102 BPM 和 128 → 124 BPM 输出复测。
- stems 不完整时 non-stem 不崩溃。

## 7.3 RK 真机

```text
GET  /health
GET  /state
POST /load_plan
POST /play
POST /xfade
POST /trigger
POST /internal/flush_events
```

真机验收：

1. 同步 4 首歌，其中至少一首故意缺 stems。
2. 完整歌曲下载 original + 4 stems，sha256 全部通过。
3. 连续播放 4 首歌，不出现戛然而止。
4. `vocal_handoff`、`bass_swap`、`blend`、`filter`、`echo_freeze` 至少各试听一次。
5. 缺 stems 歌曲自动降级，App 能看到 actual tier 和 degrade reason。
6. `/trigger` 验证 7 / 8 / 9 stem FX。
7. 断网后事件落盘，恢复后补发。

---

## 8. 完成定义

只有满足以下条件，才能把本轮标记为完成：

- [ ] 所有导歌入口自动进入统一分析流水线。
- [ ] 本地上传不再需要人工点击分析和分轨。
- [ ] Planner 优先使用真实 stem activity 和 stem quality。
- [ ] 每个 A → B 至少有一个安全候选，高质量 pair 保留 Top 3。
- [ ] App 同步 original + 4 stems，不再手工拼 original-only manifest。
- [ ] Playlist manifest 使用真实 playlist 或 MixPlan tracks，不再回退任意 20 首歌。
- [ ] RK audio callback 真正执行 `stem_curves` 和 `eq_curves`。
- [ ] RK 按 planned fallback 降级，并返回原因。
- [ ] Beatmatch ratio 有音频级回归测试。
- [ ] `/prewarm_beatmatch` 和 `/beat_reinforce` 已实现，或明确返回 unsupported。
- [ ] Sync-worker 不会被陈旧 sidecar 欺骗。
- [ ] SessionEvent 在云端可查询，重复 flush 不重复写入。
- [ ] 至少 6 首歌完成 all-pairs 离线评测。
- [ ] 至少 4 首歌完成 RK 连续播放验收。
- [ ] Stem-aware 和 non-stem 两条路线都能稳定播放。

---

## 9. 暂时不要做的事情

以下工作有价值，但不应抢在播放闭环之前：

- 不要继续增加十几个新 preset。
- 不要急着训练大型风格模型。
- 不要让 RK 跑 Demucs。
- 不要把 App 做成专业 DJ 台。
- 不要先做复杂云端推荐系统。
- 不要把真实密码、JWT、设备 token 或 `cypher.env` 提交到 Git。

先让一份 canonical plan 从分析结果走到扬声器，并且每次都能解释：为什么选这首歌、为什么在这里接、为什么使用这种接法、现场是否发生了降级。

---

## 10. 交接给 AI Agent 的执行提示

可以把下面这段直接发给接手的 AI：

```text
请阅读 docs/DJ_AUTOMIX_REMEDIATION_EXECUTION_SPEC.md。
从 origin/codex/integrate-analysis-session 的最新提交创建独立工作分支。
不要覆盖用户当前工作区中的未提交改动。
按 Phase 0 到 Phase 6 顺序执行，每个 Phase 单独提交。
先修 P0 播放闭环，不要先增加新 preset。
每完成一个 Phase，运行文档中的本地测试并报告结果。
涉及 RK 部署时，先备份 /home/cat/cypher，再覆盖文件并重启相关服务。
不要提交密码、JWT、设备 token 或 cypher.env。
达到离线听感明显改善或 RK 四首连续播放验收通过后，再 push 远端。
```
