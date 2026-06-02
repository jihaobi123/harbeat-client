# HarBeat 当前项目交接说明

版本: 2026-06-02  
状态: 当前真实实现说明，面向后续开发者和 AI Agent  
适用读者: Flutter、FastAPI、Jetson、RK3588、音频算法、运维部署工程师

---

## 0. 文档用途

本文用于说明 HarBeat 当前代码库的真实结构、功能边界和部署状态。它不是愿景文档，也不是重新设计方案，而是帮助接手者快速回答这些问题：

- 现在系统由哪些端组成，各自负责什么。
- 前端、后端、Jetson、RK3588 之间如何通信。
- 当前已经实现哪些音乐分析、自动混音和 RK 播放能力。
- 关键接口、数据表、文件目录和部署配置在哪里。
- 后续修改应先看哪些文件，如何测试，哪些风险需要优先处理。

---

## 1. 项目定位

HarBeat 是一个面向街舞 cypher、练习局、小型 party 和 battle warm-up 的自动控乐系统。目标不是做一个专业 DJ 台，而是让没有专业 DJ 的现场也能完成相对自然的选歌、接歌、混音和氛围控制。

一句话理解：

```text
用户表达现场意图
→ 后端分析曲库并规划选歌/转场
→ Flutter App 展示和下发控制
→ RK3588 负责现场低延迟播放、缓存、混音和硬件输入
→ Jetson / 云端负责重计算、歌曲分析、stems、manifest 和网关
```

核心原则：

- Jetson / 后端做重计算，RK 做现场实时音频执行。
- Flutter App 是控制台和解释层，不是 P0 主播放引擎。
- RK 本地缓存是现场可靠性的核心，公网或 Jetson 不应进入实时音频闭环。
- stems 是增强能力，不是播放前置条件。stems 缺失时必须降级到普通 crossfade 或安全 cut。

---

## 2. 总体架构

```text
Flutter App
  ├─ 调用后端 API: 登录、曲库、歌单、DJ set、transition plan、manifest
  └─ 调用 RK edge-agent: 播放、暂停、prefetch、xfade、FX、状态查询

FastAPI 后端 / Jetson / 云网关
  ├─ 曲库入库、在线搜索、下载
  ├─ BPM / beatgrid / key / energy / phrase / stems 分析
  ├─ DJ Control / DJ Set 选歌和 transition strategy
  ├─ manifest 生成和 /api/assets 文件下载
  └─ session events / RK 事件回收

RK3588
  ├─ edge-agent :9000，对 App 暴露播放控制 API
  ├─ sync-worker :9100，本机服务，从 manifest 下载 original + stems 到 cache
  ├─ audio-engine，通过 Unix socket 执行双 deck 播放、xfade、stem 曲线、EQ、FX
  └─ input-daemon，接收实体按键 / HID 控制

数据与文件
  ├─ PostgreSQL: 用户、曲库、歌单、分析结果、会话
  ├─ Redis: 可选缓存
  ├─ UPLOAD_DIR: 原曲、stems、处理结果
  └─ RK cache: /home/cat/cypher/cache/{song_id}/
```

当前线上常见链路：

```text
手机 App
→ http://8.136.120.255 后端网关
→ /api/manifest/song/{song_id}
→ manifest.files.original + manifest.files.stems.*
→ RK edge-agent / sync-worker 下载到本地 cache
→ RK /play 播放
→ RK /xfade 切歌
```

---

## 3. 代码目录总览

| 路径 | 作用 |
|---|---|
| `app/` | FastAPI 后端主代码 |
| `app/main.py` | FastAPI 入口、CORS、路由挂载、SPA fallback、异常处理 |
| `app/shared/` | 配置、数据库、响应结构等公共代码 |
| `app/modules/` | 后端业务模块 |
| `mobile/` | Flutter App |
| `mobile/lib/src/api_client.dart` | 后端 API 客户端 |
| `mobile/lib/src/edge_agent_client.dart` | RK edge-agent 客户端 |
| `mobile/lib/src/dj_control_page.dart` | DJ Control 核心页面和同步/切歌逻辑 |
| `cypher-integration/rk3588-edge/` | RK3588 edge-agent、audio-engine、sync-worker、input-daemon、部署文件 |
| `jetson/` | Jetson 部署和补丁相关脚本 |
| `deploy/` | 云端 / Docker / nginx 部署配置 |
| `docs/` | 项目文档、模块说明、交接说明 |
| `scripts/` | 批处理、分析、运维脚本 |
| `tests/` / `app/tests/` | 后端和集成测试 |

---

## 4. 后端架构

后端使用 FastAPI + SQLAlchemy + Pydantic Settings。入口为 `app/main.py`，总路由在 `app/modules/router.py` 汇总。

### 4.1 配置

核心配置文件：

- `app/shared/config.py`
- `.env.example`

关键环境变量：

| 变量 | 作用 |
|---|---|
| `DATABASE_URL` | PostgreSQL 连接 |
| `REDIS_URL` | Redis 连接 |
| `JWT_SECRET` | JWT 签名密钥 |
| `UPLOAD_DIR` | 原曲、stems、处理文件根目录 |
| `PUBLIC_ASSET_BASE_URL` | RK 可访问的公网或 Tailscale 下载基址 |
| `MANIFEST_COMPUTE_SHA256` | 是否在 manifest 请求中实时计算 SHA256，默认关闭 |
| `SPOTIPY_CLIENT_ID / SECRET` | Spotify 元数据补充 |
| `DISCOGS_USER_TOKEN` | Discogs 风格标签补充 |

注意：`PUBLIC_ASSET_BASE_URL` 很关键。如果为空，manifest 会根据请求头推断 base URL；如果部署在反代后，必须设置为 RK 能访问的地址，例如 `http://8.136.120.255` 或 Tailscale 地址。

### 4.2 后端模块表

| 模块 | 路径 | 主要接口 / 能力 | 当前状态 |
|---|---|---|---|
| assets | `app/modules/assets/` | `GET /api/assets/{path}`，给 RK 下载原曲和 stems | 已实现 |
| auth | `app/modules/auth/` | 注册、登录、刷新 token、当前用户 | 已实现 |
| users | `app/modules/users/` | 用户基础 CRUD | 已实现 |
| library | `app/modules/library/` | 曲库、上传、分析、stems 分离、歌曲元数据 | 已实现，分析仍需校准 |
| manifest | `app/modules/manifest/` | 单曲 / 歌单 manifest，给 RK sync-worker 使用 | 已实现，近期已修复 |
| stream | `app/modules/stream/` | 原曲和 stem 流式播放 | 已实现 |
| fangpi | `app/modules/fangpi/` | fangpi 搜索、下载、外部歌单解析、批量搜索 | 已实现 |
| playlists | `app/modules/playlists/` | 歌单导入、创建、排序、离线 DJ mix | 已实现，部分高级能力为原型 |
| dj_control | `app/modules/dj_control/` | 能量排序、风格切歌、transition plan、DJ set、FX | 已实现，持续迭代 |
| dj_set | `app/modules/dj_set/` | set 模板、track profile、beam search、pair analysis | 已实现原型 |
| recommendations | `app/modules/recommendations/` | vibe search、推荐、导入 | 部分实现 |
| sessions | `app/modules/sessions/` | 练舞会话、RK 事件回收 | 已实现基础链路 |
| profiles | `app/modules/profiles/` | 用户音乐画像 | 已实现基础 |
| music | `app/modules/music/` | 早期歌曲、cue、标签处理 | 遗留 + 可用 |

---

## 5. 数据模型

### 5.1 核心表

| 表 | 模型文件 | 作用 |
|---|---|---|
| `users` | `app/modules/users/models.py` | 用户账号、舞种、水平、偏好 |
| `library_songs` | `app/modules/library/models.py` | 用户曲库实体，保存真实音频路径和完整分析结果 |
| `songs` | `app/modules/playlists/models.py` | 全局歌曲目录，用 title + artist 去重 |
| `playlists` | `app/modules/playlists/models.py` | 用户歌单 |
| `playlist_songs` | `app/modules/playlists/models.py` | 歌单歌曲关联和排序 |
| `song_tags` | `app/modules/playlists/models.py` | 歌曲人工标签，如 bpm、energy、style、groove |

### 5.2 `LibrarySong` 关键字段

`library_songs` 是当前自动混音最重要的表。关键字段包括：

- 基础信息：`id`, `user_id`, `song_id`, `title`, `artist`, `duration`, `format`, `file_size`
- 文件：`source_path`, `stems`
- 平台：`platform_id`, `platform_url`, `source_type`
- 基础分析：`bpm`, `key`, `camelot_key`, `energy`, `analysis_status`
- 节拍：`beat_points`, `bpm_curve`, `tempo_stability`, `beat_confidence`, `beat_grid_offset`, `beat_grid_interval`, `beat_needs_review`
- 结构：`downbeats`, `phrase_map`, `cue_points`, `dj_hot_cues`
- 响度：`loudness_profile`
- 调性：`key_confidence`, `key_profile`
- 流派和舞感：`genre_profile`, `music_features`, `dance_styles`, `dance_style_scores`, `dance_style_status`, `groove_score`, `danceability_score`, `dancefloor_profile`
- stems 分析：`stem_activity`, `stem_activity_windows`, `stem_quality_score`, `stem_quality_profile`
- 转场风险：`vocal_events`, `bass_risk_windows`, `transition_windows`, `transition_recommendations`
- clean window：`intro_is_clean`, `outro_is_clean`, `intro_clean_score`, `outro_clean_score`, `has_drum_loop`

注意：当前模型没有 `stem_status` 字段。manifest 中的 `stemStatus` 是运行时根据 stems 完整度推导出来的。

---

## 6. 歌曲分析与风格识别

### 6.1 分析入口

主要文件：

- `app/modules/library/analysis.py`
- `app/modules/library/background_tasks.py`
- `app/modules/library/stem_analysis.py`
- `app/modules/library/genre_classifier.py`
- `app/modules/library/dj_feature_extractor.py`
- `scripts/jetson_analysis_pipeline.py`

入口通常是：

```text
POST /api/library/songs/{song_id}/analyze
POST /api/library/songs/{song_id}/separate-stems
```

后台会读原曲、运行 BPM / key / beatgrid / phrase / loudness / energy / genre / stems 等分析，并写回 `library_songs`。

### 6.2 已有分析能力

当前已实现或原型实现的能力：

- BPM、BPM 曲线、tempo stability
- beat points、beat confidence、beat grid offset / interval、needs review
- downbeats、time signature 安全回退
- key、Camelot、key confidence、key profile
- loudness / replay gain / clipping risk
- energy、energy curve
- phrase map、cue points、DJ hot cues
- groove、danceability、dancefloor profile、mood tags
- Demucs 四轨 stems: vocals / drums / bass / other
- stem activity windows、stem quality proxy
- vocal events、bass risk windows
- intro / outro clean score
- transition windows、transition recommendations
- genre profile，包括规则特征、Spotify、Discogs 可扩展补充

### 6.3 风格 / 流派标签

当前风格识别不是一个单一外部 API 决定，而是多源融合：

- 本地音频规则特征：BPM、鼓密度、低频、能量、stem 活跃度等
- 人工 / 歌单标签：`song_tags`, `dance_styles`
- Spotify 元数据：可补充 artist / album / genre 信息
- Discogs：可补充 release 的 genre / style 标签，适合作为 metadata enrichment

实现位置：

- `app/modules/library/genre_classifier.py`
- `app/modules/dj_control/dance_style.py`
- `docs/song-style-analysis.md`

重要边界：Discogs 标签适合补充曲风库，但不是实时音频分析替代品。后续如果接入更多平台，应写入 `genre_profile` 的来源和置信度，而不是覆盖所有本地分析结果。

---

## 7. 自动混音和选歌逻辑

### 7.1 DJ Control 模块

主要文件：

- `app/modules/dj_control/router.py`
- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/transition_strategy.py`
- `app/modules/dj_control/energy_hiphop.py`
- `app/modules/dj_control/vibe_search.py`
- `app/modules/dj_control/cut_strategy.py`

主要接口：

| 接口 | 作用 |
|---|---|
| `GET /api/dj/styles` | 获取可选风格 |
| `POST /api/dj/styles/pick` | 按风格选歌 |
| `GET /api/dj/energy/buckets` | 获取能量桶 |
| `POST /api/dj/sequence` | 生成能量 / 风格序列 |
| `GET /api/dj/transitions/rules` | 转场规则列表 |
| `POST /api/dj/transitions/plan` | 生成两首歌之间的转场计划 |
| `POST /api/dj/cut/plan` | 切歌策略 |
| `POST /api/dj/vibe/search` | 氛围搜索 |
| `POST /api/dj/set/generate` | 生成 DJ set |
| `GET /api/dj/set/{set_id}` | 获取 DJ set |
| `POST /api/dj/transition/preview` | 转场预览 |
| `POST /api/dj/set/{set_id}/preview` | set 预览 |

### 7.2 已有转场规则

基础规则位于 `mixer_rules.py`，包括：

- harmonic blend
- eq swap
- filter sweep
- drop swap
- echo tail
- loop roll
- spin back
- drum only bridge
- key lift
- reverb throw
- back-to-back drop
- raw fallback crossfade / hard cut / fade out in / echo drop

新增跨风格策略位于 `transition_strategy.py`，核心思路是先计算 `TransitionContext`：

- `bpmDiff`, `bpmDiffRatio`
- `tempoRelation`: close / half-time / double-time / unrelated
- `keyDistance`
- `genreDistance`
- `energyDiff`
- `vocalConflictRisk`
- `phraseBarsAvailable`
- `stemsAvailable`

然后选择跨风格方案，例如：

- Echo Out Hard Drop
- Percussion Bridge
- Stem Strip And Rebuild
- Auto BPM Ramp
- Half-Time / Double-Time Pivot
- Neutral FX Bridge
- Breakdown Reset
- Vocal Avoidance Cut

输出会合并进 transition spec，包含 `duration_sec`, `style`, `fallback_style`, `stem_curves`, `eq_curves`, `timeline`, `strategy` 等。

### 7.3 当前声音执行边界

后端可以生成很丰富的转场意图，但最终听感取决于 RK 是否具备：

- 目标歌曲 original 已缓存
- 目标歌曲四路 stems 已缓存
- RK audio-engine 当前版本是否执行 `stem_curves` / `eq_curves`
- `/xfade` 是否收到与现网 schema 兼容的字段
- 网络是否允许提前拉取大 stems

如果 stems 不完整，必须返回或表现为 non-stem / fallback 方案。

---

## 8. Manifest 与资源同步

### 8.1 Manifest 作用

manifest 是后端告诉 RK “这首歌需要下载哪些文件”的标准清单。它由：

- `app/modules/manifest/__init__.py`
- `app/modules/manifest/router.py`

生成。

单曲接口：

```text
GET /api/manifest/song/{song_id}
```

返回结构同时兼容旧字段和新字段：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "manifest": {
      "song_id": "uuid",
      "library_song_id": "uuid",
      "songId": "uuid",
      "librarySongId": "uuid",
      "title": "...",
      "files": {
        "original": {"url": "...", "size": 123, "sha256": null, "format": "mp3"},
        "stems": {
          "vocals": {"url": "...", "size": 123, "sha256": null, "format": "wav"},
          "drums": {"url": "..."},
          "bass": {"url": "..."},
          "other": {"url": "..."}
        }
      },
      "analysis": {},
      "qualityFlags": {},
      "analysisStatus": "completed",
      "stemStatus": "ready"
    }
  },
  "ok": true,
  "manifest": {}
}
```

### 8.2 近期已修复的关键点

当前分支最新修复包括：

- `stemStatus` 不再依赖不存在的 ORM 字段。
- manifest 默认不实时计算 SHA256，避免大文件请求超时。
- 资源 URL 会做百分号编码，避免空格导致 RK 下载失败。
- 新增 `/api/assets/{path}`，RK 可真实下载 `UPLOAD_DIR` 下的 original 和 stems。
- `PUBLIC_ASSET_BASE_URL` 用于生成 RK 可访问 URL。

### 8.3 RK 下载路径

RK sync-worker 接收 playlist / set / tracks manifest：

```text
POST http://127.0.0.1:9100/sync
GET  http://127.0.0.1:9100/status
GET  http://127.0.0.1:9100/cache/check?song_id=...
```

缓存目录：

```text
/home/cat/cypher/cache/{song_id}/original.*
/home/cat/cypher/cache/{song_id}/vocals.wav
/home/cat/cypher/cache/{song_id}/drums.wav
/home/cat/cypher/cache/{song_id}/bass.wav
/home/cat/cypher/cache/{song_id}/other.wav
```

当前瓶颈：公网网关下载 stems 很慢，单个 stem 可能 60MB 以上。生产上应优先走局域网或 Tailscale 到 Jetson，而不是所有大文件经公网网关。

---

## 9. Flutter App

### 9.1 技术栈

- Flutter / Dart
- HTTP 调用后端和 RK
- SharedPreferences 保存登录 token、RK 地址等
- Android debug APK 已可构建

主要文件：

| 文件 | 作用 |
|---|---|
| `mobile/lib/src/app.dart` | App 入口、默认后端 base URL |
| `mobile/lib/src/api_client.dart` | FastAPI 后端客户端 |
| `mobile/lib/src/edge_agent_client.dart` | RK edge-agent 客户端 |
| `mobile/lib/src/dj_control_page.dart` | DJ Control 主页面，选歌、同步、prefetch、xfade |
| `mobile/lib/src/home_page.dart` | 曲库 / 歌单主界面 |
| `mobile/lib/src/live_deck_page.dart` | 实时播放 / Deck 相关页面 |
| `mobile/lib/src/models.dart` | 后端数据模型 |
| `mobile/lib/src/live_models.dart` | RK live 状态模型 |
| `mobile/lib/src/sync_worker_client.dart` | sync-worker 客户端封装 |

### 9.2 后端 API 调用

`HarBeatApiClient` 负责：

- `/api/auth/login`, `/api/auth/register`, `/api/auth/me`
- `/api/library/songs`, `/api/library/songs/search`
- `/api/playlists`
- `/api/fangpi/search`, `/api/fangpi/download`
- `/api/recommendations/vibe-search`
- `/api/manifest/song/{song_id}`
- `/api/dj/*`

### 9.3 RK API 调用

`EdgeAgentClient` 负责：

- `GET /health`
- `GET /state`
- `POST /play`
- `POST /pause`
- `POST /resume`
- `POST /seek`
- `POST /prefetch`
- `POST /prewarm_beatmatch`
- `POST /beat_reinforce`
- `POST /stem_solo`
- `POST /trigger`
- `POST /xfade`

当前 `/xfade` 现网 schema：

```json
{
  "to_song_id": "uuid",
  "fade_sec": 8.0,
  "to_at_sec": 0.0,
  "style": "blend",
  "fallback_style": "echo_freeze",
  "tempo_ratio": 1.02,
  "stem_curves": {},
  "eq_curves": {},
  "phase_anchor_sec": 0.0
}
```

注意：旧字段 `next_song_id` / `duration_sec` 不应直接发给 RK edge-agent。Flutter 当前 `edge_agent_client.dart` 已使用 `to_song_id` / `fade_sec`。

---

## 10. RK3588 端

RK 代码位于：

```text
cypher-integration/rk3588-edge/
```

### 10.1 服务组成

| 服务 | 路径 | 端口 / 通信 | 作用 |
|---|---|---|---|
| audio-engine | `audio-engine/` | Unix socket `/tmp/cypher-audio.sock` | 双 deck、播放、xfade、FX、stem 自动化 |
| edge-agent | `edge-agent/` | HTTP `:9000` | App 访问入口，转发命令到 audio-engine |
| sync-worker | `sync-worker/` | HTTP `127.0.0.1:9100` | 从后端 manifest 下载 original + stems |
| input-daemon | `input-daemon/` | HID / internal HTTP | 实体按键输入 |

### 10.2 systemd

部署文件：

- `cypher-integration/rk3588-edge/deploy/cypher-audio-engine.service`
- `cypher-integration/rk3588-edge/deploy/cypher-edge-agent.service`
- `cypher-integration/rk3588-edge/deploy/cypher-sync-worker.service`
- `cypher-integration/rk3588-edge/deploy/cypher-input-daemon.service`
- `cypher-integration/rk3588-edge/deploy/cypher.target`
- `cypher-integration/rk3588-edge/deploy/cypher.env.example`

常用命令：

```bash
sudo systemctl status cypher-audio-engine
sudo systemctl status cypher-edge-agent
sudo systemctl status cypher-sync-worker
sudo systemctl restart cypher-audio-engine cypher-edge-agent cypher-sync-worker
journalctl -u cypher-edge-agent -n 100 --no-pager
journalctl -u cypher-audio-engine -n 100 --no-pager
```

### 10.3 当前实测状态说明

最近一次成功实测链路：

- 后端 gateway `http://8.136.120.255/health` 正常。
- RK `http://192.168.43.7:9000/health` 曾正常。
- RK `sync-worker` 曾恢复为 systemd 管理并监听 `127.0.0.1:9100`。
- Rump Shaker / War manifest 返回正常且 stems ready。
- RK 可从 `/api/assets/...` 下载 stem WAV 字节。
- RK `/play` 可播放第一首。
- RK `/xfade` 用 `to_song_id` / `fade_sec` schema 可返回 200，并切到第二首。

当前如果更换热点，需要重新发现 RK IP。旧 IP `192.168.43.7` 可能失效。

---

## 11. Jetson / 云网关

Jetson 主要承担：

- FastAPI 服务运行
- 歌曲分析和 stems 分离
- manifest 生成
- 音频文件资产下载
- 与云网关 / Tailscale 配合对外提供 API

常见部署路径：

```text
/home/mark/harbeat
/home/mark/venvs/harbeat
/etc/systemd/system/harbeat-api.service
```

常用命令：

```bash
systemctl status harbeat-api.service --no-pager -l
journalctl -u harbeat-api.service -n 120 --no-pager
curl http://127.0.0.1:8000/health
curl http://127.0.0.1/health
```

关键运维点：

- `.env` 中必须设置 `UPLOAD_DIR`。
- 如果 RK 通过公网或 Tailscale 下载资产，必须设置 `PUBLIC_ASSET_BASE_URL`。
- 不要让 manifest 请求实时计算大文件 SHA256，除非是离线校验任务。
- `/api/assets/{path}` 必须能从 RK 网络访问。

---

## 12. 主要功能链路

### 12.1 登录与曲库浏览

```text
App 登录
→ POST /api/auth/login
→ 保存 JWT
→ GET /api/auth/me
→ GET /api/library/songs
→ 展示曲库 / 歌单
```

涉及文件：

- `mobile/lib/src/api_client.dart`
- `app/modules/auth/router.py`
- `app/modules/library/router.py`

### 12.2 歌曲导入和分析

```text
上传 / fangpi 下载
→ LibrarySong 入库
→ analyze / separate-stems
→ 写入 bpm/key/beatgrid/phrase/energy/stems 等字段
→ manifest 可使用
```

涉及文件：

- `app/modules/library/router.py`
- `app/modules/library/background_tasks.py`
- `app/modules/library/analysis.py`
- `app/modules/library/stem_analysis.py`
- `app/modules/fangpi/router.py`

### 12.3 DJ Control 选歌和切歌

```text
App DJ Control
→ GET /api/dj/* 获取规则、能量桶、FX
→ POST /api/dj/transitions/plan 获取 A→B 过渡计划
→ GET /api/manifest/song/{next_song_id}
→ RK sync-worker 下载 original + stems
→ RK /prefetch 解码进内存
→ RK /xfade 执行切歌
```

涉及文件：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/api_client.dart`
- `mobile/lib/src/edge_agent_client.dart`
- `app/modules/dj_control/router.py`
- `app/modules/dj_control/mixer_rules.py`
- `app/modules/dj_control/transition_strategy.py`
- `app/modules/manifest/*`
- `cypher-integration/rk3588-edge/*`

### 12.4 RK 现场播放

```text
App / 硬件输入
→ edge-agent :9000
→ audio-engine Unix socket
→ 双 deck load / play / xfade / FX
→ state 回传 App
→ SessionEvent flush 到后端
```

涉及文件：

- `cypher-integration/rk3588-edge/edge-agent/main.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`
- `cypher-integration/rk3588-edge/sync-worker/main.py`
- `cypher-integration/rk3588-edge/input-daemon/`
- `app/modules/sessions/router.py`

---

## 13. 部署说明

### 13.1 本地开发

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Flutter：

```powershell
cd mobile
flutter pub get
flutter build apk --debug
```

注意：Windows 本机如果是 Python 3.13，部分依赖如 `numpy<2` 可能需要源码编译并失败。建议生产和 Jetson 使用 Python 3.10 / 3.11。

### 13.2 Docker

当前 `docker-compose.yml` 包含：

- `app`: FastAPI
- `redis`
- `nginx`

PostgreSQL 当前 compose 文件没有直接定义 postgres 服务，README 中的旧说明和当前 compose 有差异。部署前应确认数据库是外部 RDS 还是本机容器。

启动：

```bash
docker-compose up -d --build
docker-compose logs -f app
```

### 13.3 Jetson

典型服务：

```bash
systemctl status harbeat-api.service
systemctl restart harbeat-api.service
journalctl -u harbeat-api.service -n 120 --no-pager
```

必查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/manifest/song/{song_id}
curl http://127.0.0.1:8000/api/assets/{encoded_path}
```

### 13.4 RK3588

安装 systemd：

```bash
cd /home/cat/cypher
sudo cp deploy/cypher-*.service /etc/systemd/system/
sudo cp deploy/cypher.target /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cypher-audio-engine cypher-edge-agent cypher-sync-worker cypher-input-daemon
```

检查：

```bash
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9100/status
ss -ltnp | grep -E '9000|9100'
```

App 需要能访问 RK 的 `:9000`。`sync-worker :9100` 可以只监听 `127.0.0.1`，由 edge-agent 或本机调用。

---

## 14. 测试和验收

### 14.1 后端单元测试

常用测试：

```powershell
D:\python\python3.13.7\python.exe -m pytest app\tests\test_assets_router.py app\tests\test_analysis_manifest.py cypher-integration\rk3588-edge\tests\test_sync_worker.py -q
D:\python\python3.13.7\python.exe -m pytest app\tests\test_transition_strategy.py -q
```

近期通过的关键测试：

- `test_assets_router.py`
- `test_analysis_manifest.py`
- `test_sync_worker.py`
- `test_transition_strategy.py`

### 14.2 Flutter

```powershell
cd mobile
flutter pub get
flutter analyze
flutter build apk --debug
adb install -r build\app\outputs\flutter-apk\app-debug.apk
```

当前 `flutter analyze` 可能有历史 warning/info，但 debug APK 可构建。

### 14.3 端到端手工验收

最小闭环：

```text
1. App 登录成功。
2. 曲库能拉到 completed 歌曲。
3. 后端 /api/manifest/song/{id} 返回 original + 4 stems。
4. RK 能 GET manifest 中的 /api/assets URL。
5. RK sync-worker 下载 cache 完成。
6. RK /play 播放第一首。
7. RK /xfade 切到第二首。
8. /health 和 /state 返回 current_song_id 更新。
```

建议用 curl 验证：

```bash
curl http://RK_IP:9000/health
curl http://RK_IP:9100/status
curl -r 0-1023 http://BACKEND/api/assets/...
```

---

## 15. 当前风险和缺口

| 优先级 | 问题 | 影响 | 建议 |
|---|---|---|---|
| P0 | RK 换热点后 IP 会变化 | App 无法连接 RK | 做设备发现 / 配对 / 二维码配置；App 中显示当前 RK 地址和健康状态 |
| P0 | 大 stems 走公网下载很慢 | 切歌前缓存来不及 | 现场优先走局域网或 Tailscale；App 需要提前 30 秒以上拉取 |
| P0 | manifest / assets 必须 RK 可访问 | 同步失败 | 部署时固定 `PUBLIC_ASSET_BASE_URL` 并做 RK curl 验收 |
| P1 | 分析结果质量需要人工校准 | 转场听感不稳定 | 建立 100-300 首人工标注集，校准 beatgrid、phrase、vocal、bass risk |
| P1 | RK stem-aware 能力依赖完整缓存 | 听感可能降级 | 在 App UI 明确显示 `stem_aware / non_stem / original_only` |
| P1 | README 与当前 compose 有差异 | 新人部署误解 | 后续统一 README、compose、Jetson 部署文档 |
| P2 | 风格分类仍是规则 + metadata | 精度不如训练模型 | 引入可版本化的 genre / dance style 模型，保留 source/confidence |
| P2 | Session / Live Intent 仍是原型化 | 自动现场调度不完整 | 将 C6 session coordinator 接入真实 edge-agent |

---

## 16. AI Agent 接手顺序

建议按以下顺序读代码：

1. `docs/project.md` 本文。
2. `README.md` 了解原始项目和部署。
3. `docs/DJ_AUTOMIX_REMEDIATION_EXECUTION_SPEC.md` 了解最近一次 automix 修复目标。
4. `docs/song-style-analysis.md` 了解风格分析设计。
5. `app/main.py` 和 `app/modules/router.py`。
6. `app/modules/library/models.py` 和 `app/modules/library/analysis.py`。
7. `app/modules/manifest/__init__.py` 和 `app/modules/manifest/router.py`。
8. `app/modules/dj_control/router.py`, `mixer_rules.py`, `transition_strategy.py`。
9. `mobile/lib/src/api_client.dart`, `edge_agent_client.dart`, `dj_control_page.dart`。
10. `cypher-integration/rk3588-edge/edge-agent/main.py`。
11. `cypher-integration/rk3588-edge/audio-engine/engine.py`。
12. `cypher-integration/rk3588-edge/sync-worker/main.py`。
13. 相关测试：`app/tests/`, `cypher-integration/rk3588-edge/tests/`。

修改原则：

- 不要重写主链路，优先修闭环。
- 不要提交 token、JWT、设备密码、`.env`。
- 不要在 audio callback 中做磁盘 IO、网络请求、JSON 解析或重计算。
- 后端新增字段要兼容旧字段读取。
- RK 接口 schema 改动必须同步 Flutter `EdgeAgentClient`。
- manifest 改动必须同时用 RK curl 验证真实下载。
- 每次改动都说明影响前端、后端、数据库、Jetson、RK 哪一层。

---

## 17. 最近 Git 状态

当前分支：

```text
codex/dj-automix-remediation
```

近期关键提交：

```text
92dcd2f fix(manifest): serve rk-downloadable assets
6f6fc9a fix(manifest): tolerate cross-drive asset paths
859313e fix(automix): remediate rk manifest sync and automation
7e7b57f docs: explain song style analysis pipeline
1de3f07 feat(automix): integrate transition strategy and metadata enrichment
```

最新已推送到：

```text
origin/codex/dj-automix-remediation
```

`docs/project.md` 是本文档，当前作为交接说明文档维护。

---

## 18. 完成交接的最低标准

接手者应至少能做到：

- 说明四端分工：Flutter、FastAPI/Jetson、RK、云网关。
- 找到曲库、分析、DJ Control、manifest、assets、RK sync/play/xfade 的关键代码。
- 解释 `LibrarySong` 中哪些字段用于自动混音。
- 解释 manifest 如何让 RK 下载 original + 4 stems。
- 用 curl 验证后端、Jetson、RK 三端健康状态。
- 用 App 或脚本完成一次 `play → xfade`。
- 知道 stems 缺失或网络慢时系统应如何降级。

---

## 19. 真实部署读档快照

本节记录 2026-06-02 实际连接设备后看到的部署状态。后续排查时，不要只看 Git HEAD，要优先确认设备上真正运行的代码和配置。

### 19.1 Jetson 后端

Jetson 在 Tailscale 中可见，设备名为 `jetson`，Tailscale IP 为 `100.87.142.21`；当前局域网 `wlan0` 地址为 `192.168.5.100/24`。

后端服务：

```text
service: harbeat-api.service
status: active running
workdir: /home/mark/harbeat
command: /home/mark/venvs/harbeat/bin/python /home/mark/venvs/harbeat/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
branch: feature/harbeat-full-project
commit: 79f288d
```

重要现实情况：

- Jetson 工作区是 dirty 状态，有大量未提交修改。
- `app/modules/manifest/router.py` 已经读取 `PUBLIC_ASSET_BASE_URL`。
- `app/modules/manifest/__init__.py` 已经有 `MANIFEST_COMPUTE_SHA256` 开关和 `_stem_status_for_song` 兼容逻辑。
- `.env` 中存在 `PUBLIC_ASSET_BASE_URL=http://8.136.120.255`，所以 RK 下载资源时默认走公网可访问地址。
- `/api/assets/{asset_path:path}` 已部署，用于让 RK 下载原曲和 stems。

如果要改 Jetson 后端，先执行：

```powershell
ssh root@jetson
cd /home/mark/harbeat
git status --short
systemctl status harbeat-api --no-pager
journalctl -u harbeat-api -n 100 --no-pager
```

### 19.2 RK3588

RK 当前换热点后可连接地址为 `192.168.43.7`，SSH 用户为 `cat`。健康检查：

```text
GET http://192.168.43.7:9000/health
audio_ready: true
current_song_id: 6bd0fa93f2794dea860066c914ac9414
plan_id: test_mix_001
session_id: 6e77b85830ee486a9d94fcb020d9df77
gateway_url: http://8.136.120.255
device_id: rk-001
```

RK 上运行三个核心服务：

```text
cypher-audio-engine.service  -> 实际播放、缓存、xfade、stems 混音
cypher-edge-agent.service    -> 手机访问的 HTTP API，端口 9000
cypher-sync-worker.service   -> 资源同步 worker，本地监听 127.0.0.1:9100
```

RK 代码目录：

```text
/home/cat/cypher
branch: main
commit: f9c6797
```

重要现实情况：

- RK 工作区也是 dirty 状态，包含 audio-engine、edge-agent、sync-worker 的未提交修改。
- 日志中已经看到真实成功链路：`prefetch ok`、`playing song_id`、`deck.load hit prefetch cache`、`crossfade start`。
- 曾出现一次 `sounddevice status: output underflow`，说明高负载或缓存不足时音频回调可能欠载。
- `/xfade` 接口真实 schema 是 `to_song_id` + `fade_sec`，不是旧的 `next_song_id` + `duration_sec`。

如果要查 RK：

```powershell
ssh cat@192.168.43.7
cd /home/cat/cypher
git status --short
systemctl status cypher-audio-engine cypher-edge-agent cypher-sync-worker --no-pager
journalctl -u cypher-audio-engine -n 100 --no-pager
journalctl -u cypher-edge-agent -n 100 --no-pager
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9100/status
```

### 19.3 手机 App

USB ADB 可连接手机：

```text
adb serial: 130ddcca
package: com.example.mobile
versionName: 1.0.0
versionCode: 1
lastUpdateTime: 2026-06-02 12:21:06
phone wlan ip: 192.168.43.9/24
rk base url in prefs: http://192.168.43.7:9000
```

手机当前使用 SharedPreferences 保存登录 token 和 RK 地址。不要在文档、日志、commit 中输出 token。

常用检查命令：

```powershell
C:\Android\platform-tools\adb.exe devices
C:\Android\platform-tools\adb.exe shell dumpsys package com.example.mobile | Select-String version
C:\Android\platform-tools\adb.exe shell pidof com.example.mobile
C:\Android\platform-tools\adb.exe logcat -d | Select-String -Pattern "HarBeat|Exception|Timeout|Socket|Dio|http"
```

---

## 20. 导入音频与分析数据详解

### 20.1 导入链路

音频导入入口在后端曲库模块：

```text
app/modules/library/router.py
app/modules/library/schemas.py
app/modules/library/models.py
app/modules/library/background_tasks.py
```

典型流程：

1. 手机或网页调用曲库上传接口。
2. 后端创建 `LibrarySong` 记录，写入基础 metadata。
3. 后台任务开始分析 BPM、key、energy、beat、phrase、vocal、bass risk、genre、dance style、stems。
4. 分析结果写回 `library_songs` 表。
5. manifest 读取这些字段，生成 RK 可下载的资源清单。
6. DJ Control 读取这些字段，决定选歌和切歌策略。

### 20.2 `LibrarySong` 中对混音最重要的字段

基础播放：

| 字段 | 作用 | 主要修改文件 |
| --- | --- | --- |
| `id` / `song_id` | 后端和 RK 传递歌曲身份 | `app/modules/library/models.py`, `mobile/lib/src/models.dart` |
| `title`, `artist` | UI 展示和搜索 | `app/modules/library/schemas.py`, `mobile/lib/src/home_page.dart` |
| `duration` | 计算 outro、过渡窗口、缓存进度 | `analysis.py`, `mixer_rules.py` |
| `source_path` | 原曲所在路径，manifest/assets 下载依赖 | `manifest/__init__.py`, `assets/router.py` |
| `stems` | 4 stems 文件路径和状态 | `models.py`, `manifest/__init__.py`, RK sync-worker |

节拍和结构：

| 字段 | 作用 | 用在哪里 |
| --- | --- | --- |
| `bpm` | 选歌兼容度、beatmatch、BPM ramp | `mixer_rules.py`, `transition_strategy.py`, Flutter DJ Control |
| `beat_points` | beatgrid 基础点位 | `analysis.py`, `mixer_rules.py` |
| `downbeats` | 强拍落点，切入和 drop 对齐 | `mixer_rules.py`, `transition_strategy.py` |
| `phrase_map` | intro/verse/chorus/outro 等乐句 | 智能 exit/entry、长短 fade |
| `cue_points` | hot cue / drop / intro / outro 候选点 | `/api/dj/cut/plan`, `/api/dj/transitions/plan` |
| `beat_grid_offset`, `beat_grid_interval` | beatgrid 校正 | beat 对齐、RK phase anchor |
| `tempo_stability`, `beat_confidence` | 判断是否允许长混或 BPM ramp | transition selector |

调性和风格：

| 字段 | 作用 | 用在哪里 |
| --- | --- | --- |
| `key`, `camelot_key` | harmonic blend、keyDistance | `mixer_rules.py`, `transition_strategy.py` |
| `key_confidence`, `key_profile` | 调性可信度和段落调性变化 | 避免低可信度时强行 harmonic |
| `genre_profile` | genreDistance、跨风格策略 | `genre_classifier.py`, `dance_style.py` |
| `dance_styles` | App 舞种筛选候选 | `/api/dj/styles`, Flutter DJ Control |
| `dance_style_scores` | 舞种排序和置信度 | `/api/dj/styles/pick` |
| `dance_style_status` | 风格分析是否完成 | 曲库 UI 和 DJ Control 降级 |

能量和人声风险：

| 字段 | 作用 | 用在哪里 |
| --- | --- | --- |
| `energy`, `energy_curve` | 能量排序、能量切歌 | `/api/dj/energy/buckets`, `/api/dj/sequence` |
| `loudness_profile` | trim/gain、响度归一 | `mixer_rules.py`, RK audio-engine |
| `vocal_events` | 判断双人声冲突 | `transition_strategy.py`, stem strip |
| `bass_risk_windows` | 判断低频打架风险 | bass swap、eq_swap |
| `transition_windows` | 可用 4/8/16 小节窗口 | transition selector |
| `transition_recommendations` | 分析阶段给出的建议 | DJ Control plan |
| `stem_activity`, `stem_activity_windows` | 每个 stem 活跃时间 | stem-aware xfade |
| `stem_quality_score`, `stem_quality_profile` | 决定是否信任 stems | manifest 和 RK fallback |

### 20.3 分析结果从哪里来

主要实现位置：

```text
app/modules/library/analysis.py
app/modules/library/stem_analysis.py
app/modules/library/genre_classifier.py
app/modules/library/background_tasks.py
```

当前是多源规则和本地分析为主：

- BPM / beatgrid / downbeat：音频分析引擎计算，并写入 beat 相关字段。
- key / camelot：分析引擎或 metadata 推导，后续转成 Camelot 距离。
- energy：整体能量 + 分段能量曲线。
- vocal / bass risk：根据 stem 活跃度、频段、能量窗口推断。
- genre / dance style：`genre_classifier.py` 和 `dance_style.py` 做规则分类、metadata 映射和分数归一。
- stems：分离任务产出 drums、bass、vocals、other/harmonics，写入 `stems` JSON。

后续如果接 Discogs、Spotify、MusicBrainz 或自训练模型，推荐只扩展 `genre_profile` 和 `dance_style_scores` 的来源，不要直接改 DJ Control UI。应保留：

```text
source: metadata | discogs | model | manual
confidence: 0.0 - 1.0
labels: [...]
version: classifier version
```

这样后续可以比较不同来源，不会把外部标签直接写死为唯一真相。

---

## 21. DJ Control 舞种、能量和选歌实现

### 21.1 Flutter 页面

DJ Control 主页面：

```text
mobile/lib/src/dj_control_page.dart
```

它负责：

- 显示能量/风格/实时控制相关卡片。
- 调用后端获取舞种、能量桶、推荐序列、transition plan。
- 调用 RK edge-agent 做 `prefetch`、`play`、`xfade`、`beatReinforce`。
- 保存和读取 RK 地址。
- 在开始播放前尝试保证 RK 已缓存当前歌曲。

后端 API 封装：

```text
mobile/lib/src/api_client.dart
```

RK API 封装：

```text
mobile/lib/src/edge_agent_client.dart
```

### 21.2 舞种选择不是只在前端做

舞种数据来自后端 DJ Control：

```text
app/modules/dj_control/router.py
app/modules/dj_control/dance_style.py
app/modules/library/genre_classifier.py
```

关键接口：

```text
GET  /api/dj/styles
POST /api/dj/styles/pick
POST /api/dj/sequence
POST /api/dj/set/generate
```

当前实现逻辑：

1. 曲库分析阶段给每首歌写入 `dance_styles` 和 `dance_style_scores`。
2. `/api/dj/styles` 汇总当前曲库里可用的舞种。
3. App 选择舞种后，调用 `/api/dj/styles/pick` 或生成 sequence/set。
4. 后端根据舞种分数、能量、BPM、风格距离、可用转场窗口排序。
5. App 只负责展示和发起请求，不应该在 UI 里硬编码舞种分类规则。

如果要改舞种识别：

```text
优先改: app/modules/library/genre_classifier.py
再改:   app/modules/dj_control/dance_style.py
必要时: app/modules/library/models.py / schemas.py
最后改: mobile/lib/src/dj_control_page.dart 的展示
```

如果要改舞种 UI 文案、筛选按钮、卡片布局：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/models.dart
mobile/lib/src/api_client.dart
```

### 21.3 能量排序

能量排序不是 AI 随机排序，核心数据来自 `LibrarySong.energy`、`energy_curve`、`dancefloor_profile` 和 DJ Control 的排序规则。

关键后端接口：

```text
GET  /api/dj/energy/buckets
POST /api/dj/sequence
GET  /api/dj/songs/{song_id}/energy
```

关键代码：

```text
app/modules/dj_control/router.py
app/modules/dj_control/energy.py
app/modules/dj_control/mixer_rules.py
```

如果前端仍显示“AI 排序”，通常只是 UI 文案没跟上。需要改：

```text
mobile/lib/src/dj_control_page.dart
```

推荐文案改成：

```text
能量排序
能量递进
风格切歌
跨风格过渡
```

不要在前端把按钮命名为“AI 排序”后再让后端解释成能量排序，这会导致测试时误判。

---

## 22. 混音技术方案与选择逻辑

### 22.1 总入口

自动混音的后端主入口：

```text
app/modules/dj_control/router.py
app/modules/dj_control/mixer_rules.py
app/modules/dj_control/transition_strategy.py
app/modules/dj_set/
```

Flutter 调用入口：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
mobile/lib/src/edge_agent_client.dart
```

RK 实际执行入口：

```text
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
cypher-integration/rk3588-edge/audio-engine/socket_server.py
cypher-integration/rk3588-edge/audio-engine/engine.py
cypher-integration/rk3588-edge/audio-engine/envelopes.py
cypher-integration/rk3588-edge/audio-engine/mix_plan.py
```

### 22.2 选择逻辑的数据输入

后端选择切歌策略时会看这些信息：

| 输入 | 来源字段 | 决策作用 |
| --- | --- | --- |
| BPM 差 | `bpm` | 决定 long mix、beatmatch、BPM ramp、hard cut |
| 倍速关系 | `bpm` | 判断 70/140、85/170 这类 half-time/double-time |
| 调性距离 | `camelot_key`, `key` | 决定 harmonic blend 或避开双旋律叠加 |
| 风格距离 | `genre_profile`, `dance_styles` | 决定普通混音还是跨风格桥接 |
| 能量差 | `energy`, `energy_curve` | 决定升能量、降能量、drop 进入 |
| 人声风险 | `vocal_events`, `stem_activity_windows` | 决定 vocals 提前退出或延后进入 |
| 低频风险 | `bass_risk_windows`, stems bass | 决定 bass swap |
| 乐句窗口 | `phrase_map`, `downbeats`, `transition_windows` | 决定从哪里出、从哪里进、fade 多长 |
| stems 是否完整 | `stems`, `stem_quality_score` | 决定 stem-aware 还是普通 xfade |

推荐统一上下文结构：

```text
TransitionContext
  bpmDiff
  bpmDiffRatio
  tempoRelation
  keyDistance
  genreDistance
  energyDiff
  vocalConflictRisk
  phraseBarsAvailable
  stemsAvailable
```

这个结构应该只由后端生成，Flutter 不应该自己计算。

### 22.3 当前普通切歌方案

普通切歌规则主要在：

```text
app/modules/dj_control/mixer_rules.py
```

| 方案 | 适用场景 | 技术实现 |
| --- | --- | --- |
| `harmonic_blend` | BPM 接近、key 兼容 | 8/16 小节长 fade，保持乐句边界，尽量保留旋律连续 |
| `eq_swap_4bar` | BPM 接近但低频可能冲突 | 4 小节过渡，中点附近执行 bass swap，避免双 bass |
| `filter_sweep_high` | 风格略不同但 BPM 还能接 | A 高通/低通 sweep，B 逐步进入 |
| `drop_swap` | 两首都有明显 drop | A 在 drop/phrase 结束退出，B 在 downbeat/drop 进入 |
| `echo_tail` | A 需要自然散掉 | A 最后 1 拍/1 小节 echo，B 强拍进入 |
| `loop_roll` | A 结尾弱或无明显落点 | A 做短 loop/roll，制造节奏落点 |
| `spin_back` | BPM/风格跨度大 | 戏剧化切出，不强行叠拍 |
| `drum_only_bridge` | 需要鼓桥 | A 移除 vocal/harmonics/bass，只保留 drums，再引入 B |
| `key_lift` | 情绪上扬 | 利用 key/FX 做上升感，通常结合短 fade |
| `reverb_throw` | A 有 vocal hook | A vocal 加 reverb tail 后退出 |
| `back_to_back_drop` | EDM/drop-driven | smash cut + kick/roll lead-in |

这些方案在后端产出“计划”，RK 端实际只能执行已经传给它的字段。不要以为后端计划里写了某个效果，RK 就一定已经执行；必须检查 Flutter 是否发送、edge-agent 是否接收、audio-engine 是否实现。

### 22.4 新增跨风格策略

跨风格策略在：

```text
app/modules/dj_control/transition_strategy.py
```

它是普通规则上面的一层 selector，用来避免差异很大时强行长时间叠加。

| 策略 | 适用 | 关键动作 | 修改位置 |
| --- | --- | --- | --- |
| `echo_out_hard_drop` | BPM/key/genre 都远 | A bass 降低，echo out，B 强拍进 | `transition_strategy.py`, `mixer_rules.py`, RK FX |
| `percussion_bridge` | 风格不同但要不断舞步 | A/B drums 作为无调性桥，移除 vocal/bass/harmonics | `transition_strategy.py`, `envelopes.py`, `engine.py` |
| `stem_strip_rebuild` | stems 完整、人声冲突明显 | A 按 vocals/harmonics/bass 拆掉，B 按 drums/bass/harmonics/vocals 重建 | `transition_strategy.py`, `envelopes.py` |
| `auto_bpm_ramp` | BPM 差 8%-12% 内 | A 在 4/8 小节变速靠近 B，弱化 vocal/harmonics | `transition_strategy.py`, RK beatmatch |
| `half_time_double_time_pivot` | 70/140、85/170 等倍速 | 不强行同 BPM，用鼓填充切换听感 | `transition_strategy.py`, `mixer_rules.py` |
| `neutral_fx_bridge` | 无 stems 且不兼容 | noise/riser/impact/percussion fill 中性桥 | `transition_strategy.py`, FX assets |
| `breakdown_reset` | A/B 都有 breakdown 或冷启动点 | A 收到 breakdown，短暂 reset 后 B 进 | `transition_strategy.py` |
| `vocal_avoidance_cut` | 双人声风险高 | A vocal 先退，B vocal 延后到 phrase/downbeat | `transition_strategy.py`, `envelopes.py` |

### 22.5 Bass swap 和 vocal handoff

这两个是目前听感最关键的点。

Bass swap 目标：

- 不允许两首歌 bass 长时间同时满音量。
- A bass 在过渡前半段退出。
- B bass 在中点或后半段进入。

主要修改：

```text
app/modules/dj_control/mixer_rules.py
app/modules/dj_control/transition_strategy.py
cypher-integration/rk3588-edge/audio-engine/envelopes.py
cypher-integration/rk3588-edge/audio-engine/engine.py
```

Vocal handoff 目标：

- A 的 vocal 在 B 主体进来前退出。
- B 的 vocal 只在 phrase/downbeat 上进入。
- keyDistance 小时可以允许短暂叠 vocal，否则禁止。

主要修改：

```text
app/modules/library/stem_analysis.py
app/modules/dj_control/transition_strategy.py
cypher-integration/rk3588-edge/audio-engine/envelopes.py
```

---

## 23. RK 实时执行细节

### 23.1 手机到 RK 的命令链路

实时播放不经过 Jetson 转发，手机直接请求 RK：

```text
Flutter DJ Control
  -> EdgeAgentClient
  -> http://RK:9000/play 或 /xfade 或 /prefetch
  -> RK edge-agent
  -> audio-engine socket/http command
  -> sounddevice output
```

关键文件：

```text
mobile/lib/src/edge_agent_client.dart
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
cypher-integration/rk3588-edge/audio-engine/socket_server.py
cypher-integration/rk3588-edge/audio-engine/engine.py
```

### 23.2 开始播放前 30 秒预取

目标行为：

1. 用户点击开始播放。
2. 手机先让 RK 拉取第一首。
3. 如果第一首 original + 4 stems 已拉完，继续预取第二首。
4. 播放过程中，下一首转场前继续预取后续需要混音的 stems。

涉及文件：

```text
mobile/lib/src/dj_control_page.dart       # 何时调用 _ensureRkCache / prefetch
mobile/lib/src/edge_agent_client.dart     # prefetch 请求格式
app/modules/manifest/__init__.py          # manifest 返回 original/stems 下载地址
app/modules/assets/router.py              # RK 真正下载资源
cypher-integration/rk3588-edge/sync-worker/main.py
cypher-integration/rk3588-edge/audio-engine/engine.py
```

如果第二首切第三首出现 `rk409`、`409 conflict`、缓存不完整或无法播放，排查顺序：

1. 手机当前保存的 RK 地址是否正确。
2. RK `/health` 是否 active。
3. App 是否在切歌前调用了 `prefetch`。
4. Jetson manifest 是否返回 200。
5. RK 是否能 curl manifest 中的 `original_url` 和 stem URL。
6. sync-worker 是否还在下载上一首，导致同一 song_id 状态冲突。
7. audio-engine 是否已经在播放/xfade 中，拒绝新的互斥命令。

### 23.3 Stem-aware xfade

后端计划中会产出 `stem_curves`。Flutter 通过 `/xfade` 发送给 RK。RK 如果发现 stems 完整，就走 stem-aware 混音；如果 stems 不完整，应降级到普通 crossfade。

关键文件：

```text
app/modules/dj_control/mixer_rules.py
app/modules/dj_control/transition_strategy.py
mobile/lib/src/edge_agent_client.dart
cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/audio-engine/socket_server.py
cypher-integration/rk3588-edge/audio-engine/engine.py
cypher-integration/rk3588-edge/audio-engine/envelopes.py
```

当前 RK 部署重点注意：

- 已确认 audio-engine 能读取 `stem_curves`。
- Flutter 已经会发送 `fallback_style`、`tempo_ratio`、`stem_curves`、`eq_curves`、`phase_anchor_sec` 等可选字段。
- 但 RK 当前部署的 edge-agent 主要确认转发了 `stem_curves`；`eq_curves` 和 `fallback_style` 是否完整贯通，需要同时检查 `edge_agent/models.py`、`main.py`、`socket_server.py` 和 `engine.py`。
- 所以后续如果要实现真正 EQ 曲线，不能只改 Flutter 或后端计划，必须打通 RK 全链路。

### 23.4 Audio callback 中不能做什么

RK 实时音频最敏感的是 audio callback。以下操作不能放进去：

- 网络请求。
- 磁盘下载。
- JSON 解析。
- 大数组重采样。
- stems 路径查找。
- 日志狂刷。

这些必须提前在 prefetch、load、plan 阶段完成。callback 内只做：

- 读取已经加载/缓存的音频 buffer。
- 根据时间计算 envelope gain。
- 混合 stems/original。
- limiter。
- 写输出 buffer。

如果出现 `output underflow`，优先检查：

```text
audio-engine 是否在 callback 中做了重计算
stems 是否太晚加载
buffer/blocksize 是否太小
设备 CPU 是否被分离/下载任务占满
prefetch 是否没有提前完成
```

---

## 24. 功能修改定位表

### 24.1 登录、注册、用户字段

| 要改什么 | 改哪里 |
| --- | --- |
| 登录接口 | `app/modules/auth/router.py`, `app/modules/auth/schemas.py` |
| 用户表字段 | `app/modules/users/models.py`, migration 或初始化脚本 |
| Flutter 登录 UI | `mobile/lib/src/auth_page.dart` 或登录相关页面 |
| API token 保存 | `mobile/lib/src/api_client.dart`, SharedPreferences |

### 24.2 曲库和导入

| 要改什么 | 改哪里 |
| --- | --- |
| 上传接口 | `app/modules/library/router.py` |
| 歌曲模型字段 | `app/modules/library/models.py`, `schemas.py`, `mobile/lib/src/models.dart` |
| 后台分析任务 | `app/modules/library/background_tasks.py` |
| 原曲路径/资源访问 | `app/modules/assets/router.py`, `app/modules/manifest/__init__.py` |
| Flutter 曲库列表 | `mobile/lib/src/home_page.dart`, `mobile/lib/src/api_client.dart` |

### 24.3 音频分析

| 要改什么 | 改哪里 |
| --- | --- |
| BPM/beat/downbeat | `app/modules/library/analysis.py` |
| phrase/cue/transition windows | `analysis.py`, `mixer_rules.py` |
| vocal/bass/stem 活跃度 | `app/modules/library/stem_analysis.py` |
| energy 曲线 | `analysis.py`, `app/modules/dj_control/energy.py` |
| loudness/trim | `analysis.py`, RK `audio-engine/engine.py` |
| 分析测试 | `app/tests/test_analysis_manifest.py` 或新增 tests |

### 24.4 风格和舞种

| 要改什么 | 改哪里 |
| --- | --- |
| genre 标签来源 | `app/modules/library/genre_classifier.py` |
| dance style 映射 | `app/modules/dj_control/dance_style.py` |
| 舞种 API | `app/modules/dj_control/router.py` |
| 舞种 UI | `mobile/lib/src/dj_control_page.dart` |
| 文档 | `docs/song-style-analysis.md`, `docs/project.md` |

### 24.5 自动选歌和歌单生成

| 要改什么 | 改哪里 |
| --- | --- |
| 能量排序 | `app/modules/dj_control/energy.py`, `router.py` |
| 风格切歌排序 | `dance_style.py`, `router.py` |
| set 生成 | `app/modules/dj_set/` |
| beam search / template | `app/modules/dj_set/` |
| Flutter 5 卡片 UI | `mobile/lib/src/dj_control_page.dart` |

### 24.6 切歌方案和混音策略

| 要改什么 | 改哪里 |
| --- | --- |
| 普通切歌规则 | `app/modules/dj_control/mixer_rules.py` |
| 跨风格策略 | `app/modules/dj_control/transition_strategy.py` |
| transition plan API | `app/modules/dj_control/router.py` |
| stem envelope 曲线 | RK `audio-engine/envelopes.py` |
| xfade 实时混音 | RK `audio-engine/engine.py` |
| xfade schema | `mobile/lib/src/edge_agent_client.dart`, RK `edge_agent/models.py` |

### 24.7 RK 同步和播放

| 要改什么 | 改哪里 |
| --- | --- |
| manifest 内容 | `app/modules/manifest/__init__.py`, `router.py` |
| assets 下载 | `app/modules/assets/router.py` |
| RK 资源同步 | `cypher-integration/rk3588-edge/sync-worker/main.py` |
| RK HTTP API | `cypher-integration/rk3588-edge/edge-agent/main.py` |
| RK API schema | `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py` |
| audio engine socket | `audio-engine/socket_server.py` |
| 播放/xfade/cache | `audio-engine/engine.py`, `deck.py`, `cache.py` |
| systemd 部署 | `cypher-integration/rk3588-edge/deploy/` |

### 24.8 手机实时调试

| 要改什么 | 改哪里 |
| --- | --- |
| RK 地址设置 | `mobile/lib/src/dj_control_page.dart` |
| 网络请求超时 | `mobile/lib/src/api_client.dart`, `edge_agent_client.dart` |
| App build/install | `mobile/pubspec.yaml`, `mobile/android/`, Flutter build |
| 运行日志 | ADB logcat |

---

## 25. 当前部署与 Git 一致性注意事项

目前最容易踩坑的是“本地 Git、Jetson 部署、RK 部署、手机 APK”四者不完全一致。

| 位置 | 当前状态 | 风险 |
| --- | --- | --- |
| 本机仓库 | `codex/dj-automix-remediation`，最新已推 `92dcd2f` | `docs/project.md` 当前未提交 |
| Jetson | `/home/mark/harbeat`，dirty，commit `79f288d` | 现网修复可能没全部进 Git |
| RK | `/home/cat/cypher`，dirty，commit `f9c6797` | audio-engine/edge-agent/sync-worker 有部署态修改 |
| 手机 | debug APK，最后安装 2026-06-02 12:21:06 | 本机改 Flutter 后必须重新 build/install |

因此每次修改建议按这个顺序闭环：

1. 本机改代码。
2. 本机跑 Python/Flutter 测试。
3. 部署 Jetson 或 RK。
4. 在设备上 `git diff` 或 grep 确认代码真的变化。
5. `systemctl restart` 对应服务。
6. `journalctl` 看启动日志。
7. 手机重新安装 APK。
8. 用真实手机发起 `prefetch -> play -> xfade`。
9. RK 日志确认 `prefetch ok`、`playing`、`crossfade start`。
10. 再 commit/push。

---

## 26. 修改混音听感时的推荐路径

如果用户反馈“中间旋律没接好、节奏没接好、人声太早进”，不要直接改 RK 混音代码。先按下面顺序定位：

1. 看这两首歌的分析数据是否正确：

```text
bpm
downbeats
phrase_map
vocal_events
bass_risk_windows
stem_activity_windows
stems
```

2. 看后端选了什么策略：

```text
POST /api/dj/transitions/plan
POST /api/dj/cut/plan
```

3. 看计划里有没有表达正确意图：

```text
exit_sec / entry_sec
fade_sec
style / strategy
stem_curves
beat_reinforce
prewarm_beatmatch
```

4. 看 Flutter 是否把这些字段发给 RK：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/edge_agent_client.dart
```

5. 看 RK edge-agent 是否接收并转发：

```text
edge-agent/edge_agent/models.py
edge-agent/main.py
```

6. 看 audio-engine 是否真正执行：

```text
audio-engine/socket_server.py
audio-engine/engine.py
audio-engine/envelopes.py
```

针对具体听感问题：

| 听感问题 | 优先修改 |
| --- | --- |
| War vocal 太早进 | `transition_strategy.py` 的 vocal handoff 阈值，RK `envelopes.py` 的 vocals in_late |
| Rump Shaker melody 清不干净 | A 的 harmonics/other 曲线，`stem_strip_rebuild` |
| bass 糊 | bass swap 时间点，A bass 提前 out，B bass 延后 in |
| 鼓断了 | `percussion_bridge` 或 beat reinforce |
| 切得太突兀 | phrase/downbeat 选择，fade_sec，echo/reverb tail |
| RK 播不了 | manifest/assets/sync-worker/edge-agent schema |

这套顺序可以避免“后端计划是对的，但 RK 没执行”或“RK 能执行，但 Flutter 没传字段”的误判。
