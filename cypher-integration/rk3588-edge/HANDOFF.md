# Cypher RK3588 现场盒 — 交接与联调说明

> **版本**：2026-05-21
> **仓库**：https://github.com/Trail-0511/cypher-rk3588
> **板子路径**：`~/cypher/`（用户 `cat`，venv `~/venvs/edge/`）
> **读者**：接手 RK 开发、HarBeat App 联调、Jetson 后端联调

---

## 1. 项目是做什么的

RK3588 在现场演出中扮演 **「播放 + 加花 + 按排歌计划切歌」** 的盒子：

| 做 | 不做 |
|----|------|
| 接收 App 的播放/暂停/切歌/加花命令 | 上传曲库、GPU 分析、生成 MixPlan |
| 按 MixPlan 自动 8 秒 crossfade | 存全曲库（只缓存本场 manifest） |
| USB 九键实时加花（&lt;30ms） | App UI |
| 可选：从 Jetson 下载音频到本地 cache | |

**三机分工**（详见桌面 `cypher-feature-flows.md`）：

- **Jetson**：赛前 MixPlan、AssetManifest、曲库分析
- **RK3588（本仓库）**：现场快链路
- **手机 App**：UI + 双链路客户端

---

## 2. 进程与端口（联调必看）

```
手机 App ──HTTP/WS──▶ edge-agent :9000
                         │
                         ▼ Unix socket
                    audio-engine
                         ▲
USB 九键 ──▶ input-daemon ─┘

App/Jetson 慢链路 ──▶ sync-worker :9100（仅下载，可选）
```

| 服务 | systemd 单元 | 端口/路径 | 说明 |
|------|----------------|-----------|------|
| **edge-agent** | `cypher-edge-agent` | **HTTP + WS 均在 `9000`** | HarBeat App 主入口 |
| **audio-engine** | `cypher-audio-engine` | `/tmp/cypher-audio.sock` | 播放、crossfade、FX |
| **input-daemon** | `cypher-input-daemon` | evdev USB HID | MYKB E9s 九键 |
| **sync-worker** | `cypher-sync-worker` | `9100`（默认未随 target 拉起） | manifest 下载 |

### 2.1 App 使用的地址（重要）

在 RK 上查 **当前局域网 IP**（会随 WiFi 变化）：

```bash
hostname -I | awk '{print $1}'
# 示例：10.203.164.80
```

| 用途 | URL |
|------|-----|
| HTTP 基址 | `http://<RK_LAN_IP>:9000` |
| 设备信息 | `GET /api/edge/info` |
| 播放状态 | `GET /api/edge/status` |
| WebSocket | `ws://<RK_LAN_IP>:9001/ws` |

**不要用** `127.0.0.1` 给手机填。当前 WS 独立监听 `9001`，暂未强制 token。

更完整的 App 字段定义见仓库内 `RK3588_API_SPEC.md`；App 自带的 `mock_rk3588_server.py` 仅用于 App 自测，**以真机 edge-agent 为准**。

---

## 3. 首次部署（RK 板子上）

### 3.1 克隆与依赖

```bash
git clone https://github.com/Trail-0511/cypher-rk3588.git ~/cypher
python3 -m venv ~/venvs/edge
source ~/venvs/edge/bin/activate
pip install -r ~/cypher/edge-agent/requirements.txt
pip install -r ~/cypher/audio-engine/requirements.txt
pip install -r ~/cypher/sync-worker/requirements.txt
pip install evdev
sudo apt install -y ffmpeg   # sync 转码 MP3→wav 需要
```

### 3.2 用户权限

```bash
sudo usermod -aG input,audio cat
# 重新登录 SSH 后生效（九键需要 input 组）
```

### 3.3 配置文件

```bash
cp ~/cypher/deploy/cypher.env.example ~/cypher/deploy/cypher.env
nano ~/cypher/deploy/cypher.env
```

| 变量 | 说明 | 示例 |
|------|------|------|
| `CYPHER_HOME` | 项目根目录 | `/home/cat/cypher` |
| `CYPHER_AUDIO_DEVICE` | 声卡 | `pulse` 或 `2`（ES8388 耳机孔） |
| `INPUT_DEVICE_PATH` | 九键 by-id 路径 | 见 `sniff_keys.py` |
| `PUBLIC_BASE_URL` | **给 App 的 LAN 地址** | `http://10.203.164.80:9000` |
| `JETSON_BASE_URL` | Jetson Tailscale | 联调时填写 |
| `JWT_TOKEN` | Jetson Bearer | 联调时填写 |
| `RK_ID` | 上报用 | `rk-001` |

**勿将** `cypher.env`（含 token）提交 Git；已在 `.gitignore`。

### 3.4 systemd 开机自启

```bash
sudo bash ~/cypher/deploy/install-systemd.sh
sudo systemctl enable cypher.target
sudo systemctl start cypher.target
# 若需要 sync：
sudo systemctl enable --now cypher-sync-worker
```

### 3.5 测试素材

```bash
python ~/cypher/audio-engine/scripts/make_test_wav.py   # cache/101
python ~/cypher/audio-engine/scripts/make_samples.py    # samples/

# 导入真歌（示例）
mkdir -p ~/cypher/cache/102
ffmpeg -i /path/to/song.mp3 -ar 44100 -ac 2 ~/cypher/cache/102/original.wav
```

---

## 4. 日常运维命令

```bash
# 状态
systemctl status cypher.target
curl -s http://127.0.0.1:9000/health
curl -s http://127.0.0.1:9000/api/edge/info

# 日志
journalctl -u cypher-edge -u cypher-audio -u cypher-input -f

# 重启（改代码或 cypher.env 后）
sudo systemctl restart cypher.target

# 本机冒烟
bash ~/cypher/deploy/rk-smoke-test.sh
```

### 4.1 不要混用手动 `python run.py`

若已用 systemd，`python run.py` 会与 `cypher-edge-agent` **抢 9000**，出现 `address already in use`。

- **日常**：只用 `sudo systemctl restart cypher-edge-agent`
- **调试**：先 `sudo systemctl stop cypher-edge-agent`，再手动 `python run.py`

---

## 5. 本机播放与九键测试

### 5.1 播放

```bash
# 短测试曲
curl -X POST http://127.0.0.1:9000/play \
  -H "Content-Type: application/json" \
  -d '{"song_id":101,"start_at_sec":0}'

# 长曲
curl -X POST http://127.0.0.1:9000/play \
  -H "Content-Type: application/json" \
  -d '{"song_id":102,"start_at_sec":0}'

curl -X POST http://127.0.0.1:9000/pause  -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:9000/resume -H "Content-Type: application/json" -d '{}'
```

成功返回含 `"success":true`；耳机/音箱应有声。

### 5.2 加花（curl 模拟 App）

```bash
curl -X POST http://127.0.0.1:9000/play -H "Content-Type: application/json" -d '{"song_id":101}'
curl -X POST http://127.0.0.1:9000/trigger -H "Content-Type: application/json" -d '{"key":1}'
```

| 键 | 效果 | 依赖 |
|----|------|------|
| 1–3 | one-shot（ha/scratch/horn） | `samples/01~03_*.wav` |
| 4–6 | loop toggle | `samples/04~06_*.wav` |
| 7–9 | stem FX | cache 内 4 个 stem wav |
| 0 | 暂停/继续（仅 API） | 硬件无 0 键 |

### 5.3 硬件九键

1. 先 `play`
2. 按 MYKB 1–9
3. 日志：`journalctl -u cypher-input-daemon -f`

### 5.4 自动切歌 demo

```bash
bash ~/cypher/audio-engine/scripts/load_demo_plan.sh
# 101 播约 4s 后 8s crossfade 到 102
```

---

## 6. HarBeat App 联调（详细）

### 6.1 网络前提

- [ ] 手机与 RK **同一 WiFi**（非访客网络、非蜂窝）
- [ ] 手机 IP 与 RK 同网段（如 `10.203.164.x`）
- [ ] 路由器关闭 **AP/无线隔离**（否则手机访问不了 RK）
- [ ] RK 上 `hostname -I` 的 IP 与 App 配置一致

**手机浏览器验证**（不经过 App）：

```
http://<RK_LAN_IP>:9000/api/edge/info
```

应看到 JSON；若打不开，先解决网络，再调 App。

### 6.2 配对流程

```bash
# 1. 开始配对（返回 6 位 pair_code）
curl -s http://<RK_IP>:9000/api/edge/pair/start

# 2. 确认配对
curl -s -X POST http://<RK_IP>:9000/api/edge/pair/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "rk3588-01",
    "pair_code": "123456",
    "client_name": "HarBeat Mobile",
    "client_type": "mobile"
  }'
```

响应中的 `device_token` 用于后续请求：

```
Authorization: Bearer <device_token>
```

默认 `REQUIRE_DEVICE_TOKEN=0`（未强制）；联调稳定后可设 `REQUIRE_DEVICE_TOKEN=1`。

### 6.3 App HTTP 接口清单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/edge/info` | 设备信息 |
| GET | `/api/edge/status` | 播放状态（含 duration_sec、bpm） |
| GET | `/api/edge/pair/start` | 配对码 |
| POST | `/api/edge/pair/confirm` | 获取 token |
| POST | `/play` | `{"song_id":102,"start_at_sec":0}` |
| POST | `/pause` `/resume` `/next` `/seek` | 播放控制 |
| POST | `/trigger` | `{"key":1}`，返回 `latency_ms` |
| 规划中 | `/energy` `/style` `/mix` `/loop` | 现场 UI 控制，当前尚未暴露 |
| POST | `/load_plan` | **赛前必用**，见下节 |

播放类接口成功格式：`{"success":true,"message":"...","ok":true,...}`。

### 6.4 赛前 `load_plan`（App → RK）

```bash
curl -X POST http://<RK_IP>:9000/load_plan \
  -H "Content-Type: application/json" \
  -d @/path/to/plan_and_manifest.json
```

body 结构：

```json
{
  "mix_plan": { "plan_id": "...", "tracks": [...], "transitions": [...] },
  "manifest": { "plan_id": "...", "tracks": [{ "song_id": 101, "files": {...} }] }
}
```

RK 会：

1. 写入 `~/cypher/plans/current.json`
2. 通知 audio-engine 加载 MixPlan
3. 异步调用 sync-worker `POST :9100/sync` 下载 cache

查下载进度：

```bash
curl -s http://127.0.0.1:9100/status
# 或 health 里的 sync_status
```

### 6.5 WebSocket

连接：

```
ws://<RK_LAN_IP>:9001/ws
```

推送类型：

| type | 频率 | 内容 |
|------|------|------|
| `playback_state` | ~200ms | 播放进度 |
| `device_info` | ~5s | CPU/内存/Jetson 可达等 |
| `key_event` | 按键时 | 硬件/App 触发 |

### 6.6 Android 注意

Android 9+ 需 App 侧允许 **明文 HTTP**（`usesCleartextTraffic` 或网络安全配置放行 RK IP），否则只有浏览器能访问、App 连不上。

### 6.7 发给 App 同学的联调包（可复制）

```
【RK3588 联调】
仓库: https://github.com/Trail-0511/cypher-rk3588
LAN IP: <填 hostname -I 结果>
HTTP: http://<IP>:9000
WS:   ws://<IP>:9001/ws
测试: GET /api/edge/info
配对: GET /api/edge/pair/start → POST /api/edge/pair/confirm
赛前: POST /load_plan（mix_plan + manifest）
现场: POST /play → POST /trigger
说明: RK3588_API_SPEC.md（仓库根目录）
```

---

## 7. Jetson 联调（详细）

详见桌面 `jetson-handoff-for-rk3588.md`。RK 侧要点：

### 7.1 需要 Jetson 提供

| 项 | 用途 |
|----|------|
| `JETSON_BASE_URL` | 如 `http://100.87.142.21:8000` |
| `JWT_TOKEN` | service-account Bearer |
| `RK_ID` | 如 `rk-001` |
| `HARBEAT_RK_TOKEN` | 可选 |
| 真 manifest / MixPlan | App push 或 RK 拉取 |

写入 `~/cypher/deploy/cypher.env` 后：

```bash
sudo systemctl restart cypher-edge-agent
sudo systemctl start cypher-sync-worker
```

### 7.2 下载与 cache 目录

下载后文件布局：

```
~/cypher/cache/<song_id>/
  original.wav
  vocals.wav
  drums.wav
  bass.wav
  other.wav
```

`play` 至少需要 `original.wav`；键 7–9 需要 4 个 stem。

### 7.3 SessionEvent 上报

RK 自动批量：

`POST {JETSON}/api/sessions/rk/{session_id}/events`

Body：`{"rk_id":"...","events":[...]}`

失败写入 `~/cypher/logs/events-buffer.jsonl`，启动时重试。

手动刷一次：

```bash
curl -X POST http://127.0.0.1:9000/internal/flush_events -d '{}'
```

Jetson 侧验证事件是否入库。

---

## 8. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `No output device matching 'pulse'` | 声卡/Pulse 未就绪 | `cypher.env` 改 `CYPHER_AUDIO_DEVICE=2`，`sudo systemctl restart cypher-audio-engine` |
| `address already in use` :9000 | systemd 与手动 run.py 冲突 | 只保留一种；`stop cypher-edge-agent` 后再调试 |
| 杀了进程又出现新 PID | `Restart=always` | 用 `systemctl stop`，不要只 `kill` |
| App 连不上 9000 | 错 IP/端口/隔离/https | 手机浏览器测 `/api/edge/info`；填 LAN IP；关 AP 隔离 |
| `pair/start` 里 `local_url` 不对 | 未设公网/LAN | 设 `PUBLIC_BASE_URL=http://<LAN_IP>:9000` |
| sync 9100 拒绝连接 | sync-worker 未启动 | `sudo systemctl start cypher-sync-worker` |
| `play` 409 | 缺 cache | sync 完成或手拷 `original.wav` |
| 九键无反应 | 未 play / 无 input 权限 | 先 play；`usermod -aG input cat` 重登 |
| `resume` 没有曲目 | 上次 play 失败 | 先成功 play 再 resume |

声卡自检：

```bash
bash ~/cypher/deploy/test-sound.sh
```

---

## 9. 完成度与待办

| 模块 | 状态 |
|------|------|
| 现场播放 / crossfade / 九键 1–6 | ✅ 可本机验收 |
| HarBeat App API（9000 + pair + WS） | ✅ 已实现，待 App 真机联调 |
| sync-worker | ✅ 代码有，需启服务 + Jetson token |
| SessionEvent → Jetson | ✅ MVP，待 Jetson 查库验证 |
| 键 7–9（stem） | ⚠️ 需 cache 齐 5 个 wav |
| 云网关 `/edge/rk-001` | ❌ 可选，未做 |
| HTTP Range 大文件断点 | ❌ 可选增强 |

---

## 10. 相关文档索引

| 文件 | 说明 |
|------|------|
| `README.md` | 安装、运行总览 |
| `RK3588_API_SPEC.md` | App 提供的接口规范 v1.0 |
| `mock_rk3588_server.py` | App 自测 mock，非真机实现 |
| `TASK-STATUS.md` | 开发任务进度（可能略旧） |
| `deploy/README.md` | systemd 说明 |
| 桌面 `cypher-feature-flows.md` | 三机架构 |
| 桌面 `team-rk3588-edge.md` | RK 任务规范 |
| 桌面 `jetson-handoff-for-rk3588.md` | Jetson 交接 |

---

## 11. 联系人（请填写）

| 角色 | 负责人 | 备注 |
|------|--------|------|
| RK3588 | | 本仓库、`~/cypher/` |
| HarBeat App | | `RK3588_API_SPEC.md` |
| Jetson | | manifest / JWT / SessionEvent |

---

*文档随 `~/cypher/` 代码维护；LAN IP 以板子 `hostname -I` 为准。*
