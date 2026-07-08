# HarBeat DJ Control 真实运行链路与开发修改文档

版本：2026-07-08
适用对象：手机端 HarBeat DJ Control、RK/LubanCat 边缘播放端、HarBeat 后端/Jetson 算法与资源服务
用途：作为后续优化 DJ Control 播放、同步、转场、状态回传的开发依据。

## 1. 本文边界

本文只记录当前已经在真机或源码中确认的流程，不把未启用能力写成已运行事实。

本文覆盖：

- 手机用户从打开 App 到进入 DJ Control 的完整操作链路。
- 用户选歌、排序、开始混音、自动转场、FX、能量/风格切歌等操作对应的后台请求。
- 手机端、业务后端、RK edge-agent、RK sync-worker、RK audio-engine 之间的真实调用关系。
- 当前已验证的真实运行状态、端口、缓存、播放层级。
- 当前实现中的风险点和优化入口。

本文不覆盖：

- 机械结构、BOM、硬件键盘电路。
- 新算法设计细节。
- 未来量产通信协议设计。

## 2. 本次真机验证结论

验证时间：2026-07-08 17:53-18:00 左右，Asia/Shanghai
手机包名：`com.example.mobile`
RK/LubanCat：`192.168.43.7`
手机 WLAN 地址：日志中显示请求来源为 `192.168.43.9`
开发机地址：日志中显示调试请求来源为 `192.168.43.6`

### 2.1 手机当前真实配置

手机 SharedPreferences 中只保存了登录 token，没有保存自定义 API/RK 地址。

因此手机当前使用代码默认值：

| 项目 | 当前真实值 |
|---|---|
| 业务 API Base URL | `http://8.136.120.255` |
| RK Edge-Agent URL | `http://192.168.43.7:9000` |
| RK Sync-Worker URL | 从 RK 地址推导为 `http://192.168.43.7:9100` |

对应源码：

- `mobile/lib/src/app.dart`
- `mobile/lib/src/edge_agent_client.dart`
- `mobile/lib/src/sync_worker_client.dart`

### 2.2 RK 当前真实服务

RK 上 systemd 服务全部 active：

```text
cypher-edge-agent.service
cypher-audio-engine.service
cypher-sync-worker.service
cypher-input-daemon.service
```

真实监听端口：

| 端口 | 服务 | 状态 |
|---:|---|---|
| `9000` | edge-agent | 已监听 |
| `9100` | sync-worker | 已监听 |
| `9001` | WebSocket | 当前未监听 |

重要结论：

- 当前手机不是通过 WebSocket 收播放状态。
- 当前手机通过高频 HTTP 轮询 `GET /state` 获得播放状态。

### 2.3 RK 当前真实后端资源地址

RK 环境变量文件：

```text
/home/cat/cypher/deploy/cypher.env
```

当前真实配置：

```text
JETSON_BASE_URL=http://8.136.120.255
```

重要结论：

- 虽然 Tailscale 中 `jetson` 的 HTTP 服务 `http://100.87.142.21:8000` 可访问，但 RK 当前并没有直接使用该地址。
- 当前 RK sync-worker 拉 manifest、音频、default render 资源时，使用的是阿里云网关 `http://8.136.120.255`。
- 文档和代码中继续叫 `JETSON_BASE_URL` 会造成理解混乱，后续建议改名为 `HARBEAT_API_BASE_URL` 或 `RESOURCE_BASE_URL`。

### 2.4 本次播放真实发生的事件

手机正常播放后，RK `/state` 返回：

```json
{
  "playing": true,
  "current_song_id": "fba025a6ef6e4ae7aa50ad1bc3e1c3f0",
  "position_sec": 159.707,
  "duration_sec": 249.587,
  "playback_tier": "basic"
}
```

后端确认该歌曲为：

```text
Big Poppa - The Notorious B.I.G.
```

17:57:25，edge-agent 日志确认手机触发：

```text
POST /autoplay/default/render
```

同一时间 audio-engine 日志确认：

```text
crossfade start fba025a6ef6e4ae7aa50ad1bc3e1c3f0 -> 3083c66434a84af3b5ad4bee34d6d673
```

后端确认目标歌曲为：

```text
So Fresh, So Clean - OutKast
```

切歌后 `/state` 返回：

```json
{
  "playing": true,
  "current_song_id": "3083c66434a84af3b5ad4bee34d6d673",
  "playback_tier": "basic",
  "last_transition": {
    "action": "default_render_resume",
    "playback_tier": "default_render_playback",
    "degraded": false
  }
}
```

重要结论：

- 当前使用的是 default preset 的 default render 分支。
- default render 只负责转场片段。
- 转场片段播完后，audio-engine 恢复播放目标歌曲 original 音频。
- 实时 `playback_tier` 回到 `basic`。
- 当前不是 stem-aware 播放。

### 2.5 当前缓存真实状态

当前歌曲缓存：

```text
/home/cat/cypher/cache/fba025a6ef6e4ae7aa50ad1bc3e1c3f0/original.mp3
```

目标歌曲缓存：

```text
/home/cat/cypher/cache/3083c66434a84af3b5ad4bee34d6d673/original.mp3
```

default render 缓存：

```text
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render.wav
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render_meta.json
```

重要结论：

- 当前播放链路只依赖 original 音频和 default render 转场片段。
- 当前没有使用 `vocals/drums/bass/other` 四轨 stems。

## 3. 当前真实总体架构

```text
手机 HarBeat App
  |
  |-- HarBeatApiClient
  |     -> http://8.136.120.255
  |        登录、曲库、歌单、DJ 排序、转场计划、manifest、default render 资源
  |
  |-- EdgeAgentClient
  |     -> http://192.168.43.7:9000
  |        播放控制、状态查询、转场执行、FX 触发
  |
  |-- SyncWorkerClient
        -> http://192.168.43.7:9100
           缓存检查、资源同步、同步进度查询

RK/LubanCat
  |
  |-- edge-agent :9000
  |     HTTP API，接收手机播放控制
  |     通过 Unix socket 转发命令给 audio-engine
  |
  |-- sync-worker :9100
  |     从 http://8.136.120.255 下载音频/转场资源
  |     写入 /home/cat/cypher/cache/
  |
  |-- audio-engine
        监听 /tmp/cypher-audio.sock
        实际解码、播放、转场、恢复目标歌曲
```

## 4. 关键代码模块

### 4.1 手机端

| 文件 | 作用 |
|---|---|
| `mobile/lib/src/app.dart` | App 启动、恢复 token、默认 API/RK 地址、设置页地址保存 |
| `mobile/lib/src/home_page.dart` | 首页、曲库、歌单、进入 DJ Control、创建 EdgeAgentClient |
| `mobile/lib/src/dj_control_page.dart` | DJ Control 主流程：选歌、排序、同步、开始播放、自动转场、手动切歌、FX |
| `mobile/lib/src/api_client.dart` | 业务后端 API 客户端 |
| `mobile/lib/src/edge_agent_client.dart` | RK edge-agent 客户端 |
| `mobile/lib/src/sync_worker_client.dart` | RK sync-worker 客户端 |

### 4.2 业务后端/Jetson 侧

| 文件 | 作用 |
|---|---|
| `app/modules/dj_control/router.py` | `/api/dj/*`：排序、能量、转场计划、default render |
| `app/modules/dj_control/sequencer.py` | 歌曲排序、default preset、能量曲线 |
| `app/modules/dj_control/cut_strategy.py` | fast cut、能量切歌、目标风格切歌候选选择 |
| `app/modules/dj_control/default_mix/*` | default mix 计划与 render 资源 |
| `app/modules/library/router.py` | 曲库歌曲详情、分析、manifest 相关入口 |

### 4.3 RK 侧

| 文件 | 作用 |
|---|---|
| `cypher-integration/rk3588-edge/edge-agent/main.py` | RK HTTP 控制入口，端口 9000 |
| `cypher-integration/rk3588-edge/edge-agent/edge_agent/audio_client.py` | edge-agent 到 audio-engine 的 Unix socket 客户端 |
| `cypher-integration/rk3588-edge/sync-worker/main.py` | RK 资源同步服务，端口 9100 |
| `cypher-integration/rk3588-edge/audio-engine/socket_server.py` | audio-engine Unix socket 服务端 |
| `cypher-integration/rk3588-edge/audio-engine/engine.py` | 实际播放、预解码、crossfade、default render resume |

## 5. 用户操作到后台触发的完整流程

### 5.1 用户打开 App

用户操作：

```text
打开 HarBeat App
```

手机端触发：

1. `RootPage.initState()`
2. `_restoreSession()`
3. 从 SharedPreferences 读取：
   - `harbeat_token`
   - `harbeat_api_base_url`
   - `harbeat_rk_base_url`

当前真机状态：

- 只读到 `harbeat_token`。
- 没有读到自定义 API/RK 地址。
- 使用默认：
  - `http://8.136.120.255`
  - `http://192.168.43.7:9000`

后台请求：

```text
GET http://8.136.120.255/api/auth/me
GET http://8.136.120.255/api/library/songs
GET http://8.136.120.255/api/playlists?user_id={user_id}
```

作用：

- 验证 token。
- 获取用户信息。
- 拉取曲库。
- 拉取歌单。

失败表现：

- token 失效：手机清除 token，回到登录页。
- API 地址不可达：首页显示网络请求失败。

### 5.2 用户登录

用户操作：

```text
输入用户名/密码 -> 点击登录
```

后台请求：

```text
POST /api/auth/login
GET  /api/auth/me
GET  /api/library/songs
GET  /api/playlists
```

成功后：

- 手机保存 `harbeat_token`。
- 进入 HomePage。

### 5.3 用户进入 DJ Control

用户操作：

```text
点击底部导航 DJ Control
```

手机端对象创建：

```text
DjControlPage(
  apiClient: HarBeatApiClient(http://8.136.120.255),
  edgeClient: EdgeAgentClient(http://192.168.43.7:9000),
  token: 当前用户 token,
  userId: 当前用户 ID,
  librarySongs: 当前曲库
)
```

同时创建：

```text
SyncWorkerClient(http://192.168.43.7:9100)
```

后台请求：

```text
GET  /api/dj/sequence/presets
GET  /api/dj/transitions/rules
GET  /api/dj/fx
GET  /api/playlists?user_id={user_id}
GET  /api/dj/energy/buckets
```

用途：

- 加载 DJ 排序 preset。
- 加载转场规则。
- 加载 FX catalog。
- 加载歌单。
- 加载能量桶配置。

### 5.4 用户选歌

用户操作：

```text
在 DJ Control Step 1 中添加歌曲
```

手机端行为：

- 将 `LibrarySong` 加入 `_picked`。
- 如果已有 live session，会先尝试 `POST /pause` 停掉 RK。
- 清空已有 sequence、auto sets、active plans。

后台请求：

- 单纯添加本地已加载曲库歌曲时，不一定触发后端。
- 如果通过歌单详情导入，会触发：

```text
GET /api/playlists/{playlist_id}
```

### 5.5 用户使用 Vibe/外部歌单导入

用户操作：

```text
输入 vibe 描述 / 粘贴歌单链接 / 下载歌曲
```

可能触发的业务后端请求：

```text
POST /api/recommendations/vibe-search
POST /api/recommendations/import-from-vibe
POST /api/fangpi/parse-playlist
POST /api/fangpi/batch-search
POST /api/fangpi/download
POST /api/playlists/create
POST /api/playlists/{playlist_id}/add-songs
```

后端职责：

- 搜索/解析外部歌曲。
- 下载音频到服务端。
- 进行曲库入库。
- 后台或同步触发音频分析。

注意：

- 这些属于选歌/曲库准备阶段，不会直接让 RK 播放。
- 只有后续开始混音或播放单曲时，才会同步到 RK。

### 5.6 用户点击排序/生成方案

用户操作：

```text
Step 2 点击排序 / 生成 DJ set
```

当前手机有两类排序入口。

#### 5.6.1 普通 sequence 排序

后台请求：

```text
POST /api/dj/sequence
```

请求体：

```json
{
  "song_ids": ["..."],
  "preset": "default 或 battle_4rounds 等"
}
```

后端处理：

- 根据 preset 调用 `sequencer.sequence_songs_with_details()`。
- 返回排序后的 sequence：

```json
{
  "preset": "default",
  "sequence": [
    {
      "position": 0,
      "song_id": "...",
      "target_energy": 0.5,
      "actual_energy": 0.7
    }
  ],
  "ordering_mode": "...",
  "pair_scores": [],
  "pair_breakdowns": []
}
```

手机处理：

- 保存 `_sequence`。
- 后台异步为每首歌加载能量：

```text
GET /api/dj/songs/{song_id}/energy?style={style}
```

#### 5.6.2 自动 DJ set 生成

后台请求：

```text
POST /api/dj/set/generate
```

请求体：

```json
{
  "song_ids": ["..."],
  "drop_failed": false
}
```

后端处理：

- 生成多个候选 DJ set。
- 每个 set 包含：
  - tracks
  - energy_curve
  - transitions
  - purposes
  - plans
  - quality
  - score

手机处理：

- 保存 `_autoSets`。
- 默认选择第一个 set。
- 将 set 转换为旧版 `_sequence` 结构，供后续播放流程复用。

### 5.7 用户点击开始混音

用户操作：

```text
Step 3 点击开始混音 / 开始播放
```

手机入口：

```text
_startLiveMix()
```

完整后台流程如下。

#### 5.7.1 停止旧播放

手机请求：

```text
POST http://192.168.43.7:9000/pause
```

RK edge-agent：

- 收到 `/pause`。
- 转发 Unix socket 命令：

```json
{"cmd": "pause"}
```

audio-engine：

- 设置 `_paused = true`。
- 返回 paused 状态。

目的：

- 防止新 set 继承上一轮播放状态。

#### 5.7.2 准备 live 候选池

手机请求：

```text
POST http://8.136.120.255/api/dj/live/pool/prepare
```

请求体核心字段：

```json
{
  "active_queue_song_ids": ["..."],
  "style": "hiphop/breaking/generic...",
  "target_reserve_per_bucket": 2,
  "include_buckets": ["30-40", "40-50", "..."],
  "exclude_song_ids": []
}
```

后端返回：

```json
{
  "reserve_pool": {
    "60-70": ["song_id"]
  },
  "style_reserve_pool": {
    "hiphop": ["song_id"]
  },
  "energy_profiles": {
    "song_id": {
      "dance_energy_score": 80,
      "bucket": "80-90"
    }
  }
}
```

手机保存：

- `_reservePoolByBucket`
- `_styleReservePoolByStyle`
- `_liveEnergyProfiles`

用途：

- 支持后续目标能量切歌。
- 支持后续目标风格切歌。
- 支持候选池提前同步到 RK。

#### 5.7.3 等待 sync-worker 空闲

手机请求：

```text
GET http://192.168.43.7:9100/status
```

sync-worker 返回：

```json
{
  "running": false,
  "plan_id": "...",
  "total": 14,
  "downloaded": 14,
  "completed": 14,
  "percent": 100,
  "errors": []
}
```

如果 `running=true`：

- 手机会等待。
- 避免重复启动同步任务。

#### 5.7.4 检查 RK 缓存

手机对每首候选歌曲请求：

```text
GET http://192.168.43.7:9100/cache/check?song_id={song_id}&kind=original
```

sync-worker 检查路径：

```text
/home/cat/cypher/cache/{song_id}/original.mp3
/home/cat/cypher/cache/{song_id}/original.wav
```

如果缓存存在：

```json
{
  "ok": true,
  "exists": true,
  "path": "/home/cat/cypher/cache/{song_id}/original.mp3",
  "ext": "mp3"
}
```

如果缓存不存在：

- 手机向业务后端获取 manifest。

#### 5.7.5 获取歌曲 manifest

手机请求：

```text
GET http://8.136.120.255/api/manifest/song/{song_id}
```

后端返回 manifest，核心结构：

```json
{
  "manifest": {
    "song_id": "...",
    "files": {
      "original": {
        "url": "/api/stream/{song_id}",
        "format": "mp3",
        "size": 123456,
        "sha256": "..."
      },
      "stems": {
        "vocals": {...},
        "drums": {...},
        "bass": {...},
        "other": {...}
      }
    },
    "qualityFlags": {
      "has_stems": true
    }
  }
}
```

当前真实播放链路：

- 实际只同步了 original。
- 未同步/未使用 stems。

#### 5.7.6 启动 RK 资源同步

手机请求：

```text
POST http://192.168.43.7:9100/sync
```

请求体：

```json
{
  "plan_id": "mobile-...",
  "tracks": [
    {
      "song_id": "...",
      "files": {
        "original": {
          "url": "http://8.136.120.255/api/stream/...",
          "format": "mp3"
        }
      }
    }
  ]
}
```

sync-worker 处理：

1. 解析 manifest。
2. 提取需要下载的 files。
3. 将相对 URL 拼接到 `JETSON_BASE_URL`。
4. 使用 httpx 下载，失败时 fallback 到 curl。
5. 写入：

```text
/home/cat/cypher/cache/{song_id}/original.mp3
```

如果是 default mix，还会下载：

```text
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render.wav
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render_meta.json
```

本次真机确认：

```json
{
  "running": false,
  "plan_id": "default-mix-render-sync-1783504406790",
  "total": 14,
  "downloaded": 14,
  "completed": 14,
  "percent": 100,
  "errors": []
}
```

#### 5.7.7 校验 RK 可播放缓存

手机请求：

```text
POST http://192.168.43.7:9000/cache/validate
```

请求体：

```json
{
  "song_ids": ["..."],
  "require_stems": false
}
```

edge-agent 转发给 audio-engine：

```json
{
  "cmd": "validate_cache",
  "song_ids": ["..."],
  "require_stems": false
}
```

audio-engine 校验：

- 是否存在 original 音频。
- 是否可解码。
- 如果 `require_stems=false`，不强制检查四轨 stems。

当前真实状态：

- `require_stems=false`。
- `playback_tier=basic`。

#### 5.7.8 预解码队列

手机请求：

```text
POST http://192.168.43.7:9000/prefetch
```

当前手机端在正式开始播放前的请求体：

```json
{
  "song_ids": ["..."],
  "wait": true,
  "load_stems": false
}
```

edge-agent 转发：

```json
{
  "cmd": "prefetch",
  "song_ids": ["..."],
  "wait": true,
  "load_stems": false
}
```

audio-engine 行为：

- 将 original 音频解码进内存 prefetch cache。
- 当前 DJ Control 启动播放路径不加载 stems。
- 如果未来把 `load_stems` 改回 `true`，也只有在 RK 缓存里真实存在 stems 时才会加载 stems。

当前真机日志：

```text
prefetch ok: fba025a6ef6e4ae7aa50ad1bc3e1c3f0 in 1193ms
prefetch ok: 3083c66434a84af3b5ad4bee34d6d673 in 1601ms
```

注意：

- 当前代码为了稳定播放，启动路径显式使用 `load_stems=false`。
- 当前缓存目录只有 original.mp3，因此实际仍是 basic/original 播放。
- default preset 分支还会调用 `/autoplay/default/prefetch`，用于让 audio-engine 检查队列歌曲和 default render 资源，而不是启用 stems。

## 6. default preset 播放分支

本次真机实际走的是 default preset 的 default render 分支。

### 6.1 生成 default transition plan

手机为相邻歌曲请求：

```text
POST http://8.136.120.255/api/dj/transitions/plan
```

请求体：

```json
{
  "prev_song_id": "...",
  "next_song_id": "...",
  "cursor_sec": 0,
  "rule_key": "default_mix_auto",
  "transition_mode": "default_mix",
  "eq_mix_user_mode": "render",
  "target_lufs": -14
}
```

后端处理：

1. 调用 default transition planner。
2. 生成 pair_id。
3. 确保 reference render 资源存在。
4. 返回：

```json
{
  "transition_mode": "default_mix",
  "execution_mode": "default_render_playback",
  "pair_id": "...",
  "transition_render_url": "http://.../api/dj/default/render/{pair_id}",
  "default_mix": {
    "from_song_id": "...",
    "to_song_id": "...",
    "transition_render_path": "...",
    "to_at_sec": 0.603,
    "resume_at_sec": 14.418
  }
}
```

### 6.2 同步 default render 资源

手机调用 sync-worker：

```text
POST http://192.168.43.7:9100/sync
```

请求中包含：

```json
{
  "default_mix_pairs": [
    {
      "pair_id": "...",
      "files": {
        "transition_render": {
          "url": "/api/dj/default/render/{pair_id}"
        },
        "transition_render_meta": {
          "url": "/api/dj/default/render/{pair_id}/meta"
        }
      }
    }
  ]
}
```

sync-worker 下载：

```text
GET http://8.136.120.255/api/dj/default/render/{pair_id}
GET http://8.136.120.255/api/dj/default/render/{pair_id}/meta
```

写入：

```text
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render.wav
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render_meta.json
```

### 6.3 启动 default autoplay

手机请求：

```text
POST http://192.168.43.7:9000/autoplay/default/prefetch
POST http://192.168.43.7:9000/autoplay/default/start
```

`/autoplay/default/prefetch` 用于确认：

- 队列歌曲可预解码。
- default render wav/json 都存在。

`/autoplay/default/start` 用于开始播放第一首。

edge-agent 转发给 audio-engine：

```json
{
  "cmd": "default_autoplay_start",
  "queue": ["..."],
  "transitions": [{...}],
  "start_song_id": "...",
  "start_at_sec": 0,
  "session_id": "mobile-..."
}
```

本次真机实际播放第一首：

```text
Big Poppa - The Notorious B.I.G.
```

### 6.4 default render 自动转场

手机持续轮询：

```text
GET http://192.168.43.7:9000/state
```

轮询频率：

```text
约 600ms 一次
```

当手机判断到达转场时机后，调用：

```text
POST http://192.168.43.7:9000/autoplay/default/render
```

请求体：

```json
{
  "transition_plan": {...},
  "to_song_id": "3083c66434a84af3b5ad4bee34d6d673"
}
```

edge-agent 转发：

```json
{
  "cmd": "default_render_playback",
  "transition_plan": {...},
  "to_song_id": "...",
  "render_path": null
}
```

audio-engine 执行：

1. 找到本地 default render wav。
2. 播放该 wav 作为转场片段。
3. 计算 render offset。
4. 片段完成后加载目标歌曲 original。
5. 从 `resume_at_sec` 继续播放目标歌曲。

本次真机日志：

```text
POST /autoplay/default/render
crossfade start fba025a6ef6e4ae7aa50ad1bc3e1c3f0 -> 3083c66434a84af3b5ad4bee34d6d673
deck.load hit prefetch cache: 3083c66434a84af3b5ad4bee34d6d673
```

最终 `/state`：

```json
{
  "current_song_id": "3083c66434a84af3b5ad4bee34d6d673",
  "playback_tier": "basic",
  "last_transition": {
    "action": "default_render_resume",
    "playback_tier": "default_render_playback"
  }
}
```

解释：

- `last_transition.playback_tier=default_render_playback` 表示上一次转场使用了 default render。
- 当前实时 `playback_tier=basic` 表示现在目标歌曲已经回到 original 普通播放。

## 7. 非 default preset 播放分支

该分支在源码中存在，本次现场没有直接验证完整切歌，但代码路径明确。

用户选择非 default preset 后，开始播放流程仍会：

1. 准备 live pool。
2. 同步候选池到 RK。
3. 为相邻歌曲预生成 transition plan。
4. 调用 RK `/play` 播放第一首。
5. 轮询 `/state`。
6. 到点后调用 RK `/xfade`。

### 7.1 生成 section_match transition plan

手机请求：

```text
POST http://8.136.120.255/api/dj/transitions/plan
```

请求体：

```json
{
  "prev_song_id": "...",
  "next_song_id": "...",
  "cursor_sec": 0,
  "rule_key": "...",
  "transition_mode": "section_match",
  "eq_mix_user_mode": "auto",
  "target_lufs": -14
}
```

后端返回：

```json
{
  "transition_mode": "section_match",
  "execution_mode": "...",
  "from_at_sec": 123.4,
  "to_at_sec": 8.0,
  "fade_sec": 6.0,
  "rule_key": "...",
  "rule_label_zh": "...",
  "tempo_ratio": 1.02,
  "stem_curves": {...},
  "eq_curves": {...}
}
```

### 7.2 手机触发 RK xfade

手机请求：

```text
POST http://192.168.43.7:9000/xfade
```

请求体：

```json
{
  "to_song_id": "...",
  "fade_sec": 6,
  "to_at_sec": 8,
  "style": "blend",
  "transition_id": "...",
  "tempo_ratio": 1.02,
  "stem_curves": {...},
  "eq_curves": {...},
  "transition_mode": "eq_band_mix 或 ordinary_xfade",
  "transition_plan": {...}
}
```

edge-agent 转发给 audio-engine：

```json
{
  "cmd": "xfade",
  "to_song_id": "...",
  "fade_sec": 6,
  "to_at_sec": 8,
  "style": "blend",
  "tempo_ratio": 1.02,
  "stem_curves": {...},
  "eq_curves": {...}
}
```

audio-engine：

- 加载目标歌曲到 inactive deck。
- 如果 stems 可用且需要 stem-aware，则加载 stems。
- 如果 stems 不可用，则降级为 original/non-stem/basic 风格。
- 执行 crossfade。

当前注意：

- 本次真机没有看到 stems。
- 所以即使 plan 中有 `stem_curves`，如果 RK 缓存没有 stems，最终仍会降级。

## 8. 手动切歌流程

### 8.1 用户点击 fast cut / energy up / energy down

用户操作：

```text
实时控制页点击快速切歌/能量上升/能量下降
```

手机请求业务后端：

```text
POST /api/dj/cut/plan
```

请求体：

```json
{
  "strategy": "fast_cut 或 energy_up_cut 或 energy_down_cut",
  "current_song_id": "...",
  "cursor_sec": 123.4,
  "queue_song_ids": ["..."],
  "current_index": 0,
  "pool_song_ids": ["..."],
  "max_wait_sec": 5
}
```

后端职责：

- 选择下一首。
- 必要时从 pool 中替换队列下一首。
- 附加 prepared section transition。

后端返回：

```json
{
  "next_song_id": "...",
  "switch_at_sec": 123.4,
  "prepared_transition": {...}
}
```

手机随后调用：

```text
POST http://192.168.43.7:9000/xfade
```

最终由 audio-engine 执行切歌。

## 9. 目标能量切歌流程

用户操作：

```text
实时控制页点击某个能量桶，例如 70-80
```

手机先做 preview：

```text
POST /api/dj/cut/plan
```

请求体：

```json
{
  "strategy": "target_energy_bucket",
  "intent": "target_energy_bucket",
  "mode": "preview",
  "current_song_id": "...",
  "cursor_sec": 123.4,
  "active_queue_song_ids": ["..."],
  "reserve_pool_song_ids": ["..."],
  "played_song_ids": ["..."],
  "blocked_song_ids": ["..."],
  "exclude_song_ids": ["..."],
  "cached_song_ids": ["..."],
  "syncing_song_ids": [],
  "target_energy_bucket": {
    "min": 70,
    "max": 80
  },
  "current_style": "hiphop",
  "prefer_cached": true
}
```

后端返回：

```json
{
  "selected_song": {
    "song_id": "...",
    "title": "...",
    "energy_score": 75,
    "bucket": "70-80",
    "cache_status": "ready/missing"
  },
  "prepared_transition": {...},
  "reason": []
}
```

手机行为：

1. 如果目标歌未缓存，先同步/预解码。
2. 保存 `_targetEnergyPreview`。
3. 用户确认后，调用：

```text
POST http://192.168.43.7:9000/xfade
```

## 10. 目标风格切歌流程

用户操作：

```text
实时控制页点击 Breaking / Hip Hop / Popping 等目标风格
```

手机 preview 请求：

```text
POST /api/dj/cut/plan
```

请求体：

```json
{
  "strategy": "target_dance_style",
  "intent": "target_dance_style",
  "mode": "preview",
  "current_song_id": "...",
  "cursor_sec": 123.4,
  "target_style": "breaking",
  "active_queue_song_ids": ["..."],
  "style_reserve_pool_song_ids": ["..."],
  "played_song_ids": ["..."],
  "blocked_song_ids": ["..."],
  "cached_song_ids": ["..."],
  "syncing_song_ids": [],
  "current_style": "hiphop",
  "prefer_cached": true
}
```

后端返回：

```json
{
  "selected_song": {
    "song_id": "...",
    "style_score": 0.9,
    "source": "active_queue/style_reserve_pool/library"
  },
  "prepared_transition": {...},
  "recommended_transition_hint": "..."
}
```

用户确认后：

```text
POST http://192.168.43.7:9000/xfade
```

## 11. FX Pad 流程

用户操作：

```text
点击 FX Pad
```

手机流程：

1. 在 `_fxItems` 中查找对应 FX。
2. 如果 FX 有 `rk_key`，优先触发 RK。
3. 如果 RK 触发失败，回退为手机本地播放 FX wav。

优先路径：

```text
POST http://192.168.43.7:9000/trigger
```

请求体：

```json
{
  "key": 1
}
```

edge-agent 转发：

```json
{
  "cmd": "trigger",
  "key": 1
}
```

audio-engine：

- 根据 key 播放 sample 或执行暂停/恢复等动作。

回退路径：

```text
GET http://8.136.120.255/api/dj/fx/{fx_key}.wav
```

手机用本地 `just_audio` 播放。

## 12. 播放状态更新流程

当前真实状态：

- RK 未监听 `9001`。
- 手机通过 HTTP 轮询。

手机轮询：

```text
GET http://192.168.43.7:9000/state
```

频率：

```text
约每 600ms 一次
```

edge-agent 处理：

1. 通过 Unix socket 向 audio-engine 发送：

```json
{"cmd": "state"}
```

2. audio-engine 返回：

```json
{
  "playing": true,
  "paused": false,
  "current_song_id": "...",
  "position_sec": 123.4,
  "duration_sec": 249.5,
  "playback_tier": "basic",
  "last_transition": {}
}
```

3. edge-agent 转成 RKPlaybackState 返回给手机。

手机更新：

- `_isPlaying`
- `_position`
- `_duration`
- `_rkCurrentSongId`
- `_rkExecutionHint`

手机随后调用 `_maybeAutoXfade()` 判断是否需要自动转场。

## 13. edge-agent 到 audio-engine 的内部协议

edge-agent 不直接播放音频。

内部调用方式：

```text
edge-agent HTTP API
  -> /tmp/cypher-audio.sock
  -> audio-engine socket_server
  -> engine.py
```

socket 协议：

```text
4 字节 big-endian JSON 长度 + JSON body
```

示例：播放

```json
{
  "cmd": "play",
  "song_id": "fba025a6ef6e4ae7aa50ad1bc3e1c3f0",
  "start_at_sec": 0
}
```

示例：default render 播放

```json
{
  "cmd": "default_render_playback",
  "transition_plan": {...},
  "to_song_id": "3083c66434a84af3b5ad4bee34d6d673",
  "render_path": null
}
```

示例：普通 xfade

```json
{
  "cmd": "xfade",
  "to_song_id": "...",
  "fade_sec": 6,
  "to_at_sec": 8,
  "style": "blend",
  "tempo_ratio": 1.02,
  "stem_curves": {...},
  "eq_curves": {...}
}
```

## 14. 当前实现中必须注意的真实问题

### 14.1 `next_song_id` 当前不能完全信任

本次验证中曾看到：

```json
{
  "next_song_id": "e4d49cd6ba5f48058a8fad217ce6661a"
}
```

但用当前用户 token 查询后端：

```text
404 song not found
```

后续实际切到的是：

```text
3083c66434a84af3b5ad4bee34d6d673
```

开发结论：

- default render 分支中，`state.next_song_id` 可能是旧状态或不代表最终切歌目标。
- 手机端不要只依赖 RK `/state.next_song_id` 决定 UI 队列。
- 应以手机 `_sequence` / `_preparedTransitionPlans` 作为队列真相。
- RK `/state.next_song_id` 只作为辅助显示。

### 14.2 当前没有 WebSocket 状态推送

源码和 README 中提过 `9001/ws`，但真机 `ss -lntp` 没有监听 `9001`。

开发结论：

- 当前状态同步是 HTTP polling。
- 如果要优化实时性和耗电，应先恢复/实现 WS 服务。
- 文档中不能写“当前使用 WebSocket”。

### 14.3 当前不是 stem-aware 播放

真实缓存中当前歌和目标歌只有：

```text
original.mp3
```

`/state` 返回：

```text
playback_tier=basic
```

开发结论：

- 目前产品演示的稳定链路是 original + default render。
- stems 相关能力属于代码存在但当前未启用/未验证。
- 如果要启用 stems，需要同步策略、缓存校验、播放层级一起改。

### 14.4 default render 的状态表达容易误解

切歌后状态：

```json
"playback_tier": "basic",
"last_transition": {
  "playback_tier": "default_render_playback"
}
```

开发结论：

- `last_transition.playback_tier` 表示上一段转场使用 default render。
- 顶层 `playback_tier` 表示当前实时播放层级。
- UI 应分别展示“当前播放层级”和“上次转场方式”。

### 14.5 sync-worker 当前是单任务模型

如果已有同步任务：

```json
{
  "ok": false,
  "error": "sync already running"
}
```

开发结论：

- 当前手机端需要等待 sync-worker idle。
- 产品化建议支持队列、去重、优先级。

## 15. 建议优化路线

### 15.1 第一优先级：缩短开始播放等待

当前 `_startLiveMix()` 会倾向于同步候选池后再播放。

建议改为：

```text
必须同步：
  当前首歌
  下一首
  当前转场 pair render

后台同步：
  后续队列
  备用能量池
  备用风格池
```

目标：

- 用户点击开始后更快出声。
- 后台继续补齐候选池。

### 15.2 第二优先级：明确 default render 队列状态

当前问题：

- `/state.next_song_id` 可能不可靠。
- default render 后续队列状态不清楚。

建议：

edge-agent `/state` 增加：

```json
{
  "queue": ["song1", "song2", "..."],
  "queue_index": 1,
  "planned_next_song_id": "...",
  "state_source": "audio_engine_default_autoplay"
}
```

手机端：

- UI 队列以本地 `_sequence` 为主。
- RK state 只报告实际播放和执行结果。

### 15.3 第三优先级：恢复 WebSocket

目标：

```text
ws://192.168.43.7:9001/ws
```

或直接：

```text
ws://192.168.43.7:9000/ws/control
```

推送消息：

```json
{
  "type": "playback_state",
  "playing": true,
  "current_song_id": "...",
  "position_sec": 123.4
}
```

收益：

- 降低 600ms HTTP 轮询。
- 更准时触发 UI 状态。
- 更利于硬件控制台实时反馈。

### 15.4 第四优先级：重命名资源服务配置

当前：

```text
JETSON_BASE_URL=http://8.136.120.255
```

建议：

```text
HARBEAT_API_BASE_URL=http://8.136.120.255
RESOURCE_BASE_URL=http://8.136.120.255
```

兼容期：

- sync-worker 先读取 `RESOURCE_BASE_URL`。
- 如果为空，再 fallback 到 `JETSON_BASE_URL`。

### 15.5 第五优先级：stem-aware 明确开关

建议在手机和 RK 都明确：

```json
{
  "require_stems": false,
  "prefer_stems": false,
  "playback_mode": "default_render_original"
}
```

如果要启用 stems：

```json
{
  "require_stems": true,
  "prefer_stems": true,
  "playback_mode": "stem_aware"
}
```

并且 sync-worker 必须同步：

```text
vocals.wav
drums.wav
bass.wav
other.wav
```

## 16. 开发修改检查清单

修改手机端前，确认：

- `HarBeatApiClient.baseUrl` 当前是否为预期 API。
- `EdgeAgentClient.baseUrl` 当前是否为预期 RK。
- `SyncWorkerClient.baseUrl` 是否从 RK 地址正确推导到 `9100`。
- `_startLiveMix()` 是否会阻塞等待完整候选池。
- default preset 是否走 `_startDefaultAutoplayOnRk()`。
- 非 default preset 是否走 `/play` + `/xfade`。

修改 RK 前，确认：

- `systemctl is-active cypher-edge-agent`
- `systemctl is-active cypher-audio-engine`
- `systemctl is-active cypher-sync-worker`
- `ss -lntp` 是否监听 `9000/9100`。
- `/tmp/cypher-audio.sock` 是否存在。
- `/home/cat/cypher/deploy/cypher.env` 中资源服务地址是否正确。

修改后测试最小闭环：

```text
1. GET  /health
2. GET  /state
3. GET  /sync-worker/status
4. cache/check 当前歌
5. cache/check 下一首
6. POST /prefetch
7. POST /play
8. 等待自动转场
9. 确认 POST /autoplay/default/render 或 POST /xfade
10. 确认 /state.current_song_id 更新
```

## 17. 当前真实链路一句话总结

当前 DJ Control 的真实稳定链路是：

```text
手机通过 8.136.120.255 生成排序、转场计划和资源 manifest；
手机通过 192.168.43.7:9100 要求 RK 下载 original 音频和 default render 转场片段；
手机通过 192.168.43.7:9000 控制 RK 播放；
edge-agent 通过 /tmp/cypher-audio.sock 调 audio-engine；
audio-engine 在 RK 本地播放 original.mp3，并在 default preset 下播放预渲染转场 wav 后恢复目标歌曲。
```

当前没有启用：

```text
WebSocket 状态推送
stem-aware 四轨混音播放
RK 直连 Tailscale Jetson 作为资源地址
```

## 18. 用户操作与后台触发总表

这一节把手机 UI 操作、手机端函数、业务后端、RK sync-worker、RK edge-agent、audio-engine 的关系按实际链路对齐。后续修改时优先看这一节。

| 用户操作/状态 | 手机端入口 | 业务后端触发 | RK sync-worker 触发 | RK edge-agent 触发 | audio-engine 触发 | 最终结果 |
|---|---|---|---|---|---|---|
| 打开 App | `RootPage._restoreSession()` | `GET /api/auth/me`、`GET /api/library/songs`、`GET /api/playlists` | 无 | 无 | 无 | 恢复登录、加载曲库和歌单 |
| 进入 DJ Control | `DjControlPage.initState()` -> `_loadCatalogs()` | `GET /api/dj/sequence/presets`、`GET /api/dj/transitions/rules`、`GET /api/dj/fx`、`GET /api/dj/energy/buckets` | 无 | 无 | 无 | 加载 DJ preset、规则、FX、能量桶 |
| Step 1 添加歌曲 | `_addSongs()` | 通常无；导入歌单时 `GET /api/playlists/{id}` | 无 | 若已有 live，best-effort `POST /pause` | `pause` | 更新 `_picked`，清空旧 sequence/set |
| Step 2 普通排序 | `_runSequence()` | `POST /api/dj/sequence`，随后多次 `GET /api/dj/songs/{id}/energy` | 无 | 无 | 无 | 得到 `_sequence` 和能量信息 |
| Step 2 自动 DJ set | `_runAutoSets()` | `POST /api/dj/set/generate` | 无 | 无 | 无 | 得到 `_autoSets`，并转成 `_sequence` |
| Step 3 开始混音 | `_startLiveMix()` | `POST /api/dj/live/pool/prepare`、`GET /api/manifest/song/{id}`、`POST /api/dj/transitions/plan` | `GET /status`、`GET /cache/check`、`POST /sync` | `POST /pause`、`POST /cache/validate`、default 分支额外 `/autoplay/default/*` | `pause`、`validate_cache`、`default_autoplay_start` 或 `play` | 候选池就绪后开始播放 |
| 播放中状态刷新 | `_startRkPolling()` | 无 | 无 | `GET /state` | `state` | 手机每约 600ms 更新播放进度和当前歌曲 |
| default 自动转场 | `_maybeAutoXfade()` | 必要时补 `POST /api/dj/transitions/plan` | 已提前同步 default render | `POST /autoplay/default/render` | `default_render_playback` | 播放转场 wav，随后恢复目标歌 original |
| 非 default 自动转场 | `_maybeAutoXfade()` | 必要时补 `POST /api/dj/transitions/plan` | 已提前同步 original | `POST /xfade` | `xfade` 或 `xfade_eq_band_mix` | 执行实时 crossfade/eq_band_mix |
| 播放/暂停按钮 | `_togglePlay()` | 无 | 无 | `POST /pause` 或 `POST /resume` | `pause` 或 `resume` | RK 播放暂停切换 |
| 手动下一首 | `_advanceLive()` | 需要 section_match plan 时 `POST /api/dj/transitions/plan` | 无 | `POST /xfade` | `xfade` | 切到队列下一首 |
| 快速/能量升降切歌 | `_doCut(strategy)` | `POST /api/dj/cut/plan` | 无 | `POST /xfade` | `xfade` | 后端选目标歌，RK 执行切歌 |
| 目标能量预览 | `_previewTargetEnergyBucket()` | `POST /api/dj/cut/plan`，strategy=`target_energy_bucket` | 无 | 预解码目标歌 `POST /prefetch` | `prefetch` | 得到推荐歌曲并准备转场 |
| 目标能量确认 | `_confirmTargetEnergyCut()` | 无，使用 preview 中的 prepared transition | 无 | `POST /xfade` | `xfade` | 把推荐歌曲插入下一首并切换 |
| 目标风格预览 | `_previewTargetStyle()` | `POST /api/dj/cut/plan`，strategy=`target_dance_style` | 无 | 预解码目标歌 `POST /prefetch` | `prefetch` | 得到目标风格推荐 |
| 目标风格确认 | `_confirmTargetStyleCut()` | 无，使用 preview 中的 prepared transition | 无 | `POST /xfade` | `xfade` | 把推荐歌曲插入下一首并切换 |
| FX Pad | `_triggerFx()`/实时控制卡片回调 | RK 失败时回退 `GET /api/dj/fx/{key}.wav` | 无 | 优先 `POST /trigger` | `trigger` | RK 播放/执行 FX；失败则手机本地播放 FX |

## 19. 开始混音的完整后台流程

这是当前最重要的一条链路。用户在 Step 3 点击“开始混音”后，手机端不是立刻播放，而是先把完整候选池同步到 RK，确认可解码，再启动播放。

### 19.1 手机端会先建立新的 live session

入口：

```text
mobile/lib/src/dj_control_page.dart
_startLiveMix()
```

执行顺序：

1. 如果 `_liveStartInFlight=true`，直接返回，防止重复点击。
2. 从 `_sequence` 或 `_picked` 生成 `ordered`。
3. 取第一首歌的 RK 播放 ID。
4. 取消旧的 `_rkPoll`。
5. best-effort 调用 `POST http://192.168.43.7:9000/pause`，停止旧播放。
6. `_resetLiveSessionForNewSet()` 清空旧状态。
7. 设置 `_liveStarted=true`、`_liveIdx=0`、`_backgroundSyncInProgress=true`。

此时用户界面已经进入实时操作页，但按钮会受 `_backgroundSyncInProgress` 限制，避免候选池没准备好就切歌。

### 19.2 准备 live pool

手机调用：

```text
POST http://8.136.120.255/api/dj/live/pool/prepare
```

手机传入：

```json
{
  "active_queue_song_ids": ["当前 set 队列"],
  "style": "由 preset scene 映射出的 breaking/hiphop/generic",
  "target_reserve_per_bucket": 2,
  "include_buckets": ["围绕当前能量的若干能量桶"],
  "exclude_song_ids": ["已播放歌曲"]
}
```

后端返回后，手机写入：

```text
_reservePoolByBucket
_styleReservePoolByStyle
_liveEnergyProfiles
```

这三个状态决定后续“目标能量切歌”和“目标风格切歌”能从哪些候选歌里选。

### 19.3 同步完整候选池到 RK

入口：

```text
_syncMissingLiveCandidatesBeforePlay()
```

候选池 ID 来源：

```text
ordered 队列歌曲
_reservePoolByBucket 中的备用能量歌曲
_styleReservePoolByStyle 中的备用风格歌曲
```

手机先等待 sync-worker 空闲：

```text
GET http://192.168.43.7:9100/status
```

如果 `running=true`，手机每约 2 秒继续等。超时后抛出 `RK sync-worker is still busy`。

随后手机逐首检查缓存：

```text
GET http://192.168.43.7:9100/cache/check?song_id={song_id}&kind=original
```

如果缺失，手机先向业务后端拿 manifest：

```text
GET http://8.136.120.255/api/manifest/song/{song_id}
```

然后手机会把 manifest 改造成 original-only：

```json
{
  "song_id": "...",
  "files": {
    "original": {
      "url": "http://8.136.120.255/api/stream/{song_id}?token=...",
      "format": "mp3"
    }
  },
  "qualityFlags": {
    "has_stems": false,
    "stem_model": null
  },
  "stemStatus": "not_requested"
}
```

注意：这是源码里的当前行为。即使服务端 manifest 提供 stems，DJ Control 启动链路也会主动裁掉 stems，只同步 original。

随后手机启动同步：

```text
POST http://192.168.43.7:9100/sync
```

sync-worker 下载后写入：

```text
/home/cat/cypher/cache/{song_id}/original.mp3
```

同步过程中手机轮询：

```text
GET http://192.168.43.7:9100/status
```

同步完成后，手机不会只相信文件存在，还会要求 audio-engine 解码校验。

### 19.4 校验 RK 可播放缓存

入口：

```text
_ensurePlayableRkCacheIds()
```

手机分批调用：

```text
POST http://192.168.43.7:9000/cache/validate
```

请求体：

```json
{
  "song_ids": ["最多一批 8 首"],
  "require_stems": false
}
```

edge-agent 转给 audio-engine：

```json
{
  "cmd": "validate_cache",
  "song_ids": ["..."],
  "require_stems": false
}
```

audio-engine 会实际检查 original 文件并尝试解码。手机根据结果更新：

```text
_rkCacheStatus[id] = ready / failed / syncing
_prefetched.add(id)
```

如果校验失败，手机最多重试 3 轮：

1. 标记该歌曲 `syncing`。
2. 等 sync-worker 空闲。
3. `DELETE http://192.168.43.7:9100/cache/song/{song_id}` 删除坏缓存。
4. 重新 `GET /api/manifest/song/{song_id}`。
5. 重新 `POST /sync`。
6. 再次 `POST /cache/validate`。

全部通过后，手机写入：

```text
_startupValidatedCacheIds = 全部候选池 ID
```

后续实时切歌会依赖这个集合。如果目标歌没有在启动阶段验证过，当前代码会拒绝播放时临时补缓存。

### 19.5 预生成转场计划

入口：

```text
_prepareAllTransitionPlansBeforePlay()
```

手机会对相邻歌曲逐对生成 plan，并保存到：

```text
_preparedTransitionPlans[transitionIndex]
```

default preset：

```text
POST http://8.136.120.255/api/dj/transitions/plan
```

请求体关键字段：

```json
{
  "rule_key": "default_mix_auto",
  "transition_mode": "default_mix",
  "eq_mix_user_mode": "render",
  "target_lufs": -14.0
}
```

手机会强校验返回值必须满足：

```text
transition_mode = default_mix
execution_mode = default_render_playback
pair_id 非空
transition_render_url 非空
```

非 default preset：

```json
{
  "transition_mode": "section_match",
  "eq_mix_user_mode": "auto",
  "target_lufs": -14.0
}
```

手机会强校验返回值必须满足：

```text
transition_mode = section_match
execution_mode = eq_band_mix
rule_key 以 section_match: 开头
section_match 存在且不是 fallback
from_at_sec/to_at_sec 存在
```

这说明当前非 default 分支不是“普通随便 xfade”，而是要求后端给出真实的 section_match/eq_band_mix 计划。

### 19.6 default preset 启动播放

入口：

```text
_startDefaultAutoplayOnRk()
```

先同步 default mix 资源：

```text
_syncDefaultMixAssetsForSession()
```

它会从 `_preparedTransitionPlans` 提取 default mix pair，然后调用：

```text
POST http://192.168.43.7:9100/sync
```

请求里除了 `tracks`，还会包含：

```json
{
  "default_mix_pairs": [
    {
      "pair_id": "...",
      "files": {
        "transition_render": {"url": "/api/dj/default/render/{pair_id}"},
        "transition_render_meta": {"url": "/api/dj/default/render/{pair_id}/meta"}
      }
    }
  ]
}
```

sync-worker 下载：

```text
GET http://8.136.120.255/api/dj/default/render/{pair_id}
GET http://8.136.120.255/api/dj/default/render/{pair_id}/meta
```

写入：

```text
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render.wav
/home/cat/cypher/cache/default-mix/pairs/{pair_id}/transition_render_meta.json
```

然后手机调用：

```text
POST http://192.168.43.7:9000/autoplay/default/prefetch
```

如果 RK 返回 `render_missing` 非空，手机直接抛错，不启动播放。

通过后手机调用：

```text
POST http://192.168.43.7:9000/autoplay/default/start
```

edge-agent 转给 audio-engine：

```json
{
  "cmd": "default_autoplay_start",
  "queue": ["..."],
  "transitions": ["..."],
  "start_song_id": "第一首",
  "start_at_sec": 0,
  "session_id": "mobile-{sessionId}"
}
```

audio-engine 从 RK 本地缓存加载第一首 original，并进入 default autoplay 状态。

### 19.7 非 default preset 启动播放

非 default preset 不走 default render。

手机先尝试 beatmatch 预热：

```text
POST http://192.168.43.7:9000/prewarm_beatmatch
```

只有 transition plan 中存在 `tempo_ratio` 且不是 eq_band_mix 时才会触发。失败不会中断主流程。

然后手机预解码队列：

```text
POST http://192.168.43.7:9000/prefetch
```

请求体：

```json
{
  "song_ids": ["ordered 队列"],
  "wait": true,
  "load_stems": false
}
```

最后播放第一首：

```text
POST http://192.168.43.7:9000/play
```

edge-agent 转给 audio-engine：

```json
{
  "cmd": "play",
  "song_id": "第一首",
  "start_at_sec": 0
}
```

## 20. 播放中自动转场的完整流程

### 20.1 状态轮询

播放启动成功后，手机调用：

```text
_startRkPolling(sessionId)
```

每约 600ms 执行：

```text
GET http://192.168.43.7:9000/state
```

edge-agent 内部转发：

```json
{"cmd": "state"}
```

audio-engine 返回：

```json
{
  "playing": true,
  "paused": false,
  "current_song_id": "...",
  "position_sec": 123.4,
  "duration_sec": 249.5,
  "playback_tier": "basic",
  "last_transition": {}
}
```

手机更新：

```text
_isPlaying
_position
_duration
_rkCurrentSongId
_rkExecutionHint
```

随后手机执行：

```text
_maybeAutoXfade()
```

### 20.2 自动转场触发条件

`_maybeAutoXfade()` 会先做保护：

- `_backgroundSyncInProgress=true` 时不触发。
- `_xfadeInFlight=true` 时不重复触发；如果超过约 8 秒会释放卡住的 in-flight。
- 当前 `_liveIdx` 已经触发过时不重复触发。
- 如果 RK 仍报告刚切过去的 `_lastXfadeToSongId`，且播放位置还没超过 `fade_sec + 4s`，不继续触发。
- 距上次转场不足 `max(8s, fade_sec + 4s)` 时不触发。
- 队列没有下一首时不触发。

触发时间判断：

1. 优先使用 plan 中的 `from_at_sec`。
2. 如果已到 `from_at_sec`，触发。
3. 如果接近歌曲结尾，`remainingSec <= 1.0`，强制触发。
4. 如果没有 `from_at_sec`，则回退为 `remainingSec <= 5.0`。

### 20.3 default 自动转场执行

如果当前 preset 是 default：

```text
_edgeDefaultRenderFromPlan()
```

手机请求：

```text
POST http://192.168.43.7:9000/autoplay/default/render
```

请求体：

```json
{
  "transition_plan": "之前生成的 default_mix plan",
  "to_song_id": "下一首"
}
```

edge-agent 转发：

```json
{
  "cmd": "default_render_playback",
  "transition_plan": {...},
  "to_song_id": "...",
  "render_path": null
}
```

audio-engine 执行：

1. 根据 plan 找到本地 `transition_render.wav`。
2. 播放该 wav 作为转场片段。
3. 根据 meta/plan 中的 resume 信息定位目标歌。
4. 转场片段结束后加载目标歌曲 original。
5. 从 `resume_at_sec` 继续播放目标歌曲。
6. 返回 `last_transition.action=default_render_resume`。

手机收到成功响应后：

```text
_liveIdx += 1
_lastXfadeFromIdx = 旧 liveIdx
_lastXfadeAt = 当前时间
_lastXfadeToSongId = 下一首 ID
_lastTransitionDebug = 本次转场调试信息
```

如果 RK 返回 degraded，当前手机端会认为 default render 不可信并抛错。

### 20.4 非 default 自动转场执行

如果当前 preset 不是 default：

```text
_edgeXfadeFromPlan()
```

手机请求：

```text
POST http://192.168.43.7:9000/xfade
```

请求体关键字段：

```json
{
  "to_song_id": "下一首",
  "fade_sec": 6.0,
  "to_at_sec": 8.0,
  "style": "blend/filter/bass_swap/...",
  "transition_id": "...",
  "fallback_style": "...",
  "tempo_ratio": 1.02,
  "stem_curves": {...},
  "eq_curves": {...},
  "transition_mode": "eq_band_mix",
  "transition_plan": {...}
}
```

edge-agent 如果看到 `transition_mode=eq_band_mix` 且有 `transition_plan`，会先尝试：

```json
{"cmd": "xfade_eq_band_mix"}
```

如果失败，会降级为：

```json
{"cmd": "xfade"}
```

audio-engine 执行：

- `xfade_eq_band_mix`：按后端 plan 做 EQ band 级混音。
- `xfade`：按 style、fade_sec、to_at_sec 做普通 crossfade。
- 如果目标歌缓存不存在或不可解码，会报错。

手机收到响应后更新 `_liveIdx`、`_activeRule`、`_cutInfo`、`_lastTransitionDebug`。

## 21. 手动切歌、目标能量、目标风格的完整流程

### 21.1 fast cut / energy up / energy down

入口：

```text
_doCut(strategy)
```

如果 `_backgroundSyncInProgress=true`，手机直接弹提示，不允许切歌。

否则手机请求业务后端：

```text
POST http://8.136.120.255/api/dj/cut/plan
```

请求体：

```json
{
  "strategy": "fast_cut / energy_up_cut / energy_down_cut",
  "current_song_id": "当前歌",
  "cursor_sec": 123.4,
  "queue_song_ids": ["完整队列"],
  "current_index": 0,
  "pool_song_ids": ["当前 picked 歌曲"],
  "max_wait_sec": 5.0
}
```

后端返回 `next_song_id` 后，手机找到目标歌，再取或补 section_match plan：

```text
_ensurePreparedSectionMatchPlanFor()
```

然后调用：

```text
POST http://192.168.43.7:9000/xfade
```

注意：当前 `_doCut()` 源码始终使用 section_match/xfade 路径，没有走 default render。也就是说，即使当前 preset 是 default，手动 fast cut 这条链路仍是手动 xfade 逻辑。

### 21.2 目标能量预览

入口：

```text
_previewTargetEnergyBucket(label)
```

手机请求：

```text
POST http://8.136.120.255/api/dj/cut/plan
```

请求体关键字段：

```json
{
  "strategy": "target_energy_bucket",
  "intent": "target_energy_bucket",
  "mode": "preview",
  "current_song_id": "当前歌",
  "cursor_sec": 123.4,
  "active_queue_song_ids": ["当前 liveIdx 后面的队列"],
  "reserve_pool_song_ids": ["能量备用池"],
  "played_song_ids": ["已播歌曲"],
  "blocked_song_ids": ["RK 缓存失败歌曲"],
  "exclude_song_ids": ["用户换一首时排除的候选"],
  "cached_song_ids": ["_rkCacheStatus=ready 的歌曲"],
  "syncing_song_ids": [],
  "target_energy_bucket": {"min": 70, "max": 80},
  "current_style": "当前 preset 映射风格",
  "prefer_cached": true
}
```

后端选出 `selected_song` 后，手机调用：

```text
_prepareTargetCutPreview()
```

这个函数会做三件事：

1. 确认目标歌在 `_startupValidatedCacheIds` 里，否则拒绝。
2. 调 `POST /prefetch` 对目标歌做内存预解码。
3. 调 `POST /api/dj/transitions/plan` 为“当前歌 -> 目标歌”生成 section_match plan。

如果原本队列下一首不是目标歌，手机还会提前为“目标歌 -> 原队列下一首”生成 follow-up transition。

### 21.3 目标能量确认切歌

入口：

```text
_confirmTargetEnergyCut()
```

确认时不再重新请求后端选歌，而是使用 preview 阶段保存的：

```text
_targetEnergyPreview.prepared_transition
```

手机会把目标歌插到当前歌后面：

```text
_insertTargetAsNext(target)
```

然后调用：

```text
POST http://192.168.43.7:9000/xfade
```

切歌成功后更新 `_liveIdx`、`_lastXfadeAt`、`_lastXfadeToSongId`，并清空目标能量 preview 状态。

### 21.4 目标风格预览与确认

目标风格流程与目标能量基本一致，差别在请求体：

```json
{
  "strategy": "target_dance_style",
  "intent": "target_dance_style",
  "mode": "preview",
  "target_style": "breaking / hiphop / popping / ...",
  "active_queue_song_ids": ["当前 liveIdx 后面的队列"],
  "style_reserve_pool_song_ids": ["风格备用池"],
  "played_song_ids": ["已播歌曲"],
  "blocked_song_ids": ["RK 缓存失败歌曲"],
  "cached_song_ids": ["_rkCacheStatus=ready 的歌曲"],
  "syncing_song_ids": [],
  "current_style": "当前 preset 映射风格",
  "prefer_cached": true
}
```

后端返回推荐歌后，手机同样走：

```text
_prepareTargetCutPreview()
_confirmTargetStyleCut()
POST http://192.168.43.7:9000/xfade
```

## 22. 后端/RK 内部接口职责

### 22.1 业务后端职责

业务后端负责“算”和“给资源入口”，不直接控制 RK 播放。

关键接口：

| 接口 | 当前职责 |
|---|---|
| `POST /api/dj/sequence` | 根据 preset 对用户选歌排序 |
| `POST /api/dj/set/generate` | 生成多个候选 DJ set |
| `GET /api/dj/songs/{id}/energy` | 返回街舞能量/能量桶 |
| `POST /api/dj/live/pool/prepare` | 准备能量/风格备用候选池 |
| `POST /api/dj/transitions/plan` | 生成 default render 或 section_match 转场计划 |
| `POST /api/dj/cut/plan` | 根据实时意图选择下一首和切歌计划 |
| `GET /api/manifest/song/{id}` | 返回歌曲资源 manifest |
| `GET /api/stream/{id}` | 给 RK 下载 original 音频 |
| `GET /api/dj/default/render/{pair_id}` | 给 RK 下载 default 转场 wav |
| `GET /api/dj/default/render/{pair_id}/meta` | 给 RK 下载 default 转场 meta |

### 22.2 sync-worker 职责

sync-worker 只负责“下载资源到 RK 本地缓存”，不播放。

关键接口：

| 接口 | 当前职责 |
|---|---|
| `POST /sync` | 根据 tracks/default_mix_pairs 启动下载任务 |
| `GET /status` | 返回当前同步任务进度 |
| `GET /cache/check` | 检查某个 song_id 的 original/stem 文件是否落盘 |
| `DELETE /cache/song/{song_id}` | 删除某首歌的缓存，用于坏缓存修复 |

当前限制：

- 同一时间只允许一个 sync 任务。
- 忙时返回 `{"ok": false, "error": "sync already running"}`。
- 当前 DJ Control 传入的是 original-only manifest。

### 22.3 edge-agent 职责

edge-agent 是手机能直接访问的 RK 控制 API，但它不直接播放音频。

关键接口：

| 接口 | 转发给 audio-engine 的命令 | 当前职责 |
|---|---|---|
| `GET /state` | `state` | 查询真实播放状态 |
| `POST /play` | `play` | 播放指定歌曲 |
| `POST /pause` | `pause` | 暂停 |
| `POST /resume` | `resume` | 继续播放 |
| `POST /xfade` | `xfade` 或 `xfade_eq_band_mix` | 手动/自动实时转场 |
| `POST /autoplay/default/prefetch` | `default_autoplay_prefetch` | default 分支播放前检查 |
| `POST /autoplay/default/start` | `default_autoplay_start` | default 分支开始播放 |
| `POST /autoplay/default/render` | `default_render_playback` | default 分支执行预渲染转场 |
| `POST /prefetch` | `prefetch` | 预解码音频到内存 |
| `POST /cache/validate` | `validate_cache` | 解码校验本地缓存 |
| `POST /trigger` | `trigger` | FX/按键触发 |

### 22.4 audio-engine 职责

audio-engine 是真正播放声音的进程。

当前职责：

- 从 `/home/cat/cypher/cache/{song_id}/original.mp3` 或其它支持格式加载 original。
- 解码音频并写入声卡。
- 维护当前播放状态。
- 执行 pause/resume/seek。
- 执行 ordinary xfade、eq_band_mix、default_render_playback。
- 维护 prefetch cache，减少切歌时磁盘 IO。
- 返回 `playback_tier`、`last_transition` 等执行结果。

当前真实播放层级：

```text
basic：当前稳定链路，播放 original
default_render_playback：只出现在 default 转场片段/last_transition 中
eq_band_mix：源码支持，非 default 分支计划要求该 execution_mode
stem_aware：源码存在，但本次真机未启用
```

## 23. 你后续开发时最容易改错的点

1. 不要把“manifest 有 stems”理解成“RK 已经播放 stems”。当前手机启动链路会主动裁成 original-only。
2. 不要只看顶层 `playback_tier` 判断上次转场方式。default 转场后顶层会回到 `basic`，上次转场方式在 `last_transition`。
3. 不要把 `next_song_id` 当作唯一队列真相。default render 分支已验证它可能与最终目标不一致。
4. 不要绕过 `_startupValidatedCacheIds` 临时切未验证歌曲。当前代码设计是启动前把候选池全部准备好。
5. 不要在 sync-worker 忙时强行发第二个 `/sync`。当前模型是单任务，手机端必须等 `/status.running=false`。
6. default 自动转场走 `/autoplay/default/render`，但 fast cut/能量/风格切歌目前走 `/xfade`。
7. 如果要优化首歌出声速度，应改 `_startLiveMix()` 的同步策略，而不是只改 `/play`。现在瓶颈在“完整候选池同步+校验”。
