# Cypher Integration — RK3588 + Flutter App

本目录包含与 Jetson 后端联调所需的完整代码。

## 目录结构

```
cypher-integration/
├── rk3588-edge/       # RK3588 现场盒（edge-agent + audio-engine + input-daemon + sync-worker）
├── flutter-app/       # Flutter 手机 App
└── README.md
```

## 三方联调清单

### 1. Jetson 后端（主仓库 `app/`）
- `/api/users/login|register|me` — App 认证别名 ✅
- `/api/playlists/{id}/manifest` — P3 AssetManifest ✅
- `/api/playlists/{id}/dj-mix-stream` — SSE MixPlan 流 ✅
- `/api/sessions/rk/{id}/events` — P7 SessionEvent 接收 ✅
- `/api/library/songs?only_ready=true` — 过滤 ready 歌曲 ✅

### 2. RK3588 现场盒（`rk3588-edge/`）
**部署步骤：**
```bash
# 1. 复制配置
cp deploy/cypher.env.example ~/cypher/cypher.env
# 编辑 JETSON_BASE_URL=http://100.87.142.21:8000, RK_ID=rk-001

# 2. 复制 edge-agent 配置
cp edge-agent/.env.example edge-agent/.env
# 编辑同上

# 3. 启动 4 个进程（或用 systemd）
cd edge-agent && python run.py          # REST :9000 + WS :9001
cd audio-engine && python main.py       # Unix socket
cd input-daemon && python main.py       # USB HID
cd sync-worker && python main.py        # HTTP :9100
```

**关键配置：**
- `JETSON_BASE_URL=http://100.87.142.21:8000`（Jetson Tailscale IP）
- `RK_ID=rk-001`（需与云网关 `RK_REGISTRY` 一致）
- `JWT_TOKEN=` — 从 App 登录后获取

### 3. Flutter App（`flutter-app/`）
**关键配置：**
- Jetson URL: `http://8.136.120.255`（生产云网关）
- RK3588 URL: `http://<RK LAN IP>:9000`（局域网直连）
- WebSocket: `ws://<RK LAN IP>:9001/ws/control`（自动切换端口）

### 网络链路
```
App ──(快链路 LAN)──▶ RK3588 :9000/:9001  ──(Tailscale)──▶ Jetson :8000
App ──(慢链路 4G)──▶ 阿里云 :80 ──(Tailscale)──▶ Jetson :8000
App ──(慢链路 4G)──▶ 阿里云 :80 ──(/edge/rk-001/)──▶ RK3588 :9000
```

### 协议对照
| 协议 | 端点 | 状态 |
|---|---|---|
| P1 SongStatus | `/api/library/songs?only_ready=true` | ✅ |
| P2 MixPlan | `/api/playlists/{id}/dj-mix-stream` (SSE) | ✅ |
| P3 AssetManifest | `/api/playlists/{id}/manifest` | ✅ |
| P4 ControlCommand | RK: `/play /pause /resume /next /seek /trigger /load_plan` | ✅ |
| P5 RKPlaybackState | RK WS :9001 每 200ms 推送 | ✅ |
| P6 KeyEvent | RK WS + `/internal/key_event` | ✅ |
| P7 SessionEvent | RK → `/api/sessions/rk/{id}/events` | ✅ |
| P8 DeviceInfo | RK WS :9001 每 5s 推送 | ✅ |
