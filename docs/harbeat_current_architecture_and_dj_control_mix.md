# HarBeat 当前项目架构�?DJ Control 混音全链�?
本文记录当前代码库和真实三端部署的工作方式，重点说明 DJ Control 的选歌、排歌、缓存、切歌、v3.2 混音计划�?RK 执行细节。它面向后续接手开发者，优先描述“现在真实怎么跑”，不是早期方案文档�?
## 1. 三端角色

### 手机 App

位置：`mobile/lib/src/`

手机负责用户交互和流程编排：

- 曲库、详情页、DJ Control UI�?- 调用 Jetson API 做选歌、排歌、切歌计划�?- 调用 RK Edge Agent 做播放、暂停、seek、prefetch、xfade�?- 轮询或接�?RK 状态，显示当前曲目、进度、缓存进度、实际执�?tier�?
关键文件�?
- `mobile/lib/src/dj_control_page.dart`：DJ Control 主流程�?- `mobile/lib/src/api_client.dart`：Jetson 后端 API 客户端�?- `mobile/lib/src/edge_agent_client.dart`：RK Edge Agent 客户端，包含 `/state`、`/play`、`/xfade`、`/prefetch`、`/cache/validate`�?- `mobile/lib/src/live_models.dart`：实时播放状态模型�?
### Jetson 后端

位置：`app/`

Jetson 负责曲库、音频分析、推荐、选歌、排歌、v3.2 混音计划生成�?
- 保存 `library_songs` 曲库元数据�?- 保存 BPM、Camelot key、energy、phrase_map、energy_curve、vocal_events、bass_risk_windows、downbeats 等分析数据�?- 生成 DJ Control 的队列、备选池、切歌计划�?- 为自动接歌、快切、能量切歌、舞种切歌生成统一�?`prepared_transition`�?- v3.2 的核心计划是 `section_match + eq_band_mix`�?
关键文件�?
- `app/modules/dj_control/router.py`
- `app/modules/dj_control/cut_strategy.py`
- `app/modules/dj_control/spotify_mix/section_matcher.py`
- `app/modules/dj_control/spotify_mix/section_features.py`
- `app/modules/dj_control/spotify_mix/section_scorer.py`
- `app/modules/dj_control/eq_transition_presets.py`
- `app/modules/dj_control/eq_transition_strategy.py`
- `app/modules/library/models.py`
- `app/modules/library/analysis_vocal_patch_gpu.py`
- `app/modules/manifest/__init__.py`
- `app/modules/manifest/router.py`

当前 Jetson 服务�?
- `harbeat-api.service`
- health：`http://127.0.0.1:8000/health`

### RK3588

位置：`cypher-integration/rk3588-edge/`

RK 负责边缘播放、缓存、解码和真实混音执行�?
- `edge-agent` 暴露手机调用�?REST API，默认端�?`9000`�?- `sync-worker` �?Jetson manifest 拉取音频文件�?RK 本地缓存，默认端�?`9100`�?- `audio-engine` 播放音频、执�?crossfade �?`eq_band_mix`�?- `input-daemon` 处理实体控制输入�?
关键文件�?
- `cypher-integration/rk3588-edge/edge-agent/main.py`
- `cypher-integration/rk3588-edge/edge-agent/edge_agent/state.py`
- `cypher-integration/rk3588-edge/sync-worker/main.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`
- `cypher-integration/rk3588-edge/audio-engine/socket_server.py`
- `cypher-integration/rk3588-edge/audio-engine/envelope_runner.py`
- `cypher-integration/rk3588-edge/audio-engine/mix_plan.py`

当前 RK 常用地址�?
- Edge Agent：`http://192.168.43.7:9000`
- Sync Worker：`http://192.168.43.7:9100`
- 本地缓存：`/home/cat/cypher/cache/{song_id}/`

## 2. 曲库数据与分析字�?
核心表：`library_songs`

DJ Control 混音依赖字段�?
- `id`：UUID，三端传递主键�?- `title` / `artist` / `duration`
- `bpm`
- `camelot_key`
- `energy`
- `phrase_map`：段落结构。每项常见字段：`label/start/end/energy/intensity`�?- `energy_curve`：时间点能量曲线�?- `vocal_events`：GPU 或分析任务产生的人声区间，当前目标格式为 `{start, end, confidence}`�?- `bass_risk_windows`：低频风险区间�?- `downbeats`：小�?强拍点，用于吸附切点�?- `loudness_profile`
- `music_features`
- `dance_style_scores`、外部风格标签相关字段�?
人声检测：

- 新增 GPU 人声检测在 `app/modules/library/analysis_vocal_patch_gpu.py`�?- v3.2 混音只需�?`vocal_events` 区间，不要求 stems 文件参与实际混音�?- 当前混音规则允许单边人声，但禁止或强惩罚双边人声重叠�?
## 3. DJ Control 用户流程

手机 DJ Control 通常分四步：

1. 选歌
2. 排歌
3. 混音配置
4. 实时操作

### 选歌

常用 Jetson API�?
- `GET /api/dj/styles`
- `POST /api/dj/styles/pick`
- `GET /api/library/songs`
- `POST /api/dj/live/pool/prepare`

`/live/pool/prepare` 会根据当前队列生成：

- `active_queue`
- `reserve_pool`：按能量桶准备的备选池�?- `style_reserve_pool`：按舞种/风格准备的备选池�?- `energy_profiles`
- `sync_priority`
- `style_pool_status`

### 排歌

常用 Jetson API�?
- `GET /api/dj/sequence/presets`
- `POST /api/dj/sequence`

请求体由 `SequenceRequest` 定义�?
```json
{
  "song_ids": ["..."],
  "preset": "warmup_to_peak"
}
```

返回 `SequenceResponse`�?
- `preset`
- `sequence[]`
- 每个 `SequenceEntry` 包含 `song_id/position/target_energy/actual_energy/breakdown`

### 混音计划

自动接歌和三种实时切歌最终都应拿�?Jetson �?`prepared_transition`。当前目标是统一走：

```text
transition_mode = section_match
execution_mode = eq_band_mix
```

核心接口�?
- `POST /api/dj/transitions/plan`
- `POST /api/dj/cut/plan`

## 4. 自动接歌 v3.2 方案

核心函数�?
- `plan_section_match_transition()`
  文件：`app/modules/dj_control/spotify_mix/section_matcher.py`

输入是两首歌的结构化分析�?
- BPM
- Camelot key
- duration
- phrase_map
- transition_windows
- energy_curve
- vocal_events
- bass_risk_windows
- downbeats
- bpm_curve

输出�?RK 可执行的 transition plan�?
```json
{
  "transition_mode": "section_match",
  "execution_mode": "eq_band_mix",
  "strategy": "soft_bass_swap",
  "duration_sec": 6.0,
  "fade_sec": 6.0,
  "from_at_sec": 117.493,
  "to_at_sec": 12.887,
  "target": {
    "song_id": "...",
    "start_cue_sec": 12.887
  },
  "deck_a": {
    "fader": [],
    "eq": {"low": [], "mid": [], "high": []},
    "filter": null
  },
  "deck_b": {
    "fader": [],
    "eq": {"low": [], "mid": [], "high": []},
    "filter": null
  },
  "section_match": {
    "score": 80.2,
    "quality": "good",
    "compatibility_breakdown": {},
    "vocal_policy": {}
  }
}
```

### 选点逻辑

当前逻辑不是只在歌曲尾端切，而是寻找中后段可退出位置：

- 当前歌候选出口来�?`enumerate_outro_sections()`�?- 候选包括中后段 `chorus/drop/break/bridge/instrumental/outro/verse`�?- 至少要过一个“音乐上足够表达”的时间点：大致不早�?45 秒或歌曲 25%�?- 38%-78% 进度区间会加分，太靠近结尾会扣分�?- 切点会吸附到附近 downbeat�?
入口来自 `enumerate_intro_sections()`�?
- 优先早期 `chorus/drop/verse/intro`�?- intro 默认偏后进入，即 `cue_offset = duration * 0.7`�?
### 人声规则

当前规则�?
- 单边人声允许�?- 双边人声同时重叠才是风险�?- “段落边界人声”与“实�?6 秒混音窗口人声”都会参与评分�?- 实际窗口检查函数在 `section_matcher._score_actual_mix_window()`�?
判断窗口�?
```text
当前歌窗�?= from_at_sec ~ from_at_sec + fade_sec
下一首窗�?= to_at_sec ~ to_at_sec + fade_sec
```

关键 breakdown 字段�?
- `actual_a_vocal`
- `actual_b_vocal`
- `actual_both_vocal`
- `actual_max_vocal`
- `actual_one_sided_vocal_allowed`
- `actual_hard_vocal_conflict`

阈值：

- `actual_both_vocal >= 0.25`：认为双边人声重叠，需要强惩罚或过滤�?- `a_vocal >= 0.60 && b_vocal >= 0.60`：硬双人声冲突�?- 单边人声高但另一边低，允许�?
### 当前策略集合

策略 preset �?`app/modules/dj_control/eq_transition_presets.py`�?
当前可主动选择策略�?
- `smooth_blend`：丝滑频段融合�?- `soft_bass_swap`：软低频换底�?- `hard_bass_swap`：强节奏低频换底�?- `vocal_safe`：人声保护衔接�?- `overlap`：段落重叠融合�?
`filter_sweep / 扫频打开` 当前已禁用：

- 自动策略不会再选它�?- fallback 不再选它�?- 用户模式 `filter` 会映射到 `soft_bass_swap`�?- �?preset 仍保留，只为兼容�?plan，不作为新计划主动策略�?
### 为什么现在常见是 soft_bass_swap

如果 BPM 差、调性距离或响度差较大，原来会�?`filter_sweep`。现�?`filter_sweep` 禁用后，这类风险对会默认转为 `soft_bass_swap`，继续通过 Low/Mid/High EQ �?fader 曲线完成衔接�?
## 5. eq_band_mix 执行方案

v3.2 的执行层�?`eq_band_mix`，不依赖 Spotify API，也不要�?stems。它基于原始 MP3/PCM 解码后做三频和音量包络�?
RK 执行入口�?
- 手机调用 RK：`POST /xfade`
- 请求中带�?  - `transition_mode: "eq_band_mix"`
  - `transition_plan`
  - `to_song_id`
  - `fade_sec`
  - `to_at_sec`
  - `style`

手机客户端方法：

- `EdgeAgentClient.xfade()`
  文件：`mobile/lib/src/edge_agent_client.dart`

RK Edge Agent�?
- `cypher-integration/rk3588-edge/edge-agent/main.py`
- `_run_xfade()`

�?`req.transition_mode == "eq_band_mix"` 且存�?`transition_plan`�?
```text
edge-agent /xfade
  -> _forward("xfade_eq_band_mix", transition_plan=...)
  -> audio-engine socket_server
  -> engine.manual_eq_band_mix()
```

audio-engine�?
- `socket_server.py` 接收 `xfade_eq_band_mix`
- `engine.py::manual_eq_band_mix()` 执行
- `envelope_runner.py`/`engine.py` �?envelope �?Low/Mid/High + fader 曲线

成功状态：

```json
{
  "playback_tier": "eq_band_mix",
  "style": "eq_band_mix",
  "degraded": false
}
```

失败/降级�?
- 如果目标歌未缓存或解码失败，可能 fallback�?- 当前代码会返�?`degraded=true` �?`degrade_reason`�?- 手机 UI 不应�?degraded 当作成功�?v3.2 接歌�?
## 6. 三种实时切歌

入口：`POST /api/dj/cut/plan`

请求模型：`CutPlanRequest`

### 快切

intent/strategy�?
- `fast_cut`

逻辑�?
- 只选择下一首和当前歌附近切点�?- 不重新设计接歌方式�?- 最终仍通过 `_attach_prepared_section_transition()` 附加 v3.2 `prepared_transition`�?- 具体衔接仍复用自动接歌的 `section_match + eq_band_mix`�?
### 能量切歌

intent�?
- `target_energy_bucket`

请求包含�?
```json
{
  "current_song_id": "...",
  "cursor_sec": 103.0,
  "target_energy_bucket": {"min": 80, "max": 90},
  "active_queue_song_ids": [],
  "reserve_pool_song_ids": [],
  "cached_song_ids": [],
  "syncing_song_ids": []
}
```

核心函数�?
- `plan_target_energy_cut()`
  文件：`app/modules/dj_control/cut_strategy.py`

候选评分：

- 优先目标能量区间�?- 现在不是只看整首�?energy，也看某个段落的 `segment_energy_score`�?- 段落候选来�?`phrase_map` �?`energy_curve`�?- 单边人声不再降低能量匹配�?- 缓存状态参与评分，但没�?exact bucket 时才逐步放宽�?
返回中重要字段：

- `selected_song`
- `entry_start_sec`
- `entry_label`
- `segment_energy_score`
- `score_breakdown.segment_energy_match`
- `score_breakdown.song_energy_match`
- `score_breakdown.segment_vocal_density`
- `prepared_transition`

能量入口覆盖�?
- `_attach_prepared_section_transition()` 会先生成普�?section_match�?- 如果 `selected_song.entry_start_sec` 存在，会尝试覆盖 `to_at_sec`�?- 覆盖前会调用 `_override_would_create_double_vocal()`�?- 如果覆盖会导致双边人声重叠，则拒绝覆盖，保留 section_match 原入口�?
### 舞种/风格切歌

intent�?
- `target_dance_style`

核心函数�?
- `plan_target_style_cut()`
  文件：`app/modules/dj_control/cut_strategy.py`

候选来源：

- active queue
- style reserve pool
- library fallback

评分因素�?
- 目标风格匹配分�?- 当前能量连续性�?- BPM 兼容�?- 缓存状态�?- 过往播放/blocked/excluded�?- transition safety�?
风格匹配数据来源�?
- `dance_style_scores`
- 外部标签富集后的字段
- `style_evidence_status`
- `external_sources`
- `matched_labels`

返回同样会附�?`prepared_transition`，接歌仍使用 v3.2�?
## 7. 缓存与拉取链�?
### Jetson manifest

接口�?
- `GET /api/manifest/song/{song_id}`
- `GET /api/manifest/playlist/{playlist_id}`

manifest 描述 RK 需要拉取的文件�?
当前 DJ 混音 `eq_band_mix` 主要需�?original 音频，不要求 stems�?
详情页分轨播放会使用 stem MP3 文件，但 DJ Control �?v3.2 本地 Spotify 风格混音不依�?stems�?
### RK sync-worker

位置�?
- `cypher-integration/rk3588-edge/sync-worker/main.py`

接口�?
- `POST /sync`
- `GET /status`
- `GET /cache/check?song_id=...&kind=original&format=mp3`
- `DELETE /cache/song/{song_id}`

下载目标�?
```text
/home/cat/cypher/cache/{song_id}/original.mp3
/home/cat/cypher/cache/{song_id}/vocals.mp3
/home/cat/cypher/cache/{song_id}/drums.mp3
/home/cat/cypher/cache/{song_id}/bass.mp3
/home/cat/cypher/cache/{song_id}/other.mp3
```

DJ Control 混音路径优先保证 original 可用�?
### RK audio-engine cache

`audio-engine/engine.py` 中：

- `check_song_cache(song_id, require_stems=False)`
- `prefetch(song_ids, wait=False, load_stems=False/True)`
- `validate_cache(song_ids, require_stems=False)`

对于 DJ Control 自动混音�?
- 播放和接歌至少要 original 可解码�?- `eq_band_mix` 不要�?stems�?- �?missing，会报错�?degraded，手机应显示失败/降级�?
## 8. 手机如何触发真实混音

手机拿到 Jetson �?`prepared_transition` 后，需要把字段映射�?RK�?
Jetson plan�?
```json
{
  "transition_mode": "section_match",
  "execution_mode": "eq_band_mix",
  "fade_sec": 6.0,
  "to_at_sec": 12.887,
  "to_song_id": "...",
  "transition_id": "...",
  "strategy": "soft_bass_swap",
  "deck_a": {},
  "deck_b": {}
}
```

手机调用 RK�?
```json
{
  "to_song_id": "...",
  "fade_sec": 6.0,
  "to_at_sec": 12.887,
  "style": "eq_band_mix",
  "transition_mode": "eq_band_mix",
  "transition_plan": {
    "...": "完整 prepared_transition"
  }
}
```

注意�?
- Jetson �?`transition_mode=section_match` 是计划层�?- 发给 RK 时必须用 `transition_mode=eq_band_mix`，让 Edge Agent �?`xfade_eq_band_mix`�?- `transition_plan` 应保留完�?deck_a/deck_b EQ 曲线�?- 不能只传普�?`/xfade` 字段，否则会变成普�?crossfade �?degraded�?
## 9. 当前真实策略状�?
当前已启用：

- 自动接歌：v3.2 `section_match + eq_band_mix`
- 快切：选择下一�?切点，接歌复�?v3.2
- 能量切歌：选择目标能量区间歌曲/段落，接歌复�?v3.2
- 舞种切歌：选择目标舞种候选，接歌复用 v3.2
- 人声规则：允许单边人声，避免双边人声
- 中段出口：启用，不再默认等尾�?- `filter_sweep`：禁用主动选择
- 默认风险替代策略：`soft_bass_swap`

当前策略优先级大致为�?
1. 双边人声：`vocal_safe` 或过滤�?2. 高低频冲突：`hard_bass_swap` / `soft_bass_swap`�?3. 兼容性好：`smooth_blend` / `overlap`�?4. BPM/调�?响度风险大且原本应扫频：现在转为 `soft_bass_swap`�?
## 10. 运行态验证命�?
### 手机

```powershell
& 'C:\Android\platform-tools\adb.exe' devices
& 'C:\Android\platform-tools\adb.exe' shell dumpsys window | Select-String -Pattern 'mCurrentFocus|mFocusedApp'
& 'C:\Android\platform-tools\adb.exe' shell uiautomator dump /sdcard/window.xml
& 'C:\Android\platform-tools\adb.exe' pull /sdcard/window.xml tmp_window.xml
```

### Jetson

```powershell
ssh -o BatchMode=yes root@100.87.142.21 "curl -sS --max-time 5 http://127.0.0.1:8000/health"
ssh -o BatchMode=yes root@100.87.142.21 "systemctl status harbeat-api --no-pager --lines=40"
ssh -o BatchMode=yes root@100.87.142.21 "journalctl -u harbeat-api --since '30 minutes ago' --no-pager | tail -120"
```

### RK

```powershell
ssh -o BatchMode=yes rk "hostname; ip -brief addr; ss -lntp | grep -E ':9000|:9100|:22' || true"
curl.exe -sS --max-time 5 http://192.168.43.7:9000/state
curl.exe -sS --max-time 5 http://192.168.43.7:9100/status
ssh -o BatchMode=yes rk "journalctl --since '30 minutes ago' --no-pager | grep -E 'xfade|eq_band_mix|degraded|fallback|crossfade start' | tail -160"
```

### 重新跑核心测�?
本地�?
```powershell
py -m pytest app/tests/test_section_matching.py app/tests/test_eq_band_mix_strategy.py app/tests/test_target_energy_cut_strategy.py -q
```

Jetson�?
```powershell
ssh -o BatchMode=yes root@100.87.142.21 "cd /home/mark/harbeat && /home/mark/venvs/harbeat/bin/python -m pytest app/tests/test_section_matching.py app/tests/test_eq_band_mix_strategy.py app/tests/test_target_energy_cut_strategy.py -q"
```

## 11. 常见问题定位

### 手机显示接歌成功，但听起来像普�?xfade

检�?RK `/state`�?
- `last_transition.actual_tier`
- `last_transition.actual_style`
- `last_transition.degraded`
- `last_transition.degrade_reason`

如果 `degraded=true`，说明没有真实执�?v3.2�?
### 仍然听到人声冲突

查看 Jetson plan�?
- `section_match.compatibility_breakdown.actual_a_vocal`
- `actual_b_vocal`
- `actual_both_vocal`
- `actual_hard_vocal_conflict`

当前允许单边人声。如果听到的是一首歌的人声进入，这符合规则；如果两边人声同时明显出现，需要降�?`actual_both_vocal` 阈值或加大惩罚�?
### 为什么策略全是软低频换底

因为 `filter_sweep` 已禁用。BPM、调性、响度风险较大的歌对，原先会扫频，现在映射为 `soft_bass_swap`�?
### 为什么还要拉 stems

DJ Control v3.2 不要�?stems�?
详情页鼓�?人声/贝斯/其他分轨播放需�?stem MP3�?
如果只测�?DJ Control，应优先确保 original MP3 缓存�?
### 为什么能量切歌听感不明显

检�?`selected_song.segment_energy_score` �?`prepared_transition.energy_entry_override`�?
- 如果 `energy_entry_override.applied=true`，说明入口被覆盖到目标能量段�?- 如果 `applied=false` �?reason �?`rejected_double_vocal_overlap`，说明该能量入口会双人声，系统保留了更安全的 section_match 入口�?
## 12. 修改指南

### 改接歌点

优先改：

- `app/modules/dj_control/spotify_mix/section_features.py`
- `enumerate_outro_sections()`
- `enumerate_intro_sections()`

### 改人声规�?
优先改：

- `app/modules/dj_control/spotify_mix/section_scorer.py`
- `app/modules/dj_control/spotify_mix/section_matcher.py::_score_actual_mix_window()`
- `app/modules/dj_control/router.py::_override_would_create_double_vocal()`

### 改策略选择

优先改：

- `app/modules/dj_control/spotify_mix/section_scorer.py::choose_strategy()`
- `app/modules/dj_control/eq_transition_strategy.py::_auto_strategy()`
- `app/modules/dj_control/eq_transition_presets.py`

### 改能量切�?
优先改：

- `app/modules/dj_control/cut_strategy.py::plan_target_energy_cut()`
- `_section_energy_candidates()`
- `_best_target_energy_segment()`
- `_candidate_plan_item()`

### 改舞种切�?
优先改：

- `app/modules/dj_control/cut_strategy.py::plan_target_style_cut()`
- `app/modules/dj_control/dance_style.py`
- 外部标签富集模块：`app/modules/library/external_metadata/`

### �?RK 执行

优先改：

- `cypher-integration/rk3588-edge/edge-agent/main.py::_run_xfade()`
- `cypher-integration/rk3588-edge/audio-engine/engine.py::manual_eq_band_mix()`
- `cypher-integration/rk3588-edge/audio-engine/envelope_runner.py`

## 13. 部署注意事项

Jetson 同步后需要：

```powershell
ssh root@100.87.142.21 "cd /home/mark/harbeat && /home/mark/venvs/harbeat/bin/python -m py_compile app/modules/dj_control/spotify_mix/section_matcher.py"
ssh root@100.87.142.21 "systemctl restart harbeat-api && sleep 10 && curl -sS http://127.0.0.1:8000/health"
```

RK 同步后需要确认：

```powershell
ssh rk "ps -eo pid,cmd | grep -E 'audio-engine|edge-agent|sync-worker|input-daemon'"
ssh rk "ss -lntp | grep -E ':9000|:9100'"
curl.exe -sS http://192.168.43.7:9000/state
```

手机修改后需要：

```powershell
flutter analyze
flutter build apk
& 'C:\Android\platform-tools\adb.exe' install -r build\app\outputs\flutter-apk\app-release.apk
```

## 14. 当前验收标准

一�?DJ Control 混音应满足：

- 手机 UI 进入实时操作页�?- Jetson 返回 `prepared_transition`�?- `prepared_transition.transition_mode == section_match`�?- `prepared_transition.execution_mode == eq_band_mix`�?- 手机发给 RK �?`/xfade` 包含 `transition_mode=eq_band_mix` 和完�?`transition_plan`�?- RK `/state.last_transition.actual_tier == eq_band_mix`�?- `degraded == false`�?- 自动接歌、快切、能量切歌、舞种切歌都不应走普�?xfade�?- 如果降级，UI 必须显示失败�?degraded，不能伪装成成功�?
