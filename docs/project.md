# HarBeat 项目交接文档

版本日期：2026-06-09
适用对象：后续开发者、部署维护人员、接手项目的 AI Agent
覆盖范围：Jetson/FastAPI 后端、RK3588 播放盒、Flutter 手机 App、DJ Control、候选池预加载、风格/能量切歌、调性/EQ 混音、部署与排障。

> 安全边界：本文不写明文密码、JWT、`.env` 或 `cypher.env` 的真实值。连接凭据请从项目负责人处获取；GitHub 只保存源码、部署模板和文档。

---

## 1. 项目一句话

HarBeat 是面向街舞练习、cypher、battle warm-up 和小型 party 的自动 DJ 系统。手机 App 负责登录、选歌、DJ Control 和实时操作；Jetson/FastAPI 后端负责曲库、分析、排序、候选池和转场计划；RK3588 负责真实现场播放、缓存、解码、自动接歌、EQ 混音和硬件按键。

```text
手机 App
  -> Jetson 公网 API: 登录、曲库、DJ Control 选歌/排序/切歌计划
  -> RK3588 LAN API: 播放、xfade、缓存校验、状态轮询、FX

Jetson/FastAPI
  -> PostgreSQL/本地音频文件
  -> 生成 manifest、live pool、DJ set、transition plan

RK3588
  -> edge-agent :9000 接收手机控制
  -> sync-worker :9100 从 Jetson 拉取音频
  -> audio-engine Unix socket 执行播放和混音
  -> input-daemon 监听九键控制器
```

正式使用时手机不依赖电脑转发。电脑只用于开发、ADB 安装、日志和临时测试。

---

## 2. 当前真实部署

### Jetson / FastAPI 后端

```text
公网 API: http://8.136.120.255
Tailscale: 100.87.142.21
SSH: root@100.87.142.21
真实运行目录: /home/mark/harbeat
Python venv: /home/mark/venvs/harbeat
systemd: harbeat-api.service
uvicorn: 0.0.0.0:8000
nginx: :80 -> :8000
PUBLIC_ASSET_BASE_URL=http://8.136.120.255
```

常用命令：

```bash
ssh root@100.87.142.21
systemctl status harbeat-api --no-pager
journalctl -u harbeat-api -n 160 --no-pager
systemctl restart harbeat-api
curl -i http://127.0.0.1:8000/api/health
curl -i http://8.136.120.255/api/auth/me
```

`/api/auth/me` 未带 token 返回 `401` 是正常的，说明公网 API 可达。

### RK3588 / LubanCat 播放盒

```text
LAN IP: 192.168.43.7
hostname: lubancat
SSH: cat@192.168.43.7
真实运行目录: /home/cat/cypher
Python venv: /home/cat/venvs/edge
edge-agent REST: http://192.168.43.7:9000
sync-worker REST: http://192.168.43.7:9100
audio-engine socket: /tmp/cypher-audio.sock
```

常用命令：

```bash
ssh cat@192.168.43.7
hostname -I
systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9100/status
journalctl -u cypher-edge-agent -n 120 --no-pager
journalctl -u cypher-audio-engine -n 120 --no-pager
journalctl -u cypher-sync-worker -n 120 --no-pager
```

重启：

```bash
sudo systemctl restart cypher-edge-agent
sudo systemctl restart cypher-audio-engine
sudo systemctl restart cypher-sync-worker
sudo systemctl restart cypher-input-daemon
```

RK 当前服务形态：

```text
cypher-edge-agent:
  WorkingDirectory=/home/cat/cypher/edge-agent
  ExecStart=/home/cat/venvs/edge/bin/python /home/cat/cypher/edge-agent/run.py

cypher-audio-engine:
  WorkingDirectory=/home/cat/cypher/audio-engine
  ExecStart=/home/cat/venvs/edge/bin/python /home/cat/cypher/audio-engine/main.py
  XDG_RUNTIME_DIR=/run/user/1000
  PULSE_RUNTIME_PATH=/run/user/1000/pulse

cypher-sync-worker:
  WorkingDirectory=/home/cat/cypher/sync-worker
  ExecStart=/home/cat/venvs/edge/bin/uvicorn main:app --host 0.0.0.0 --port 9100

cypher-input-daemon:
  WorkingDirectory=/home/cat/cypher/input-daemon
  ExecStart=/home/cat/venvs/edge/bin/python /home/cat/cypher/input-daemon/main.py
```

### 手机 / Flutter App

```text
Flutter: D:\flutter_install\flutter
ADB: C:\Android\platform-tools\adb.exe
默认 Jetson API: http://8.136.120.255
默认 RK API: http://192.168.43.7:9000
App package: com.example.mobile
```

常用命令：

```powershell
C:\Android\platform-tools\adb.exe devices
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat build apk --debug
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
C:\Android\platform-tools\adb.exe logcat | Select-String -Pattern "flutter|HarBeat|Dio|http|edge|sync"
```

App 地址配置入口：

```text
mobile/lib/src/app.dart
  defaultBaseUrl = http://8.136.120.255
  defaultRkBaseUrl = http://192.168.43.7:9000

mobile/lib/src/home_page.dart
  设置弹窗可修改 API URL 和 RK URL，并保存到 SharedPreferences。
```

换网络后通常只需要确认 RK 的 LAN IP 是否变化；Jetson 公网 API 不随本地热点变化。

---

## 3. 代码目录地图

```text
app/
  FastAPI 后端，部署到 Jetson 的 /home/mark/harbeat/app

mobile/
  Flutter 手机 App，部署到手机

cypher-integration/rk3588-edge/
  RK3588 播放盒源码，部署到 /home/cat/cypher

docs/
  规格、交接、修复记录

deploy/
  Jetson/服务器部署脚本和 cloud gateway 辅助代码

jetson/
  Jetson 辅助脚本和历史补丁资料
```

重要文件：

```text
app/main.py
  FastAPI app、CORS、路由聚合、异常处理、可选启动分析。

app/modules/router.py
  所有 /api/* 模块路由挂载。

mobile/lib/src/app.dart
  手机 App 启动、登录态恢复、API/RK 地址持久化。

mobile/lib/src/api_client.dart
  手机到 Jetson 的 HTTP client。

mobile/lib/src/edge_agent_client.dart
  手机到 RK edge-agent :9000 的 HTTP client。

mobile/lib/src/sync_worker_client.dart
  手机到 RK sync-worker :9100 的 HTTP client。

mobile/lib/src/dj_control_page.dart
  DJ Control 主要 UI 和业务编排。

cypher-integration/rk3588-edge/edge-agent/main.py
  RK REST API，转发播放命令给 audio-engine。

cypher-integration/rk3588-edge/sync-worker/main.py
  RK 缓存下载服务。

cypher-integration/rk3588-edge/audio-engine/engine.py
  真正播放、自动接歌、xfade、EQ band mix、limiter。

cypher-integration/rk3588-edge/input-daemon/main.py
  USB 九键控制器和音量旋钮。
```

---

## 4. API 总入口

FastAPI 所有业务入口由 `app/modules/router.py` 挂载：

```text
/api/health
/api/assets/*
/api/auth/*
/api/stream/*
/api/library/*
/api/manifest/*
/api/music/*
/api/users/*
/api/playlists/*
/api/profiles/*
/api/recommendations/*
/api/sessions/*
/api/fangpi/*
/api/dj/*
```

后端统一响应格式通常是：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

手机端 `HarBeatApiClient._request()` 会自动解包 `payload["data"]`，所以 Dart 方法拿到的是 `data` 内层对象。

---

## 5. 核心功能与接口调用

### 认证与登录

```text
手机:
  mobile/lib/src/app.dart
  mobile/lib/src/api_client.dart

Jetson API:
  POST /api/auth/login
  POST /api/auth/register
  GET  /api/auth/me
  POST /api/auth/refresh
  POST /api/auth/logout

Jetson 代码:
  app/modules/auth/router.py
  app/modules/auth/service.py
  app/modules/auth/dependencies.py
```

登录成功后 App 把 `access_token` 存入 `SharedPreferences`，后续请求通过 `Authorization: Bearer <token>` 访问 Jetson。

### 曲库和音频分析

```text
手机:
  HarBeatApiClient.getLibrarySongs()
  HarBeatApiClient.searchLibrarySongs()
  HarBeatApiClient.uploadSong()
  HarBeatApiClient.analyzeSong()
  HarBeatApiClient.separateStems()

Jetson API:
  GET    /api/library/songs
  GET    /api/library/songs/search?q=
  GET    /api/library/songs/{song_id}
  POST   /api/library/upload
  POST   /api/library/songs/{song_id}/analyze
  POST   /api/library/songs/{song_id}/refresh-style-evidence
  POST   /api/library/songs/{song_id}/separate-stems
  DELETE /api/library/songs/{song_id}

Jetson 代码:
  app/modules/library/router.py
  app/modules/library/service.py
  app/modules/library/analysis.py
  app/modules/library/background_tasks.py
  app/modules/library/models.py
  app/modules/library/external_metadata/*
  app/modules/library/metadata_adapters/*
```

分析会写入 BPM、key/camelot key、能量、beat/downbeat、cue、phrase、style evidence、DJ fingerprint 等字段。DJ Control 的风格、能量、调性混音都依赖这些字段。

### Manifest 与音频资源

```text
手机:
  HarBeatApiClient.getSongManifest()
  SyncWorkerClient.startSync()

Jetson API:
  GET /api/manifest/song/{song_id}
  GET /api/manifest/playlist/{playlist_id}
  GET /api/assets/{asset_path}
  GET /api/stream/{song_id}
  GET /api/stream/{song_id}/stem/{stem_name}

Jetson 代码:
  app/modules/manifest/router.py
  app/modules/manifest/__init__.py
  app/modules/assets/router.py
  app/modules/stream/router.py
```

manifest 是 RK 下载音频的蓝图，包含每首歌的 `song_id`、`files.original.url`、格式、size、sha256。`PUBLIC_ASSET_BASE_URL` 必须指向手机/RK 可访问的公网地址，否则 RK 会拿到内网 URL 导致下载失败。

### 歌单导入和外部搜索

```text
手机:
  HarBeatApiClient.parseExternalPlaylist()
  HarBeatApiClient.batchSearchExternal()
  HarBeatApiClient.downloadFangpiCandidate()
  HarBeatApiClient.createPlaylist()
  HarBeatApiClient.addSongsToPlaylist()

Jetson API:
  POST /api/fangpi/search
  POST /api/fangpi/download
  POST /api/fangpi/parse-playlist
  POST /api/fangpi/batch-search
  POST /api/playlists/create
  POST /api/playlists/{playlist_id}/add-songs

Jetson 代码:
  app/modules/fangpi/router.py
  app/modules/fangpi/service.py
  app/modules/fangpi/playlist_parser.py
  app/modules/playlists/router.py
  app/modules/playlists/service.py
```

### 推荐、Vibe 和练习列表

```text
手机:
  HarBeatApiClient.vibeSearch()
  HarBeatApiClient.importFromVibe()
  HarBeatApiClient.discoverSongs()
  HarBeatApiClient.generatePracticeList()

Jetson API:
  POST /api/recommendations/vibe-search
  POST /api/recommendations/import-from-vibe
  POST /api/recommendations/discover
  POST /api/sessions/generate-practice-list

Jetson 代码:
  app/modules/recommendations/*
  app/modules/sessions/router.py
  app/modules/sessions/playlist_engine.py
```

---

## 6. DJ Control 正常流程

DJ Control 的主流程在 `mobile/lib/src/dj_control_page.dart`，当前是四步：

```text
1. 选歌
   手动选择曲库歌曲、导入歌单、Vibe 搜索、或按舞种+时长选歌。

2. 排序
   调用 Jetson 进行 sequence 或 DJ set 生成，得到实际播放顺序。

3. 开始前准备
   App 调 /api/dj/live/pool/prepare 获取主队列、能量备选池、风格备选池。
   App 汇总所有候选 song_id。
   App 调 RK sync-worker 下载缺失音频。
   App 调 RK edge-agent /cache/validate 强制解码校验。
   App 预生成相邻歌曲的 transition plan。
   全部通过后才调用 RK /play 播放第一首。

4. 实时操作
   自动接歌：接近转场点时使用已准备好的 transition plan 调 RK /xfade。
   能量切歌：用户选择目标能量段，Jetson 从队列/备选池/曲库扩展中选候选。
   风格切歌：用户选择目标舞种，Jetson 从队列/风格备选池/曲库扩展中选候选。
   FX：手机直接触发 RK /trigger 或播放 Jetson 渲染的 FX wav。
```

关键手机方法：

```text
_runSequence()
  -> POST /api/dj/sequence

_runAutoSets()
  -> POST /api/dj/set/generate

_prepareLivePoolForOrdered()
  -> POST /api/dj/live/pool/prepare

_syncAllLiveCandidatesBeforePlay()
_syncMissingLiveCandidatesBeforePlay()
_syncMissingCacheFilesForIds()
  -> RK sync-worker /cache/check
  -> RK sync-worker /sync

_ensurePlayableRkCacheIds()
_validatePlayableRkCacheIds()
  -> RK edge-agent /cache/validate
  -> RK sync-worker DELETE /cache/song/{song_id} 后重拉

_prepareAllTransitionPlansBeforePlay()
_planEqBandTransition()
  -> POST /api/dj/transitions/plan

_startLiveMix()
  -> RK /play

_maybeAutoXfade()
_edgeXfadeFromPlan()
  -> RK /xfade

_previewTargetEnergyBucket()
  -> POST /api/dj/cut/plan intent=target_energy_bucket

_previewTargetStyle()
  -> POST /api/dj/cut/plan intent=target_dance_style

_confirmTargetEnergyCut()
_confirmTargetStyleCut()
  -> 插入下一首并调用 RK /xfade
```

当前重要产品原则：所有主队列、能量备选池、风格备选池和首选候选在首曲播放前就要同步并校验到 RK。播放过程中不要再做大规模后台下载，避免两首歌衔接中出现加载空挡。

---

## 7. DJ Control /api/dj 接口

### 舞种列表和按舞种选歌

```text
GET /api/dj/styles
  调用: HarBeatApiClient.djListStyles()
  代码: app/modules/dj_control/router.py:list_styles_endpoint()
  逻辑: app/modules/dj_control/dance_style.py:list_styles()

POST /api/dj/styles/pick
  调用: HarBeatApiClient.djPickByStyle()
  请求: {style, target_duration_sec, min_score}
  代码: router.py:pick_by_style_endpoint()
  逻辑: dance_style.pick_songs_for_duration()
```

### 排序和 DJ set

```text
GET /api/dj/sequence/presets
  调用: HarBeatApiClient.djSequencePresetsMeta()
  代码: router.py:list_sequence_presets()
  逻辑: sequencer.PRESETS, sequencer.list_presets()

POST /api/dj/sequence
  调用: HarBeatApiClient.djSequence()
  请求: {song_ids, preset}
  代码: router.py:sequence_endpoint()
  逻辑: sequencer.sequence_songs()

POST /api/dj/set/generate
  调用: HarBeatApiClient.djSetGenerate()
  请求: {song_ids, template_names?, beam_width?, drop_failed?}
  代码: router.py:set_generate_endpoint()
  逻辑: app/modules/dj_set/service.py:generate_dj_sets()

GET /api/dj/set/{set_id}
POST /api/dj/transition/preview
POST /api/dj/set/{set_id}/preview
  用于查看缓存 set 和单转场预览。
```

`/api/dj/set/generate` 会走 `TrackProfiler -> SectionEnergy -> RoleClassifier -> EdgeAnalyzer -> SetOptimizer -> PurposePlanner -> TransitionPlan -> QualityGate`，返回候选 set，手机默认选分最高的第一个。

### 能量和实时切歌

```text
GET /api/dj/energy/buckets
  调用: HarBeatApiClient.djListEnergyBuckets()
  代码: router.py:list_energy_buckets_endpoint()

GET /api/dj/songs/{song_id}/energy?style=hiphop
  调用: HarBeatApiClient.djSongEnergyV2()
  代码: router.py:energy_breakdown_endpoint()
  逻辑: energy_hiphop.compute_dance_energy(), get_dance_energy_profile()

POST /api/dj/live/pool/prepare
  调用: HarBeatApiClient.djPrepareLivePool()
  请求:
    active_queue_song_ids
    style
    target_reserve_per_bucket
    include_buckets
    exclude_song_ids
    target_style_reserve_per_style
    include_styles
  返回:
    active_queue
    reserve_pool
    style_reserve_pool
    energy_profiles
    sync_priority
    style_pool_status
  代码: router.py:prepare_live_pool_endpoint()
  逻辑: cut_strategy.prepare_live_pool()

POST /api/dj/cut/plan
  调用:
    HarBeatApiClient.djPlanCut()
    HarBeatApiClient.djPlanTargetEnergyCut()
    HarBeatApiClient.djPlanTargetStyleCut()
  intent:
    fast_cut
    energy_up_cut
    energy_down_cut
    target_energy_bucket
    target_dance_style
  代码: router.py:plan_cut_endpoint()
  逻辑:
    cut_strategy.plan_cut()
    cut_strategy.plan_target_energy_cut()
    cut_strategy.plan_target_style_cut()
```

`target_energy_bucket` 当前会从 `active_queue + reserve_pool + library_pool` 搜索；`target_dance_style` 会从 `active_queue + style_reserve_pool + library_fallback` 搜索。这样二次选择不同舞种/时长时，不会只困在第一次候选池里。

### 转场和调性/EQ 混音

```text
GET /api/dj/transitions/rules
  调用: HarBeatApiClient.djListTransitionRules()
  代码: router.py:list_transition_rules_endpoint()
  逻辑: mixer_rules.list_transition_rules()

POST /api/dj/transitions/plan
  调用: HarBeatApiClient.djPlanTransition()
  请求:
    prev_song_id
    next_song_id
    cursor_sec
    rule_key?
    transition_mode = ordinary_xfade | eq_band_mix
    eq_mix_user_mode = auto
    target_style?
  代码: router.py:plan_transition_endpoint()
  普通转场逻辑: mixer_rules.build_transition_spec()
  EQ 调性混音逻辑: eq_transition_strategy.plan_eq_band_mix_transition()
```

当前用户不需要手动选择混音方案。App 请求 `transition_mode=eq_band_mix` 和 `eq_mix_user_mode=auto`，Jetson 根据 BPM、camelot key、能量、vocal density、low band 冲突自动选择：

```text
smooth_blend
soft_bass_swap
hard_bass_swap
vocal_safe
filter_sweep
```

生成的 transition plan 同时包含兼容字段：

```text
transition_mode=eq_band_mix
strategy / eq_strategy
duration_beats
deck_a / deck_b 的 fader 和 low/mid/high EQ 曲线
safety: headroom=-6, limiter=-1, smooth_ms=30
fallback_style
fade_sec / to_at_sec / transition_id
```

如果 RK 不能执行 `eq_band_mix`，edge-agent/audio-engine 会回退普通 xfade；如果当前播放已经停止，则使用 `play_fallback`，避免 “200 OK 但无声”。

### FX 和 Vibe

```text
GET /api/dj/fx
  调用: HarBeatApiClient.djListFx()
  代码: router.py:list_fx_endpoint()
  逻辑: fx_synth.list_fx()

GET /api/dj/fx/{fx_key}.wav
  调用: HarBeatApiClient.djFxAudioUrl()
  代码: router.py:render_fx_endpoint()
  逻辑: fx_synth.render_to_wav_bytes()

POST /api/dj/vibe/search
  调用: HarBeatApiClient.djVibeSearch()
  代码: router.py:vibe_search_endpoint()
  逻辑: vibe_search.score_songs()
```

---

## 8. RK 接口和播放链路

### edge-agent :9000

代码：

```text
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/audio_client.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/state.py
```

接口：

```text
GET  /health
GET  /state
POST /play
POST /pause
POST /resume
POST /seek
POST /xfade
POST /prefetch
POST /cache/validate
POST /trigger
POST /stem_solo
POST /eq
POST /load_plan
POST /internal/key_event
POST /internal/flush_events

兼容接口:
GET  /api/edge/info
GET  /api/edge/status
GET  /api/edge/pair/start
POST /api/edge/pair/start
POST /api/edge/pair/confirm
```

手机调用：

```text
mobile/lib/src/edge_agent_client.dart
  getState()
  play()
  pause()
  resume()
  seek()
  xfade()
  prefetch()
  validateCache()
  trigger()
  stemSolo()
```

`POST /xfade` 是自动接歌、风格切歌、能量切歌的核心入口。请求里如果带 `transition_mode=eq_band_mix` 和 `transition_plan`，edge-agent 会转发 `xfade_eq_band_mix` 给 audio-engine；失败则降级到普通 `xfade`。

### sync-worker :9100

代码：

```text
cypher-integration/rk3588-edge/sync-worker/main.py
```

接口：

```text
POST   /sync
GET    /status
GET    /cache/check?song_id=
DELETE /cache/song/{song_id}
```

手机调用：

```text
mobile/lib/src/sync_worker_client.dart
  startSync()
  getStatus()
  cacheExists()
  deleteSongCache()
  syncAndWait()
```

缓存目录：

```text
/home/cat/cypher/cache/{song_id}/original.wav
/home/cat/cypher/cache/{song_id}/original.wav.sha256
```

sync-worker 会根据 manifest 下载 Jetson 资源。MP3 original 会转成 `original.wav` 供 audio-engine 快速读取；sidecar 记录 sha256、大小和转换来源。App 在播放前会先 `/cache/check`，缺失则 `/sync`，之后 `/cache/validate`，失败则删除该歌缓存并重新拉取。

### audio-engine

代码：

```text
cypher-integration/rk3588-edge/audio-engine/main.py
cypher-integration/rk3588-edge/audio-engine/socket_server.py
cypher-integration/rk3588-edge/audio-engine/engine.py
cypher-integration/rk3588-edge/audio-engine/mix_plan.py
cypher-integration/rk3588-edge/audio-engine/envelope_runner.py
cypher-integration/rk3588-edge/audio-engine/dsp.py
```

职责：

```text
加载本地缓存音频
维护 active/inactive 双 deck
普通 xfade
eq_band_mix 的 low/mid/high + fader 曲线
自动接歌
FX one-shot
stem solo
3-band deck EQ
limiter 防爆音
播放状态上报
```

audio-engine 不是 HTTP 服务，而是由 edge-agent 通过 Unix socket 发送命令：

```text
state
play
pause
resume
seek
xfade
xfade_eq_band_mix
prefetch
validate_cache
trigger
set_deck_eq
stem_solo
load_plan
```

### input-daemon

代码：

```text
cypher-integration/rk3588-edge/input-daemon/main.py
cypher-integration/rk3588-edge/input-daemon/config.py
cypher-integration/rk3588-edge/input-daemon/audio_socket.py
```

当前按键语义：

```text
1-5: DJ 加花音效 sample_key 1-5
6: 黑胶刹停，实际触发 audio-engine sample_key 3
7-9: 只上报 edge-agent key_event，交由手机处理实时切歌语义
0: pause/resume
KEY_VOLUMEUP / KEY_VOLUMEDOWN: amixer 调 ES8388 card 2 的 PCM 音量
```

注意：不要用 `Headphone` 或 `Speaker` 作为音量控制，它们是开关，误调会导致耳机口/音箱无声。当前只调 `amixer -c 2 sset PCM 5%+/-`。

---

## 9. 播放前缓存策略

当前稳定策略：

```text
1. 选歌和排序后，App 调 /api/dj/live/pool/prepare。
2. App 汇总所有需要的歌曲：
   主播放队列
   reserve_pool 能量备选
   style_reserve_pool 风格备选
   切歌首选候选
3. App 对这些 song_id 调 RK /cache/check。
4. 缺失的歌曲组成 manifest tracks，调 RK sync-worker /sync。
5. App 等待 sync-worker idle。
6. App 调 RK edge-agent /cache/validate，让 audio-engine 真正解码测试。
7. validate 失败的歌：
   DELETE /cache/song/{song_id}
   再次 /sync
   再次 /cache/validate
8. 全部成功后才 /play 第一首。
9. 播放中不做大规模后台同步，自动接歌直接使用已准备好的 transition plan。
```

这个策略是为了解决两首歌衔接时中间出现加载检查空挡的问题。切歌时如果目标来自已校验候选池，理论上不需要二次下载；如果因为用户二次选择导致候选池变化，App 会重置 live session 并重新做启动前完整同步。

缓存何时清除：

```text
手动调用 DELETE /cache/song/{song_id}
App validate 失败后主动删除坏缓存并重拉
人工在 RK 删除 /home/cat/cypher/cache/*
sync-worker 不会因为播放结束自动清空全部缓存
```

---

## 10. 调性/EQ 混音实现

文档规格参考：

```text
docs/HarBeat_EQ_Band_Mix_Implementation.md
docs/HarBeat_EQ_Band_Mix_Evaluation.md
```

后端新增/相关文件：

```text
app/modules/dj_control/band_analysis.py
app/modules/dj_control/mix_profile.py
app/modules/dj_control/eq_transition_presets.py
app/modules/dj_control/eq_transition_strategy.py
app/modules/dj_control/router.py
app/modules/dj_control/schemas.py
app/tests/test_eq_band_mix_strategy.py
```

手机新增/相关文件：

```text
mobile/lib/src/api_client.dart
  djPlanTransition(... transitionMode='eq_band_mix', eqMixUserMode='auto')

mobile/lib/src/dj_control_page.dart
  _planEqBandTransition()
  _prepareTransitionPlanForPair()
  _prepareAllTransitionPlansBeforePlay()
  _edgeXfadeFromPlan()
```

RK 新增/相关文件：

```text
cypher-integration/rk3588-edge/audio-engine/envelope_runner.py
cypher-integration/rk3588-edge/audio-engine/engine.py
cypher-integration/rk3588-edge/audio-engine/socket_server.py
cypher-integration/rk3588-edge/audio-engine/mix_plan.py
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
cypher-integration/rk3588-edge/tests/test_eq_band_mix_envelope.py
```

关键链路：

```text
App _prepareTransitionPlanForPair()
  -> POST /api/dj/transitions/plan transition_mode=eq_band_mix
  -> Jetson eq_transition_strategy.plan_eq_band_mix_transition()
  -> 返回 deck_a/deck_b EQ/fader 曲线和 fallback 字段
  -> App 缓存 plan 到 _preparedTransitionPlans
  -> 自动接歌或手动切歌时 _edgeXfadeFromPlan()
  -> RK POST /xfade transition_mode=eq_band_mix transition_plan={...}
  -> edge-agent forward xfade_eq_band_mix
  -> audio-engine 在 callback 中按 beat 评估 envelope_runner.eval_deck()
  -> 双 deck 混合，headroom=-6dB，limiter 防削波
```

当前策略选择为自动，不让用户判断。`eq_mix_user_mode=auto` 时根据当前/下一首的 BPM 差、camelot key 距离、能量变化、vocal density 和 low band 冲突选策略。

---

## 11. 部署流程

### 部署 Jetson

目标目录必须是 `/home/mark/harbeat`，因为 systemd 的 `WorkingDirectory` 指向这里。

```powershell
cd D:\work\harbeat-client

# 示例：同步 app、scripts、deploy、requirements 等源码到 Jetson
# 可用 scp、rsync 或 IDE 同步；不要同步 .env、data、logs、venv、pycache。
```

远端重启：

```bash
ssh root@100.87.142.21
cd /home/mark/harbeat
systemctl restart harbeat-api
journalctl -u harbeat-api -n 120 --no-pager
curl -i http://127.0.0.1:8000/api/health
```

### 部署 RK3588

目标目录必须是 `/home/cat/cypher`：

```powershell
cd D:\work\harbeat-client

# 同步 cypher-integration/rk3588-edge/* 到 /home/cat/cypher
# 不同步 cache、logs、.env、deploy/cypher.env、pycache、*.bak。
```

远端重启：

```bash
ssh cat@192.168.43.7
cd /home/cat/cypher
sudo systemctl daemon-reload
sudo systemctl restart cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
```

只改缓存下载逻辑：

```bash
sudo systemctl restart cypher-sync-worker
```

只改播放/混音逻辑：

```bash
sudo systemctl restart cypher-audio-engine cypher-edge-agent
```

### 部署手机

```powershell
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat clean
D:\flutter_install\flutter\bin\flutter.bat pub get
D:\flutter_install\flutter\bin\flutter.bat build apk --debug
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

如果安装后仍是旧行为：

```powershell
C:\Android\platform-tools\adb.exe shell pm list packages | Select-String harbeat
C:\Android\platform-tools\adb.exe shell pm clear com.example.mobile
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

---

## 12. 排障入口

### App 显示“网络请求失败”

先从手机真实网络检查，不要依赖 `adb reverse`：

```powershell
C:\Android\platform-tools\adb.exe shell curl -i http://8.136.120.255/api/auth/me
C:\Android\platform-tools\adb.exe shell curl -i http://192.168.43.7:9000/health
```

判断：

```text
Jetson /api/auth/me 返回 401: 正常，API 可达但未登录。
Jetson 无响应: 查 nginx、harbeat-api、公网/安全组。
RK /health 无响应: 查手机和 RK 是否同一热点/LAN、RK IP 是否变化、edge-agent 是否 active。
```

日志：

```powershell
C:\Android\platform-tools\adb.exe logcat | Select-String -Pattern "flutter|SocketException|http|edge|sync|401|403|500"
```

### “end recovery failed”

通常原因：

```text
当前歌已播到末尾，自动恢复尝试 xfade 或 fallback。
目标歌未缓存/缓存损坏/validate 失败。
audio-engine 当前 state.playing=false，普通 xfade 不能平滑衔接。
```

检查：

```bash
ssh cat@192.168.43.7
curl http://127.0.0.1:9000/state
curl http://127.0.0.1:9100/status
journalctl -u cypher-edge-agent -n 160 --no-pager
journalctl -u cypher-audio-engine -n 160 --no-pager
journalctl -u cypher-sync-worker -n 160 --no-pager
```

预期策略：首曲播放前已经 `/cache/validate` 全部候选。如果仍出现，重点看是否发生了二次选择新 session、候选池变化、或 validate 后文件被删/损坏。

### 自动接歌失败或风格/能量切歌失败

查调用链：

```text
App 是否已经 _backgroundSyncInProgress=false
App 是否有 _preparedTransitionPlans
POST /api/dj/cut/plan 是否返回 selected_song
POST /api/dj/transitions/plan 是否返回 transition_mode=eq_band_mix
RK /xfade 是否返回 ok=true
audio-engine 日志是否出现 xfade_eq_band_mix 或 fallback
```

命令：

```bash
journalctl -u harbeat-api -n 160 --no-pager
journalctl -u cypher-edge-agent -n 160 --no-pager
journalctl -u cypher-audio-engine -n 160 --no-pager
```

### RK 没声音

检查服务和声卡：

```bash
systemctl is-active cypher-audio-engine
journalctl -u cypher-audio-engine -n 120 --no-pager
aplay -l
pactl info
amixer -c 2 sget PCM
```

注意：当前 systemd 用 PulseAudio 用户运行时：

```text
XDG_RUNTIME_DIR=/run/user/1000
PULSE_RUNTIME_PATH=/run/user/1000/pulse
CYPHER_AUDIO_DEVICE=pulse
```

音量只调 ES8388 的 `PCM`，不要调 `Headphone`/`Speaker` 开关。

---

## 13. 本地测试建议

后端关键测试：

```powershell
cd D:\work\harbeat-client
python -m pytest app/tests/test_target_style_cut_strategy.py
python -m pytest app/tests/test_target_energy_cut_strategy.py
python -m pytest app/tests/test_live_pool_prepare.py
python -m pytest app/tests/test_eq_band_mix_strategy.py
```

RK 关键测试：

```powershell
python -m pytest cypher-integration/rk3588-edge/tests/test_edge_audio_forward.py
python -m pytest cypher-integration/rk3588-edge/tests/test_eq_band_mix_envelope.py
```

Flutter 检查：

```powershell
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat analyze
```

真实端到端最小闭环：

```text
1. 手机能访问 http://8.136.120.255/api/auth/me。
2. 手机能访问 http://192.168.43.7:9000/health。
3. App 登录成功。
4. 进入 DJ Control。
5. 选择舞种/时长或歌单，生成排序。
6. 开始播放前等待候选池同步和 validate 完成。
7. 第一首开始播放。
8. 自动接歌时无加载空挡。
9. 风格切歌、能量切歌可选出候选并 xfade。
10. RK 日志显示 eq_band_mix 或明确 fallback。
```

---

## 14. Git 提交边界

应该提交：

```text
app/**/*.py
mobile/lib/**/*.dart
mobile/android 配置
cypher-integration/rk3588-edge 源码、测试、deploy/*.service、deploy/*.example
docs/*.md
deploy 源码和模板
```

不应该提交：

```text
.env
deploy/cypher.env
JWT/token/password
data/music-files
/home/cat/cypher/cache
logs
pycache
*.bak
Flutter build/
APK 构建产物
ADB 截图、window XML、临时 log、.tmp*
```

当前三端部署源码已经在仓库中对应：

```text
Jetson: app/, scripts/, deploy/, requirements.txt
RK3588: cypher-integration/rk3588-edge/
手机: mobile/
```

---

## 15. 接手优先阅读顺序

```text
1. docs/project.md 的 1-10 节，先理解三端职责和 DJ Control 链路。
2. mobile/lib/src/dj_control_page.dart，理解用户操作和启动前缓存策略。
3. mobile/lib/src/api_client.dart、edge_agent_client.dart、sync_worker_client.dart，理解手机调用。
4. app/modules/dj_control/router.py，理解 /api/dj 分发。
5. app/modules/dj_control/cut_strategy.py，理解候选池、能量切歌、风格切歌。
6. app/modules/dj_control/eq_transition_strategy.py，理解自动调性/EQ 混音选择。
7. cypher-integration/rk3588-edge/edge-agent/main.py，理解 RK REST API。
8. cypher-integration/rk3588-edge/sync-worker/main.py，理解缓存下载。
9. cypher-integration/rk3588-edge/audio-engine/engine.py，理解真实播放和混音。
```

如果只改一个功能，优先按“手机方法 -> Jetson API -> RK API -> audio-engine 日志”的顺序追踪，不要直接从 audio-engine 猜。
