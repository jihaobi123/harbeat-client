# Cypher 场景：架构与功能流程书

> 标准：本文档自包含。读完一份就能开始动工，不依赖会议、不依赖问人。其它三份开发文档基于本文档展开。

---

## 1. 三个根本问题（最容易混的地方）

### 1.1 混音工作到底在哪台机器执行？

**混音分 3 层，每层在不同地方完成**。这是整个系统最关键的拆分。

| 层 | 工作内容 | 时机 | 执行机器 | 时长 |
|---|---|---|---|---|
| **L1 顺序规划** | 11 首歌排成什么顺序、在哪秒过渡、淡入淡出曲线 | **赛前** | Jetson `GrooveEngine` | 30~60s（优化后）|
| **L2 过渡执行** | 真正用 audio buffer 把两首歌叠在一起 crossfade 出来 | **现场实时**（到达 transition 时间点）| RK3588 `audio-engine` | 持续 8s |
| **L3 加花 / Stem 操控** | 按 1~9 键叠加 sample、mute 主轨、滤波 | **现场实时**（人手按下）| RK3588 `audio-engine` | < 30ms 响应 |

**核心结论**：Jetson 算"剧本"，RK3588 演"现场"。Jetson 不在实时路径里。

### 1.2 音频上传 / 预处理速度怎么解决？

Jetson 上 Demucs 分离 4 轨 stem 大约 **3 分钟/首**。这个慢是物理瓶颈，没法消除。

**解决方案 = 提前 + 异步 + 状态机**：

```
[T-7 天]  MC 把候选歌曲提前上传到 Jetson
            ↓ 立刻返回 song_id（不等分析）
[T-7 天 + 5min]  Jetson 后台流水线（PostgreSQL 列 analysis_status）：
              pending → bpm_done → beats_done → stems_done → embed_done → ready
[T-1 天]  MC 在 App 赛前页只看 status="ready" 的歌（其它灰掉，标"处理中"）
[赛前 30min]  MC 选歌做 Set List → 调 /dj-mix → 拿到 MixPlan
[赛前 25min]  App 点 "Sync to RK" → sync-worker 拉 manifest → 下载到 RK 本地
[赛前 20min]  RK 本地 cache/<song_id>/ 齐了 → 开场
```

**两个硬性产品规则**：
1. **只有 `analysis_status="ready"` 的歌能进 Set List**（App 强制）
2. **只有 RK 本地缓存齐了的歌能开始播放**（RK 拒绝 play 不在本地的歌）

### 1.3 三台机器的精确职责边界

| 机器 | 干 | 不干 |
|---|---|---|
| **Jetson** | 用户/曲库/playlist 数据；GPU 跑 Demucs+CLAP+BeatNet；GrooveEngine 排序；推荐；TTL 文件 | 不在现场实时路径；不直接给 App 推流；不存"现场状态" |
| **RK3588** | 本地缓存歌曲 + stems；混音执行；加花；输入处理；上报 SessionEvent | 不做长时间 GPU 推理；不存全曲库；不参与 GrooveEngine 规划 |
| **手机 App** | UI；双链路客户端；本地缓存当前 MixPlan；触觉反馈 | 不做任何音频处理；不存歌曲文件 |

---

## 2. 系统拓扑

```
┌──────┐ Wi-Fi   ┌──────────────┐ LAN(同房间)  ┌────────────┐
│ MC手机│────────▶│ 路由器        │◀────────────▶│ RK3588      │──▶ 🔊 音箱
│ App  │         │ (家里现场)    │              │ (现场盒)    │
└──┬───┘         └──────┬───────┘              └─────┬──────┘
   │ 4G/Wi-Fi           │ 上行                       │ USB HID
   │                    │                            ▼
   │                    │                       ┌────────────┐
   │                    │                       │ 9 键硬件盒  │
   │                    │                       └────────────┘
   ▼                    ▼
┌─────────────────────────────────────┐
│ 阿里云 ECS 8.136.120.255            │
│  - nginx :80                        │
│  - cloud_gateway :8080              │
│    /api/*  → Jetson                 │
│    /edge/<rk_id>/*  → 对应 RK3588 (Tailscale)
└──────────┬──────────────────────────┘
           │ Tailscale
           ▼
┌─────────────────────────────────────┐
│ Jetson Orin NX (家里另一台)         │
│  - FastAPI :8000                    │
│  - PostgreSQL :5432                 │
│  - Redis :6379                      │
│  - ChromaDB / NAS / GPU             │
└─────────────────────────────────────┘
```

**链路分类**：
- **慢链路**（App → 阿里云 → Jetson）：登录、搜歌、上传、生成 MixPlan、推荐、查 sessions。延迟 200~800ms 可接受。
- **快链路**（App → 路由器 → RK3588 LAN 直连）：播放、暂停、切歌、加花。延迟 < 100ms 必达。
- **离场链路**（RK3588 → Tailscale → 阿里云 → 反向接 Jetson）：现场结束后 SessionEvent 批量上报。或者 RK 直接连家里 Jetson 的 LAN（如果两台机在同 LAN）。

---

## 3. 共享协议（A/B/C 三人合同）

所有协议 JSON Schema 放在 git `shared/protocols/`，三方共同维护，任何字段改动需三人 PR review。

| # | 协议 | 产生方 | 消费方 | 用途 |
|---|---|---|---|---|
| P1 | `SongStatus` | Jetson | App | 每首歌的 `analysis_status` |
| P2 | `MixPlan` | Jetson GrooveEngine | RK3588 + App | 整场顺序 + 过渡点 |
| P3 | `AssetManifest` | Jetson | RK3588 sync-worker | 每首歌要下载的文件清单 + sha256 |
| P4 | `ControlCommand` | App | RK3588 edge-agent | play/pause/next/trigger 命令 |
| P5 | `RKPlaybackState` | RK3588 | App | 当前在播什么、进度 |
| P6 | `KeyEvent` | RK3588 input-daemon | App + Jetson 归档 | 按键时间戳 |
| P7 | `SessionEvent` | RK3588 | Jetson | 一场的所有事件 |
| P8 | `DeviceInfo` | RK3588 | App | CPU/温度/磁盘/网络 |

### 协议字段定义（紧凑版，开发员据此生成各语言模型）

```jsonc
// P1 SongStatus
{
  "song_id": 101,
  "title": "Track A", "artist": "Foo",
  "duration_sec": 180, "bpm": 92, "key": "Am",
  "analysis_status": "pending|bpm_done|beats_done|stems_done|embed_done|ready|failed",
  "analysis_error": null,
  "analyzed_at": "2026-05-19T12:00:00Z"
}

// P2 MixPlan
{
  "plan_id": "uuid-v4",
  "playlist_id": 42,
  "generated_at": "2026-05-19T12:00:00Z",
  "tracks": [
    { "song_id": 101, "order": 0, "start_at_sec": 0, "play_duration_sec": 174 }
  ],
  "transitions": [
    { "from_song": 101, "to_song": 102, "from_at_sec": 174, "to_at_sec": 8,
      "fade_sec": 8, "fade_curve": "linear|equal_power|exp" }
  ]
}

// P3 AssetManifest
{
  "plan_id": "uuid-v4",
  "tracks": [{
    "song_id": 101,
    "files": {
      "original": {"url":"/api/stream/101/audio","size":5200000,"sha256":"..."},
      "stems": {
        "vocals": {"url":"/api/stream/101/stem/vocals","size":...,"sha256":"..."},
        "drums":  {"url":"...","size":...,"sha256":"..."},
        "bass":   {"url":"...","size":...,"sha256":"..."},
        "other":  {"url":"...","size":...,"sha256":"..."}
      }
    }
  }]
}

// P4 ControlCommand (POST 到 RK 的不同 endpoint，body 简单)
POST /play       {"song_id": 101, "start_at_sec": 0}
POST /pause      {}
POST /resume     {}
POST /next       {}  // 按 MixPlan 切下一首
POST /seek       {"sec": 30.5}
POST /trigger    {"key": 1}  // key 取值 0-9
POST /load_plan  {"mix_plan": MixPlan, "manifest": AssetManifest}

// P5 RKPlaybackState (WebSocket 推送，每 200ms 一帧)
{
  "type": "playback_state",
  "ts": 1716100000000,
  "playing": true, "paused": false,
  "current_song_id": 101, "position_sec": 42.3,
  "next_song_id": 102, "next_transition_in_sec": 132,
  "active_loops": [4, 6],     // 4/5/6 toggle loop 当前哪些开着
  "active_stem_fx": null      // 7/8/9 当前有没有在生效
}

// P6 KeyEvent (推 App + 入 SessionEvent)
{ "type":"key_event", "ts":1716100012345, "key":1, "source":"hid|app" }

// P7 SessionEvent (RK 批量 POST 给 Jetson)
{
  "events": [
    {"ts":..., "type":"play_start|play_end|pause|resume|key_press|transition|next|load", "data":{...}}
  ]
}

// P8 DeviceInfo (WebSocket 推送，每 5s)
{
  "type":"device_info", "ts":...,
  "cpu_percent":35.2, "mem_used_mb":2140, "temp_c":62.1,
  "disk_free_gb":18.3, "audio_xrun_count":0,
  "jetson_reachable":true, "wifi_ssid":"home"
}
```

---

## 4. 功能流程（按组分类，去掉赛后组）

每个功能用统一模板：**触发 → 链路 → 反馈 → 时延 → 负责人**。

### A 组：赛前（慢链路）

#### A1 登录
- 触发：App 输入账号密码点 Login
- 链路：App → 阿里云 → Jetson `POST /api/auth/login` → bcrypt 校验 → 签 JWT
- 反馈：App 存 token 跳赛前页
- 时延：< 2s
- 负责：C 写表单；A 现有接口

#### A2 浏览/搜索曲库
- 触发：App 输入关键词
- 链路：→ Jetson `GET /api/library/search?q=...&only_ready=true`（重要：必带 `only_ready=true` 过滤掉未处理完的）
- 反馈：App 列表显示 `SongStatus`，"ready" 可点，其它灰
- 时延：< 1s
- 负责：A 给 `only_ready` 参数；C 写列表

#### A3 上传新歌
- 触发：App 选文件 Submit
- 链路：→ Jetson `POST /api/music/upload`（multipart）→ NAS 存原文件 → 立即返回 `{song_id, analysis_status:"pending"}` → 后台任务流水线 ①librosa(BPM/key, 5s) → ②BeatNet(beats, 30s) → ③Demucs(stems, **3min/首**) → ④CLAP(embed, 10s) → ⑤标记 `ready`
- 反馈：App 立刻返回 song_id，赛前页定期轮询 `GET /api/library/songs/{id}` 看 status 变化
- 时延：上传 < 5s；分析 **~4min/首**
- 负责：A 现有 + 加 `analysis_status` 字段 + 加状态轮询 API

> **产品硬规则**：MC 不能拿"非 ready"的歌进 Set List。App 必须拦截。

#### A4 编辑 Set List（playlist）
- 触发：App 加歌 / 删歌 / 拖排序
- 链路：→ Jetson `POST/DELETE/PUT /api/playlists/{id}/songs`
- 反馈：列表更新
- 时延：< 1s
- 负责：A 现有 playlist 接口够用；C 写 UI

#### A5 生成 MixPlan
- 触发：App 点 "Plan This Set"
- 链路：→ Jetson `POST /api/playlists/{id}/dj-mix-stream`（**SSE 流式**）→ GrooveEngine 算 → 边算边推 plan
- 反馈：App 立刻看到第一个 plan（~30s），如有更优自动替换
- 时延：首个 plan < 60s（5 首歌）
- 负责：A 改造 GrooveEngine（详见 team-jetson-backend.md T3）

#### A6 同步到 RK3588
- 触发：App 点 "Sync to RK"
- 链路：
  - App `POST {rk}/load_plan` 把 MixPlan + AssetManifest 全部 push 给 RK
  - RK sync-worker 收到 → 并发下载 manifest 里所有未缓存的文件
  - sync-worker 算 sha256 与 manifest 对比，不匹配则重下
  - 进度通过 WS 推回 App
- 反馈：App 进度条 0~100%
- 时延：取决于网速，5 首歌 ~1GB，目标 5~10min
- 负责：A 提供 manifest；B 写 sync-worker；C 写进度 UI

### B 组：现场实时（快链路，RK 本地）

#### B1 开始播放
- 触发：App 点 Track 第一首 → 点"开始"
- 链路：App → RK `POST /play {song_id}`（LAN）→ edge-agent → audio-engine（Unix socket）→ ALSA 出声
- 反馈：音箱响 + App 进度条开始走
- 时延：< 200ms
- 负责：B；C 写按钮

#### B2 暂停 / 继续
- 触发：App 大按钮 / 硬件键 0
- 链路：→ RK `POST /pause` 或 `/resume`
- 反馈：音箱静音/复响
- 时延：< 50ms
- 负责：B + C

#### B3 切下一首（自动 + 手动）
- 自动触发：audio-engine 到达 MixPlan 中的 `transition.from_at_sec`
- 手动触发：App 长按 NEXT 0.5s（防误触）→ RK `POST /next`
- 链路：audio-engine 预加载下一首到 deck_b → 到点开始 fade → 完成切 deck
- 反馈：音箱无停顿；App 当前歌切换
- 时延：fade 期间抖动 < 20ms
- 负责：B（核心 audio-engine）

#### B4 9 键加花
- 触发：硬件键按下 1~9 / 0；或 App 点对应按钮
- 链路：
  - **硬件路径**：USB HID → input-daemon 收 keycode → Unix socket `trigger_sample(N)` → audio-engine mix 进主输出
  - **App 路径**：App → RK `POST /trigger {key:N}` → edge-agent → audio-engine
- 反馈：音箱"啪"；App 按钮闪一下确认收到
- 时延：硬件 < 30ms；App < 80ms
- 负责：B 全部；C 给 App UI

**9 键映射**（B 实现，C 显示）：

| 键 | 类型 | 行为 | 实现方式 |
|---|---|---|---|
| 1 | one-shot | "ha!" 人声 | 播 `~/cypher/samples/01_ha.wav` 叠加主轨 |
| 2 | one-shot | scratch | `02_scratch.wav` 叠加 |
| 3 | one-shot | air horn | `03_horn.wav` 叠加 |
| 4 | loop toggle | 鼓 loop | `04_drum_loop.wav` 循环叠加，再按关 |
| 5 | loop toggle | bass loop | `05_bass_loop.wav` |
| 6 | loop toggle | hi-hat loop | `06_hat_loop.wav` |
| 7 | stem fx | 主轨人声 mute 2s | 当前歌的 `vocals.wav` 暂时 gain=0 |
| 8 | stem fx | 只听鼓 2s | 临时只输出 `drums.wav`，其它 gain=0 |
| 9 | stem fx | 低通扫频 2s | 主轨实时 biquad LPF 滤波 |
| 0 | control | 暂停/继续 toggle | 同 B2 |

7/8/9 工作的前提：audio-engine 启动时**预加载当前歌的 4 个 stem 到内存**（不是只主轨），保证按下可立即操作。

### C 组：现场半实时（慢链路兜底）

#### C1 现场临时上传新歌
- 触发：App 选文件 Upload（极少用）
- 链路：同 A3
- 反馈：分析中（4min 后才能用）
- 负责：A 复用

#### C2 语音命令
- 触发：App 长按麦克风录 2s
- 链路：
  - 优先：App → RK `/voice` 本地关键词匹配（< 500ms）
  - 复杂指令：App → Jetson `/api/voice/keyword`（CLAP/Whisper, 1~2s）
- 反馈：App 显示识别文字 → 自动执行（next/pause/...）
- 负责：A 提供云端；B 写本地词模型（先做"下一首"、"暂停"、"播 X"三个）；C 录音 UI

---

## 5. 故障 / 降级行为（必须实现）

| 故障 | 现场表现 | 兜底逻辑 |
|---|---|---|
| Jetson 不可达 | 赛前页报错；现场正常 | App 灰掉所有 Jetson 接口按钮；RK 缓存的 MixPlan 继续用 |
| App ↔ RK LAN 断 | App 现场页瘫；硬件键正常 | App 顶部红点闪烁；硬件键 0~9 全可用 |
| 硬件键盒拔了 | App 现场页正常 | input-daemon 5s 后重试，期间 App 触发可用 |
| RK 死机/重启 | 现场停 | RK 用 `Restart=always` systemd；启动后重读 `~/cypher/plans/current.json` 恢复 |
| 某首歌 stem 没下完 | 该歌不能加花/切 | RK `/play` 检查到缺文件 → 直接返回 409；App 显示"未同步" |

四条铁律：
1. **任何 Jetson 调用必须带 3s 超时**，超时走本地降级
2. **9 键加花路径绝对不能经过 Jetson**
3. **App↔RK 用 WebSocket 长连**，断后 1s 内重连
4. **audio-engine 启动后立刻预加载当前歌全部 4 个 stem**

---

## 6. 三人交付物总览

| 模块 | 负责人 | 主要交付 |
|---|---|---|
| Jetson 后端 | A | `analysis_status` 字段 + 轮询 API；`/manifest`；SSE `/dj-mix-stream`；`/sessions/{id}/events`；`/edge/<rk_id>/*` 网关透传 |
| RK3588 现场盒 | B | 4 进程：`edge-agent`(FastAPI)、`audio-engine`(Python→Rust)、`input-daemon`(evdev)、`sync-worker`(httpx)；本地 9 键 sample 库 |
| 手机 App | C | Flutter App：登录页、赛前页、现场页（9 大按钮）；双链路客户端；本地缓存 |

详见 [team-jetson-backend.md](team-jetson-backend.md) / [team-rk3588-edge.md](team-rk3588-edge.md) / [team-mobile-app.md](team-mobile-app.md)。

---

## 7. 端到端事件链（一次完整 Cypher）

```
T-7d  MC 在 App 上传 30 首候选歌      → Jetson 后台流水线（每首 ~4min）
T-1d  Jetson 全部 ready              → App 显示绿色可选
T-30m MC 选 11 首组 Set List          → Jetson playlist 写入
T-25m MC 点 Plan This Set            → Jetson SSE 推第 1 个 MixPlan（30s）
                                       App 显示，可手动调整顺序
T-20m MC 点 Sync to RK               → App push MixPlan+Manifest 给 RK
                                       sync-worker 并发下载（~5min, 1GB）
T-15m sync 完成                       → App 现场页解锁
T 0   MC 点开始                       → RK audio-engine play 第 1 首
T+15s MC 按硬件键 1                   → input-daemon → audio-engine 立刻叠 "ha!"
T+2m  audio-engine 到 transition_at  → fade 8s 切第 2 首
T+5m  MC 长按 App NEXT 0.5s          → RK 直接切第 3 首（跳过原 plan）
T+45m 现场结束 MC 关 App              → RK 继续上报 SessionEvent buffer
                                       下次联网时批量发 Jetson
```

读完应能回答：每个时间点哪台机器在做什么、哪个进程被唤醒、哪条网络链路被使用。如不能，重读 §1。
