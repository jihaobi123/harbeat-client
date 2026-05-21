# Cypher RK3588 现场盒 — 交付与联调说明

> 面向：接手 RK3588 开发的工程师，以及 **App（C）**、**Jetson（A）** 联调负责人。  
> 板子角色：现场实时播放 + 九键加花 + 按 MixPlan 自动 crossfade；**不算歌、不存曲库**。

关联文档（桌面/仓库）：

| 文档 | 内容 |
|------|------|
| `cypher-feature-flows.md` | 三机架构、协议 P1–P8、端到端时间线 |
| `team-rk3588-edge.md` | RK 任务 T1–T5 规范 |
| `jetson-handoff-for-rk3588.md` | Jetson 接口、manifest、SessionEvent |

---

## 1. 架构与职责

```
┌─────────────┐  慢链路(赛前)   ┌──────────────┐
│ 手机 App(C) │ ──────────────▶│ Jetson(A)    │
│             │  MixPlan/Manifest│ GrooveEngine │
└──────┬──────┘                 └──────┬───────┘
       │ 快链路(现场) LAN               │ Tailscale
       │ HTTP/WS :9000/:9001          │ manifest/下载
       ▼                              ▼
┌──────────────────────────────────────────────┐
│ RK3588 现场盒 (本仓库 ~/cypher/)              │
│  edge-agent → audio-engine ← input-daemon    │
│  本地 cache/  plans/  samples/               │
└──────────────────────────────────────────────┘
       │
       ▼ 耳机 / USB 声卡
```

| 层 | 执行位置 | RK 是否实现 |
|----|----------|-------------|
| L1 排歌 / MixPlan | Jetson 赛前 | 只消费 JSON |
| L2 crossfade 切歌 | **RK 现场** | **已实现** |
| L3 九键加花 | **RK 现场** | **已实现（1–6；7–9 需 stem）** |
| 曲库下载 | RK sync-worker | **已实现 MVP（需 Jetson token / ffmpeg 联调）** |
| SessionEvent 上报 | RK → Jetson | **已实现 MVP（批量 flush + 失败落盘）** |

---

## 2. 已完成内容（截至交付）

### 2.1 进程与服务

| 组件 | 路径 | 端口/接口 | 状态 |
|------|------|-----------|------|
| **edge-agent** | `edge-agent/` | HTTP **9000**，WS **9001** `/ws` | 可用 |
| **audio-engine** | `audio-engine/` | Unix `/tmp/cypher-audio.sock` | 可用 |
| **input-daemon** | `input-daemon/` | 读 USB 九键 MYKB E9s | 可用 |
| **sync-worker** | `sync-worker/` | HTTP **9100** | 可用 |
| **systemd** | `deploy/` | `cypher.target` 三服务 | 可用（可选） |

### 2.2 功能清单

- [x] `POST /play` `/pause` `/resume` `/next` `/seek` `/trigger` `/load_plan`
- [x] `GET /health` `/state`；WS 推送 `playback_state`（200ms）、`device_info`（5s）
- [x] 本地播放 `cache/<song_id>/original.wav`（44100 stereo WAV）
- [x] 九键 1–6：one-shot / loop；7–9：stem 效果（需 4 个 stem 文件）
- [x] 双 deck + MixPlan 自动 **8s crossfade**（P2 + Jetson `transition_plan` 均可解析）
- [x] `POST /internal/key_event`（input-daemon → edge-agent WS）
- [x] 演示计划 `plans/demo_101_102.json`（101→102 @ 4s）
- [x] sync-worker 按 manifest 从 Jetson 下载 + sha256（待真 Jetson manifest 压测）
- [x] SessionEvent 批量上报 `POST /api/sessions/rk/{id}/events`（待 Jetson token 联调）
- [ ] App 正式联调 / 云网关 `rk-001` 注册 IP

### 2.3 环境

- 硬件：RK3588（LubanCat），板载 **3.5mm 耳机**（PulseAudio），USB **MYKB E9s** 九键
- Python：`~/venvs/edge/`（3.10+）
- 用户 `cat` 需在 **`input` 组**（九键）：`sudo usermod -aG input cat` 后重新登录

---

## 3. 目录结构

```
~/cypher/
├── edge-agent/          # REST + WebSocket
├── audio-engine/        # 播放、crossfade、加花
├── input-daemon/        # 九键 HID
├── sync-worker/         # Jetson manifest 下载 + sha256 校验
├── cache/<song_id>/     # 歌曲缓存
│   ├── original.wav     # 播放必需
│   ├── vocals.wav       # 键 7–9 可选
│   ├── drums.wav
│   ├── bass.wav
│   └── other.wav
├── samples/             # 九键 01_ha ~ 06_hat_loop
├── plans/               # MixPlan；load_plan 写入 current.json
├── deploy/              # systemd、cypher.env
└── logs/                # SessionEvent 落盘 / session_id
```

---

## 4. 安装依赖（首次）

```bash
python3 -m venv ~/venvs/edge
source ~/venvs/edge/bin/activate
pip install -r ~/cypher/edge-agent/requirements.txt
pip install -r ~/cypher/audio-engine/requirements.txt
pip install evdev   # input-daemon

sudo usermod -aG input,audio cat
# 重新 SSH 登录
```

生成测试素材：

```bash
python ~/cypher/audio-engine/scripts/make_test_wav.py      # cache/101
python ~/cypher/audio-engine/scripts/make_samples.py     # samples/
```

导入真歌（示例）：

```bash
mkdir -p ~/cypher/cache/102
ffmpeg -i "/path/to/song.mp3" -ar 44100 -ac 2 ~/cypher/cache/102/original.wav
```

---

## 5. 如何运行（二选一，勿同时）

### 5.1 方式 A：systemd（推荐长期挂机）

```bash
sudo bash ~/cypher/deploy/install-systemd.sh
sudo systemctl start cypher.target
sudo systemctl enable cypher.target   # 开机自启
```

配置：`~/cypher/deploy/cypher.env`（声卡 `CYPHER_AUDIO_DEVICE=pulse`、九键路径等）

```bash
# 验证
systemctl status cypher.target
curl -s http://127.0.0.1:9000/health
```

停止后改用手动：

```bash
sudo systemctl stop cypher.target
```

### 5.2 方式 B：手动三终端（调试推荐）

**必须先 audio-engine，再 edge-agent。**

```bash
# 若 systemd 在跑，先停
sudo systemctl stop cypher.target
pkill -f cypher || true
```

| 终端 | 命令 |
|------|------|
| 1 | `source ~/venvs/edge/bin/activate && python ~/cypher/audio-engine/main.py` |
| 2 | `source ~/venvs/edge/bin/activate && cd ~/cypher/edge-agent && python run.py` |
| 3 | `newgrp input` 后 `python ~/cypher/input-daemon/main.py` |

确认 socket：

```bash
ls -la /tmp/cypher-audio.sock
```

---

## 6. 本机自测（无需 App / Jetson）

复制整行执行（避免引号/换行错误）：

```bash
# 健康
curl -s http://127.0.0.1:9000/health

# 播放《等你下课》song_id=102
curl -X POST http://127.0.0.1:9000/play -H "Content-Type: application/json" -d '{"song_id":102}'

# 加花
curl -X POST http://127.0.0.1:9000/trigger -H "Content-Type: application/json" -d '{"key":1}'

# 自动切歌 demo（101 → 102，约 4s 后 crossfade）
bash ~/cypher/audio-engine/scripts/load_demo_plan.sh

# 手动下一首
curl -X POST http://127.0.0.1:9000/next -H "Content-Type: application/json" -d '{}'
```

九键：先 `play`，再按键盘；日志：`journalctl -u cypher-input -f` 或终端 3 输出。

---

## 7. 与 App（C）联调

### 7.1 网络

- App 与 RK 在 **同一局域网**，直连 RK IP（不要用 127.0.0.1）。
- 快链路目标：`http://<RK_LAN_IP>:9000`，WS：`ws://<RK_LAN_IP>:9001/ws`。

### 7.2 App → RK 接口（协议 P4）

| 方法 | 路径 | Body 示例 |
|------|------|-----------|
| POST | `/play` | `{"song_id":102,"start_at_sec":0}` |
| POST | `/pause` | `{}` |
| POST | `/resume` | `{}` |
| POST | `/next` | `{}` |
| POST | `/seek` | `{"sec":30.5}` |
| POST | `/trigger` | `{"key":1}` （0–9，本硬件无 0 键可只用 API） |
| POST | `/load_plan` | `{"mix_plan":{...},"manifest":{...}}` |
| GET | `/health` | — |
| GET | `/state` | — |

`load_plan` 会：

1. 写入 `~/cypher/plans/current.json`
2. 转发 `mix_plan` 给 audio-engine
3. 尝试 `POST http://127.0.0.1:9100/sync`（sync-worker 后台下载，不阻塞 plan 加载）

### 7.3 App 订阅 WS（协议 P5 / P8）

连接 `ws://<RK_IP>:9001/ws`，接收：

- `playback_state`（约 200ms）：`playing`, `current_song_id`, `position_sec`, `next_song_id`, `next_transition_in_sec`, `active_loops`
- `device_info`（约 5s）
- `key_event`：`{"type":"key_event","key":1,"source":"hid"|"app"}`

### 7.4 推荐现场流程（与 Jetson 配合）

```
1. App → Jetson：生成 MixPlan + Manifest（赛前）
2. App → RK POST /load_plan（带 mix_plan + manifest）
3. RK：sync-worker 下载 cache（真机需配置 `JETSON_BASE_URL` / `JWT_TOKEN`）
4. App → RK POST /play {第一首 song_id}
5. 现场：App 控制 + 九键；RK 到点自动 crossfade
```

### 7.5 App 联调检查表

- [ ] 同 WiFi 能 `curl http://<RK_IP>:9000/health`
- [ ] `load_plan` 后 `health` 含 `plan_id`
- [ ] `play` 后 WS 有 `playback_state` 进度
- [ ] `trigger` 与九键行为一致
- [ ] 断 Jetson 后 RK 仍能 `play` 已缓存歌曲

---

## 8. 与 Jetson（A）联调

### 8.1 网络与配置

| 项 | 值 |
|----|-----|
| Jetson Base URL | `http://100.87.142.21:8000`（Tailscale，以交接文档为准） |
| RK ID | `rk-001`（云网关注册） |
| RK 暴露给网关 | `http://<RK_TAILSCALE_OR_LAN_IP>:9000` |

在 `~/cypher/deploy/cypher.env` 中取消注释并填写：

```bash
JETSON_BASE_URL=http://100.87.142.21:8000
RK_ID=rk-001
# JWT_TOKEN=<service-account 登录后 Bearer>
# HARBEAT_RK_TOKEN=<若 Jetson 启用>
```

### 8.2 Jetson → RK：Manifest 与下载

- `GET /api/playlists/{id}/manifest` → 得到每首歌 `url` + `sha256`
- 下载：`GET /api/stream/{song_id}`、`/api/stream/{song_id}/stem/{name}`
- RK 落盘：`~/cypher/cache/<song_id>/original.wav` 等
- URL 拼接：`JETSON_BASE_URL + 相对路径`

`sync-worker` 已提供 `POST /sync` 与 `GET /status`。真机联调时需确保 `deploy/cypher.env` 中配置 `JETSON_BASE_URL`、`JWT_TOKEN`，若 Jetson 返回 MP3 则 RK 需安装 `ffmpeg` 转为 44100 stereo wav。

### 8.3 App → RK：MixPlan 格式

RK `audio-engine` 已支持两种 JSON：

**协议 P2（cypher-feature-flows）：**

```json
{
  "plan_id": "uuid",
  "tracks": [{"song_id": 101, "order": 0}],
  "transitions": [{
    "from_song": 101, "to_song": 102,
    "from_at_sec": 174, "to_at_sec": 0,
    "fade_sec": 8, "fade_curve": "equal_power"
  }]
}
```

**Jetson DjMixPlanResult：**

```json
{
  "playlist": [{"song_id": 88, "library_song_id": 88}],
  "transition_plan": [{
    "from_song_id": 88, "to_song_id": 89,
    "from_out_sec": 200.0, "to_in_sec": 0.0,
    "crossfade_sec": 8.0
  }]
}
```

由 `audio-engine/mix_plan.py` 统一解析。

### 8.4 RK → Jetson：SessionEvent

- `POST /api/sessions/rk/{session_id}/events`
- Body：`{"rk_id":"rk-001","events":[...]}`
- 建议：满 50 条或 5s flush；失败写 `logs/events-buffer.jsonl`

### 8.5 Jetson 联调检查表

- [ ] RK `curl -H "Authorization: Bearer $TOKEN" $JETSON/api/playlists/12/manifest`
- [ ] sync 完成后 `ls cache/<id>/` 含 original + 4 stems
- [ ] `play` 不返回 409
- [ ] 到 transition 点自动 crossfade
- [ ] SessionEvent 在 Jetson 可查询

### 8.6 云网关反控 RK（可选）

`POST https://<gw>/edge/rk-001/play` → 透传到 RK `:9000/play`（需网关注册 RK 可达地址）。

---

## 9. 九键映射（MYKB E9s）

| 键 | 功能 | sample / 条件 |
|----|------|----------------|
| 1 | ha one-shot | `01_ha.wav` |
| 2 | scratch | `02_scratch.wav` |
| 3 | horn | `03_horn.wav` |
| 4 | 鼓 loop toggle | `04_drum_loop.wav` |
| 5 | bass loop toggle | `05_bass_loop.wav` |
| 6 | hi-hat loop toggle | `06_hat_loop.wav` |
| 7 | mute 人声 2s | 需 `vocals.wav` |
| 8 | solo 鼓 2s | 需 `drums.wav` |
| 9 | 低通 2s | 需 stems |
| — | 暂停/继续 | 本硬件**无 0 键**，用 App/`POST /pause` |

设备路径：`INPUT_DEVICE_PATH=/dev/input/by-id/usb-MYKB_E9s_vial:f64c2b3c-event-kbd`（见 `cypher.env`）

---

## 10. 常见问题

| 现象 | 处理 |
|------|------|
| `audio socket 不存在` | 先起 **audio-engine**，再起 edge-agent；`ls /tmp/cypher-audio.sock` |
| `address already in use` :9000 | systemd 与手动二选一：`sudo systemctl stop cypher.target` |
| systemd 无声 | `cypher.env` 设 `CYPHER_AUDIO_DEVICE=pulse`，并含 `XDG_RUNTIME_DIR=/run/user/1000` |
| 九键无反应 | `newgrp input` 或 systemd 已启；先 `play`；`journalctl -u cypher-input -f` |
| `curl` 报 JSON 错 | 用单行命令；JSON 引号闭合：`'{"song_id":102}'` |
| `play` 409 | 缺 `cache/<id>/original.wav` |
| 键 7–9 无效 | 缺 4 个 stem 文件 |

声卡测试：

```bash
bash ~/cypher/deploy/test-sound.sh
```

---

## 11. 接手人待办（建议优先级）

1. **与 App 联调**：LAN IP、WS、`load_plan` 进度（sync 状态可用 `/status`）
2. **与 Jetson 联调**：JWT、manifest、真 plan 多场 crossfade
3. **压测 sync-worker**：多首歌 / 大文件 / sha256 / ffmpeg 转码耗时
4. **压测 SessionEvent**：断网落盘、恢复补发、Jetson 查询一致性
5. 云网关注册 `rk-001` → RK 当前 Tailscale/LAN IP
6. systemd 与手动部署文档统一（本文 §5）

---

## 12. 三方联系人约定（填写）

| 角色 | 负责人 | 备注 |
|------|--------|------|
| RK3588 |  | 本文档、`~/cypher/` |
| Jetson |  | `jetson-handoff-for-rk3588.md` |
| App |  | `team-mobile-app.md`（若有） |

---

## 13. 参考命令速查

```bash
# 状态
systemctl status cypher.target
curl -s http://127.0.0.1:9000/health
curl -s http://127.0.0.1:9000/state
curl -s http://127.0.0.1:9100/status

# 日志
journalctl -u cypher-audio -u cypher-edge -u cypher-input -u cypher-sync -f

# 重启服务
sudo systemctl restart cypher.target

# 本机冒烟测试
bash ~/cypher/deploy/rk-smoke-test.sh
```

---

*文档版本：与当前 `~/cypher/` 代码一致；sync-worker / SessionEvent 为 MVP，可进入真机联调与压测。*
