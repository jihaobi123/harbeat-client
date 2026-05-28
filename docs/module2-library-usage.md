# 曲库模块（Library）

> 范围：手机 App 的"曲库 / 详情页 / MiniPlayer"端到端链路。
>
> 涉及组件：mobile（Flutter）→ 阿里云 ECS 网关 → Jetson 后端 → RK3588 边缘盒（edge-agent + sync-worker + audio-engine）。
>
> 写作时间：2026-05-29。代码出处见每节末尾的"相关文件"链接。

---

## 1. 功能清单

| 功能 | 入口 | 出声端 | 备注 |
|---|---|---|---|
| 曲库列表 | 主页"曲库" Tab | — | 显示用户已上传/已抓取的歌；附随状态（`pending` / `running` / `completed`） |
| 曲库搜索 | 列表上方搜索框 | — | Jetson 端模糊匹配 title/artist |
| 上传歌曲 | AppBar `upload_file` 图标 | — | 多选 mp3/flac/wav/ogg/aac/m4a/opus/ncm |
| 删除歌曲 | 长按列表项 → 删除 | — | DELETE `/api/library/songs/{id}` |
| 重新分析 | 详情页"重新分析" | — | 触发 BPM / Key / 段落分析 |
| 分离音轨 | 详情页"分离音轨" | — | Jetson 后台跑 Demucs 出 vocals/drums/bass/other |
| **整曲播放** | 列表项点 ▶ / 详情页 ▶ | RK3588 音箱 | edge-agent `/play` |
| **暂停/继续** | MiniPlayer / 详情页 | RK3588 | edge-agent `/pause` `/resume` |
| **进度条拖动** | MiniPlayer / 详情页 | RK3588 | edge-agent `/seek`，带 1.5s 防回弹锁 |
| **段落跳转 (Cue)** | 详情页"段落 / Cue"芯片 | RK3588 | `/seek` 到 cue 时间 |
| **音轨独奏** | 详情页"音轨切换" | RK3588 | edge-agent `/stem_solo` |
| 探活 / 随机试听 | AppBar 工具图标 | RK3588 | 调试用 |

> 主播放路径全部走 **RK3588**——手机不出声、网页另有独立 `<audio>` 路径（不在本文档范围）。

---

## 2. 总架构

```
┌─────────────────┐                          ┌─────────────────────────┐
│   Mobile App    │   public HTTPS(token)    │  阿里云 ECS 8.136.120.255│
│  (Flutter)      │ ──────────────────────▶  │  nginx :80              │
│                 │                          │  └─ proxy_pass :8080    │
│  ┌─ home_page  ─┤                          │     uvicorn HarBeat      │
│  ├─ song_detail ┤                          │     Gateway (httpx 反代) │
│  ├─ EdgeAgent   │   private LAN HTTP       │           │              │
│  └─ SyncWorker  │ ──────────────────────▶  │           ▼ Tailscale    │
└─────────────────┘                          │  Jetson (100.87.142.21)  │
        │                                    │  uvicorn :8000           │
        │  same wifi: http://192.168.43.7    │  - /api/library/...      │
        │                                    │  - /api/stream/{id}      │
        │                                    │  - /api/stream/{id}/stem │
        │                                    │  - PostgreSQL            │
        │                                    │  - storage/songs+stems   │
        │                                    └─────────────────────────┘
        │                                                ▲
        ▼                                                │ stem url（其中带 token=）
┌─────────────────────────────────────────────┐          │
│   RK3588 (192.168.43.7, 同一 wifi)          │          │
│                                             │          │
│  edge-agent      :9000 (FastAPI)            │          │
│   /play /pause /resume /seek /xfade         │          │
│   /stem_solo /state                         │          │
│                                             │          │
│  sync-worker     :9100 (FastAPI) ───────────┼──────────┘
│   /sync /status /cache/check                │
│                                             │
│  audio-engine    Unix socket /tmp/cypher-... │
│   PCM mix loop, in-memory deck.audio +      │
│   deck.stems[name]                          │
│                                             │
│  cache: ~/cypher/cache/<song_id>/           │
│   ├─ original.mp3                           │
│   ├─ vocals.mp3                             │
│   ├─ drums.mp3                              │
│   ├─ bass.mp3                               │
│   └─ other.mp3                              │
└─────────────────────────────────────────────┘
```

### 2.1 Mobile 客户端三个 client

| Client | 地址 | 用途 |
|---|---|---|
| [HarBeatApiClient](../mobile/lib/src/api_client.dart) | 用户配置的 `apiBaseUrl`（默认 `http://8.136.120.255`） | 走 ECS 网关到 Jetson；用于曲库 CRUD、stream URL 生成、search、stem URL 生成 |
| [EdgeAgentClient](../mobile/lib/src/edge_agent_client.dart) | `http://<rkBaseUrl>` （默认 `http://192.168.43.7:9000`） | 直连 RK 控制播放；要求 App 与 RK 在同一 wifi |
| [SyncWorkerClient](../mobile/lib/src/sync_worker_client.dart) | `http://<rkHost>:9100` （从 rkBaseUrl 推导） | 直连 RK 触发"把 Jetson 文件拉到 RK 本地缓存" |

> **设计含义**：手机要播一首歌，必须能同时直连 RK + 间接连 Jetson。RK 拿 Jetson stem URL 自己去下（不经过手机），所以 stem URL 的 token 必须是手机当前登录态的有效 token。

---

## 3. 数据来源 / 存储

### 3.1 Jetson PostgreSQL `library_songs` 表

mobile 实际消费的字段（其余后端中间产物在本文档范围外）：

```text
id              (UUID, str)        ← mobile 用作 RK 的 song_id
song_id         (int, nullable)    ← LibrarySong.songId, DJ Control 备用
user_id         (int)
title           (str)
artist          (str)
duration        (float, sec)
format          (str)
file_size       (int, bytes)
source_type     (str)
created_at      (datetime → ISO str)
analysis_status (str: none|pending|running|completed|failed)
bpm             (float, nullable)
key             (str, nullable)
camelot_key     (str, nullable)
energy          (float, nullable)
stems           (jsonb: dict[name → fs path] | null) ← hasStems 判断
cue_points      (jsonb: list[dict])
beat_points     (jsonb: list[float])
```

模型定义：[mobile/lib/src/models.dart#LibrarySong](../mobile/lib/src/models.dart)（fromJson @ L90-128）。

### 3.2 Jetson 文件系统

| 类型 | 路径模板 | 由谁产生 |
|---|---|---|
| 原始上传 | `~/harbeat/storage/songs/<song_id>.<ext>` | upload 流程 |
| 分轨 wav | `~/harbeat/storage/stems/<song_id>/{vocals,drums,bass,other}.wav` | Demucs 后台任务 |
| 分轨 mp3 | `~/harbeat/storage/stems/<song_id>/{vocals,drums,bass,other}.mp3` | `background_tasks.py:249` 自动 mp3 转码（~10x 小） |

Jetson 的 [stream router](http://100.87.142.21:8000/api/stream/{id}/stem/{stem})（[/home/mark/harbeat/app/modules/stream/router.py:209](http://gh)）**优先返回 .mp3**，没 mp3 才回退 .wav。

### 3.3 RK3588 缓存

```text
~/cypher/cache/<song_id>/
   original.<ext>            ← Jetson 原文件原样（通常 mp3）
   vocals.<ext>
   drums.<ext>
   bass.<ext>
   other.<ext>
```

文件后缀**保留服务器返回格式**——sync-worker 不再强制转 wav（[sync-worker/main.py 中 `_choose_ext`](../../cypher-rk3588/sync-worker/main.py)）。

audio-engine 通过 [`_find_existing_stem(out_dir, name)`](../../cypher-rk3588/audio-engine/engine.py) 按 wav→mp3→flac→m4a→ogg→opus→aac 顺序定位文件，soundfile/libsndfile 1.2.2 直接解码 mp3。

---

## 4. 端到端链路（按功能拆）

### 4.1 列表加载 / 搜索

```
mobile.HomePage initState
  ↓ widget.onRefresh() ← 由 main.dart 注入
  ↓ HarBeatApiClient.getDashboard(token)
  ↓ GET http://8.136.120.255/api/library/dashboard
  ↓ ECS gateway httpx 反代 → http://100.87.142.21:8000/api/library/dashboard
  ↓ Jetson 查 PostgreSQL，返回 {profile, songs[], playlists[]}
LibraryTab.songs ← _displaySongs
```

搜索：`searchLibrarySongs(query)` → Jetson 端 ILIKE 匹配。

相关文件：[home_page.dart](../mobile/lib/src/home_page.dart)（`_searchLibrary`）、[api_client.dart](../mobile/lib/src/api_client.dart)。

### 4.2 上传歌曲

```
file_picker → _pickAndUpload
  ↓ for each file: HarBeatApiClient.uploadSong(token, file, title, artist)
  ↓ POST http://8.136.120.255/api/library/songs (multipart)
  ↓ ECS gateway 反代到 Jetson
  ↓ Jetson:
      1) 写入 ~/harbeat/storage/songs/<new_uuid>.<ext>
      2) INSERT library_songs (analysis_status='pending')
      3) 后台触发 BPM/Key 分析（模块 1）
返回 LibrarySong → 加到 _displaySongs 顶部
```

`analysis_status` 为 pending/running 时，HomePage 起 8s 周期 `_analysisWatcher` 静默刷新。

### 4.3 整曲播放（核心快路径）

#### 时序

```
用户点列表 ▶ (列表项底部 sheet → onPlay)
  └─ HomePage._playSong(song)
       │
       ├─ 1) _tryDirectPlay(song)            POST RK :9000 /play {song_id}
       │      └─ RK 缓存命中 → 立刻出声 → 早退
       │
       ├─ 2) _fastPlayWhenCached(song)       未命中 → "200ms 轮询"快路径
       │      ├─ unawaited POST RK :9100 /sync (manifest 含 original mp3)
       │      ├─ loop 直至 8s deadline:
       │      │   ├─ GET RK :9100 /cache/check?song_id=<id>
       │      │   │   └─ {"exists": true/false}
       │      │   ├─ exists=true → POST RK :9000 /play → 出声 → return true
       │      │   ├─ 否则 GET RK :9100 /status 刷 prefetchPercent
       │      │   └─ sleep 200ms
       │      └─ 命中 → 早退；超时 → 走兜底
       │
       └─ 3) _prefetchToRkCache(song)        SyncWorkerClient.syncAndWait
              ├─ POST RK :9100 /sync
              ├─ 1Hz 轮询 /status 直到 running=false
              └─ 之后 _tryDirectPlay 二次尝试
```

`/sync` manifest 形态（mobile 端构造）：

```jsonc
{
  "plan_id": "mobile-<song_id>",
  "tracks": [{
    "song_id": "<UUID>",
    "files": {
      "original": {
        "url": "http://8.136.120.255/api/stream/<song_id>?token=...",
        "format": "mp3"
      }
    }
  }]
}
```

> **注**：`url` 字段 mobile 走 ECS 网关。sync-worker 拿到后**直接** GET 这个 URL；它的 `_download_one` 见到 query 里带 `token=` 就不再添加 `Authorization` 头（[sync-worker/main.py 见 `url_has_token`](../../cypher-rk3588/sync-worker/main.py)）。

#### 状态轮询 + 防回弹

播放成功后 `_startRkStatePolling` 起 1Hz Timer 拉 [RK /state](#52-rk-edge-agent)：

```dart
final guard = _seekGuardUntil;
final inGuard = guard != null && DateTime.now().isBefore(guard);
if (!inGuard) {
  _position = Duration(milliseconds: (st.positionSec * 1000).round());
}
```

`_seekGuardUntil` 在 `_seek()` 里被设为 "现在 + 1000ms"——**这 1 秒内忽略 RK 回报的旧 position**，避免拖动后进度条跳回。

### 4.4 进度条拖动 / Seek

```
MiniPlayer Slider
  ├─ onChangeStart  → _dragValue = value (本地预览，停止从外部覆盖)
  ├─ onChanged      → _dragValue = value (跟手指走)
  └─ onChangeEnd    → _dragValue = null
                      _latchTarget = value
                      _latchUntil  = now + 1500ms        ← MiniPlayer 内"软锁"
                      onSeek(value)
                        └─ HomePage._seek(value)
                              ├─ setState _position = target
                              ├─ _seekGuardUntil = now + 1000ms
                              └─ EdgeAgentClient.seek(value)
                                  └─ POST RK :9000 /seek {sec}
                                       └─ audio-engine 跳到目标帧（不重载文件）
```

软锁逻辑：MiniPlayer 在 build 时如果 `_latchTarget` 非空，**优先**用 latchTarget 显示，直到：

- `_latchUntil` 过期（1.5s），或
- 外部传进来的 `livePosition` 已经在 latchTarget ±1.0s 之内（说明 RK 真的跳过去了）

→ 才解除软锁返回 livePosition。

UI 表现：松手→立刻在新位置；不会被旧轮询拽回。

相关文件：[home_page.dart `_seek` / MiniPlayer](../mobile/lib/src/home_page.dart)、[edge_agent_client.dart `seek`](../mobile/lib/src/edge_agent_client.dart)。

### 4.5 详情页：完整曲 + 段落 + 音轨独奏

详情页[song_detail_page.dart](../mobile/lib/src/library/song_detail_page.dart)**完全不走 just_audio**——所有声音从 RK 出。

#### 4.5.1 状态机

```
_loaded = false             ← 初始
_activeSource = "full"      ← 'full' | 'vocals' | 'drums' | 'bass' | 'other'
```

`_loaded` 表示"RK 已经 /play 过本曲"，决定后续动作能否走 /seek 直接来。

#### 4.5.2 首播（Player 卡片的 ▶ / 段落 chip）

```
_togglePlay → !_loaded 时 _ensureLoaded(0.0)
                          复刻 4.3 节的 fast-cache race
                          但只 sync original.mp3，不带 stem
                          成功 → _loaded=true, _startStatePolling()
```

#### 4.5.3 段落 chip 跳转

```
ActionChip onPressed → _seekTo(Duration(ms: cue.time*1000))
  ├─ if !_loaded → _ensureLoaded(startAtSec=cue.time)   ← 第一次直接定位起播
  └─ else        → _seek 走 RK /seek + guard window
```

cue 数据来源：`song.cuePoints`（Jetson 分析阶段写入 DB）。

#### 4.5.4 音轨切换（关键路径）

```
ChoiceChip onSelected(s) → _switchSource(s)
  ├─ if !_loaded → _ensureLoaded(0)            先把 original.mp3 拉好出整曲
  │
  ├─ if s != 'full' → _ensureStemCached(s)     等 stem 文件落盘到 RK
  │      └─ POST RK :9100 /sync {tracks:[{song_id, files:{stems:{<s>:{url,format}}}}]}
  │      └─ syncAndWait 1Hz 轮询直到 running=false
  │      └─ Jetson 服务 stem mp3 (~5MB)
  │      └─ sync-worker 落到 cache/<song_id>/<s>.mp3
  │
  └─ POST RK :9000 /stem_solo {stem: 'vocals'|null}
       └─ audio-engine.set_stem_solo(stem):
           ├─ stem 已在 active_deck.stems → 直接切
           └─ 否则 _find_existing_stem(...) 惰性 _load_wav_stereo 读盘
              （soundfile 直接解码 mp3）
```

> **`/sync` manifest 必须用 `files.stems.{name}` 嵌套结构**，否则 sync-worker 的 `_file_items` 会忽略它（这是早期一个 bug 的根因）。详见 [sync-worker/main.py `_file_items` L104-118](../../cypher-rk3588/sync-worker/main.py)。

切回 `full` → `_edge.stemSolo(null)` → audio-engine 把 `_stem_solo` 设回 None，输出恢复 deck.audio 混音。

#### 4.5.5 stem 文件惰性加载

audio-engine 加载完整曲时（`Deck.load`），只有当 `<song_dir>/<stem>.wav|mp3|...` 在磁盘上**存在**才装载到 `deck.stems[name]`。如果 stem 是后续才下来的，`set_stem_solo` 会按这个顺序补救：

```python
# cypher-rk3588/audio-engine/engine.py set_stem_solo
if stem not in active_deck.stems:
    stem_path = _find_existing_stem(_song_dir(song_id), stem)
    if stem_path is not None:
        active_deck.stems[stem] = _load_wav_stereo(stem_path)
        # 装载完成，继续走切换
    else:
        raise SongCacheError(f"stem '{stem}' 未加载", code=409)
```

**意味着 mobile 必须在调 `/stem_solo` 之前等到 stem 真落盘**——这就是 `_ensureStemCached` 用 `await syncAndWait` 而不是 `unawaited` 的原因。

---

## 5. RK3588 接口契约

### 5.1 sync-worker `:9100`

| 端点 | 入参 | 出参 |
|---|---|---|
| `POST /sync` | manifest `{plan_id, tracks:[{song_id, files:{original?, stems?}}]}` | `{ok, sync_started, total, manifest:{track_count, asset_count, missing}}` |
| `GET /status` | — | `{running, plan_id, total, downloaded, completed, percent, current_file, errors}` |
| `GET /cache/check?song_id=...` | query | `{ok, exists, path?, size?, ext?}` —— 仅查 `original.*` |

manifest `files` 结构（**两种 key 并存**）：

```jsonc
"files": {
  "original": {"url": "...", "format": "mp3", "sha256?": "...", "size?": 0},
  "stems": {
    "vocals":  {"url": "...", "format": "mp3"},
    "drums":   {"url": "...", "format": "mp3"},
    "bass":    {"url": "...", "format": "mp3"},
    "other":   {"url": "...", "format": "mp3"}
  }
}
```

`_choose_ext` 决定落盘后缀：优先 info.format → 否则 url 后缀 → 否则 wav。

### 5.2 RK edge-agent `:9000`

| 端点 | 入参 | 行为 |
|---|---|---|
| `POST /play` | `{song_id, start_at_sec?}` | 加载 + 开播；**会重置 `_stem_solo=None`** |
| `POST /pause` / `/resume` | — | |
| `POST /seek` | `{sec}` | 仅跳帧，不重载文件 |
| `POST /xfade` | `{to_song_id, fade_sec, to_at_sec, style}` | DJ 用 |
| `POST /stem_solo` | `{stem: "vocals"\|null}` | None=取消独奏 |
| `POST /prefetch` | `{song_ids: []}` | 后台预解码 |
| `GET /state` | — | `{playing, position_sec, current_song_id, duration_sec?, ...}` |

### 5.3 audio-engine 内部

不暴露 HTTP，通过 `/tmp/cypher-audio.sock` 收 JSON 命令。命令在 [edge_agent main.py](../../cypher-rk3588/edge-agent/main.py) `_forward()` 里串行下发。

---

## 6. 已知性能特征（2026-05-29 测量）

针对 levitating（203 秒，stem mp3 ≈ 4.9MB）：

| 操作 | 缓存命中 | 缓存未命中（首次）|
|---|---|---|
| 列表 → /play | 200-300 ms | 6-9 秒（受 Jetson 上行带宽限制 ~360 KB/s） |
| 进度条 /seek | 50-100 ms | — |
| 段落 cue 跳转 | 50-100 ms | 同首播 |
| stem 切换 | 50-100 ms（同曲第二次以上） | 9-13 秒（stem mp3 下载 + 惰性加载） |

**首次链路瓶颈**：`Jetson → ECS gateway → RK` 这条路 ECS 网关是 buffered（`resp.content` 等待全量），且 Jetson 的家庭/办公室上行带宽 ≈ 360 KB/s。stem 切换时间几乎等于 mp3 文件大小 / 360KB/s。

后续优化方向（未实施）：

1. ECS 网关改成 stem 缓存层（FileResponse 命中本地、未命中流式回源）—— 二次访问从 9s 降到 1-2s。
2. mobile 在用户停留详情页时后台预拉 stem—— 用户点击时已经命中。
3. ECS 网关流式转发（不等 `resp.content` 全量）—— 节省一段串行等待。

---

## 7. 故障排查速查

| 现象 | 第一步看哪儿 |
|---|---|
| 列表为空 / 401 | mobile token 是否有效；`api_client.dart` 的 `apiBaseUrl` 是否指向可用 ECS |
| 点 ▶ 长时间转圈 | 看 sync-worker 日志 `journalctl --user -u cypher-sync-worker.service -f`；常见是 Jetson 端 stem URL 401（token 过期） |
| 点了 stem 还是混音 | 看 RK cache 是否真有 `<stem>.mp3`；用 `ffprobe` 确认 codec 不是 mp3-in-wav 容器；惰性加载是否 raise 409 |
| /seek 之后 1 秒位置闪回 | 检查 `_seekGuardUntil` 是否生效（只有 mobile 端 1.0s 防回弹生效，RK /state 仍返回旧值是预期） |
| 详情页切 stem 反应 ≥ 10s | 见 §6——是 Jetson 上行带宽，目前无解决方案落地 |

---

## 8. 相关源码索引

| 模块 | 路径 |
|---|---|
| 主页（曲库 Tab + MiniPlayer） | [mobile/lib/src/home_page.dart](../mobile/lib/src/home_page.dart) |
| 详情页 | [mobile/lib/src/library/song_detail_page.dart](../mobile/lib/src/library/song_detail_page.dart) |
| Jetson 网关客户端 | [mobile/lib/src/api_client.dart](../mobile/lib/src/api_client.dart) |
| RK edge-agent 客户端 | [mobile/lib/src/edge_agent_client.dart](../mobile/lib/src/edge_agent_client.dart) |
| RK sync-worker 客户端 | [mobile/lib/src/sync_worker_client.dart](../mobile/lib/src/sync_worker_client.dart) |
| LibrarySong / CuePoint 模型 | [mobile/lib/src/models.dart](../mobile/lib/src/models.dart) |
| RK edge-agent 服务 | cypher-rk3588 仓库 `edge-agent/main.py` |
| RK sync-worker 服务 | cypher-rk3588 仓库 `sync-worker/main.py` |
| RK audio-engine | cypher-rk3588 仓库 `audio-engine/engine.py` |
| Jetson 后端（曲库 / stream） | jetson:/home/mark/harbeat/app/modules/{library,stream}/ |
