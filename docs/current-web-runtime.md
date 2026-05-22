# HarBeat 当前 Web 项目运行说明（现状版）

> 适用版本：现 `dev` 分支的网页端项目（含 Cypher / RK3588 / 手机 App 之前的状态）
> 更新时间：2026-05-18

本文档说明**当前线上系统**的部署形态和请求处理流程。给新员工读完能立即知道：
- 用户访问 `http://8.136.120.255/` 后请求经过了哪些机器
- 每个功能的代码跑在哪台机器上
- 哪些数据存在哪里
- 排查问题时该去哪台机器看日志

> Cypher / RK3588 / 手机 App 是**新增**功能，参见 [team-collaboration-guide.md](team-collaboration-guide.md) 等文档。

---

## 1. 物理拓扑（两台服务器）

```
┌──────────────────────────────────────────────────────────────────────┐
│                          用户浏览器                                    │
│                http://8.136.120.255/  (公网 IP)                       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTP :80
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  阿里云 ECS  (8.136.120.255, 杭州, 2核4G)                             │
│  Tailscale: 100.125.245.31  · hostname: iZbp15a9gsa7lz3xezxc1lZ      │
│                                                                       │
│  ┌────────────────────┐                                               │
│  │  Nginx :80         │  公网入口                                      │
│  │  proxy_pass →      │                                               │
│  └─────────┬──────────┘                                               │
│            ▼                                                          │
│  ┌────────────────────────────────┐                                   │
│  │  cloud_gateway :8080           │  FastAPI 透传代理                  │
│  │  systemd: harbeat-gateway      │  代码: /opt/harbeat-api/           │
│  │  .env: JETSON_BASE_URL=        │                                   │
│  │   http://100.87.142.21:8000   │                                   │
│  └─────────┬──────────────────────┘                                   │
│            │ 其他服务: redis-server, tailscaled                        │
└────────────┼──────────────────────────────────────────────────────────┘
             │
             │ Tailscale 加密虚拟网 (100.x.x.x)
             │ RTT ≈ 60~150ms (走 DERP 中继时)
             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Jetson Orin NX  (Tailscale: 100.87.142.21)                          │
│  位置: NAT 后, 公网 IP 不固定 (~220.200.73.1)                          │
│  硬件: 8核 ARM + Ampere GPU + 8/16GB 共享内存                          │
│                                                                       │
│  ┌────────────────────────────────────────┐                          │
│  │  FastAPI :8000  (uvicorn)              │  ⭐ 真正的业务后端         │
│  │  systemd: harbeat.service              │                          │
│  │  代码: /home/mark/harbeat/             │                          │
│  │  venv: ~/venvs/harbeat/                │                          │
│  │  日志: /home/mark/harbeat/uvicorn.log  │                          │
│  └─────────────┬──────────────────────────┘                          │
│                │                                                      │
│  ┌─────────────┴────────────┐                                         │
│  │ PostgreSQL :5432  (apt 14.x, 本地)                                 │
│  │ Redis :6379                                                       │
│  │ ChromaDB (本地文件, ~/harbeat/data/chroma_db/)                     │
│  │ CLAP 模型 (1.8GB, ~/harbeat/data/clap_model/)                     │
│  │ 音乐文件 (NAS 192.168.5.63 → ~/harbeat/data/music-files/)         │
│  │   ├─ shared/  (原曲)                                              │
│  │   └─ stems/htdemucs/<song>/ (Demucs 4 轨)                         │
│  └──────────────────────────┘                                         │
│                                                                       │
│  GPU 任务: Demucs 分轨 / CLAP 嵌入 / BeatNet / GrooveEngine 算分      │
│  其他服务: redis-server, tailscaled                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 谁跑在哪：服务清单

### 2.1 阿里云 ECS（公网入口节点）

| 服务 | 端口 | 用途 | 文件 / 单元 |
|---|---|---|---|
| **Nginx** | :80 公网 | 接收公网 HTTP，反代到 8080 | `/etc/nginx/conf.d/default.conf`（同 [deploy/cloud_gateway/nginx_default.conf](deploy/cloud_gateway/nginx_default.conf)）|
| **cloud_gateway** | :8080 内网 | FastAPI 透传代理 | systemd `harbeat-gateway.service`，代码 `/opt/harbeat-api/`（来自 [deploy/cloud_gateway/app/main.py](deploy/cloud_gateway/app/main.py)）|
| **Tailscale** | — | 加密通道接入 tailnet | systemd `tailscaled.service` |
| **Redis** | :6379 | 备用（实际业务 Redis 在 Jetson 上）| systemd `redis-server` |

**阿里云不存任何业务数据**。它的全部职责就是"把公网流量加密转发到 Jetson"。

### 2.2 Jetson Orin NX（业务主机）

| 服务 | 端口 | 用途 | 备注 |
|---|---|---|---|
| **FastAPI** | :8000 | ⭐ 主业务后端 | systemd `harbeat.service`，uvicorn 跑 `app.main:app` |
| **PostgreSQL** | :5432 | 业务数据库 | apt 安装 14.x，**全部业务数据**在这 |
| **Redis** | :6379 | 任务锁 / 缓存 / startup_lock | 启动时用 SETNX 防多 worker 重复初始化 |
| **ChromaDB** | 嵌入式 | 语义向量索引 | 本地文件 `~/harbeat/data/chroma_db/` |
| **Tailscale** | — | 接入 tailnet | systemd `tailscaled.service` |

**已禁用的旧服务**：`harbeat-api`、`harbeat-tunnel`（autossh），不要重启它们。

---

## 3. 前端代码在哪

> 前端代码是 React + Vite，**最终在 Jetson 上由 FastAPI 通过 StaticFiles 挂载提供**。阿里云不存任何前端文件。

| 阶段 | 位置 |
|---|---|
| 源码 | Windows 本机 `d:\work\harbeat-client\web\src\` |
| 本地构建产物 | `web/dist/`（`npx vite build` 输出）|
| 打包 | `dist.tgz`（[deploy.ps1](deploy.ps1) / [deploy.sh](deploy.sh) 自动）|
| Jetson 上的位置 | `/home/mark/harbeat/web/dist/` |
| 提供方式 | FastAPI 启动时如果 `web/dist/` 存在，挂载到 SPA 路由（[app/main.py](app/main.py)）|

**⚠️ 关键陷阱**（来自 [memories/repo/harbeat-deploy.md](memories/repo/harbeat-deploy.md)）：

> SPA fallback 路由在 FastAPI **启动时**才注册，且只在 `/home/mark/harbeat/web/dist/` 存在时注册。如果先重启服务再部署 dist，`/` 会返回 FastAPI 404 直到下次重启。**永远先部署 dist，再重启服务。**

---

## 4. 数据流：一次请求的完整路径

### 4.1 用户访问首页 `GET /`

```
浏览器 → 8.136.120.255:80 (公网)
       ↓ Nginx proxy_pass
       127.0.0.1:8080 (阿里云本机)
       ↓ cloud_gateway 通配路由 /{path:path}
       ↓ httpx 请求到 JETSON_BASE_URL/
       100.87.142.21:8000 (Tailscale)
       ↓ FastAPI 路由匹配，命中 SPA fallback
       返回 /home/mark/harbeat/web/dist/index.html
       ← (一路返回原 chain)
```

### 4.2 用户搜索曲库 `GET /api/library/search?q=hiphop`

```
浏览器 → Nginx :80 → cloud_gateway :8080 → Jetson :8000
       ↓ app/modules/router.py 路由到 library_router
       ↓ app/modules/library/router.py
       ↓ 查 PostgreSQL (LibrarySong 表)
       ↓ 可能查 ChromaDB 做语义搜索
       ← JSON 响应
```

### 4.3 用户播放歌曲 `GET /api/stream/{song_id}/audio`

```
浏览器 (HTML <audio>) → Nginx → cloud_gateway → Jetson FastAPI
       ↓ app/modules/stream/router.py
       ↓ 读 /home/mark/harbeat/data/music-files/shared/<file>
       ↓ 返回 206 Partial Content (Range 支持)
       ← 音频流式返回浏览器
```

⚠️ 注意：**音频文件经阿里云 2 核 4G 转发**，这是个瓶颈。直播多用户播放会受限于阿里云的 nginx + httpx 转发能力。

### 4.4 上传新歌 `POST /api/music/upload`

```
浏览器 → Nginx (client_max_body_size 500m) → cloud_gateway → Jetson
       ↓ app/modules/music/router.py
       ↓ 保存到 NAS: /mnt/nas/harbeat/music-files/shared/
       ↓ 后台任务 (background_tasks):
       │   1. librosa BPM / key 分析
       │   2. BeatNet beat 检测
       │   3. Demucs 分轨 (GPU, ~3min/首)
       │   4. CLAP 语义嵌入 (GPU)
       │   5. 写 ChromaDB + PostgreSQL
       ← 立即返回，分析在后台
```

### 4.5 生成 DJ 混音 `POST /api/playlists/{id}/dj-mix`

```
浏览器 → ... → Jetson
       ↓ app/modules/playlists/router.py
       ↓ app/modules/playlists/service.py: generate_dj_mix_plan()
       ↓ app/modules/playlists/groove_adapter.py: run_groove_engine_plan()
       ↓ 加载 GrooveEngine/ (sys.path)
       ↓ 11 因子算分 + 全排列搜索 ⚠️ 5 首需 280s
       ↓ 返回 DjMixPlanResult
       ← (用户长时间等待)
```

⚠️ 这是当前已知瓶颈。Cypher 场景下被重构成"流式多 plan"，详见 [team-jetson-backend.md](team-jetson-backend.md)。

---

## 5. FastAPI 模块对照表（功能 → 代码位置）

| Web 功能 | 路由前缀 | 代码 | 数据存储 | 重计算 |
|---|---|---|---|---|
| 健康检查 | `/health` | `app/modules/health/` | — | — |
| 用户注册/登录 | `/api/auth/*` | `app/modules/auth/` | PostgreSQL `users` | — |
| 用户资料 | `/api/users/*`, `/api/profiles/*` | `app/modules/users/`, `profiles/` | PostgreSQL | — |
| 曲库浏览/搜索 | `/api/library/*` | `app/modules/library/` | PostgreSQL `library_songs` + ChromaDB | CLAP 嵌入(上传时) |
| 音乐上传/元数据 | `/api/music/*` | `app/modules/music/` | PostgreSQL + NAS 文件 | Demucs + BeatNet |
| 播放/流媒体 | `/api/stream/*` | `app/modules/stream/` | NAS 文件 | — |
| 歌单管理 | `/api/playlists/*` | `app/modules/playlists/` | PostgreSQL `playlists` + GrooveEngine | DJ Mix Plan ⚠️ |
| 推荐 | `/api/recommendations/*` | `app/modules/recommendations/` | ChromaDB + PostgreSQL | CLAP 相似度 |
| 会话/课程 | `/api/sessions/*` | `app/modules/sessions/` | PostgreSQL | — |
| 现场混音预览 | `/api/dev/*` | `app/modules/dev_mix/` | NAS | 在线混音 (CPU) |
| 方批（仿批工具）| `/api/fangpi/*` | `app/modules/fangpi/` | PostgreSQL | — |
| 语音命令 | `/api/voice/*` | `app/modules/voice/` | — | keyword_matcher |

---

## 6. 数据存储分布

### 6.1 PostgreSQL（Jetson 本地）

权威数据，**只在 Jetson**：
- `users` / `profiles` —— 用户账号
- `library_songs` —— 曲库主表（BPM / key / 风格 / 标签 / 文件路径）
- `songs` / `playlists` / `playlist_songs` —— 歌单
- `sessions` —— 上课/会话记录
- `song_tags` —— 标签

> 历史 RDS（`pgm-wz99am1...rds.aliyuncs.com`）已**废弃**，2026-04 切到 Jetson 本地。

### 6.2 ChromaDB（Jetson 本地文件）

`~/harbeat/data/chroma_db/`：CLAP 语义嵌入向量索引。
⚠️ 注意：`onnxruntime` 在 ARM64 上 SIGABRT，已用 `SentenceTransformerEmbeddingFunction` 替代。

### 6.3 音乐文件（NAS via CIFS）

| 路径 | 内容 |
|---|---|
| `~/harbeat/data/music-files/shared/` | 原曲（用户上传）|
| `~/harbeat/data/music-files/stems/htdemucs/<song>/` | Demucs 输出：vocals/drums/bass/other.wav |
| `~/harbeat/data/music-files/shared/mixes/` | DJ Mix 临时产物（1 小时清理一次）|
| `~/harbeat/data/music-files/shared/processed/` | 历史缓存，启动时清空 |

NAS 挂载：`/mnt/nas/harbeat` → 192.168.5.63（SMB/CIFS），通过符号链接进 `~/harbeat/data/music-files`。

### 6.4 模型权重（Jetson 本地 SSD）

- Demucs（htdemucs）
- BeatNet
- CLAP（`~/harbeat/data/clap_model/`, 1.8GB）
- SentenceTransformer

---

## 7. 部署与运维

### 7.1 部署 Web 前端

来自 [memories/repo/harbeat-deploy.md](memories/repo/harbeat-deploy.md)：

```powershell
# Windows 本机
cd web; npx vite build
cd dist; tar -czf ..\..\dist.tgz .; cd ..\..

scp -i C:\Users\xueyawen\.ssh\id_ed25519 -o StrictHostKeyChecking=no `
    -o ProxyJump=root@8.136.120.255 dist.tgz mark@100.87.142.21:/tmp/dist.tgz

ssh.exe -i C:\Users\xueyawen\.ssh\id_ed25519 -o StrictHostKeyChecking=no `
    -o ProxyJump=root@8.136.120.255 mark@100.87.142.21 `
    "rm -rf /home/mark/harbeat/web/dist && mkdir -p /home/mark/harbeat/web/dist && `
     tar -xzf /tmp/dist.tgz -C /home/mark/harbeat/web/dist && `
     sudo -n /bin/systemctl restart harbeat"
```

### 7.2 部署后端代码

```bash
# 在 Jetson 上
cd ~/harbeat
git fetch && git checkout <branch>
sudo -n /bin/systemctl restart harbeat
```

### 7.3 看日志

| 在哪 | 看什么 | 命令 |
|---|---|---|
| 阿里云 | nginx | `journalctl -u nginx -f` |
| 阿里云 | gateway | `journalctl -u harbeat-gateway -f` |
| Jetson | 业务后端 | `tail -f /home/mark/harbeat/uvicorn.log` |
| Jetson | 业务后端（systemd）| `sudo -n /bin/journalctl -u harbeat -f` |
| Jetson | PostgreSQL | `journalctl -u postgresql -f` |

### 7.4 常用排查命令

```bash
# 阿里云上测网关
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/jetson/health  # 经 Tailscale 测 Jetson

# 本机 Windows 测公网
curl http://8.136.120.255/health

# Jetson 上测本机
curl http://127.0.0.1:8000/health
```

### 7.5 sudoers 白名单（Jetson）

[memories/repo/harbeat-deploy.md](memories/repo/harbeat-deploy.md) 已记录，`mark` 用户 NOPASSWD 仅限：
- `/bin/systemctl restart harbeat`
- `/bin/systemctl status harbeat`
- `/bin/systemctl stop harbeat`
- `/bin/systemctl start harbeat`

注意：必须用绝对路径 `/bin/systemctl`，**不能用 bare `systemctl`**；`is-active` 不在白名单。

---

## 8. 已知问题与陷阱

| 陷阱 | 来源 |
|---|---|
| SPA fallback 路由启动时才注册，dist 缺失会让 `/` 永久 404 | `app/main.py` |
| Windows OpenSSH ControlMaster 损坏，多路复用不可用 | 部署脚本 |
| 经阿里云 SSH 到 Jetson 偶尔会跳到错的机器（Tailscale ProxyJump 怪事）| harbeat-deploy.md |
| `onnxruntime` 在 ARM64 上 SIGABRT | jetson-setup.md |
| `torchaudio` PyPI 版会破坏 NVIDIA torch | jetson-setup.md |
| HuggingFace 国内超时 → 用 `HF_ENDPOINT=https://hf-mirror.com` | jetson-setup.md |
| `demucs` 必须 `-d cuda`，否则慢 10 倍 | background_tasks.py |
| ChromaDB EF 与旧 collection 冲突 → 启动时 catch ValueError 重建 | jetson-setup.md |
| GrooveEngine 5 首歌混音规划 ≈ 280s | jetson-setup.md |
| 阿里云 ECS 2 核 4G 是单点 + 性能瓶颈 | 拓扑 |

---

## 9. 一张图记住

```
                    ┌─────────────┐
                    │   浏览器     │
                    └──────┬──────┘
                           │ 公网 HTTP
                    ┌──────▼──────────────────┐
                    │  阿里云 ECS              │
                    │  - Nginx :80            │  纯转发，不存数据
                    │  - cloud_gateway :8080  │  FastAPI 透传
                    │  - Tailscale            │
                    └──────┬──────────────────┘
                           │ Tailscale 内网
                    ┌──────▼──────────────────────────────┐
                    │  Jetson Orin NX                     │
                    │  ┌──────────────────────────────┐  │
                    │  │ FastAPI :8000 (harbeat)      │  │  所有业务逻辑
                    │  │ ├─ 14 个 modules             │  │
                    │  │ └─ 提供 web/dist 静态文件     │  │
                    │  ├──────────────────────────────┤  │
                    │  │ PostgreSQL :5432             │  │  所有业务数据
                    │  │ Redis :6379                  │  │
                    │  │ ChromaDB (本地文件)          │  │
                    │  │ NAS 挂载 (音频 + stems)      │  │
                    │  │ GPU (Demucs / CLAP / etc.)   │  │  AI 推理
                    │  └──────────────────────────────┘  │
                    └─────────────────────────────────────┘
```

**记住三句话**：
1. **阿里云是邮差**——只转发，不存数据，不做计算。
2. **Jetson 是大脑**——所有业务、数据、AI、文件都在它身上。
3. **NAS 是仓库**——只存音频原文件和 stems，挂载在 Jetson 上。

---

## 10. 后续演进

新增的 Cypher 现场混音系统会在这个架构基础上加入：
- **RK3588**：现场实时音频执行器（新机器）
- **手机 App**：MC 决策面板（Flutter）
- **阿里云 Gateway 改造**：支持双后端 `/jetson/*` + `/edge/<device_id>/*`

详见 [team-collaboration-guide.md](team-collaboration-guide.md)。
