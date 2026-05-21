# Cypher RK3588 现场盒 · 任务进度

> 对照文档：`~/桌面/team-rk3588-edge.md`、`~/桌面/jetson-handoff-for-rk3588.md`  
> 代码目录：`~/cypher/`  
> 更新日期：2026-05-19

---

## 总览

| 类别 | 状态 |
|------|------|
| 现场核心（App 控 RK、播放、九键、自动切歌） | **基本完成**，可本机 / App 联调 |
| 与 Jetson 对接（manifest 下载、SessionEvent） | **未实现** |
| 文档「完工自检」 | 约 **一半** 通过 |

**整体完成度（估）：~60%**

---

## 一、已完成

### 1.1 环境与目录（team §0.1）

| 项 | 说明 |
|----|------|
| Python venv | `~/venvs/edge/`（Python 3.10+） |
| 工作目录 | `~/cypher/` |
| 子目录 | `edge-agent/`、`audio-engine/`、`input-daemon/`、`samples/`、`cache/`、`plans/`、`deploy/` |
| 用户权限 | `cat` 已加入 `input` 组（九键 evdev） |
| 测试资源 | `cache/101`、`cache/102`（`original.wav`）；`samples/01~06_*.wav`；`plans/demo_101_102.json` |

### 1.2 T1 edge-agent（team §T1）

| 项 | 文件 / 说明 |
|----|-------------|
| FastAPI `:9000` | `edge-agent/main.py` |
| REST 全套 P4 | `POST /play` `/pause` `/resume` `/next` `/seek` `/trigger` `/load_plan`；`GET /health` `/state` |
| Unix socket 转发 | `edge_agent/audio_client.py` → `/tmp/cypher-audio.sock` |
| `load_plan` 落盘 | 写入 `plans/current.json`，转发 `mix_plan` 给 audio-engine |
| 可选鉴权 | Header `X-Edge-Token`（`EDGE_TOKEN` 环境变量） |
| WebSocket `:9001/ws` | `edge_agent/ws_server.py`：200ms `playback_state`、5s `device_info`、`key_event` |
| input-daemon 回调 | `POST /internal/key_event` |
| 事件缓冲（内存） | `edge_state.event_buffer` + `append_event`（play/pause/load 等） |
| systemd | `deploy/cypher-edge-agent.service`，纳入 `cypher.target` |

### 1.3 T3 / T4 audio-engine（team §T3、§T4）

| 项 | 说明 |
|----|------|
| 双 deck + crossfade | `audio-engine/engine.py`，equal-power 曲线 |
| MixPlan 自动切歌 | 到点 preload + 8s crossfade；支持 P2 与 Jetson `transition_plan`（`mix_plan.py`） |
| 手动下一首 | `POST /next` → 立即 crossfade |
| 本地播放 | `cache/<song_id>/original.wav`，44100 stereo |
| 九键 1–6 | one-shot（1–3）、loop toggle（4–6） |
| 九键 7–9 | mute_vocals / solo_drums / lpf（**需 cache 内有 4 个 stem**） |
| 键 0 暂停/继续 | 经 API `trigger key=0`（硬件无 0 键） |
| 缺 original 返回 409 | `check_song_cache` → edge-agent 透传 |
| Unix socket 服务 | `audio-engine/socket_server.py` |
| systemd | `deploy/cypher-audio-engine.service`（`Nice=-10`，PulseAudio 环境变量） |

### 1.4 T5 input-daemon（team §T5 前半）

| 项 | 说明 |
|----|------|
| evdev 九键 | MYKB E9s，`KEY_1~9` + `KEY_KP*` 映射 |
| 低延迟路径 | 按键 → 直连 audio socket `trigger` |
| WS 通知 | 按键 → `POST edge-agent/internal/key_event` |
| 设备 grab / 多节点 | 支持 by-id、fallback event 路径 |
| 断线重连 | 约 5s 重试（`INPUT_RECONNECT_SEC`） |
| systemd | `deploy/cypher-input-daemon.service` |

### 1.5 部署与文档

| 项 | 说明 |
|----|------|
| systemd 三服务 + target | `cypher.target`、`install-systemd.sh`、`cypher.env` |
| 交付 README | `~/cypher/README.md`（含 App §7、Jetson §8 联调说明） |
| 本机验证 | `curl /play`、`load_demo_plan.sh` 自动 101→102 crossfade |

### 1.6 Jetson 交接文档 · 已由 RK 承接的部分（handoff）

| 项 | 说明 |
|----|------|
| 接收 App 推送的 MixPlan | `POST /load_plan`，两种 JSON 格式均可解析 |
| 接收 App 推送的 Manifest | body 存入 `current.json`；**不自行拉取** |
| RK 暴露 HTTP 给 App | `:9000` REST + `:9001` WS |
| `GET /health` | 简化版（`ok`、`audio_ready`、`plan_id` 等） |

---

## 二、部分完成（有代码但未到文档标准）

| 任务 | 已有 | 缺口 |
|------|------|------|
| `load_plan` → sync | edge-agent 会 `POST :9100/sync` | **sync-worker 进程不存在**，恒为 `sync_error` |
| WS `playback_state` | 200ms 广播 | **进度不跟 audio-engine**，仅在 REST 命令时更新 `position_sec` |
| WS `device_info` | 5s 广播 | CPU/内存/温度/`jetson_reachable` **未采集**，多为默认值 |
| audio-engine 事件推 WS | — | 无 subscribe；**crossfade 开始/结束不会即时推 App** |
| `play` 缓存检查 | 缺 `original.wav` → 409 | 文档要求 **original + 4 stems**；当前 **不强制 stems** |
| 九键 7–9 | 逻辑已实现 | `cache/` 无 `vocals/drums/bass/other.wav`，现场无效 |
| 键 0 | API 支持 | 硬件九键盒 **无 0 键** |
| systemd | 3 服务 `Restart=always` | 缺 **第 4 个 sync-worker**；无 `CPUAffinity` / realtime IO |
| plan 恢复 | edge-agent 启动读 `plan_id` | **audio-engine 重启不会自动 `load_plan`** |
| LPF（键 9） | 简化一阶滤波 | 非文档 scipy biquad 8kHz→200Hz 扫频 |
| 样本音量 | 6 个 wav 已生成 | 未严格校验 peak ≤ -6dB |
| Jetson env | `deploy/cypher.env` 注释项 | `JETSON_BASE_URL`、`JWT_TOKEN` **代码未读取使用**（sync 除外 URL 也未用） |

---

## 三、未完成

### 3.1 T2 sync-worker（team §T2）— **整块未做**

| 项 | 文档要求 |
|----|----------|
| 进程 | `~/cypher/sync-worker/main.py`，FastAPI `:9100` |
| 接口 | `POST /sync`（body: manifest）、`GET /status` |
| 下载 | `JETSON_BASE_URL` + 相对 URL；HTTP Range；sha256 + size 校验 |
| 并发 | `asyncio.Semaphore(4)` |
| 落盘 | `cache/<song_id>/original.wav` + 4× stem |
| 转换 | 下载后统一 44100 Hz stereo WAV（文档建议） |
| systemd | 第 4 个 unit + 纳入 `cypher.target` |

**现状**：`sync-worker/` 仅 `.gitkeep`，无 Python 实现。

### 3.2 T5 SessionEvent（team §T5 后半 + handoff §5）

| 项 | 文档要求 |
|----|----------|
| 上报 | `POST {JETSON}/api/sessions/rk/{session_id}/events` |
| Header | `Authorization: Bearer`、可选 `X-RK-Token` |
| Flush | 满 50 条或 5s；失败保留 buffer |
| 持久化 | `~/cypher/logs/events-buffer.jsonl`；启动优先重放 |
| session_id | UUID 自管理（每场 cypher） |
| 事件词表 | `play_started`、`crossfade_start`、`key_press` 等与 App 对齐 |

**现状**：`event_buffer` 仅内存；`logs/` 空；**无任何 httpx 调 Jetson**。

### 3.3 edge-agent 与 audio-engine 联动缺口（team §T1 WS）

| 项 | 文档要求 |
|----|----------|
| 订阅 audio-engine | Unix socket subscribe，把 progress / transition 转 WS |
| 实时 `position_sec` | App WS 应反映真实播放进度 |
| `DeviceInfo` | cpu、mem、temp、disk、`jetson_reachable`、wifi 等 |

### 3.4 Jetson 交接 · RK 必须实现的部分（handoff）

| 章节 | 未完成内容 |
|------|------------|
| §1 步骤 6–7 | RK 按 manifest **自动下载** stems（当前靠手拷 / ffmpeg） |
| §2 AssetManifest | RK **GET** `/api/playlists/{id}/manifest`（可选，App 已推则可不做） |
| §3 下载策略 | Range 分块、重试退避、超时、并发策略 |
| §4 主动拉 plan | `GET .../mix-plan/latest`（可选路径） |
| §5 SessionEvent | 见 §3.2 |
| §9 错误矩阵 | 401 刷新 token、409 通知 App、5xx 重试等 **未编码** |
| §11 联调 | JWT 登录、真 manifest 大清单下载、Jetson 侧查事件 |

### 3.5 文档「完工自检」未勾项（team 文末）

- [ ] App WS 持续收到**真实进度**的 `playback_state`（当前 position 不跟播）
- [ ] Jetson 能查到本场 **SessionEvent**
- [ ] sync-worker 对 manifest（如 5 首 ~1GB）**10min 内下载且 sha256 全过**
- [ ] 硬件键 **7–9** 在真实 stem 下全生效（需 cache 齐 5 个 wav）
- [ ] audio-engine 重启后从 **`plans/current.json` 恢复** MixPlan 到引擎
- [ ] （可选）云网关 `/edge/rk-001/*` 与 RK 联调登记

---

## 四、按任务编号速查（team-rk3588-edge.md）

| 任务 | 标题 | 状态 |
|------|------|------|
| **T1** | edge-agent FastAPI 接口集 | ✅ 完成（WS 实时进度、DeviceInfo 为部分） |
| **T2** | sync-worker 拉清单 + 下载 + 校验 | ❌ 未开始 |
| **T3** | audio-engine 双 deck + crossfade | ✅ 核心完成 |
| **T4** | 9 键加花引擎 | ✅ 1–6 完成；7–9 依赖 stem 文件 |
| **T5** | input-daemon + SessionEvent | ⚠️ 前半 ✅ / 后半 ❌ |

---

## 五、建议实施顺序

1. **T2 sync-worker** — 阻塞与 Jetson 真联调、完整 cache
2. **T5 SessionEvent flush** — 含 `logs/events-buffer.jsonl` + JWT
3. **T1 WS 进度** — edge-agent 轮询或订阅 audio-engine `get_state`
4. **T3 对齐** — 启动加载 `current.json`；是否强制 5 文件 409；补 stem 或文档降级 7–9
5. **端到端** — App `load_plan` → sync → play → Jetson 查事件

---

## 六、相关文件索引

| 用途 | 路径 |
|------|------|
| RK 实现规范 | `~/桌面/team-rk3588-edge.md` |
| Jetson 交接 | `~/桌面/jetson-handoff-for-rk3588.md` |
| 交付说明 | `~/cypher/README.md` |
| edge-agent | `~/cypher/edge-agent/main.py` |
| audio-engine | `~/cypher/audio-engine/engine.py` |
| input-daemon | `~/cypher/input-daemon/main.py` |
| systemd | `~/cypher/deploy/` |
| 环境变量 | `~/cypher/deploy/cypher.env` |

---

*本文档随代码变更更新；以仓库内实际文件为准。*
