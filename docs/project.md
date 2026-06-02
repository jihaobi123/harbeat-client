# HarBeat 当前项目详细交接文档

版本日期：2026-06-03
适用对象：后续开发者、部署运维人员、继续接手本项目的 AI Agent
覆盖范围：FastAPI 后端、Flutter 手机端、Jetson 分析端、RK3588 播放端、DJ Control、自动混音、歌曲分析、舞种选择、部署与测试。

---

## 1. 项目一句话说明

HarBeat 是一个面向街舞练习、cypher、battle warm-up、小型 party 的自动控乐系统。它的目标不是复刻专业 DJ 台，而是把“选歌、排序、接歌、预取、混音、现场切歌和舞种解释”做成一套可自动执行、可人工干预、可在 RK3588 上低延迟播放的系统。

当前真实架构是：

```text
Flutter 手机 App
  -> FastAPI 后端 / Jetson：曲库、登录、导入、分析、风格证据、DJ Control 编排
  -> RK3588 edge-agent：现场播放、暂停、预取、xfade、FX、状态轮询

FastAPI 后端
  -> PostgreSQL：用户、曲库、分析结果、歌单、session
  -> UPLOAD_DIR：原曲、stems、处理文件
  -> 外部 metadata API：MusicBrainz / Last.fm / Discogs，用于风格标签补充

RK3588
  -> sync-worker：按 manifest 把原曲和 stems 拉到本地 cache
  -> edge-agent：对手机暴露播放控制 API
  -> audio-engine：真正执行播放、stem xfade、EQ、FX、缓存解码
```

核心边界：

- Jetson / 后端做重计算：音频分析、stems、曲库 metadata、自动选歌、transition plan。
- RK3588 做实时执行：本地 cache、播放、xfade、stem envelope、FX、低延迟状态。
- 手机端做控制台：选择舞种和时长、展示推荐理由、发起同步、控制 RK。
- 外部平台标签只做“风格证据补充”，不替代本地音频分析。

---

## 2. 代码目录总览

| 路径 | 作用 | 修改时机 |
|---|---|---|
| `app/main.py` | FastAPI 入口、路由挂载、CORS、异常处理 | 后端入口或跨模块中间件 |
| `app/modules/router.py` | 后端模块总路由 | 新增后端模块 |
| `app/shared/config.py` | `.env` 配置项声明 | 新增环境变量 |
| `app/shared/database.py` | SQLAlchemy Session / Base | 数据库连接问题 |
| `app/modules/library/` | 曲库、上传、分析、stems、外部风格证据 | 歌曲导入、分析、标签、曲库接口 |
| `app/modules/dj_control/` | DJ Control：舞种选歌、能量排序、切歌计划、FX、DJ set | 舞种选择、自动混音、切歌策略 |
| `app/modules/dj_set/` | DJ set 原型管线：模板、角色、段落、质量门 | 自动生成多套 set |
| `app/modules/manifest/` | 给 RK 下载资源的 manifest | RK 拉取不到歌或 stems |
| `app/modules/assets/` | `/api/assets/...` 文件下载 | RK 下载 404、资源路径问题 |
| `app/modules/fangpi/` | 搜索、导入、外部歌单解析 | 导入音乐流程 |
| `app/modules/playlists/` | 歌单、离线 mix、老版 stem automix | 歌单和历史混音功能 |
| `app/modules/sessions/` | 练习 session、RK 事件回收 | 现场 session 记录 |
| `mobile/lib/src/` | Flutter App 主代码 | 手机端 UI 和 API 调用 |
| `cypher-integration/rk3588-edge/` | RK3588 edge-agent / audio-engine / sync-worker | RK 播放端能力 |
| `scripts/` | 后端批处理、分析补丁、运维脚本 | 批量补分析、回填数据 |
| `docs/` | 文档、规格、交接说明 | 需求说明和交接 |

---

## 3. 后端模块与接口

### 3.1 登录与用户

主要文件：

- `app/modules/auth/router.py`
- `app/modules/auth/service.py`
- `app/modules/users/models.py`
- `app/modules/users/router.py`

主要职责：

- 用户注册、登录、当前用户查询。
- JWT token 签发和鉴权。
- 手机端所有曲库、DJ Control 请求都依赖 token。

如果手机端出现登录后接口 401，优先检查：

- `mobile/lib/src/api_client.dart` 是否带了 `Authorization: Bearer ...`
- `app/modules/auth/dependencies.py`
- 后端 `.env` 的 `JWT_SECRET`

### 3.2 曲库 Library

主要文件：

- `app/modules/library/router.py`
- `app/modules/library/models.py`
- `app/modules/library/schemas.py`
- `app/modules/library/analysis.py`
- `app/modules/library/background_tasks.py`
- `app/modules/library/stem_analysis.py`
- `app/modules/library/genre_classifier.py`
- `app/modules/library/dj_feature_extractor.py`

关键接口：

| 接口 | 作用 |
|---|---|
| `GET /api/library/songs` | 手机端曲库列表 |
| `GET /api/library/songs/{song_id}` | 单曲详情 |
| `POST /api/library/upload` | 上传本地音频 |
| `POST /api/library/songs/{song_id}/analyze` | 手动触发分析 |
| `POST /api/library/songs/{song_id}/separate-stems` | 手动触发 stems 分离 |
| `POST /api/library/songs/{song_id}/refresh-style-evidence` | 刷新外部风格证据 |

当前歌曲分析会写入 `library_songs` 表，核心字段在 `app/modules/library/models.py` 的 `LibrarySong`。

关键分析数据：

| 字段 | 含义 | 主要用途 |
|---|---|---|
| `bpm` | 主 BPM | 排序、切歌策略、beat 对齐 |
| `bpm_curve` | 分段 BPM 曲线 | 判断 tempo stability |
| `beat_points` | beat 时间点 | xfade、downbeat、节奏分析 |
| `downbeats` | 强拍时间点 | 切歌落点 |
| `phrase_map` | 乐句段落 | outro / intro / phrase 边界 |
| `cue_points` | cue / hot cue | 入歌点、出歌点 |
| `key` / `camelot_key` | 调性 | harmonic blend、keyDistance |
| `energy` / `energy_curve` | 能量 | 能量排序、set 曲线 |
| `loudness_profile` | 响度和 replay gain | 响度归一 |
| `genre_profile` | 流派和外部标签证据 | 舞种选择、风格距离 |
| `dance_styles` | 各舞种排序结果 | 手机端展示和 pick |
| `dance_style_scores` | 舞种分数字典 | `/styles/pick` 快速读取 |
| `dance_style_status` | 风格证据状态 | UI 显示 ready / local_only 等 |
| `stems` | vocals / drums / bass / other 路径 | RK stem xfade |
| `stem_activity` | stem 活跃度 | 人声冲突、分轨过渡 |
| `vocal_events` | 人声事件窗口 | 避免双人声冲突 |
| `bass_risk_windows` | 低频风险窗口 | bass swap |
| `transition_windows` | 可切歌窗口 | 智能 exit / entry |
| `transition_recommendations` | 分析端建议切法 | DJ Control 可解释 |

如果要修改“导入音频后分析出什么数据”，优先看：

1. `app/modules/library/analysis.py`
2. `app/modules/library/background_tasks.py`
3. `app/modules/library/stem_analysis.py`
4. `app/modules/library/dj_feature_extractor.py`
5. `app/modules/library/models.py`

### 3.3 Manifest 与资源下载

主要文件：

- `app/modules/manifest/router.py`
- `app/modules/manifest/__init__.py`
- `app/modules/assets/router.py`

关键接口：

| 接口 | 作用 |
|---|---|
| `GET /api/manifest/song/{song_id}` | 给 RK 同步单曲原曲 + stems |
| `GET /api/manifest/playlist/{playlist_id}` | 给 RK 同步整张歌单 |
| `GET /api/assets/{asset_path}` | 下载原曲和 stems 文件 |

`build_song_manifest()` 会输出：

- `files.original.url`
- `files.stems.vocals/drums/bass/other.url`
- `analysis.bpm/key/energy/downbeats/phrase_map/...`
- `qualityFlags.has_stems`
- `stemStatus`

如果 RK 报 `409 缺少 original.wav` 或手机端提示同步失败，按顺序检查：

1. `GET /api/manifest/song/{song_id}` 是否能返回 `files.original.url`
2. 这个 URL 在 RK 网络里能否访问
3. 后端 `.env` 的 `PUBLIC_ASSET_BASE_URL`
4. `UPLOAD_DIR` 下原文件和 stems 是否真实存在
5. RK `sync-worker` 是否 active

---

## 4. DJ Control 后端

主要文件：

- `app/modules/dj_control/router.py`
- `app/modules/dj_control/schemas.py`
- `app/modules/dj_control/dance_style.py`
- `app/modules/dj_control/style_taxonomy.py`
- `app/modules/dj_control/style_reference_profiles.py`
- `app/modules/dj_control/energy_hiphop.py`
- `app/modules/dj_control/sequencer.py`
- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/transition_strategy.py`
- `app/modules/dj_control/cut_strategy.py`
- `app/modules/dj_control/fx_synth.py`
- `app/modules/dj_control/vibe_search.py`

### 4.1 DJ Control 接口

| 接口 | 文件 | 作用 |
|---|---|---|
| `GET /api/dj/styles` | `router.py` | 返回可选舞种 |
| `POST /api/dj/styles/pick` | `router.py` + `dance_style.py` | 按舞种和目标时长选歌 |
| `GET /api/dj/energy/buckets` | `router.py` | 返回能量桶 |
| `GET /api/dj/sequence/presets` | `router.py` + `sequencer.py` | 返回排序预设 |
| `POST /api/dj/sequence` | `router.py` + `sequencer.py` | 对手选歌曲按能量曲线排序 |
| `GET /api/dj/songs/{song_id}/energy` | `router.py` + `energy_hiphop.py` | 单曲街舞能量拆解 |
| `GET /api/dj/transitions/rules` | `router.py` + `mixer_rules.py` | 返回混音规则列表 |
| `POST /api/dj/transitions/plan` | `router.py` + `mixer_rules.py` | 两首歌之间生成 transition spec |
| `POST /api/dj/cut/plan` | `router.py` + `cut_strategy.py` | 现场快切/升能/降能 |
| `GET /api/dj/fx` | `router.py` + `fx_synth.py` | 返回 FX catalog |
| `GET /api/dj/fx/{fx_key}.wav` | `router.py` + `fx_synth.py` | 合成或返回 FX 音频 |
| `POST /api/dj/vibe/search` | `router.py` + `vibe_search.py` | 自然语言氛围找歌 |
| `POST /api/dj/set/generate` | `router.py` + `app/modules/dj_set/` | 生成候选 DJ set |
| `POST /api/dj/transition/preview` | `router.py` | 预览两首歌的切歌策略 |

### 4.2 舞种 + 时长选歌的真实方案

手机端点击 DJ Control 里的“舞种 + 时长”后，前端调用：

```text
mobile/lib/src/api_client.dart
  -> djPickByStyle()
  -> POST /api/dj/styles/pick
```

后端入口：

```text
app/modules/dj_control/router.py
  -> pick_by_style_endpoint()
```

真实排序逻辑：

```text
router.py
  -> dance_style.pick_songs_for_duration()
  -> dance_style.rank_songs_for_style()
  -> dance_style.style_pick_evidence()
```

`style_pick_evidence()` 的读取顺序：

1. 优先读取歌曲已持久化的 `genre_profile.style_evidence_v1[style]`。
2. 同时读取 `dance_style_scores[style]` 作为快速分数。
3. 如果没有持久化证据，降级到本地 `score_song_multisource()`。
4. `/styles/pick` 不会实时调用 Discogs / Last.fm / MusicBrainz，避免 UI 等待外部网络。

最终 `ScoredSong` 返回给手机端：

- `score`
- `final_pick_score`
- `confidence`
- `score_breakdown`
- `matched_labels`
- `recommendation_reason`
- `style_evidence_status`
- `external_sources`
- `reason`

如果要改“舞种选择为什么推荐这首歌”，优先看：

- `app/modules/dj_control/dance_style.py`
- `app/modules/dj_control/style_taxonomy.py`
- `app/modules/dj_control/style_reference_profiles.py`
- `app/modules/library/external_metadata/scorer.py`

如果要改“手机端怎么展示推荐理由”，看：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/api_client.dart`

### 4.3 多源风格证据方案

新增外部风格证据包：

```text
app/modules/library/external_metadata/
  clients.py
  musicbrainz_client.py
  lastfm_client.py
  discogs_client.py
  normalizer.py
  scorer.py
  service.py
  schemas.py
```

真实流程：

```text
歌曲分析完成
  -> genre_classifier / 本地音频特征
  -> external_metadata.service.enrich_song_external_metadata()
  -> MusicBrainz / Last.fm / Discogs 获取标签
  -> normalizer 归一化标签
  -> scorer 计算每个舞种的 external_platform_score
  -> 与 local_fingerprint / manual / tunable 融合
  -> 写回 LibrarySong.genre_profile.style_evidence_v1
  -> 写回 LibrarySong.dance_style_scores
```

触发位置：

| 触发方式 | 文件 |
|---|---|
| 后台分析任务完成后自动刷新 | `app/modules/library/background_tasks.py` |
| 手动分析接口完成后刷新 | `app/modules/library/router.py` |
| 手动刷新单曲证据 | `POST /api/library/songs/{song_id}/refresh-style-evidence` |
| 批量回填 | `scripts/backfill_style_evidence.py` |

环境变量：

| 变量 | 作用 |
|---|---|
| `ENABLE_EXTERNAL_STYLE_ENRICHMENT` | 是否启用外部证据 |
| `LASTFM_API_KEY` | Last.fm 标签 |
| `DISCOGS_USER_TOKEN` | Discogs release genre/style |
| `MUSICBRAINZ_APP_NAME` | MusicBrainz User-Agent |
| `MUSICBRAINZ_APP_VERSION` | MusicBrainz User-Agent |
| `MUSICBRAINZ_CONTACT_EMAIL` | MusicBrainz 联系邮箱 |
| `STYLE_SCORE_WEIGHT_EXTERNAL` | 外部标签权重 |
| `STYLE_SCORE_WEIGHT_LOCAL` | 本地音频指纹权重 |
| `STYLE_SCORE_WEIGHT_MANUAL` | 人工反馈权重 |
| `STYLE_SCORE_WEIGHT_TUNABLE` | 可调混音可用性权重 |
| `STYLE_EXTERNAL_WEIGHT_DISCOGS` | Discogs 在外部分中的权重 |
| `STYLE_EXTERNAL_WEIGHT_LASTFM` | Last.fm 在外部分中的权重 |
| `STYLE_EXTERNAL_WEIGHT_MUSICBRAINZ` | MusicBrainz 在外部分中的权重 |

当前规则：

- MusicBrainz 没有 key 也能用，但建议配置标准 User-Agent。
- Last.fm 没有 `LASTFM_API_KEY` 时 source 状态为 `disabled`。
- Discogs 没有 `DISCOGS_USER_TOKEN` 时 source 状态为 `disabled`。
- 外部请求失败不会阻塞歌曲进入曲库，会写入 error/miss/disabled 状态。

### 4.4 能量排序

主要文件：

- `app/modules/dj_control/energy_hiphop.py`
- `app/modules/dj_control/sequencer.py`
- `mobile/lib/src/dj_control_page.dart`

当前能量排序不是 LLM 排序，主要依赖：

- 本地音频 `energy`
- `compute_dance_energy()` 的街舞能量拆分
- BPM、kick、snare、groove、low-mid、vocal urgency 等因素
- `sequencer.PRESETS` 中的场景曲线

如果 UI 还显示“AI 排序”，那是手机端文案没有改，不代表后端仍然走 AI。修改位置：

- `mobile/lib/src/dj_control_page.dart`

### 4.5 自动混音规则

主要文件：

- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/transition_strategy.py`

当前混音分两层：

1. 常规规则层：`mixer_rules.py`
2. 跨风格策略层：`transition_strategy.py`

常规 analyzed transitions 包括：

| rule | 场景 | 技术动作 |
|---|---|---|
| `harmonic_blend` | BPM 和调性接近 | 16 bar 长混 + EQ |
| `eq_swap_4bar` | BPM 接近、key 不完全兼容 | 4 bar 低频互换 |
| `filter_sweep_high` | 风格不同但 BPM 接近 | 高通 sweep |
| `drop_swap` | drop-driven | 在 downbeat/drop 点切 |
| `echo_tail` | 想让上一首散掉 | 1/4 echo tail |
| `loop_roll` | 结尾平淡 | beat roll |
| `spin_back` | BPM 跨度大 | reverse decel |
| `drum_only_bridge` | 用鼓桥接 | prev 只留 drums |
| `key_lift` | 情绪上扬 | pitch ride |
| `reverb_throw` | vocal hook 退场 | reverb tail |
| `back_to_back_drop` | EDM/drop 对接 | smash cut + kick roll |

跨风格策略包括：

| strategy | 适用场景 | 技术动作 |
|---|---|---|
| `echo_out_hard_drop` | BPM/key/genre 差异极大 | 低频衰减、tempo echo、impact、B 强拍进 |
| `percussion_bridge` | 风格不同但要保持舞动 | A 只留 drums，B drums+bass 渐入 |
| `stem_strip_rebuild` | 人声或编曲冲突明显 | A vocals/other/bass 逐层退，B drums/bass/other/vocals 逐层进 |
| `auto_bpm_ramp` | BPM 差 8%-12% | A tempo ramp 到 B，隐藏 vocal/harmonics |
| `half_time_double_time_pivot` | 70/140、85/170 等倍速关系 | half-time / double-time 鼓点 pivot |
| `neutral_fx_bridge` | 没 stems 且 BPM/key 不兼容 | noise sweep / echo / impact 中性桥 |
| `breakdown_reset` | 能量差明显 | breakdown / air gap / reset |
| `impact_slam_cut` | 风险高或紧急切 | 极短重击切 |

`TransitionContext` 计算：

- `bpmDiff`
- `bpmDiffRatio`
- `tempoRelation`
- `keyDistance`
- `genreDistance`
- `energyDiff`
- `vocalConflictRisk`
- `phraseBarsAvailable`
- `stemsAvailable`

如果要修改“什么情况下选哪种切法”，看：

- `app/modules/dj_control/transition_strategy.py` 的 `select_cross_style_strategy()`
- `app/modules/dj_control/mixer_rules.py` 的 `pick_rule()` 和 `build_transition_spec()`

如果要修改“每种切法实际时间线”，看：

- `transition_strategy.py` 中 `_strategy_*()` 函数的 `timeline/stem_curves/eq_curves/fx`
- `mixer_rules.py` 中 `_STEM_CURVES`

---

## 5. Flutter 手机端

主要文件：

- `mobile/lib/main.dart`
- `mobile/lib/src/app.dart`
- `mobile/lib/src/api_client.dart`
- `mobile/lib/src/edge_agent_client.dart`
- `mobile/lib/src/sync_worker_client.dart`
- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/library/song_detail_page.dart`
- `mobile/lib/src/import/playlist_import_page.dart`

### 5.1 手机端 API 客户端

`api_client.dart` 调后端：

- 登录注册
- 曲库列表
- 导入音乐
- analyze/stems
- manifest
- DJ Control
- DJ set generate

`edge_agent_client.dart` 调 RK edge-agent：

- `/state`
- `/play`
- `/pause`
- `/resume`
- `/seek`
- `/xfade`
- `/prefetch`
- `/prewarm_beatmatch`
- `/beat_reinforce`
- `/trigger`

`sync_worker_client.dart` 调 RK sync-worker：

- `/sync`
- `/status`
- `/cache/{song_id}`
- `/health`

### 5.2 DJ Control 页面流程

文件：

- `mobile/lib/src/dj_control_page.dart`

当前 4 步：

1. 选歌：导入歌单 / vibe search / 舞种 + 时长。
2. 排歌：按能量预设或后端 set 模板排序。
3. 混音：展示 transition rules、BPM 差、策略、开始播放。
4. 实时操作：播放中自动 xfade、手动 cut、FX pad、状态轮询。

启动现场混音时的大致流程：

```text
_startLiveMix()
  -> _ensureRkCache(firstSong)
      -> getSongManifest()
      -> syncWorker.startSync()
      -> syncWorker.syncAndWait()
  -> edgeClient.prefetch(firstSong)
  -> edgeClient.play()
  -> _warmAllRemainingTracks()
  -> _maybeAutoXfade() 循环判断
```

自动切歌时：

```text
_maybeAutoXfade()
  -> 到当前歌还剩约 30s 时预取下一首
  -> djPlanTransition(prev,next)
  -> edgeClient.prewarmBeatmatch()
  -> edgeClient.beatReinforce()
  -> edgeClient.xfade()
  -> 更新 liveIdx / cooldown / activeRule
```

防止连切的保护：

- `_xfadeInFlight`
- `_lastXfadeAt`
- `_lastXfadeSec`
- `_lastXfadeToSongId`
- `_lastXfadeFromIdx`

如果出现“第二首切第三首 RK409”，优先看：

1. `_ensureRkCache()`
2. `_warmNextTrack()`
3. `_warmAllRemainingTracks()`
4. `SyncWorkerClient.cacheExists()`
5. RK sync-worker 日志
6. `GET /api/manifest/song/{song_id}` 是否有 original/stems

---

## 6. RK3588 播放端

主要目录：

```text
cypher-integration/rk3588-edge/
  edge-agent/
  audio-engine/
  sync-worker/
  input-daemon/
  deploy/
```

### 6.1 RK 服务

| 服务 | systemd 名称 | 作用 |
|---|---|---|
| edge-agent | `cypher-edge-agent` | 对手机暴露播放 API |
| audio-engine | `cypher-audio-engine` | 实时音频播放和混音 |
| sync-worker | `cypher-sync-worker` | 从后端 manifest 下载原曲/stems |
| input-daemon | `cypher-input-daemon` | 物理按键/HID 输入 |

### 6.2 edge-agent

主要文件：

- `cypher-integration/rk3588-edge/edge-agent/main.py`
- `cypher-integration/rk3588-edge/edge-agent/edge_agent/audio_client.py`
- `cypher-integration/rk3588-edge/edge-agent/edge_agent/transition_api.py`
- `cypher-integration/rk3588-edge/edge-agent/edge_agent/state.py`
- `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py`

典型接口：

- `GET /health`
- `GET /state`
- `POST /play`
- `POST /pause`
- `POST /resume`
- `POST /seek`
- `POST /xfade`
- `POST /prefetch`
- `POST /prewarm_beatmatch`
- `POST /beat_reinforce`
- `POST /trigger`

### 6.3 sync-worker

主要文件：

- `cypher-integration/rk3588-edge/sync-worker/main.py`

职责：

- 接收 manifest。
- 下载 `files.original`。
- 下载 `files.stems.vocals/drums/bass/other`。
- 写入 RK 本地 cache，通常是类似：

```text
/home/cat/cypher/cache/{song_id}/original.wav
/home/cat/cypher/cache/{song_id}/vocals.wav
/home/cat/cypher/cache/{song_id}/drums.wav
/home/cat/cypher/cache/{song_id}/bass.wav
/home/cat/cypher/cache/{song_id}/other.wav
```

如果想实现“第一首开始播放前 30s 拉取第一首，拉完继续第二首，同步播放时拉取后续 stems”，主要改：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/sync_worker_client.dart`
- 必要时改 `cypher-integration/rk3588-edge/sync-worker/main.py`

### 6.4 audio-engine

主要文件：

- `cypher-integration/rk3588-edge/audio-engine/main.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`
- `cypher-integration/rk3588-edge/audio-engine/dsp.py`
- `cypher-integration/rk3588-edge/audio-engine/mix_plan.py`
- `cypher-integration/rk3588-edge/audio-engine/transition_planner.py`
- `cypher-integration/rk3588-edge/audio-engine/strategy_selector.py`
- `cypher-integration/rk3588-edge/audio-engine/socket_server.py`

职责：

- 载入本地缓存音频。
- 执行 deck A / deck B 播放。
- 执行 xfade。
- 执行 stem envelope。
- 执行 limiter / EQ / FX。
- 处理预解码缓存。

如果要改真实“声音怎么混”，优先看这里，不是只改后端 spec。

---

## 7. 自动混音技术方案

当前系统的自动混音分成 7 层：

### 7.1 选规则

文件：

- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/transition_strategy.py`

规则输入：

- BPM 差异
- half-time / double-time
- Camelot 调性距离
- genre distance
- energy 差异
- vocalConflictRisk
- phraseBarsAvailable
- stemsAvailable

输出：

- `rule_key`
- `duration_sec`
- `start_in_prev`
- `start_in_next`
- `eq_curve`
- `stem_curves`
- `fx`
- `timeline`
- `rk_style`
- `transition_context`

### 7.2 找切点

文件：

- `app/modules/library/analysis.py`
- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/cut_strategy.py`

使用数据：

- `phrase_map`
- `downbeats`
- `cue_points`
- `transition_windows`
- `intro_clean_score`
- `outro_clean_score`

目标：

- A 从 outro / break / phrase end 出。
- B 从 first verse / drop / clean intro 进。
- fade duration 对齐到 4/8/16 小节。

### 7.3 BPM 与拍位

后端负责判断：

- 是否 close tempo
- 是否 half/double time
- 是否需要 `auto_bpm_ramp`
- 是否不适合强行 beatmatch

RK 负责执行：

- `/prewarm_beatmatch`
- `/xfade`
- audio-engine 内部缓存和拉伸方案

相关文件：

- `mobile/lib/src/edge_agent_client.dart`
- `mobile/lib/src/dj_control_page.dart`
- `cypher-integration/rk3588-edge/audio-engine/`

### 7.4 响度

分析字段：

- `loudness_profile`
- `replayGainDb`

manifest 输出：

- `replayGainDb`

主要文件：

- `app/modules/library/analysis.py`
- `app/modules/manifest/__init__.py`

### 7.5 节拍强化

手机端在 xfade 前会根据 transition plan 触发：

- `edgeClient.beatReinforce()`

相关文件：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/edge_agent_client.dart`
- `cypher-integration/rk3588-edge/edge-agent/`
- `cypher-integration/rk3588-edge/audio-engine/`

用途：

- 鼓弱的一侧叠加 snare/clap 或 beat reinforce。
- 让鼓密度在过渡里更连续。

### 7.6 分轨混音

后端输出：

- `stem_curves`

典型曲线：

- `linear_out`
- `linear_in`
- `out_at_break`
- `in_at_break`
- `in_late`
- `hold`
- `hold_then_out`
- `out_early`
- `in_very_late`

RK 执行：

- vocals / drums / bass / other 分别乘 envelope 后求和。

如果 stems 不完整：

- 后端仍能生成普通 xfade。
- RK / 手机端应降级到 original crossfade 或 hard cut。

### 7.7 limiter / 防爆音

真实 limiter 在 RK audio-engine 层处理。后端只描述策略，不应该假设后端能防止实时爆音。

修改入口：

- `cypher-integration/rk3588-edge/audio-engine/dsp.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`

---

## 8. 歌曲风格分析与舞种选择

### 8.1 当前标签来源

| 来源 | 是否实时 | 写入位置 | 用途 |
|---|---|---|---|
| 本地音频分析 | 分析时 | `LibrarySong` 多字段 | BPM、energy、groove、stem、transition |
| 本地 genre classifier | 分析时 | `genre_profile` | 初始 genre |
| MusicBrainz | 分析/刷新/回填时 | `genre_profile.sources.musicbrainz` | 外部标签证据 |
| Last.fm | 分析/刷新/回填时 | `genre_profile.sources.lastfm` | 外部标签证据 |
| Discogs | 分析/刷新/回填时 | `genre_profile.sources.discogs` | 外部 genre/style |
| 人工反馈 | 后续可扩展 | `genre_profile.style_feedback` | 强制修正舞种 |

### 8.2 `style_evidence_v1` 结构

保存在：

```text
LibrarySong.genre_profile["style_evidence_v1"][style]
```

每个 style 大致包含：

- `external_platform_score`
- `local_fingerprint_score`
- `manual_style_score`
- `tunable_adjustment_score`
- `final_score`
- `confidence`
- `status`
- `weights`
- `external_source_scores`
- `local_version`
- `local_breakdown`
- `reason`

### 8.3 推荐分融合

文件：

- `app/modules/library/external_metadata/scorer.py`
- `app/modules/library/external_metadata/service.py`
- `app/modules/dj_control/dance_style.py`

默认融合：

```text
final_score =
  external_platform_score * STYLE_SCORE_WEIGHT_EXTERNAL
  + local_fingerprint_score * STYLE_SCORE_WEIGHT_LOCAL
  + manual_style_score * STYLE_SCORE_WEIGHT_MANUAL
  + tunable_adjustment_score * STYLE_SCORE_WEIGHT_TUNABLE
```

外部分：

```text
external_platform_score =
  Discogs * STYLE_EXTERNAL_WEIGHT_DISCOGS
  + Last.fm * STYLE_EXTERNAL_WEIGHT_LASTFM
  + MusicBrainz * STYLE_EXTERNAL_WEIGHT_MUSICBRAINZ
```

如果某一路数据缺失，会对可用权重重新归一，不会直接把缺失源当 0 惩罚。

---

## 9. 部署说明

### 9.1 本地开发

后端常用检查：

```powershell
python -m compileall app
pytest app/tests/test_external_metadata_normalizer.py app/tests/test_external_metadata_scorer.py app/tests/test_style_score_fusion.py
pytest app/tests/test_style_enrichment_pipeline.py app/tests/test_dj_style_pick_multisource.py
```

手机端：

```powershell
cd mobile
flutter analyze --no-fatal-infos --no-fatal-warnings
flutter build apk --debug
```

安装到 USB 手机：

```powershell
C:\Android\platform-tools\adb.exe install -r mobile\build\app\outputs\flutter-apk\app-debug.apk
```

### 9.2 Jetson / 后端部署

当前部署常见路径：

```text
/home/mark/harbeat
```

常用操作：

```bash
cd /home/mark/harbeat
python -m compileall app
pytest app/tests/test_dj_style_pick_multisource.py
sudo systemctl restart harbeat-api
systemctl is-active harbeat-api
curl http://127.0.0.1:8000/api/dj/styles
```

外部风格证据 key 在 Jetson `.env` 配置。配置后需要：

```bash
sudo systemctl restart harbeat-api
python scripts/backfill_style_evidence.py --limit 50 --force
```

### 9.3 RK3588 部署

目录：

```text
cypher-integration/rk3588-edge/deploy/
```

常用检查：

```bash
systemctl is-active cypher-edge-agent
systemctl is-active cypher-audio-engine
systemctl is-active cypher-sync-worker
curl http://127.0.0.1:9000/health
```

手机连接 RK 的关键：

- edge-agent 通常是 `http://<rk-ip>:9000`
- sync-worker 通常从 edge-agent 地址推导到 `:9100`
- 手机和 RK 必须在同一可达网络，或者通过 Tailscale / 热点可达。

---

## 10. 测试索引

### 10.1 后端测试

| 测试 | 作用 |
|---|---|
| `app/tests/test_external_metadata_normalizer.py` | 标签归一化 |
| `app/tests/test_external_metadata_scorer.py` | 外部标签评分 |
| `app/tests/test_style_score_fusion.py` | 多源权重融合 |
| `app/tests/test_style_enrichment_pipeline.py` | 单曲风格证据刷新链路 |
| `app/tests/test_dj_style_pick_multisource.py` | `/styles/pick` 多源返回 |
| `app/tests/test_backfill_style_evidence.py` | 批量回填脚本 |
| `app/tests/test_external_metadata_live.py` | 真实 MusicBrainz / Last.fm / Discogs smoke test |
| `app/tests/test_transition_strategy.py` | 跨风格 transition selector |
| `app/tests/test_transition_planner.py` | 传统 transition planner |
| `app/tests/test_analysis_manifest.py` | manifest 与分析数据输出 |

真实外部 API 测试需要：

```bash
RUN_LIVE_EXTERNAL_API_TESTS=1 pytest app/tests/test_external_metadata_live.py
```

没有 Last.fm / Discogs key 时，对应测试会 skip。

### 10.2 RK 测试

RK 端测试位于：

```text
cypher-integration/rk3588-edge/tests/
```

重点：

- `test_sync_worker.py`
- `test_transition_api.py`
- `test_engine_envelopes.py`
- `test_edge_state.py`
- `test_strategy_selector.py`

### 10.3 手机端测试

基础：

```powershell
cd mobile
flutter analyze --no-fatal-infos --no-fatal-warnings
flutter build apk --debug
```

真机：

```powershell
C:\Android\platform-tools\adb.exe devices
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
C:\Android\platform-tools\adb.exe logcat
```

---

## 11. 常见问题定位

### 11.1 手机曲库拉不下来

检查：

1. 手机是否能访问后端 base URL。
2. token 是否过期。
3. `GET /api/library/songs` 是否返回 200。
4. 后端 `harbeat-api` 是否 active。
5. 后端日志是否有 DB 错误。

相关文件：

- `mobile/lib/src/api_client.dart`
- `app/modules/library/router.py`
- `app/modules/auth/dependencies.py`

### 11.2 登录报 `users.is_active does not exist`

说明数据库 schema 和 SQLAlchemy model 不一致。处理方向：

1. 检查 `app/modules/users/models.py`。
2. 检查 PostgreSQL `users` 表字段。
3. 补 migration 或直接 ALTER TABLE。

### 11.3 RK 409 / 播放失败

常见原因：

- sync-worker 没把 original 下载到 cache。
- manifest 没有 `files.original`。
- `PUBLIC_ASSET_BASE_URL` RK 不可访问。
- 手机提前触发 xfade，下一首还没同步完。
- RK cache 里 song_id 与后端 song_id 不一致。

相关文件：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/sync_worker_client.dart`
- `app/modules/manifest/__init__.py`
- `cypher-integration/rk3588-edge/sync-worker/main.py`

### 11.4 舞种推荐不准

先看这几个数据：

1. `LibrarySong.genre_profile.sources`
2. `LibrarySong.genre_profile.style_evidence_v1`
3. `LibrarySong.dance_style_scores`
4. `/api/dj/styles/pick` 返回的 `score_breakdown`
5. 手机 UI 展示的 `external_sources` 和 `reason`

修改方向：

- 标签归一化不准：`external_metadata/normalizer.py`
- 标签到舞种映射不准：`style_taxonomy.py`
- 外部源权重不合适：`.env` 和 `external_metadata/scorer.py`
- 本地 fingerprint 不合适：`dance_style.py`
- UI 解释不清楚：`mobile/lib/src/dj_control_page.dart`

### 11.5 接歌听起来人声太早

重点检查：

- `vocal_events`
- `stem_activity`
- `transition_windows`
- `transition_context.vocalConflictRisk`
- `stem_curves.next.vocals`

相关文件：

- `app/modules/library/analysis.py`
- `app/modules/dj_control/transition_strategy.py`
- `app/modules/dj_control/mixer_rules.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`

### 11.6 低频糊

重点检查：

- `bass_risk_windows`
- `stem_curves.prev.bass`
- `stem_curves.next.bass`
- 是否使用 `out_at_break` / `in_at_break`
- stems 是否完整

相关文件：

- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/transition_strategy.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`

---

## 12. 按需求找文件

| 想改的功能 | 优先文件 |
|---|---|
| 增加一个舞种 | `app/modules/dj_control/dance_style.py`, `style_taxonomy.py`, `style_reference_profiles.py`, `mobile/lib/src/dj_control_page.dart` |
| 改舞种选歌排序 | `app/modules/dj_control/dance_style.py` |
| 接入新的外部标签平台 | `app/modules/library/external_metadata/`, `metadata_adapters/`, `.env.example` |
| 改 Discogs / Last.fm / MusicBrainz 权重 | `app/shared/config.py`, `.env`, `external_metadata/scorer.py` |
| 分析后自动刷新风格证据 | `app/modules/library/background_tasks.py` |
| 手动刷新风格证据接口 | `app/modules/library/router.py` |
| 批量回填风格证据 | `scripts/backfill_style_evidence.py` |
| 改能量排序 | `app/modules/dj_control/energy_hiphop.py`, `sequencer.py` |
| 改自动切歌规则 | `app/modules/dj_control/mixer_rules.py`, `transition_strategy.py` |
| 改跨风格方案选择 | `app/modules/dj_control/transition_strategy.py` |
| 改实际 stem xfade 声音 | `cypher-integration/rk3588-edge/audio-engine/` |
| 改 RK 播放 API | `cypher-integration/rk3588-edge/edge-agent/` |
| 改 RK 同步下载 | `cypher-integration/rk3588-edge/sync-worker/main.py` |
| 改 manifest 输出 | `app/modules/manifest/__init__.py` |
| 改手机 DJ Control UI | `mobile/lib/src/dj_control_page.dart` |
| 改手机后端 API 调用 | `mobile/lib/src/api_client.dart` |
| 改手机 RK API 调用 | `mobile/lib/src/edge_agent_client.dart`, `sync_worker_client.dart` |

---

## 13. 当前已知边界

- 外部风格证据依赖平台 metadata，标签可能不稳定，必须保留本地音频 fingerprint 兜底。
- `/api/dj/styles/pick` 不实时请求外部平台，必须先分析、刷新或 backfill。
- Stems 缺失时只能降级到普通 crossfade / cut，不能假设每首歌都有 4 stems。
- RK 的实时混音效果最终由 audio-engine 决定；后端 spec 只是计划，不是声音本身。
- `PUBLIC_ASSET_BASE_URL` 是 RK 同步链路的关键配置，部署变化后必须验证。
- 手机端自动 xfade 有 cooldown 和 in-flight 保护，修改时要避免恢复连续触发问题。
- 文档中的部署地址和服务名以当前实测环境为准，换网络或换机器后需要重新验证。
